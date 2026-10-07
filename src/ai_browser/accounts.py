"""The user's Claude logins for AI Browser (AI accounts): Default, their own, and any they add.

An account is an id, a name and a folder: a Claude Code config folder (CLAUDE_CONFIG_DIR), which holds its own login,
settings, MCP servers and conversations. Default is the user's own login: $CLAUDE_CONFIG_DIR when the environment
sets it, else ~/.claude. An added account's folder is <home>/accounts/<id>/ (mode 0700), or one the user already has.
<home>/accounts.json (mode 0600) keeps {"accounts": [{"id", "name", "folder"}], "default": "<id>", "brain": "<id>"};
a missing or bad file means Default only, and reading never raises. Only the id, made here, reaches a command line or
a path; the name is the user's label. AI Browser never sees a password or a token: the user signs in in a terminal
and their browser.

<home>/usage.json (mode 0600) keeps each account's latest reading of its limits, as Claude Code reports them with each
request (limits.windows_from_event), so the Usage card shows them after a restart, with their time:
{"accounts": {"<id>": {"five_hour": {"used": <percent>, "resets_at": <seconds> | null, "at": <seconds>}, …}}}. Nothing
but account ids, window names, numbers and times; an unreadable file reads as no reading."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import secrets
import time
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from . import platforms
from .claudecli import claude_argv, spawn_options, track
from .limits import KNOWN_WINDOWS, seconds
from .syncdir import write_atomic

DEFAULT = "default"
DEFAULT_NAME = "Default"
FILE = "accounts.json"
USAGE_FILE = "usage.json"
NAME_LIMIT = 40
FOLDER_LIMIT = 1000
API_VARIABLES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")  # never passed on: Claude Code uses a login
BROWSER_FILES = ("Local State", "Preferences", "Cookies")  # at a folder's top: Chromium's or Electron's data
GONE = "That account isn't in Settings → Accounts any more"
NOT_SIGNED_IN = "{name} isn't signed in: sign in from Settings → Accounts"
STATUS_TTL = 5.0  # seconds a `claude auth status` answer is kept
STATUS_TIMEOUT = 15.0  # seconds `claude auth status` gets
UNKNOWN = {"signed_in": None, "plan": None}  # Claude Code couldn't tell (not installed, or too old for auth status)
_PLAN = re.compile(r"^[A-Za-z0-9_-]{1,30}$")
_ID = re.compile(r"^acct-[0-9a-f]{6}$")
_HIDDEN = ("Cc", "Cf", "Cs")  # control, format (bidi controls among them) and surrogate characters


@dataclass(frozen=True)
class Account:
    id: str
    name: str
    folder: str
    kind: str = "claude"  # the next design adds other AIs' command-line tools to the same list


def clean_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment Claude Code starts with: a copy of `base` (os.environ) without ANTHROPIC_API_KEY and
    ANTHROPIC_AUTH_TOKEN, so it always uses a login, never an API key."""
    return {key: value for key, value in (os.environ if base is None else base).items() if key not in API_VARIABLES}


def default_folder(env: Mapping[str, str] | None = None) -> Path:
    """Default's folder: $CLAUDE_CONFIG_DIR when the environment sets it, else ~/.claude."""
    value = (os.environ if env is None else env).get("CLAUDE_CONFIG_DIR")
    return Path(value) if value else Path.home() / ".claude"


def clean_name(text) -> str:
    """The user's label, as kept and shown: whitespace becomes spaces, control, format and surrogate characters go,
    spaces are squeezed, at most NAME_LIMIT characters. "" when nothing visible is left."""
    if not isinstance(text, str):
        return ""
    kept = "".join(" " if char.isspace() else char for char in text
                   if char.isspace() or unicodedata.category(char) not in _HIDDEN)
    name = " ".join(kept.split())[:NAME_LIMIT].strip()
    return name if any(not unicodedata.category(char).startswith(("C", "Z")) for char in name) else ""


def _logged_in(out: bytes) -> dict:
    """`claude auth status`'s JSON, of which only loggedIn and subscriptionType are read: the email, the organisation
    and their ids are never looked at, kept or logged."""
    text = out.decode("utf-8", errors="replace").strip()
    for candidate in (text, *reversed(text.splitlines())):
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("loggedIn"), bool):
            plan = data.get("subscriptionType")
            shown = plan.replace("_", " ").title() if data["loggedIn"] and isinstance(plan, str) \
                and _PLAN.match(plan) else None
            return {"signed_in": data["loggedIn"], "plan": shown}
    return dict(UNKNOWN)


class Accounts:
    """The account list. Every read goes to the file, so it is always the truth; a write keeps the keys it doesn't
    know (a newer build's)."""

    def __init__(self, home, claude: str | Sequence[str] | None = None):
        self.home = Path(home)
        self.path = self.home / FILE
        self.claude = claude  # how `claude auth status` and the sign-in command find Claude Code (claudecli)
        self._status: dict[str, tuple[float, dict]] = {}  # account id -> (monotonic time, {"signed_in", "plan"})
        self._locks: dict[str, asyncio.Lock] = {}  # one `claude auth status` per account at a time
        self._limits: dict[str, float] = {}  # account id -> when its usage limit resets (this app run only)
        self.usage_path = self.home / USAGE_FILE
        self._usage = self._read_usage()  # account id -> {window: {"used", "resets_at", "at"}}, the latest readings
        self.on_change: Callable[[], None] | None = None  # set by the app: a status changed, so pages hear it

    # ---- reading -----------------------------------------------------------------------------------------------

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _added(data: dict) -> list[Account]:
        """The accounts the user added, as far as the file makes sense: a row with a bad id, no visible name or a
        folder that isn't a full path is left out."""
        found, seen = [], set()
        rows = data.get("accounts")
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            account_id, name, folder = row.get("id"), clean_name(row.get("name")), row.get("folder")
            if not (isinstance(account_id, str) and _ID.match(account_id)) or account_id in seen or not name \
                    or not isinstance(folder, str) or not folder or not Path(folder).is_absolute():
                continue
            seen.add(account_id)
            found.append(Account(account_id, name, folder))
        return found

    def list(self) -> list[Account]:
        """Default first, then the accounts the user added, in the order they were added."""
        return [Account(DEFAULT, DEFAULT_NAME, str(default_folder())), *self._added(self._read())]

    def get(self, account_id) -> Account | None:
        return next((account for account in self.list() if account.id == account_id), None)

    def _chosen(self, key: str) -> str:
        data = self._read()
        chosen = data.get(key)
        return chosen if any(account.id == chosen for account in self._added(data)) else DEFAULT

    def default_id(self) -> str:
        """The account new agents use (Settings → Accounts → Default account for new agents)."""
        return self._chosen("default")

    def brain_id(self) -> str:
        """The account the Brain and its skill writer use (Settings → Accounts → The Brain's account)."""
        return self._chosen("brain")

    # ---- changing ------------------------------------------------------------------------------------------------

    def _write(self, data: dict) -> None:
        write_atomic(self.path, (json.dumps(data, indent=1, ensure_ascii=False) + "\n").encode("utf-8"), 0o600)

    @staticmethod
    def _rows(accounts: list[Account]) -> list[dict]:
        return [{"id": account.id, "name": account.name, "folder": account.folder} for account in accounts]

    def _name(self, name) -> str:
        cleaned = clean_name(name)
        if not cleaned:
            raise ValueError("Give the account a name")
        if any(account.name.casefold() == cleaned.casefold() for account in self.list()):
            raise ValueError(f"There is already an account named {cleaned}")
        return cleaned

    def _new_id(self) -> str:
        taken = {account.id for account in self.list()}
        while True:
            account_id = f"acct-{secrets.token_hex(3)}"
            if account_id not in taken and not (self.home / "accounts" / account_id).exists():
                return account_id

    def _keep(self, account: Account) -> Account:
        data = self._read()
        data["accounts"] = self._rows([*self._added(data), account])
        self._write(data)
        return account

    def add(self, name) -> Account:
        """A new account with a folder of AI Browser's own, <home>/accounts/<id>/ (mode 0700). The user signs it in."""
        cleaned = self._name(name)
        account_id = self._new_id()
        folder = self.home / "accounts" / account_id
        folder.mkdir(parents=True, mode=0o700)
        for made in (folder.parent, folder):
            os.chmod(made, 0o700)  # mkdir's mode is cut by the umask
        return self._keep(Account(account_id, cleaned, str(folder)))

    def add_existing(self, name, folder) -> Account:
        """An account on a Claude Code folder the user already has, used where it is."""
        cleaned = self._name(name)
        return self._keep(Account(self._new_id(), cleaned, str(self._existing(folder))))

    def _existing(self, folder) -> Path:
        """The folder a page typed, checked: a full path to a folder that exists, isn't a browser's data folder
        (Chromium's or Electron's, such as the Claude desktop app's --user-data-dir), and no account uses yet."""
        if not isinstance(folder, str) or not folder.strip() or len(folder) > FOLDER_LIMIT \
                or any(unicodedata.category(char) in _HIDDEN for char in folder):
            raise ValueError("Give the folder's full path")
        path = Path(folder.strip()).expanduser()
        if not path.is_absolute():
            raise ValueError("Give the folder's full path")
        if not path.is_dir():
            raise ValueError("That folder doesn't exist")
        if any((path / name).exists() for name in BROWSER_FILES):
            raise ValueError("That folder holds a browser's data (Local State, Preferences or Cookies), not Claude "
                             "Code's: pick the folder Claude Code uses")
        if any(Path(account.folder).expanduser().resolve() == path.resolve() for account in self.list()):
            raise ValueError("Another account already uses that folder")
        return path

    def remove(self, account_id) -> None:
        """Forget an account: its folder, conversations and sign-in stay where they are. Default can't be removed.
        An account that was the default or the Brain's gives that back to Default."""
        if account_id == DEFAULT:
            raise ValueError("Default can't be removed")
        data = self._read()
        added = self._added(data)
        if not any(account.id == account_id for account in added):
            raise ValueError(GONE)
        data["accounts"] = self._rows([account for account in added if account.id != account_id])
        for key in ("default", "brain"):
            if data.get(key) == account_id:
                data[key] = DEFAULT
        self._write(data)
        if self._usage.pop(account_id, None) is not None:  # its readings go with it
            self._write_usage()

    def _choose(self, key: str, account_id) -> None:
        if self.get(account_id) is None:
            raise ValueError(GONE)
        data = self._read()
        data[key] = account_id
        self._write(data)

    def set_default(self, account_id) -> None:
        self._choose("default", account_id)

    def set_brain(self, account_id) -> None:
        self._choose("brain", account_id)

    # ---- running Claude Code on an account -----------------------------------------------------------------------

    def env_for(self, account_id) -> dict[str, str]:
        """The environment Claude Code runs with on this account, without the two API variables. Default leaves the
        environment as it is (its CLAUDE_CONFIG_DIR, if any); any other account sets CLAUDE_CONFIG_DIR to its folder.
        KeyError for an account that isn't listed: nothing ever falls back to another account by itself."""
        account = self.get(account_id)
        if account is None:
            raise KeyError(account_id)
        env = clean_env()
        if account.id != DEFAULT:
            env["CLAUDE_CONFIG_DIR"] = account.folder
        return env

    def claude_home(self, account_id) -> Path:
        """Where this account's .claude.json is (its MCP servers): the home folder for Default without
        CLAUDE_CONFIG_DIR, else the account's folder."""
        account = self.get(account_id)
        if account is None:
            raise KeyError(account_id)
        if account.id == DEFAULT and not os.environ.get("CLAUDE_CONFIG_DIR"):
            return Path.home()
        return Path(account.folder)

    def signin_folder(self, account_id) -> str | None:
        """The folder a sign-in command names: the account's own, or for Default the environment's CLAUDE_CONFIG_DIR
        (None: the terminal's own login, ~/.claude)."""
        account = self.get(account_id)
        if account is None:
            return None
        if account.id == DEFAULT:
            return os.environ.get("CLAUDE_CONFIG_DIR") or None
        return account.folder

    # ---- signed in, and the limits -------------------------------------------------------------------------------

    async def status(self, account_id, fresh: bool = False) -> dict:
        """{"signed_in": True | False | None, "plan": "Pro" | None}, from `claude auth status` on the account's
        folder (no model turn), kept STATUS_TTL seconds. None: Claude Code couldn't tell. It never raises. An answer
        that differs from the one kept (or the first one) calls on_change: whoever asked (a page, an agent's start, a
        move), every page then shows it."""
        if self.get(account_id) is None:
            return dict(UNKNOWN)
        async with self._locks.setdefault(account_id, asyncio.Lock()):
            kept = self._status.get(account_id)
            if kept is not None and not fresh and time.monotonic() - kept[0] < STATUS_TTL:
                return dict(kept[1])
            found = await self._auth_status(account_id)
            self._status[account_id] = (time.monotonic(), found)
            if (kept is None or kept[1] != found) and self.on_change is not None:
                with contextlib.suppress(Exception):
                    self.on_change()
            return dict(found)

    async def _auth_status(self, account_id: str) -> dict:
        try:
            process = await asyncio.create_subprocess_exec(
                *claude_argv(self.claude), "auth", "status", env=self.env_for(account_id),
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                **spawn_options())
        except (OSError, KeyError):  # ClaudeNotUsable is an OSError
            return dict(UNKNOWN)
        track(process)
        try:
            out, _ = await asyncio.wait_for(process.communicate(), STATUS_TIMEOUT)
        except (TimeoutError, asyncio.CancelledError) as stopped:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            if isinstance(stopped, asyncio.CancelledError):
                raise
            return dict(UNKNOWN)
        return _logged_in(out)

    async def refresh(self) -> None:
        """Every account's status, each kept STATUS_TTL seconds: when a page of ours opens."""
        await asyncio.gather(*(self.status(account.id) for account in self.list()))

    def limit(self, account_id) -> float | None:
        """When this account's usage limit resets (seconds since 1970), if it hit one this app run, Claude Code gave
        the time, and that time hasn't come yet."""
        resets = self._limits.get(account_id)
        if resets is not None and resets <= time.time():
            del self._limits[account_id]
            return None
        return resets

    def set_limit(self, account_id, resets_at) -> None:
        """An agent or the Brain hit this account's usage limit: its reset time is kept for this app run, for the
        pickers. Without a time nothing is kept, and a known time stays."""
        if isinstance(resets_at, (int, float)) and not isinstance(resets_at, bool) and resets_at > time.time():
            self._limits[account_id] = float(resets_at)

    # ---- how much of each limit is used (the Usage card) -----------------------------------------------------------

    @staticmethod
    def _reading(value, at) -> dict | None:
        """A reading as kept: a percentage from 0 to 100, its reset time or None, and when it was read; None for
        anything else."""
        if not isinstance(value, dict):
            return None
        used = value.get("used")  # compared, never converted first: NaN, infinity and huge integers fail
        if isinstance(used, bool) or not isinstance(used, (int, float)) or not 0 <= used <= 100 or seconds(at) is None:
            return None
        return {"used": float(used), "resets_at": seconds(value.get("resets_at")), "at": seconds(at)}

    def _read_usage(self) -> dict[str, dict]:
        """usage.json's sane readings of the listed accounts; {} for a file that can't be read, however odd (too deep
        for the parser, a number too big for a float): the app always starts."""
        try:
            return self._usage_from(json.loads(self.usage_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, OverflowError, RecursionError):
            return {}

    def _usage_from(self, data) -> dict[str, dict]:
        found, listed = {}, {account.id for account in self.list()}
        accounts = data.get("accounts") if isinstance(data, dict) else None
        for account_id, windows in accounts.items() if isinstance(accounts, dict) else ():
            if account_id not in listed or not isinstance(windows, dict):  # an account of this home only
                continue
            kept = {}
            for name in KNOWN_WINDOWS:
                stored = windows.get(name)
                reading = self._reading(stored, stored.get("at")) if isinstance(stored, dict) else None
                if reading is not None:
                    kept[name] = reading
            if kept:
                found[account_id] = kept
        return found

    def _write_usage(self) -> None:
        """usage.json, with the accounts that are still listed. A write that fails is skipped: the readings stay in
        memory, and an agent's turn never stops for it."""
        listed = {account.id for account in self.list()}
        self._usage = {account_id: windows for account_id, windows in self._usage.items() if account_id in listed}
        data = (json.dumps({"accounts": self._usage}, indent=1) + "\n").encode("utf-8")
        with contextlib.suppress(OSError):
            write_atomic(self.usage_path, data, 0o600)

    def set_windows(self, account_id, windows) -> None:
        """This account's latest readings, as limits.windows_from_event read them ({"five_hour": {"used",
        "resets_at"}, …}): each known window is kept with the time it was read, the others stay as they were. Anything
        that isn't a reading, or an account that isn't listed, is ignored."""
        if not isinstance(windows, dict) or self.get(account_id) is None:
            return
        now = time.time()
        fresh = {}
        for name in KNOWN_WINDOWS:
            reading = self._reading(windows.get(name), now)
            if reading is not None:
                fresh[name] = reading
        if fresh:
            self._usage[account_id] = {**self._usage.get(account_id, {}), **fresh}
            self._write_usage()

    def windows(self, account_id) -> dict[str, dict]:
        """{window: {"used", "resets_at", "at"}}: this account's latest readings, kept across restarts. A reading
        whose reset time has passed stays, with its time: the Usage card no longer shows its number."""
        return {name: dict(reading) for name, reading in self._usage.get(account_id, {}).items()}

    # ---- what AI Browser's own pages show ------------------------------------------------------------------------

    def command(self, account_id) -> str:
        """Copy the command: what signs this account in from the user's own terminal ("" when Claude Code can't be
        found the way AI Browser finds it)."""
        if self.get(account_id) is None:
            return ""
        try:
            claude = claude_argv(self.claude)
        except OSError:
            return ""
        return platforms.signin_command(claude, self.signin_folder(account_id))

    def rows(self) -> list[dict]:
        """The accounts as Settings, the pickers and the asks show them (the snapshot's `accounts`): each one's last
        status, never an email or an organisation. It never runs Claude Code."""
        default, brain = self.default_id(), self.brain_id()
        rows = []
        for account in self.list():
            kept = self._status.get(account.id)
            status = kept[1] if kept is not None else UNKNOWN
            rows.append({"id": account.id, "name": account.name, "signed_in": status["signed_in"],
                         "plan": status["plan"], "checked": kept is not None, "limit_until": self.limit(account.id),
                         "windows": self.windows(account.id),
                         "default": account.id == default, "brain": account.id == brain,
                         "command": self.command(account.id)})
        return rows
