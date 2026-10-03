"""Which browsers are installed, whether each one runs with its remote-debugging switch on, its profiles (name and
colour) and which profile holds a copy of the Brain's watcher: found by reading files only.

Pure, like platforms.py: no module state, no cache, no threads, no writes. Every function takes its paths, or
`system` and `env`, read at call time, so the Mac's tests can ask for any OS. The OS facts (the app folders, the data
folder, the LaunchServices file, the registry) come from platforms.py; this module never spells them.

Every public function returns a safe value for a missing, broken, huge or hostile file, and never raises. The only
network use is a TCP connect to 127.0.0.1 that sends no bytes: no DevTools session is opened, so the browser never
asks "Allow remote debugging?" and shows no automation bar because of it. Account fields (emails, account names) are
never read into a result, and nothing here starts a program."""

from __future__ import annotations

import json
import ntpath
import os
import plistlib
import re
import socket
import sys
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from . import platforms

MAX_FILE = 16 * 1024 * 1024  # bytes: a bigger Local State or Preferences file is not read at all


def _system(system: str | None) -> str:
    return system or sys.platform


def by_id(browser_id: str) -> platforms.BrowserFacts | None:
    """The table's row for an id ("brave", "chrome-beta", …), or None."""
    return next((facts for facts in platforms.KNOWN_BROWSERS if facts.id == browser_id), None)


def data_dir(facts: platforms.BrowserFacts, system: str | None = None, env: Mapping | None = None) -> Path | None:
    """The browser's folder of profiles on `system`, installed or not (None when it keeps none there)."""
    return platforms.browser_data_dir(facts, system, env)


def all_data_dirs(system: str | None = None, env: Mapping | None = None) -> list[Path]:
    """Every known browser's folder of profiles on `system`, installed or not, in the table's order."""
    return [folder for facts in platforms.KNOWN_BROWSERS if (folder := data_dir(facts, system, env)) is not None]


def _path_key(path, system: str) -> str | None:
    """A path as compared here: resolved, and on Windows without regard to case; None for a path that can't be (it
    holds a NUL)."""
    try:
        resolved = os.path.realpath(path)
    except (OSError, ValueError):
        return None
    return ntpath.normcase(resolved) if system == "win32" else resolved


def for_data_dir(folder, system: str | None = None, env: Mapping | None = None) -> platforms.BrowserFacts | None:
    """Which known browser owns this data folder, or None."""
    system = _system(system)
    wanted = _path_key(folder, system)
    if wanted is None:
        return None
    for facts in platforms.KNOWN_BROWSERS:
        own = data_dir(facts, system, env)
        if own is not None and _path_key(own, system) == wanted:
            return facts
    return None


def _read(path) -> bytes | None:
    """A file's bytes, or None. Only a regular file is opened, so a pipe or a device can't hang it; the open lets the
    browser replace the file meanwhile (platforms.open_shared); a file over MAX_FILE is never read."""
    try:
        if not os.path.isfile(path):
            return None
        with platforms.open_shared(path) as handle:
            if os.fstat(handle.fileno()).st_size > MAX_FILE:
                return None
            data = handle.read(MAX_FILE + 1)
    except (OSError, ValueError):
        return None
    return data if len(data) <= MAX_FILE else None  # it grew past the limit while we looked


@dataclass(frozen=True)
class Installed:
    """A known browser whose app is on this computer: its program, its .app on macOS (None elsewhere), its version
    from the app's Info.plist (None on Windows) and its data folder."""

    facts: platforms.BrowserFacts
    binary: Path
    bundle: Path | None
    version: str | None
    data_dir: Path

    @property
    def id(self) -> str:
        return self.facts.id

    @property
    def name(self) -> str:
        return self.facts.name

    @property
    def agents(self) -> bool:
        return self.facts.agents

    @property
    def window(self) -> bool:
        return self.facts.window

    @property
    def inspect_address(self) -> str:
        return f"{self.facts.inspect}://inspect/#remote-debugging"


def _plist(path):
    """A plist file (XML or binary) as Python data, or None."""
    data = _read(path)
    if data is None:
        return None
    try:
        return plistlib.loads(data)
    except Exception:  # a cut XML plist raises ExpatError, a broken <date> AttributeError: not only ValueError
        return None


def _plain_file_name(name) -> bool:
    return isinstance(name, str) and name not in ("", ".", "..") and "/" not in name and "\0" not in name


def installed(system: str | None = None, env: Mapping | None = None, folders=None, commands=None) -> list[Installed]:
    """The known browsers whose app is on this computer, in the table's order. macOS: the .app in the app folders,
    with the row's bundle id and its program. Windows: the row's program under the app folders, or a program the
    registry names (`commands`), that is a file. Elsewhere: []."""
    system = _system(system)
    env = os.environ if env is None else env
    if system not in ("darwin", "win32"):
        return []
    if folders is None:
        folders = platforms.app_folders(system, env)
    if system == "darwin":
        return _mac_installed(folders, env)
    if commands is None:
        commands = platforms.windows_browser_commands()
    return _windows_installed(folders, commands, env)


def _mac_installed(folders, env: Mapping) -> list[Installed]:
    found = []
    for facts in platforms.KNOWN_BROWSERS:
        for folder in folders:
            bundle = Path(folder) / facts.mac_app
            info = _plist(bundle / "Contents" / "Info.plist")
            if not isinstance(info, dict):
                continue
            ident, program = info.get("CFBundleIdentifier"), info.get("CFBundleExecutable")
            if not isinstance(ident, str) or ident.lower() != facts.mac_bundle_id.lower():
                continue
            if not _plain_file_name(program) or not os.path.isfile(bundle / "Contents" / "MacOS" / program):
                continue
            version = info.get("CFBundleShortVersionString")
            version = version if isinstance(version, str) and len(version) <= 32 else None
            found.append(Installed(facts, bundle / "Contents" / "MacOS" / program, bundle, version,
                                   data_dir(facts, "darwin", env)))
            break  # the first app folder that has it wins
    return found


def _program(command: str) -> str | None:
    """The program in a command line: the text inside its leading quotes, else everything up to and including the
    first ".exe" in any letter case."""
    text = command.strip()
    if text.startswith('"'):
        end = text.find('"', 1)
        if end < 0:
            return None
        return text[1:end].strip() or None
    match = re.search(r"\.exe", text, re.IGNORECASE)
    return text[:match.end()] if match else None


def _expand(text: str, env: Mapping) -> str:
    """%NAME% from env, the name looked up without regard to case, as Windows does; an unknown one stays."""
    values = {str(key).lower(): str(value) for key, value in env.items()}
    return re.sub(r"%([^%]+)%", lambda match: values.get(match.group(1).lower(), match.group(0)), text)


def _windows_row(program: str) -> platforms.BrowserFacts | None:
    """The row whose program path is the tail of `program`, part by part without regard to case, with either
    separator; the longest tail wins."""
    parts = [part.lower() for part in re.split(r"[\\/]+", program) if part]
    best = None
    for facts in platforms.KNOWN_BROWSERS:
        tail = [part.lower() for part in facts.win_exe or ()]
        if tail and parts[-len(tail):] == tail and (best is None or len(tail) > len(best.win_exe)):
            best = facts
    return best


def _windows_installed(folders, commands, env: Mapping) -> list[Installed]:
    # The app folders give paths, used as they are; only the registry's command lines are cut down to their program
    # and have %NAME% expanded, so a user folder whose name holds ".exe" or "%" is still found.
    programs = [str(Path(folder).joinpath(*facts.win_exe))
                for folder in folders for facts in platforms.KNOWN_BROWSERS if facts.win_exe]
    for command in commands:
        program = _program(command) if isinstance(command, str) else None
        if program is not None:
            programs.append(_expand(program, env))
    binaries: dict[str, Path] = {}
    for program in programs:
        facts = _windows_row(program)
        if facts is None or facts.id in binaries or not os.path.isfile(program):
            continue
        binaries[facts.id] = Path(program)  # a browser found twice is counted once, where it was found first
    return [Installed(facts, binaries[facts.id], None, None, data_dir(facts, "win32", env))
            for facts in platforms.KNOWN_BROWSERS if facts.id in binaries]


def os_default(system: str | None = None, env: Mapping | None = None) -> str | None:
    """The id of the system's default browser for https links, or None. Only a first guess, for the user to confirm:
    macOS reads LaunchServices' https entry, Windows the https ProgId."""
    system = _system(system)
    if system == "darwin":
        data = _plist(platforms.launch_services_file())
        handlers = data.get("LSHandlers") if isinstance(data, dict) else None
        for entry in handlers if isinstance(handlers, list) else ():
            if isinstance(entry, dict) and entry.get("LSHandlerURLScheme") == "https":
                bundle = entry.get("LSHandlerRoleAll")
                if not isinstance(bundle, str):
                    return None
                return next((facts.id for facts in platforms.KNOWN_BROWSERS
                             if facts.mac_bundle_id.lower() == bundle.lower()), None)
        return None
    if system == "win32":
        progid = platforms.windows_https_progid()
        if not isinstance(progid, str):
            return None
        base = progid.split(".", 1)[0].lower()  # "ChromeHTML.ABC123" is still Chrome's
        return next((facts.id for facts in platforms.KNOWN_BROWSERS
                     if facts.win_progid and facts.win_progid.lower() == base), None)
    return None


@dataclass(frozen=True)
class Profile:
    """A profile of a browser: its folder in the data folder, the name and colour the user gave it, and whether the
    browser used it last. Nothing from the account: no email, no account name."""

    folder: str
    name: str
    color: str | None
    last_used: bool


_NOT_PROFILES = ("System Profile", "Guest Profile")
_BIDI_CONTROLS = frozenset("\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
_NAME_LIMIT = 64


def _visible(text: str) -> bool:
    """Whether a text holds a character a page shows: one outside the control, format, surrogate, private-use and
    separator categories (C* and Z*)."""
    return any(not unicodedata.category(char).startswith(("C", "Z")) for char in text)


def plain_folder(name) -> bool:
    """Whether a profile folder name is a plain name inside the data folder that a page can show as it is: not empty,
    not . or .., at most 64 characters, no /, \\, : or @, no control, format or surrogate character, and something
    visible. Chromium names its folders Default and Profile N."""
    return (isinstance(name, str) and 0 < len(name) <= _NAME_LIMIT and name not in (".", "..") and _visible(name)
            and not any(char in "/\\:@" or unicodedata.category(char) in ("Cc", "Cf", "Cs") for char in name))


def _profile_name(name, folder: str) -> str:
    """The name the user gave a profile, cleaned: no control, surrogate or bidi characters, trimmed, at most 64
    characters. A name with nothing visible in those 64, or one holding "@" (it may be an email), shows as the
    folder's name, which plain_folder() has already found safe to show."""
    if not isinstance(name, str):
        return folder
    text = "".join(char for char in name
                   if unicodedata.category(char) not in ("Cc", "Cs") and char not in _BIDI_CONTROLS).strip()
    if "@" in text:
        return folder
    text = text[:_NAME_LIMIT]
    return text if _visible(text) else folder


def _color(value) -> str | None:
    """A signed 32-bit ARGB integer as "#rrggbb", or None."""
    if isinstance(value, bool) or not isinstance(value, int) or not -2**31 <= value <= 2**32 - 1:
        return None
    return f"#{value & 0xFFFFFF:06x}"


def _json(path):
    """A JSON file as Python data, or None."""
    data = _read(path)
    if data is None:
        return None
    try:
        return json.loads(data.decode("utf-8", errors="replace"))
    except (ValueError, RecursionError):
        return None


def profiles(data_dir) -> list[Profile]:
    """The browser's profiles from its Local State, in its own order: never System, Guest or ephemeral ones, never
    a folder that isn't plain or isn't there. Only `name` and the colour are copied from each entry."""
    state = _json(Path(data_dir) / "Local State")
    profile = state.get("profile") if isinstance(state, dict) else None
    cache = profile.get("info_cache") if isinstance(profile, dict) else None
    if not isinstance(cache, dict):
        return []
    order = profile.get("profiles_order")
    order = [folder for folder in order if isinstance(folder, str)] if isinstance(order, list) else []
    listed = set(order)  # a set: a hostile file's thousands of entries are matched in linear time, never pair by pair
    rest = sorted((folder for folder in cache if folder not in listed),
                  key=lambda folder: (folder != "Default", folder))
    last_used = profile.get("last_used")
    found, seen = [], set()
    for folder in [*order, *rest]:
        entry = cache.get(folder)
        if folder in seen or not isinstance(entry, dict):
            continue
        seen.add(folder)
        if (folder in _NOT_PROFILES or entry.get("is_ephemeral") is True or not plain_folder(folder)
                or not os.path.isdir(os.path.join(data_dir, folder))):
            continue
        color = _color(entry.get("profile_highlight_color")) or _color(entry.get("default_avatar_fill_color"))
        found.append(Profile(folder, _profile_name(entry.get("name"), folder), color, folder == last_used))
    return found


@dataclass(frozen=True)
class WatcherPlace:
    """A profile folder that holds an enabled copy of a watcher, and that copy's extension id."""

    profile: str
    extension_id: str


def _extension_settings(path) -> dict:
    data = _json(path)
    extensions = data.get("extensions") if isinstance(data, dict) else None
    settings = extensions.get("settings") if isinstance(extensions, dict) else None
    return settings if isinstance(settings, dict) else {}


_MAX_PATH = 4096  # characters: no watcher folder is longer, and resolving a hostile path costs time in its square


def _watcher_key(path, system: str) -> str | None:
    """A watcher folder as compared with the path a browser recorded: on Windows the absolute path without regard
    to case and with no link resolved (as Chrome records it), elsewhere the real path, exactly. None for a path that
    can't be compared: over 4096 characters, or holding a NUL."""
    text = str(path)
    if len(text) > _MAX_PATH:
        return None
    try:
        if system == "win32":
            return ntpath.normcase(ntpath.abspath(text))
        return os.path.realpath(text)
    except (OSError, ValueError):
        return None


def _enabled(entry) -> bool:
    reasons = entry.get("disable_reasons", 0)
    if not (reasons == [] or (type(reasons) is int and reasons == 0)):
        return False
    state = entry.get("state")
    return not (type(state) is int and state == 0)  # an older Chromium's "disabled"


def watcher_places(data_dir, watchers: Mapping[str, str | Path], system: str | None = None) -> list[WatcherPlace]:
    """Which profiles hold an enabled copy of which watcher: `watchers` maps each watcher's extension id to the
    folder it was loaded from. Read from each profile's Secure Preferences, then Preferences (the first wins)."""
    system = _system(system)
    if not isinstance(watchers, Mapping):
        return []
    wanted = {extension_id: _watcher_key(folder, system) for extension_id, folder in watchers.items()
              if isinstance(extension_id, str)}
    places = []
    for profile in profiles(data_dir):
        secure = _extension_settings(Path(data_dir) / profile.folder / "Secure Preferences")
        plain = _extension_settings(Path(data_dir) / profile.folder / "Preferences")
        for extension_id, key in wanted.items():
            entry = secure[extension_id] if extension_id in secure else plain.get(extension_id)
            if (key is not None and isinstance(entry, dict) and isinstance(entry.get("path"), str)
                    and _watcher_key(entry["path"], system) == key and _enabled(entry)):
                places.append(WatcherPlace(profile.folder, extension_id))
    return places


STATES = ("not_running", "switch_off", "switch_on")


def devtools_port(data_dir) -> int | None:
    """The port in the data folder's DevToolsActivePort (its first line: 1 to 5 ASCII digits, 1 to 65535), or None.
    The file stays behind after the browser exits, so the port alone says nothing about the browser running."""
    data = _read(Path(data_dir) / "DevToolsActivePort")
    lines = data.decode("utf-8", errors="replace").splitlines() if data is not None else []
    first = lines[0].strip() if lines else ""
    if not re.fullmatch(r"[0-9]{1,5}", first):
        return None
    port = int(first)
    return port if 1 <= port <= 65535 else None


def listening(port, timeout: float = 0.5) -> bool:
    """Whether something accepts a TCP connection on 127.0.0.1:port. It connects and closes at once, sending no
    bytes: no HTTP request and no websocket, so no DevTools session and no "Allow remote debugging?" question."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def running(data_dir, system: str | None = None) -> bool | None:
    """Whether the browser of this data folder runs, from its own lock: True, False, or None when it can't tell.
    macOS and Linux: SingletonLock is a link to "<host>-<pid>" (read, never followed). Windows: the lockfile exists
    while the browser runs; it is never opened, since the browser holds it without sharing delete access."""
    system = _system(system)
    lock = os.path.join(data_dir, platforms.lock_name(system))
    if system == "win32":
        return os.path.exists(lock)
    if not os.path.lexists(lock):
        return False
    try:
        target = os.readlink(lock)
        host_name = socket.gethostname()
    except (OSError, ValueError):
        return None  # a regular file, or a link that can't be read
    host, dash, pid = target.rpartition("-")  # the host name may hold dashes itself
    if not dash or not re.fullmatch(r"[1-9][0-9]{0,8}", pid) or host != host_name:
        return None
    return platforms.pid_alive(int(pid))


def state(data_dir, system: str | None = None) -> str:
    """One of STATES. The lock tells "not running" from "switch off"; only DevToolsActivePort and the silent TCP
    check say the switch is on. A browser that isn't running gets no TCP check, so a stale port is never touched."""
    if data_dir is None or not os.path.isdir(data_dir):
        return "not_running"
    alive = running(data_dir, system)
    if alive is False:
        return "not_running"
    port = devtools_port(data_dir)
    if port is not None and listening(port):
        return "switch_on"
    return "switch_off" if alive else "not_running"  # can't tell: today's rule, the port alone


@dataclass(frozen=True)
class Found:
    """One installed browser with what detection knows of it. A browser agents can't use has no state, no profiles
    and no watchers: nothing in its data folder is read."""

    browser: Installed
    state: str | None
    profiles: tuple[Profile, ...]
    watchers: tuple[WatcherPlace, ...]
    default: bool


def detect(watchers: Mapping[str, str | Path] | None = None, system: str | None = None,
           env: Mapping | None = None) -> list[Found]:
    """Every installed browser, in the table's order, with its state, profiles and watcher copies (for the ones
    agents can use) and whether it is the system's default. Reads files only; never connects."""
    system = _system(system)
    default = os_default(system, env)
    found = []
    for browser in installed(system, env):
        if not browser.agents:
            found.append(Found(browser, None, (), (), browser.id == default))
            continue
        found.append(Found(browser, state(browser.data_dir, system), tuple(profiles(browser.data_dir)),
                           tuple(watcher_places(browser.data_dir, watchers or {}, system)), browser.id == default))
    return found


def public(found, connected=()) -> list[dict]:
    """What pages may see of detect()'s result: no paths, versions, watcher ids or account fields. `connected` holds
    the ids of browsers the app's own link is connected to; one with a known state shows "connected"."""
    connected = {browser_id for browser_id in connected if isinstance(browser_id, str)}
    copies: dict[str, int] = {}  # extension id -> how many profiles, in any browser, hold an enabled copy
    for item in found:
        for place in item.watchers:
            copies[place.extension_id] = copies.get(place.extension_id, 0) + 1
    shown = []
    for item in found:
        ids = {}
        for place in item.watchers:
            ids.setdefault(place.profile, set()).add(place.extension_id)
        state_shown = "connected" if item.state is not None and item.browser.id in connected else item.state
        shown.append({
            "id": item.browser.id, "name": item.browser.name, "agents": item.browser.agents,
            "default": item.default, "state": state_shown,
            "profiles": [{"folder": profile.folder, "name": profile.name, "color": profile.color,
                          "last_used": profile.last_used, "watcher": bool(ids.get(profile.folder)),
                          "shared_watcher": any(copies[extension_id] > 1
                                                for extension_id in ids.get(profile.folder, ()))}
                         for profile in item.profiles]})
    return shown
