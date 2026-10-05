"""Agent powers: what Claude Code's own tools may do without the user, what a card shows, and the user's rules.

Agents have Claude Code's own tools besides the browser's (the agent-powers spec, Decision 1). Every use of one reaches
the app as a `can_use_tool` request (app/bridge.py), and this module decides it from the request's own input, without
running anything (Decisions 2 to 5):
- classify(tool, input, folder): "allow" without asking (Decision 3), "ask" (a card that offers Always allow), or
  "ask_always" (a card without it, asked every time: Decision 4, and anything the app can't read as one plain command
  inside the folder);
- rule_for(tool, input): the rule Always allow saves ("Bash(npm test:*)", "Edit", "WebFetch(domain:example.com)").

A command is split the way a shell splits it (shlex), never run. Only one plain command can be harmless or match a
rule: a second command, a pipe, a substitution, a variable, a redirect, a glob or a brace never is one (Review Focus
1). Paths are compared after realpath, so a symlink or a `..` that leaves the folder is outside it (Review Focus 2)."""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from urllib.parse import urlsplit

# Task 1's probe sets these (the plan's rulings R1 to R4): facts about Claude Code 2.1.263 on macOS, not choices.
# Task 1: Ruling: the probe is deferred to the user (it needs a hand sign-in); the build uses the safest values until
# it runs — R1 SANDBOX = False (the cards are the guard; the sandbox code path stays, off), R2 UNTRUSTED_SOURCES = ""
# (nothing of the folder's own loads), R3 ASK_ALL = True (every use goes to the app's own check), R4 SUBAGENT_TOOL
# accepts both "Agent" and "Task" (the name is read from the init event's tools when present) — cost if wrong: a
# follow-up fix after the probe; never a looser default.
# Change one only with the probe's answer (tests/probe_powers.py).
SANDBOX = False  # R1: Claude Code's Bash sandbox holds in -p mode: writes stay in the folder (macOS only)
SANDBOX_NETWORK = False  # R1: and a command in it can't reach the network
UNTRUSTED_SOURCES = ""  # R2: --setting-sources for a folder that isn't trusted: none of the folder's own settings
ASK_ALL = True  # R3: a permissions.ask rule brings every command, read and edit to the app
SUBAGENT_TOOL = "Agent"  # R4: the name handed to Claude Code; both names in SUBAGENTS are read as the sub-agent tool

TOOLS = ("Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebSearch", "WebFetch", SUBAGENT_TOOL, "TodoWrite")
FREE = ("TodoWrite", SUBAGENT_TOOL)  # never asked (Decision 3): also handed to Claude Code as --allowedTools
ASKED = ("Bash", "Read", "Glob", "Grep", "Edit", "Write")  # R3: Claude Code asks the app for each of their uses
SUBAGENTS = frozenset({"Agent", "Task"})  # the sub-agent tool, by either name Claude Code has given it
READS = frozenset({"Read", "Glob", "Grep"})
EDITS = frozenset({"Edit", "Write"})

COMMAND_LIMIT = 10_000  # characters: a longer command is never one plain command
_NEVER_PLAIN = re.compile(r"[\n\r\x00`$\\{}*?\[\]!]")  # a new line, a substitution, a variable, an escape, a glob
_OPERATOR = re.compile(r"[;&|<>()]+")
_PROGRAM = re.compile(r"(?:\./|/)?[A-Za-z0-9_][A-Za-z0-9_.+-]*(?:/[A-Za-z0-9_.+-]+)*")
_WORD = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.@+:/-]*")  # a word a rule may hold: no option, quote or space
_DRIVE = re.compile(r"[A-Za-z]:[\\/]")
_CLIMB = re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)")
_GLOB = re.compile(r"[*?\[{]")

LAUNCHERS = frozenset({  # they run another command, which no rule of theirs could cover
    "sudo", "su", "doas", "sh", "bash", "zsh", "fish", "dash", "ksh", "csh", "tcsh", "env", "xargs", "eval", "exec",
    "source", "nohup", "time", "nice", "timeout", "watch", "command", "builtin", "alias", "unalias", "function",
    "trap", "osascript", "open", "ssh", "script", "expect", "parallel", "powershell", "pwsh", "cmd"})
RISKY = frozenset({  # Decision 4's, and programs whose saved rule would cover their dangerous uses too
    "rm", "rmdir", "chmod", "chown", "chgrp", "dd", "shred", "truncate", "diskutil", "fdisk", "newfs", "launchctl",
    "crontab", "defaults"})
INTERPRETERS = frozenset({"python", "python3", "node", "ruby", "perl", "php", "lua", "Rscript"})
INLINE = frozenset({"-c", "-e", "-p", "-r", "--eval", "--print", "--command"})  # code on the command line
SUBCOMMANDS = frozenset({"git", "npm", "pnpm", "yarn", "bun", "uv", "pip", "pip3", "poetry", "cargo", "go", "docker",
                         "kubectl", "brew", "gh", "dotnet", "swift", "mvn", "gradle", "deno"})
RUNNERS = frozenset({"run", "exec", "x", "dlx", "tool"})  # `npm run build`: the rule holds the third word too
HARMLESS = frozenset({"ls", "cat", "pwd"})  # Decision 3, with git's three below
GIT_READS = frozenset({"status", "diff", "log"})
GIT_UNSAFE = frozenset({"--output", "--ext-diff", "--textconv", "--open-files-in-pager", "--exec-path"})
_GIT_PROGRAM = re.compile(r"^\s*(fsmonitor|pager|external|textconv|command|cmd|sshcommand|hookspath|editor|askpass|"
                          r"helper|clean|smudge|process|path|program|worktree|gitproxy)\s*=",
                          re.IGNORECASE | re.MULTILINE)
_GIT_SECTION = re.compile(r"^\s*\[\s*(include|includeif|alias)\b", re.IGNORECASE | re.MULTILINE)

WHY_NOT_PLAIN = "It isn't one plain command: it has a second command, a pipe, a redirect, a substitution or a glob"
WHY_LAUNCHER = "It runs another command, which a rule can't cover"
WHY_RISKY = "It can delete or change files beyond repair"
WHY_OUTSIDE = "It names a path outside the task's folder"
WHY_INLINE = "It runs code written on the command line"
WHY_OPTION = "An option comes before the command's own name"
WHY_RUNNER = "It runs whatever comes after it"
WHY_SANDBOX = "It runs outside the sandbox"
WHY_READ = "It reads outside the task's folder"
WHY_EDIT = "It changes a file outside the task's folder"
WHY_GUARDED = "It changes Git's or Claude Code's own settings in this folder"
WHY_WEB = "That isn't a web address"


def user_home() -> Path:
    """The user's home folder (tests point it at a throwaway one: conftest's user_home)."""
    return Path.home()


def words_of(command) -> list[str] | None:
    """The words of one plain command, split as a shell splits them; None when it isn't one: empty, too long, more
    than one command, a pipe, a substitution, a variable, a redirect, a glob, a brace, quotes that don't close, or a
    first word that isn't a program's name (FOO=1 ls)."""
    if not isinstance(command, str) or not command.strip() or len(command) > COMMAND_LIMIT \
            or _NEVER_PLAIN.search(command):
        return None
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        words = list(lexer)
    except ValueError:  # quotes that don't close
        return None
    if not words or any(_OPERATOR.fullmatch(word) for word in words) or not _PROGRAM.fullmatch(words[0]):
        return None
    return words


def _real(path) -> str:
    return os.path.normcase(os.path.realpath(path))


def real_path(path) -> str:
    """A folder as the rules file keys it: ~ expanded, absolute, symlinks and .. resolved."""
    return os.path.realpath(os.path.expanduser(str(path)))


def inside(path, folder) -> bool:
    """Whether `path` (absolute, ~, or relative to the folder) is the folder or in it, once symlinks and .. are
    resolved. Anything that isn't a path is outside."""
    if not isinstance(path, str) or not path or "\x00" in path:
        return False
    target = Path(os.path.expanduser(path))
    if not target.is_absolute():
        target = Path(folder) / target
    real, root = _real(target), _real(folder)
    return real == root or real.startswith(root.rstrip(os.sep) + os.sep)


def _targets(word: str) -> list[str]:
    """What in one argument may name a file: the word, an option's value (--output=/x, -o/x), what follows an =."""
    if word.startswith("-"):
        value = word.split("=", 1)[1] if "=" in word else word.lstrip("-")[1:]
        return [value] if value else []
    return [word, word.split("=", 1)[1]] if "=" in word else [word]


def _outside(word: str, folder) -> bool:
    return any(part.lower().startswith("file:") or not inside(part, folder) for part in _targets(word))


def _program(word: str) -> str:
    return word.rsplit("/", 1)[-1]


def _git_runs_programs(folder) -> bool:
    """Whether Git could run a program of the folder's own on git status, diff or log: settings that name one
    (fsmonitor, a pager, a diff driver, an include, an alias), or a .git that isn't a plain folder of this folder's
    own (git would read a parent's settings, or another work tree's). Plan decision 7."""
    git = Path(folder) / ".git"
    if git.is_symlink() or not git.is_dir():
        return True
    try:
        text = (git / "config").read_text(encoding="utf-8", errors="replace")[:200_000]
    except OSError:
        return True
    return bool(_GIT_PROGRAM.search(text) or _GIT_SECTION.search(text))


def _harmless(program: str, words: list[str], folder) -> bool:
    """Decision 3's commands, whole: ls, cat and pwd, and git status, diff and log without the options that write a
    file or run a program (their paths were checked already)."""
    if program in HARMLESS:
        return True
    if program != "git" or len(words) < 2 or words[1] not in GIT_READS:
        return False
    if any(word.split("=", 1)[0] in GIT_UNSAFE or word.startswith("-O") for word in words[2:]):
        return False
    return not _git_runs_programs(folder)


def _prefix(words: list[str]) -> tuple[list[str] | None, str]:
    """The words a rule for this command holds (Decision 5: "the command's first words"), or None and why there is
    no rule: code on the command line, an option before the subcommand, a runner with nothing after it."""
    program, rest = _program(words[0]), words[1:]
    if program in INTERPRETERS and rest:
        if rest[0] in INLINE or rest[0][:2] in ("-c", "-e"):
            return None, WHY_INLINE
        if rest[0] == "-m":
            return (words[:3], "") if len(rest) > 1 and _WORD.fullmatch(rest[1]) else (None, WHY_INLINE)
        if rest[0].startswith("-"):
            return None, WHY_OPTION
    if not rest:
        return words[:1], ""
    if rest[0].startswith("-") or not _WORD.fullmatch(rest[0]):
        return (None, WHY_OPTION) if program in SUBCOMMANDS else (words[:1], "")
    if rest[0] in RUNNERS:
        return (words[:3], "") if len(rest) > 1 and _WORD.fullmatch(rest[1]) else (None, WHY_RUNNER)
    return words[:2], ""


def _bash(data: dict, folder, moved: bool) -> tuple[str, str]:
    if data.get("dangerouslyDisableSandbox") is True:
        return "ask_always", WHY_SANDBOX
    words = words_of(data.get("command"))
    if words is None:
        return "ask_always", WHY_NOT_PLAIN
    program = _program(words[0])
    if program in LAUNCHERS:
        return "ask_always", WHY_LAUNCHER
    if program in RISKY or program.startswith("mkfs"):
        return "ask_always", WHY_RISKY
    if any(_outside(word, folder) for word in words[1:]):
        return "ask_always", WHY_OUTSIDE
    if not moved and _harmless(program, words, folder):
        return "allow", ""
    prefix, why = _prefix(words)
    return ("ask", "") if prefix else ("ask_always", why)


def _glob_root(pattern: str) -> str:
    """The folder an absolute glob starts in: its parts before the first one with a wildcard."""
    kept = []
    for part in re.split(r"[\\/]", pattern):
        if _GLOB.search(part):
            break
        kept.append(part)
    return "/".join(kept) or "/"


def _reads(tool: str, data: dict, folder) -> tuple[str, str]:
    if tool == "Read":
        targets = [data.get("file_path")]
    else:
        where = data.get("path")
        targets = [where if where is not None else str(folder)]
        pattern = data.get("pattern") if tool == "Glob" else data.get("glob")
        if isinstance(pattern, str) and pattern:
            if _CLIMB.search(pattern) or pattern.startswith("~"):
                return "ask_always", WHY_READ
            if pattern.startswith(("/", "\\")) or _DRIVE.match(pattern):
                targets.append(_glob_root(pattern))
    return ("allow", "") if all(inside(target, folder) for target in targets) else ("ask_always", WHY_READ)


def _guarded(path: str, folder) -> bool:
    """A file of Git's or Claude Code's own in the folder (.git, .claude, .mcp.json): what they run or load later, so
    an edit there could turn "edit files" into "run programs" (plan decision 7)."""
    target = Path(os.path.expanduser(path))
    target = target if target.is_absolute() else Path(folder) / target
    parts = Path(os.path.relpath(_real(target), _real(folder))).parts
    return any(part in (".git", ".claude") for part in parts) or parts[:1] == (".mcp.json",)


def _host(url) -> str:
    """The host of an http(s) address, lower-case; "" for anything else."""
    if not isinstance(url, str) or len(url) > 2000:
        return ""
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
    except ValueError:
        return ""
    return host if parts.scheme in ("http", "https") and re.fullmatch(r"[a-z0-9.-]{1,253}", host) else ""


def _decide(tool: str, data, folder, moved: bool = False) -> tuple[str, str]:
    """classify's answer, and why a card that asks every time does."""
    data = data if isinstance(data, dict) else {}
    if tool in FREE or tool in SUBAGENTS:
        return "allow", ""
    if tool == "Bash":
        return _bash(data, folder, moved)
    if tool in READS:
        return _reads(tool, data, folder)
    if tool in EDITS:
        path = data.get("file_path")
        if not inside(path, folder):
            return "ask_always", WHY_EDIT
        return ("ask_always", WHY_GUARDED) if _guarded(path, folder) else ("ask", "")
    if tool == "WebFetch":
        return ("ask", "") if _host(data.get("url")) else ("ask_always", WHY_WEB)
    if tool == "WebSearch" and isinstance(data.get("query"), str) and data["query"].strip():
        return "ask", ""
    return "ask_always", ""


def classify(tool: str, data, folder, moved: bool = False) -> str:
    """"allow", "ask" or "ask_always" for one request (Decisions 3 and 4). `moved`: an allowed command may have taken
    the shell out of the folder, so no command is harmless for the rest of that Claude Code process (plan decision
    8)."""
    return _decide(tool, data, folder, moved)[0]


def rule_for(tool: str, data) -> str | None:
    """The rule Always allow saves (Decision 5), or None when no rule may cover this request."""
    data = data if isinstance(data, dict) else {}
    if tool == "Bash":
        words = words_of(data.get("command"))
        if words is None or data.get("dangerouslyDisableSandbox") is True:
            return None
        program = _program(words[0])
        if program in LAUNCHERS or program in RISKY or program.startswith("mkfs"):
            return None
        prefix, _ = _prefix(words)
        return f"Bash({' '.join(prefix)}:*)" if prefix else None
    if tool in EDITS:
        return "Edit"
    if tool == "WebFetch":
        host = _host(data.get("url"))
        return f"WebFetch(domain:{host})" if host else None
    if tool == "WebSearch":
        return "WebSearch"
    return None


_MOVES = re.compile(r"(?:^|[\s;&|(`])(?:cd|pushd|popd)(?=$|[\s;&|)])")


def moves_folder(command) -> bool:
    """Whether a command may change the shell's folder (cd, pushd, popd), which Claude Code keeps between commands."""
    return isinstance(command, str) and bool(_MOVES.search(command))
