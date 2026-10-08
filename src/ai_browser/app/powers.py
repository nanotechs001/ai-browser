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

import difflib
import json
import os
import re
import shlex
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit

from ..syncdir import write_atomic

# Task 1's probe sets these (the plan's rulings R1 to R4): facts about Claude Code 2.1.263 on macOS, not choices.
# Task 1: Ruling: the probe is deferred to the user (it needs a hand sign-in); the build uses the safest values until
# it runs — R1 SANDBOX = False (the cards are the guard; the sandbox code path stays, off), R2 UNTRUSTED_SOURCES = ""
# (nothing of the folder's own loads), R3 ASK_ALL = True (every use goes to the app's own check), R4 SUBAGENT_TOOL
# accepts both "Agent" and "Task" (the name is read from the init event's tools when present) — cost if wrong: a
# follow-up fix after the probe; never a looser default.
# The probe ran on 2026-10-07 (Claude Code 2.1.263, macOS): a sandboxed `touch` inside the folder worked, one outside
# it got "Operation not permitted", and the curl got no network (its reach came as a SandboxNetworkAccess request);
# `--setting-sources ""` ran no hook and loaded no CLAUDE.md; without the ask rule, in-folder reads, `ls` and `echo one
# && echo two` were never asked; `--tools Agent` listed nothing and `--tools Task` listed Task, whose uses stream as
# "Agent".
# Change one only with the probe's answer (tests/probe_powers.py).
SANDBOX = True  # R1: Claude Code's Bash sandbox holds in -p mode: writes stay in the folder (macOS only)
SANDBOX_NETWORK = True  # R1: and a command in it can't reach the network
UNTRUSTED_SOURCES = ""  # R2: --setting-sources for a folder that isn't trusted: none of the folder's own settings
ASK_ALL = True  # R3: a permissions.ask rule brings every command, read and edit to the app
SUBAGENT_TOOL = "Task"  # R4: the name handed to Claude Code; both names in SUBAGENTS are read as the sub-agent tool

TOOLS = ("Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebSearch", "WebFetch", SUBAGENT_TOOL, "TodoWrite")
FREE = ("TodoWrite", SUBAGENT_TOOL)  # never asked (Decision 3): also handed to Claude Code as --allowedTools
ASKED = ("Bash", "Read", "Glob", "Grep", "Edit", "Write")  # R3: Claude Code asks the app for each of their uses
SUBAGENTS = frozenset({"Agent", "Task"})  # the sub-agent tool, by either name Claude Code has given it
NETWORK = "SandboxNetworkAccess"  # R1: a sandboxed command asking to reach a site (its input: {"host": ...})
READS = frozenset({"Read", "Glob", "Grep"})
EDITS = frozenset({"Edit", "Write"})

COMMAND_LIMIT = 10_000  # characters: a longer command is never one plain command
OPTION_LIMIT = 256  # characters of a cluster of short options whose every tail is checked as a path
_NEVER_PLAIN = re.compile(r"[\n\r\x00`$\\{}*?\[\]!]")  # a new line, a substitution, a variable, an escape, a glob
_OPERATOR = re.compile(r"[;&|<>()]+")
_PROGRAM = re.compile(r"(?:\./|/)?[A-Za-z0-9_][A-Za-z0-9_.+-]*(?:/[A-Za-z0-9_.+-]+)*")
_WORD = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.@+:/-]*")  # a word a rule may hold: no option, quote or space
_DRIVE = re.compile(r"[A-Za-z]:[\\/]")
_CMD_VARIABLE = re.compile(r"%[^%\s]+%")  # %USERPROFILE%: cmd.exe, which runs npm's scripts on Windows, expands it
_CLIMB = re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)")
_GLOB = re.compile(r"[*?\[{]")

LAUNCHERS = frozenset({  # they run another command, which no rule of theirs could cover
    "sudo", "su", "doas", "sh", "bash", "zsh", "fish", "dash", "ksh", "csh", "tcsh", "env", "xargs", "eval", "exec",
    "source", "nohup", "time", "nice", "timeout", "watch", "command", "builtin", "alias", "unalias", "function",
    "trap", "osascript", "open", "ssh", "script", "expect", "parallel", "powershell", "pwsh", "cmd",
    # the security review of auto-approve (C2): more that run the command after them
    "caffeinate", "arch", "busybox", "stdbuf", "setsid", "unshare", "nsenter", "chroot", "pkexec", "run0",
    "systemd-run", "strace", "ltrace", "dtruss", "gdb", "lldb", "valgrind", "flock", "hyperfine", "at", "batch",
    "unbuffer", "entr", "watchexec", "firejail", "proxychains", "proxychains4", "torsocks",
    # Windows' (Auto-approve runs commands there too: the user's choice, 2026-10-08)
    "start", "runas", "wsl", "winpty", "mintty", "conhost", "cygstart", "explorer", "wscript", "cscript", "mshta",
    "rundll32", "regsvr32", "msiexec", "forfiles", "wmic"})
RISKY = frozenset({  # Decision 4's, and programs whose saved rule would cover their dangerous uses too
    "rm", "rmdir", "chmod", "chown", "chgrp", "dd", "shred", "truncate", "diskutil", "fdisk", "newfs", "launchctl",
    "crontab", "defaults", "unlink", "srm",
    # Windows': deleting, and changing the computer's settings, services, scheduled tasks and file permissions
    "del", "erase", "rd", "robocopy", "cipher", "format", "diskpart", "attrib", "cacls", "icacls", "takeown", "reg",
    "setx", "sc", "schtasks", "net", "netsh", "bcdedit"})
# Everyday programs whose saved rule would also cover a use that deletes files or throws work away (fresh review F2):
# those uses are asked every time, never Always (Decision 4), while the program's other uses still offer it.
FIND_DELETES = frozenset({"-delete"})  # find removes what it finds
FIND_RUNS = frozenset({"-exec", "-execdir", "-ok", "-okdir"})  # find runs another program on what it finds
GIT_DISCARDS = frozenset({"clean", "restore"})  # git deletes untracked files, or throws away uncommitted changes
GIT_FORCE = ("--force", "--mirror", "--delete")  # git push options that overwrite or delete the remote's work
# Interpreters, however their version is spelled (python3.12, pypy3, py): code on the command line is never a rule's
_INTERPRETER = re.compile(r"python\d*(?:\.\d+)*|pypy\d*(?:\.\d+)*|py|node|nodejs|tsx|ts-node|ruby|irb|perl|php|lua|"
                          r"luajit|julia|r|rscript")
INLINE = frozenset({"-c", "-e", "-p", "-r", "--eval", "--print", "--command"})  # code on the command line
_SUFFIX = re.compile(r"\.(?:exe|cmd|bat|com)$", re.IGNORECASE)  # rm.exe is rm
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
WHY_DISCARDS = "It deletes files or throws away work beyond repair"
WHY_OUTSIDE = "It names a path outside the task's folder"
WHY_INLINE = "It runs code written on the command line"
WHY_OPTION = "An option comes before the command's own name"
WHY_RUNNER = "It runs whatever comes after it"
WHY_SANDBOX = "It runs outside the sandbox"
WHY_NETWORK = "A command in the sandbox reaches a site only when you say so, each time"
WHY_READ = "It reads outside the task's folder"
WHY_MOVED = "The shell has left the task's folder: a path that isn't a full one may name a file outside it"
WHY_EDIT = "It changes a file outside the task's folder"
WHY_GUARDED = "It changes Git's, Claude Code's or an editor's own settings or hooks in this folder"
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


def _identity(path) -> tuple[int, int] | None:
    """A file's identity on its disk (device, inode), or None when it isn't there. Two spellings name the same folder
    when their identities match: a case variant on a disk that ignores case (macOS's and Windows' default), where
    realpath keeps the case it was given (fresh review F1)."""
    try:
        info = os.stat(path)
    except (OSError, ValueError):
        return None
    return (info.st_dev, info.st_ino) if info.st_ino else None


def _same(real: str, other: str) -> bool:
    """Whether two real paths name the same file: as text, or by identity."""
    if real == other:
        return True
    mine = _identity(real)
    return mine is not None and mine == _identity(other)


def _under(real: str, folder: str) -> bool:
    """Whether the real path `real` is in the real folder `folder`: as text, or because a folder above it is that
    folder by identity."""
    if real.startswith(folder.rstrip(os.sep) + os.sep):
        return True
    theirs = _identity(folder)
    return theirs is not None and any(_identity(above) == theirs for above in Path(real).parents)


def real_path(path) -> str:
    """A folder as the rules file keys it: ~ expanded, absolute, symlinks and .. resolved."""
    return os.path.realpath(os.path.expanduser(str(path)))


def inside(path, folder) -> bool:
    """Whether `path` (absolute, ~, or relative to the folder) is the folder or in it, once symlinks and .. are
    resolved, and however its name is spelled where the disk ignores case. Anything that isn't a path is outside."""
    if not isinstance(path, str) or not path or "\x00" in path:
        return False
    if os.name != "nt" and _DRIVE.match(path):
        return False  # a Windows path (C:/…): Windows reads it as a drive's; no folder here is on one
    target = Path(os.path.expanduser(path))
    if not target.is_absolute():
        target = Path(folder) / target
    real, root = _real(target), _real(folder)
    return _same(real, root) or _under(real, root)


def _targets(word: str) -> list[str]:
    """What in one argument may name a file: the word, an option's value (--output=/x), what follows an =, and in a
    cluster of short options every tail after its first letter, since any letter may be the one that takes a value
    (-o/x, -so/x, -sSo~/.zshrc)."""
    if word.startswith("-"):
        if "=" in word or word.startswith("--"):
            value = word.split("=", 1)[1] if "=" in word else word.lstrip("-")[1:]
            return [value] if value else []
        return [word[start:] for start in range(2, len(word))]
    return [word, word.split("=", 1)[1]] if "=" in word else [word]


def _outside(word: str, folder) -> bool:
    if word.startswith("-") and not word.startswith("--") and "=" not in word and len(word) > OPTION_LIMIT:
        return True  # too long to check each tail: asked every time
    if sys.platform == "win32" and _CMD_VARIABLE.search(word):
        return True  # a folder cmd.exe would put in its place (npm test -- %USERPROFILE%)
    return any(part.lower().startswith("file:") or not inside(part, folder) for part in _targets(word))


def _program(word: str) -> str:
    return word.rsplit("/", 1)[-1]


def _name(word: str) -> str:
    """A program as the deny-lists know it: its file name, lower-case, without .exe (RM and rm.exe are rm where the
    disk ignores case, as macOS's and Windows' do)."""
    return _SUFFIX.sub("", _program(word)).lower()


def _bare(word: str) -> bool:
    """A program found on the PATH, not one the folder holds (./bin/ls could be anything the agent wrote)."""
    return "/" not in word and "\\" not in word


def _own_program(word: str) -> bool:
    """A program named by a path in the folder (./run.sh, scripts/build.sh), not a name on the PATH or a full path."""
    return "/" in word and not word.startswith("/")


SHELLS = ("bash", "sh")  # with a script file first, they run the folder's own script, like python x.py


def _shell_script(words: list[str]) -> bool:
    """bash or sh running a file: its first word after it isn't an option (-c, -s, -i, --norc, +x, -, --), so it
    neither runs code given on the command line nor reads stdin (the ruling of 2026-10-08). Where the file is, the
    caller checks."""
    return words[0] in SHELLS and len(words) > 1 and not words[1].startswith(("-", "+"))


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
    file or run a program (their paths were checked already). Only the programs on the PATH: never one the folder
    holds."""
    if not _bare(words[0]):
        return False
    if program in HARMLESS:
        return True
    if program != "git" or len(words) < 2 or words[1] not in GIT_READS:
        return False
    if any(word.split("=", 1)[0] in GIT_UNSAFE or word.startswith("-O") for word in words[2:]):
        return False
    return not _git_runs_programs(folder)


_SED_QUIET = set("=dDgGhHlnNpPqQxzF")  # sed's commands that only read, print or stop
_SED_FLAGS = set("gpiImM0123456789")  # an s command's flags that neither run a command nor write a file


def _sed_part(script: str, start: int, delimiter: str) -> int:
    """Where the part of a sed command that starts at `start` ends (its delimiter), or -1."""
    index = start
    while index < len(script):
        if script[index] == "\\":
            index += 2
            continue
        if script[index] == delimiter or script[index] == "\n":
            return index if script[index] == delimiter else -1
        index += 1
    return -1


def _sed_runs(script: str) -> bool:
    """Whether a sed script may run a command or touch a file it names: an e, w, W, r or R command, or an s command's e
    or w flag (GNU sed). Anything it can't read is taken as one."""
    index, size = 0, len(script)
    while index < size:
        char = script[index]
        if char in " \t\n;{}!,~+$" or char.isdigit():  # separators, and an address's numbers and marks
            index += 1
        elif char == "#":  # a comment, to the end of its line
            end = script.find("\n", index)
            index = size if end < 0 else end + 1
        elif char in "/\\":  # an address's regular expression: /re/ or \cREc, then I or M
            delimiter, start = ("/", index + 1) if char == "/" else (script[index + 1:index + 2], index + 2)
            end = _sed_part(script, start, delimiter) if delimiter else -1
            if end < 0:
                return True
            index = end + 1
            while index < size and script[index] in "IM":
                index += 1
        elif char in "sy":
            delimiter = script[index + 1:index + 2]
            if not delimiter or delimiter in "\n\\":
                return True
            middle = _sed_part(script, index + 2, delimiter)
            end = _sed_part(script, middle + 1, delimiter) if middle >= 0 else -1
            if end < 0:
                return True
            index = end + 1
            while char == "s" and index < size and script[index] not in ";\n}":
                if script[index] not in _SED_FLAGS and script[index] not in " \t":
                    return True  # e or w (or anything else)
                index += 1
        elif char in "aic:btTv":  # text or a label, to the end of the line (a label: or to a ;)
            stops = "\n" if char in "aic" else ";\n"
            while index < size and script[index] not in stops:
                index += 2 if script[index] == "\\" else 1
        elif char in _SED_QUIET:
            index += 1
        else:
            return True  # e, w, W, r, R, or a command this reading doesn't know
    return False


def _sed_scripts(args: list[str]) -> list[str] | None:
    """The scripts of a sed command: each -e's, else its first word that isn't an option (and the second too after a
    bare -i, which BSD sed takes as the backup's suffix). None for a script in a file (-f), which isn't read."""
    scripts, plain, index, bare_i = [], [], 0, False
    while index < len(args):
        arg = args[index]
        stem = arg[2:].split("=", 1)[0] if arg.startswith("--") else ""
        if arg == "-e" or (stem and "expression".startswith(stem)):  # GNU takes --expr for --expression
            if "=" in arg and stem:
                scripts.append(arg.split("=", 1)[1])
            elif index + 1 < len(args):
                scripts.append(args[index + 1])
                index += 1
        elif arg == "-f" or (stem and "file".startswith(stem)):
            return None
        elif stem and "line-length".startswith(stem) and "=" not in arg:
            index += 1  # its value
        elif arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
            letters = arg[1:]
            for place, letter in enumerate(letters):
                if letter == "f":
                    return None
                if letter in "el":  # its value: the rest of the word, or the next word
                    value = letters[place + 1:]
                    if not value and index + 1 < len(args):
                        index += 1
                        value = args[index]
                    if letter == "e":
                        scripts.append(value)
                    break
                if letter == "i":  # GNU: the rest is the backup's suffix; BSD: the next word is
                    bare_i = place == len(letters) - 1
                    break
        elif not arg.startswith("-"):
            plain.append(arg)
        index += 1
    return scripts or plain[:2 if bare_i else 1]


def _inline(program: str, rest: list[str]) -> bool:
    """Code written on the command line beyond an interpreter's -c: deno eval, sqlite3's dot-commands (.shell,
    .system) and -cmd, a sed script that runs a command or writes a file, npx -c."""
    if program == "deno":
        return rest[:1] == ["eval"] or any(arg.startswith("--eval") for arg in rest)
    if program == "sqlite3":
        return any(re.match(r"\.[A-Za-z]", arg) or arg.lstrip("-") in ("cmd", "init") for arg in rest)
    if program == "sed":
        scripts = _sed_scripts(rest)
        return scripts is None or any(_sed_runs(script) for script in scripts)
    if program == "npx":
        return any(arg in ("-c", "--call") or arg.startswith("--call=") for arg in rest)
    return False


def _prefix(words: list[str]) -> tuple[list[str] | None, str]:
    """The words a rule for this command holds (Decision 5: "the command's first words"), or None and why there is
    no rule: code on the command line, an option before the subcommand, a runner with nothing after it."""
    program, rest = _name(words[0]), words[1:]
    if _inline(program, rest):
        return None, WHY_INLINE
    if _INTERPRETER.fullmatch(program) and rest:
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


def _long(args: list[str], *options: str) -> bool:
    """Whether an argument is one of these long options, or a short form of one (git takes --forc for --force)."""
    for arg in args:
        name = arg.split("=", 1)[0]
        if name.startswith("--") and len(name) > 2 and any(option.startswith(name) for option in options):
            return True
    return False


def _destroys(program: str, words: list[str]) -> str:
    """Why this use of an everyday program deletes files or throws work away, or "": find -delete, -exec, -execdir,
    -ok or -okdir; rsync --delete or --remove-source-files; git clean, restore, reset --hard, checkout -- / . /
    --force, push --force (or +branch, --mirror, --delete), branch -D, rm -f or -r, switch --force or
    --discard-changes, stash drop or clear, reflog expire, gc --prune, update-ref -d, worktree remove (fresh review F2,
    and the security review of auto-approve)."""
    rest = words[1:]
    if program == "find":
        return WHY_DISCARDS if FIND_DELETES & set(rest) else WHY_LAUNCHER if FIND_RUNS & set(rest) else ""
    if program == "rsync":
        return WHY_DISCARDS if any(arg.startswith(("--del", "--remove")) for arg in rest) else ""
    if program != "git" or not rest:
        return ""
    sub, args = rest[0], rest[1:]
    short = "".join(arg[1:] for arg in args if arg.startswith("-") and not arg.startswith("--"))  # -fd: f and d
    force = "--force" in args or "f" in short or _long(args, "--force")
    if sub in GIT_DISCARDS or (sub == "reset" and "--hard" in args) \
            or (sub == "checkout" and ("--" in args or "." in args or force)) \
            or (sub == "push" and (force or "d" in short or any(arg.startswith(GIT_FORCE) or arg.startswith("+")
                                                                for arg in args))) \
            or (sub == "branch" and ("D" in short or (force and ("--delete" in args or "d" in short)))) \
            or (sub == "rm" and (force or "r" in short or _long(args, "--recursive"))) \
            or (sub == "switch" and (force or _long(args, "--discard-changes"))) \
            or (sub == "stash" and args[:1] in (["drop"], ["clear"])) \
            or (sub == "reflog" and args[:1] in (["expire"], ["delete"])) \
            or (sub == "gc" and _long(args, "--prune")) \
            or (sub == "update-ref" and ("d" in short or _long(args, "--delete"))) \
            or (sub == "worktree" and args[:1] == ["remove"]):
        return WHY_DISCARDS
    return ""


_GIT_CONFIG_READS = ("--get", "--get-all", "--get-regexp", "--get-urlmatch", "--get-color", "--get-colorbool",
                     "--list")
_GIT_CONFIG_WRITES = ("--add", "--unset", "--unset-all", "--replace-all", "--rename-section", "--remove-section",
                      "--edit")


def _git_config_writes(args: list[str]) -> bool:
    """Whether `git config …` may change a setting: a write option or subcommand (set, unset, edit…), or a name with a
    value. Reading one (--get, --list, a name alone) doesn't."""
    if _long(args, *_GIT_CONFIG_WRITES) or "-e" in args \
            or args[:1] in (["set"], ["unset"], ["edit"], ["rename-section"], ["remove-section"]):
        return True
    if args[:1] in (["get"], ["list"]) or "-l" in args or _long(args, *_GIT_CONFIG_READS):
        return False
    return len([arg for arg in args if not arg.startswith("-")]) != 1


def _bash(data: dict, folder, moved: bool) -> tuple[str, str]:
    if data.get("dangerouslyDisableSandbox") is True:
        return "ask_always", WHY_SANDBOX
    words = words_of(data.get("command"))
    if words is None:
        return "ask_always", WHY_NOT_PLAIN
    program = _name(words[0])
    # A file's name without a slash: bash runs the folder's file, else the first one on the PATH (the review's C1):
    # only one that is there, while the shell is still in the folder
    script = _shell_script(words) and ("/" in words[1] or (not moved and os.path.isfile(Path(folder) / words[1])))
    if program in LAUNCHERS and not script:
        return "ask_always", WHY_LAUNCHER
    if program in RISKY or program.startswith("mkfs"):
        return "ask_always", WHY_RISKY
    why = _destroys(program, words)
    if why:
        return "ask_always", why
    named = words if _own_program(words[0]) else words[1:]  # the folder's own program: its path counts too
    if any(_outside(word, folder) for word in named):
        return "ask_always", WHY_OUTSIDE
    guarded = _guard(folder)
    if any(guarded(target) for word in named for target in _targets(word)) \
            or (program == "git" and words[1:2] == ["config"] and _git_config_writes(words[2:])):
        return "ask_always", WHY_GUARDED  # C1: what Git, Claude Code or an editor runs or loads later
    if not moved and _harmless(program, words, folder):
        return "allow", ""
    if script:
        return "ask", WHY_LAUNCHER  # no rule covers what a script does (no Always); Auto-approve may run it
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


def _full(path) -> bool:
    return isinstance(path, str) and os.path.isabs(os.path.expanduser(path))


def _reads(tool: str, data: dict, folder, moved: bool = False) -> tuple[str, str]:
    """A read, a listing or a search inside the folder is allowed (Decision 3). Once the shell may have left the
    folder (`moved`), a search without a full path, or a relative one, searches wherever the shell is now: it asks."""
    if tool == "Read":
        targets = [data.get("file_path")]
        if moved and isinstance(targets[0], str) and not _full(targets[0]):
            return "ask_always", WHY_MOVED
    else:
        where = data.get("path")
        if moved and not _full(where):
            return "ask_always", WHY_MOVED
        targets = [where if where is not None else str(folder)]
        pattern = data.get("pattern") if tool == "Glob" else data.get("glob")
        if isinstance(pattern, str) and pattern:
            if _CLIMB.search(pattern) or pattern.startswith("~"):
                return "ask_always", WHY_READ
            if pattern.startswith(("/", "\\")) or _DRIVE.match(pattern):
                targets.append(_glob_root(pattern))
    return ("allow", "") if all(inside(target, folder) for target in targets) else ("ask_always", WHY_READ)


GUARDED_FOLDERS = (".git", ".claude", ".husky", ".vscode", ".idea")  # and everything in them, anywhere in the folder
GUARDED_FILES = (".mcp.json", ".pre-commit-config.yaml")  # at the folder's top
_HOOKS_PATH = re.compile(r"^\s*hookspath\s*=\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)


def _hooks_folder(folder) -> str | None:
    """The folder the repository's core.hooksPath names (its hooks run on commit, checkout…), read from .git/config
    without running git, as a real path; None without one."""
    git = Path(folder) / ".git"
    if git.is_symlink() or not git.is_dir():
        return None
    try:
        match = _HOOKS_PATH.search((git / "config").read_text(encoding="utf-8", errors="replace")[:200_000])
    except OSError:
        return None
    value = match.group(1).strip().strip('"') if match else ""
    if not value:
        return None
    path = Path(os.path.expanduser(value))
    return _real(path if path.is_absolute() else Path(folder) / path)


def _guard(folder):
    """A test of whether a path is a file of Git's, Claude Code's or an editor's own in the folder (.git, .claude,
    .husky, .vscode, .idea, .mcp.json, .pre-commit-config.yaml, the hooks folder): what they run or load later, so an
    edit there could turn "edit files" into "run programs" (plan decision 7; the security review, C1)."""
    root, hooks = _real(folder), _hooks_folder(folder)

    def guarded(path) -> bool:
        if not isinstance(path, str) or not path or "\x00" in path:
            return False
        target = Path(os.path.expanduser(path))
        target = target if target.is_absolute() else Path(folder) / target
        real = _real(target)
        try:
            relative = os.path.relpath(real, root)
        except ValueError:  # another drive: outside, which is asked for already
            return False
        # .GIT is .git where case is ignored, and Windows drops a name's trailing dots and spaces: .git. is .git (M1)
        parts = [part.rstrip(". ").casefold() for part in Path(relative).parts]
        if any(part in GUARDED_FOLDERS for part in parts):
            return True
        if Path(real).name.rstrip(". ").casefold() in GUARDED_FILES and _same(str(Path(real).parent), root):
            return True
        return hooks is not None and (_same(real, hooks) or _under(real, hooks))

    return guarded


def _guarded(path: str, folder) -> bool:
    return _guard(folder)(path)


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
        return _reads(tool, data, folder, moved)
    if tool in EDITS:
        path = data.get("file_path")
        if not inside(path, folder):
            return "ask_always", WHY_EDIT
        return ("ask_always", WHY_GUARDED) if _guarded(path, folder) else ("ask", "")
    if tool == NETWORK:
        return "ask_always", WHY_NETWORK
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
        program = _name(words[0])
        if program in LAUNCHERS or program in RISKY or program.startswith("mkfs") or _destroys(program, words):
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


SHELL_MOVERS = frozenset({"cd", "pushd", "popd", "source", "eval", "exec", "builtin", "command"})
_MOVES_ANY = re.compile(r"(?:^|[\s;&|(`])(?:cd|pushd|popd|source|eval|exec|builtin|command)(?=$|[\s;&|)])"
                        r"|(?:^|[;&|(`])\s*\.\s")


def moves_shell(command) -> bool:
    """Whether a command may leave the shell in another folder: one plain command whose program is cd, pushd or popd,
    or runs words in this shell (source, eval, exec, builtin, command); any other command that names one of them, or
    sources a file (. file). Read from the words: "cd" in a commit message moves nothing."""
    words = words_of(command)
    if words is not None:
        return _name(words[0]) in SHELL_MOVERS
    return isinstance(command, str) and bool(_MOVES_ANY.search(command))


# ---- Auto-approve in its folder (the user's choice, 2026-10-07): a switch per task ----------------------------------
# After the security review: it runs only what classify asks about (one plain command, inside the folder, nothing
# asked every time) AND what AUTO_BASH lists; a gap costs a card, never a silent run. Commands run without a card where
# Claude Code's sandbox holds them (a Mac), and on Windows, where nothing does (the user's choice, 2026-10-08: "same list
# as Mac"), all but the uses that reach a site by themselves (AUTO_FETCHES). On Linux only edits and new files do.

AUTO_TOOLS = frozenset({"Bash", "Edit", "Write"})  # what it may run without a card
_ANY = object()  # any use classify lets through (its paths are inside the folder already)
_SCRIPT = object()  # a script file in the folder, first, with no option before it: python x.py, node x.js
_PLACE = object()  # one folder in the folder: cd src
_RUN = frozenset({"run", "test", "build", "lint"})  # a package's own scripts, never install, exec, dlx or publish

# The one table of ordinary uses (C2): a program as the agent typed it (a bare name on the PATH, never ./bin/ls), and
# what of it may run: any use, a script, a folder, or only these first words.
AUTO_BASH: dict[str, object] = {
    # reading and listing
    **dict.fromkeys(("ls", "cat", "head", "tail", "wc", "grep", "rg", "tree", "file", "stat", "du", "which", "echo",
                     "printf", "pwd", "date", "diff", "cmp", "sort", "uniq", "cut", "tr", "jq", "find"), _ANY),
    # making files and folders (Edit and Write's own reach: inside, never Git's or Claude Code's files)
    **dict.fromkeys(("mkdir", "touch", "cp", "mv"), _ANY),
    # the project's own checks and builds
    **dict.fromkeys(("make", "pytest", "tsc", "eslint", "prettier", "ruff", "black", "mypy", "jest", "vitest"), _ANY),
    "git": frozenset({"status", "diff", "log", "show", "add", "commit", "branch", "checkout", "switch", "stash", "tag",
                      "init", "rev-parse", "blame", "grep", "ls-files"}),  # each with AUTO_GIT's limits
    **dict.fromkeys(("npm", "pnpm", "yarn", "bun"), _RUN),
    "cargo": frozenset({"build", "test", "check", "fmt", "clippy", "run"}),
    "go": frozenset({"build", "test", "vet", "fmt", "run"}),
    "swift": frozenset({"build", "test"}), "dotnet": frozenset({"build", "test"}),
    "mvn": frozenset({"test", "build"}), "gradle": frozenset({"test", "build"}),
    "uv": frozenset({"run"}),  # and what it runs is in this table too
    **dict.fromkeys(("python", "python3", "node"), _SCRIPT),
    "cd": _PLACE,  # only into a folder inside: cd alone goes home, cd - goes back
}
# Options that make an ordinary use something else: it deletes, runs a program it names, or writes where it shouldn't.
# A long option is refused abbreviated too (git takes --outp for --output); a one-letter one anywhere in a cluster.
AUTO_REFUSED: dict[str, tuple[str, ...]] = {
    "find": ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fls"),
    "rg": ("--pre",), "sort": ("--compress-program",), "pytest": ("--basetemp",), "make": ("--eval", "-E"),
    "go": ("-exec", "-toolexec", "-vettool"), "cargo": ("--config", "-Z"), "mypy": ("--install-types",),
    "date": ("-s", "--set"),  # GNU date (Git Bash's) sets the computer's clock
    **dict.fromkeys(("npm", "pnpm", "yarn", "bun"), ("--script-shell", "--shell", "-c", "--call")),
    "git": (*sorted(GIT_UNSAFE), "-O"),
}
AUTO_GIT: dict[str, tuple[str, ...]] = {  # git's everyday uses, and what turns each into something else
    "branch": ("-d", "-D", "-f", "-m", "-M", "-C", "--delete", "--force", "--move", "--edit-description"),
    "tag": ("-d", "-f", "--delete", "--force"),
    "init": ("--template", "--separate-git-dir"),  # a template folder fills .git/hooks
}
GIT_STASH = (None, "push", "list", "show")  # git stash alone pushes
# Programs that download what a build or a run lacks (crates, modules, packages; Bun installs on import; the Gradle
# and Maven wrappers fetch the tool itself; npx and its kin fetch the package they run). On a Mac the sandbox asks
# for each site they reach; on Windows nothing would, so there they keep their card.
AUTO_FETCHES = frozenset({"cargo", "go", "dotnet", "mvn", "gradle", "swift", "uv", "bun", "gradlew", "mvnw", "npx",
                          "pnpx", "bunx", "pipx"})


def _refused(word: str, options: tuple[str, ...]) -> bool:
    """Whether one argument is one of these options: a long one (with a value, abbreviated, or with one dash or two),
    or a one-letter one anywhere in a cluster (-kE)."""
    if not word.startswith("-") or word in ("-", "--"):
        return False
    stem = word.split("=", 1)[0].lstrip("-")
    for option in options:
        name = option.lstrip("-")
        if len(name) == 1:
            if not word.startswith("--") and name in word[1:]:
                return True
        elif stem.startswith(name) or (len(stem) > 1 and name.startswith(stem)):
            return True
    return False


def ordinary(words: list[str]) -> bool:
    """Whether one plain command is an ordinary use in AUTO_BASH (C2), or runs a script of the folder's own: bash or sh
    with the file first, or the file as the program (the ruling of 2026-10-08). classify, which asked, has checked its
    paths are inside the folder and none is Git's or Claude Code's. The folder's copy of a program known here (pip,
    python3.12, git, gradlew) is judged as that program, so an install still asks."""
    program, rest = words[0], words[1:]
    if program in SHELLS:
        return _shell_script(words)
    if _own_program(program):
        name = _name(program)
        known = name in AUTO_BASH or name in SUBCOMMANDS or name in AUTO_FETCHES or _INTERPRETER.fullmatch(name)
        return ordinary([name, *rest]) if known else True
    use = AUTO_BASH.get(program)
    if use is None or any(_refused(arg, AUTO_REFUSED.get(program, ())) for arg in rest):
        return False
    if use is _ANY:
        return True
    if use is _SCRIPT:
        return bool(rest) and not rest[0].startswith("-")
    if use is _PLACE:
        return len(rest) == 1 and not rest[0].startswith("-")
    if not rest or rest[0] not in use:
        return False
    if program == "uv":
        # not bash or sh: what they run by name, classify checked for the command's own first word only (C1)
        return len(rest) > 1 and rest[1] not in ("uv", *SHELLS) and ordinary(rest[1:])
    if program != "git":
        return True
    sub, args = rest[0], rest[1:]
    if sub in ("checkout", "switch"):  # only a new branch: checkout -b name [start], switch -c name [start]
        return args[:1] == ["-b" if sub == "checkout" else "-c"] and len(args) in (2, 3) \
            and not any(arg.startswith("-") for arg in args[1:])
    if sub == "stash":
        return (args[0] if args else None) in GIT_STASH
    return not any(_refused(arg, AUTO_GIT.get(sub, ())) for arg in args)


def auto_commands() -> bool:
    """Whether Auto-approve in its folder may run commands on this computer: where Claude Code's sandbox holds them in
    the folder and away from sites (R1: a Mac), and on Windows, without a sandbox (the user's choice, 2026-10-08).
    Elsewhere it runs edits and new files only (the review, I3)."""
    return (sandbox_on() and SANDBOX_NETWORK) or sys.platform == "win32"


def auto_approves(tool: str, data, decision: str, sandbox: bool = False, away: bool = False) -> bool:
    """Whether Auto-approve in its folder runs this request without a card: an "ask" (never "ask_always") of Edit or
    Write, so an edit or a new file inside the task's folder; and an "ask" of Bash that AUTO_BASH lists, where the
    sandbox holds commands (`sandbox`), or on Windows unless it downloads what it lacks (AUTO_FETCHES), and in both
    only while the shell hasn't left the folder since Claude Code started (`away`). Everything else keeps its card:
    what is asked every time, Web Search and Web Fetch, a sandboxed command's reach for a site, the user's own tools,
    and every command AUTO_BASH doesn't list."""
    if decision != "ask" or tool not in AUTO_TOOLS:
        return False
    if tool != "Bash":
        return True
    held = sandbox and SANDBOX_NETWORK  # a Mac: the sandbox asks for each site a command reaches
    if away or not (held or sys.platform == "win32"):
        return False
    words = words_of(data.get("command") if isinstance(data, dict) else None)
    return words is not None and ordinary(words) and (held or _name(words[0]) not in AUTO_FETCHES)


# ---- the card: what a request will do, as plain text (Decision 2), and each action's badge (Decision 10) -------------

LINES_SHOWN = 300  # lines of a diff or of a new file a card shows
LINE_LIMIT = 300  # characters of one of them
TEXT_LIMIT = 4000  # characters of a command, a path, an address or a query
DIFF_LIMIT = 200_000  # characters of each side an edit is compared on; past it, each side is listed (Review Focus 5)
MATCH_LIMIT = 4_000_000  # lines × lines past which two sides are listed rather than compared
BINARY_PROBE = 8192  # characters looked at for a NUL: a binary file shows its size only
_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f؜​-‏‪-‮⁦-⁩﻿]")
TITLES = {"Bash": "run a command", "Edit": "edit a file", "Write": "write a file",
          "Read": "read a file outside its folder", "Glob": "list files outside its folder",
          "Grep": "search files outside its folder", "WebFetch": "fetch a page", "WebSearch": "search the web",
          NETWORK: "let a command reach a site"}
SANDBOXED = "Runs in Claude Code's sandbox: it can't write outside this folder."
SANDBOXED_OFFLINE = ("Runs in Claude Code's sandbox: it can't write outside this folder, or reach a site unless you "
                     "allow it.")
BADGES = {"Bash": "Bash", "Edit": "Edit", "Write": "Write", "Read": "Read", "Glob": "Read", "Grep": "Read",
          "WebSearch": "Web Search", "WebFetch": "Web Fetch", "Agent": "Sub-agent", "Task": "Sub-agent",
          "TodoWrite": "To-do list", NETWORK: "Bash"}
OWN = "mcp__ai-browser__"  # the browser's tools
SKILL_TOOLS = frozenset({"load_skill", "find_skills", "read_skill_file", "shell"})  # skills, in the sealed Docker box
SUMMARIZED = frozenset({"Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebFetch", "WebSearch"}) | SUBAGENTS
SUMMARY_LIMIT = 120
TODO_LIMIT = 50
STATUSES = ("pending", "in_progress", "completed")


def plain(text) -> str:
    """Text as a card shows it: tabs and new lines kept, a carriage return made visible (␍), and every other control
    character, zero-width character and direction mark replaced (�), so nothing can hide or reorder what a line says."""
    return _CONTROL.sub("�", str(text).replace("\r", "␍"))


def _clip(value, limit: int = TEXT_LIMIT) -> str:
    text = plain(value) if isinstance(value, str) else ""
    return text if len(text) <= limit else text[:limit - 1] + "…"


_PADDING = re.compile(r"[ \t]{4,}")  # a run of blanks long enough to push what follows out of sight


def _blanks(match) -> str:
    run = match.group(0)
    kind = "spaces" if set(run) == {" "} else "tabs" if set(run) == {"\t"} else "spaces and tabs"
    return f"⟨{len(run)} {kind}⟩"


def _said(value, limit: int = TEXT_LIMIT) -> str:
    """A card's text: plain, each run of 4 or more spaces or tabs shown as a marker (⟨12 spaces⟩), and when it is too
    long, clipped with how much was cut. So padding can't push the part the user approves out of sight (fresh review
    F3)."""
    text = _PADDING.sub(_blanks, plain(value)) if isinstance(value, str) else ""
    if len(text) <= limit:
        return text
    room = limit - len(f"… ({len(text)} more characters not shown)")
    return f"{text[:room]}… ({len(text) - room} more characters not shown)"


def _line(value, limit: int) -> str:
    """One line: plain, its whitespace squeezed, clipped."""
    return _clip(" ".join(plain(value).split()) if isinstance(value, str) else "", limit)


def _binary(text: str) -> bool:
    return "\x00" in text[:BINARY_PROBE]


def diff_rows(old: str, new: str) -> list[list[str]]:
    """An edit as lines: [" ", line] around a change, ["-", line] removed, ["+", line] added, and ["…", ""] between
    two changes far apart. Two sides too long to compare are listed whole instead: removed, then added."""
    a, b = old[:DIFF_LIMIT].splitlines(), new[:DIFF_LIMIT].splitlines()
    if len(old) > DIFF_LIMIT or len(new) > DIFF_LIMIT or len(a) * len(b) > MATCH_LIMIT:
        return [["-", line] for line in a] + [["+", line] for line in b]
    rows: list[list[str]] = []
    for group in difflib.SequenceMatcher(None, a, b, autojunk=False).get_grouped_opcodes(2):
        if rows:
            rows.append(["…", ""])
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                rows += [[" ", line] for line in a[i1:i2]]
            if tag in ("replace", "delete"):
                rows += [["-", line] for line in a[i1:i2]]
            if tag in ("replace", "insert"):
                rows += [["+", line] for line in b[j1:j2]]
    return rows


def _lines(shown: dict, old: str | None, new: str) -> None:
    """An edit's diff (old is a string) or a new file's lines (old is None), clipped, and the size in bytes."""
    shown["size"] = len(new.encode("utf-8", "replace")) + (len(old.encode("utf-8", "replace")) if old else 0)
    if _binary(new) or (old is not None and _binary(old)):
        shown["binary"] = True
        return
    rows = diff_rows(old, new) if old is not None else [["+", line] for line in new[:DIFF_LIMIT].splitlines()]
    shown["lines"] = [[sign, _clip(text, LINE_LIMIT)] for sign, text in rows[:LINES_SHOWN]]
    shown["hidden"] = len(rows) - len(shown["lines"])


def card(tool: str, data, folder, moved: bool = False, sandbox: bool = False) -> dict:
    """What a card shows for one request, as plain text (Decision 2): the command and its folder, a clipped diff or
    the new file, the path, the site or the query; whether Always allow is offered, and if not, why. `sandbox`: the
    command will run in Claude Code's sandbox (R1)."""
    data = data if isinstance(data, dict) else {}
    decision, why = _decide(tool, data, folder, moved)
    shown = {"tool": tool, "badge": badge(tool), "title": TITLES.get(tool, "use a tool"), "text": "",
             "folder": _clip(str(folder)), "site": "", "lines": [], "hidden": 0, "size": None, "binary": False,
             "why": why, "always": decision == "ask" and rule_for(tool, data) is not None, "sandbox": ""}
    if tool == "Bash":
        shown["text"] = _said(data.get("command"))
        if data.get("dangerouslyDisableSandbox") is True:
            shown["title"] = "run a command outside the sandbox"
        elif sandbox:
            shown["sandbox"] = SANDBOXED_OFFLINE if SANDBOX_NETWORK else SANDBOXED
    elif tool in EDITS:
        shown["text"] = _said(data.get("file_path"))
        new = data.get("new_string" if tool == "Edit" else "content")
        old = (data.get("old_string") if isinstance(data.get("old_string"), str) else "") if tool == "Edit" else None
        _lines(shown, old, new if isinstance(new, str) else "")
    elif tool in READS:
        where = data.get("file_path") if tool == "Read" else data.get("path", str(folder))
        where = where if isinstance(where, str) else ""
        pattern = data.get("pattern") if tool != "Read" and isinstance(data.get("pattern"), str) else ""
        shown["text"] = _said(f"{pattern} in {where}" if pattern else where)
    elif tool == "WebFetch":
        shown["text"], shown["site"] = _said(data.get("url")), _host(data.get("url"))
    elif tool == "WebSearch":
        shown["text"] = _said(data.get("query"))
    elif tool == NETWORK:
        host = data.get("host")
        shown["text"] = _said(host)
        shown["site"] = host.lower() if isinstance(host, str) and re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host) else ""
    else:
        shown["text"] = _said(json.dumps(data, ensure_ascii=False))
    return shown


def badge(name) -> str:
    """The badge of an action line (Decision 10): Claude Code's own tools by name, the browser's tools "Browser
    Agent" (their skill tools "Skill"), and the user's own MCP tools "Tool"."""
    name = str(name)
    if name in BADGES:
        return BADGES[name]
    if name.startswith(OWN):
        return "Skill" if name[len(OWN):] in SKILL_TOOLS else "Browser Agent"
    return "Tool"


WEB_CHOICES = ("web", "brave", "none")  # the new look's Web ▾: Web + Brave (the default), Brave only, No web
WEB_TOOLS = ("WebSearch", "WebFetch")
BROWSER_TOOLS = ("open", "observe", "act", "screenshot", "tabs", "page_log", "extract", "js", "sandbox_start",
                 "sandbox_stop", "sandbox_status",
                 "shell")  # what "No web" blocks: the page tools, and the shell (it runs in Docker, with the internet)
# Not blocked by it: the skill tools (load_skill, find_skills, read_skill_file) and read_file and write_file.


def web_tools(choice) -> tuple[tuple[str, ...], list[str]]:
    """(Claude Code's --tools, more --disallowedTools) for a task's Web ▾: "brave" drops WebSearch and WebFetch (and
    blocks them too, a backstop: the bridge then hands over no site's rule), "none" also blocks the browser's page tools
    and its shell (a Docker shell with the internet: curl would be a way to the web). Its skill tools, read_file and
    write_file stay. Anything else is the default, "web"."""
    choice = choice if choice in WEB_CHOICES else "web"
    if choice == "web":
        return TOOLS, []
    tools = tuple(tool for tool in TOOLS if tool not in WEB_TOOLS)
    return tools, [*WEB_TOOLS, *([f"{OWN}{name}" for name in BROWSER_TOOLS] if choice == "none" else [])]


def summary(tool: str, data) -> str:
    """One line for the action feed: the command, the path, the pattern, the address, the query or the sub-agent's
    task."""
    data = data if isinstance(data, dict) else {}
    if tool in SUBAGENTS:
        return subagent_task(data)
    key = {"Bash": "command", "Read": "file_path", "Edit": "file_path", "Write": "file_path", "Glob": "pattern",
           "Grep": "pattern", "WebFetch": "url", "WebSearch": "query"}.get(tool)
    return _line(data.get(key), SUMMARY_LIMIT) if key else ""


def subagent_task(data) -> str:
    """A sub-agent's task as its card and the drawer name it: its description, else its type, else its prompt's
    start."""
    data = data if isinstance(data, dict) else {}
    for key in ("description", "subagent_type", "prompt"):
        task = _line(data.get(key), 60)
        if task:
            return task
    return "a sub-agent"


def todos(data) -> list[dict]:
    """TodoWrite's list ({"todos": [{content, status, activeForm}]}) as the drawer shows it: at most TODO_LIMIT
    items, each line plain and clipped, an unknown status read as pending (Decision 9)."""
    items = data.get("todos") if isinstance(data, dict) else None
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("content"), str):
            continue
        status = item.get("status") if item.get("status") in STATUSES else "pending"
        active = item.get("activeForm") if isinstance(item.get("activeForm"), str) else item["content"]
        out.append({"content": _line(item["content"], 200), "status": status, "active": _line(active, 200)})
        if len(out) == TODO_LIMIT:
            break
    return out


# ---- the user's rules and trusted folders, and the folders no task may use (Decisions 5 to 7) ------------------------

FILE = "permissions.json"
_RULE = re.compile(r"Bash\([A-Za-z0-9_./][^\x00-\x1f()]{0,499}:\*\)|Edit|WebSearch"
                   r"|WebFetch\(domain:[a-z0-9.-]{1,253}\)")  # the rules AI Browser keeps; never a wildcard
TRUSTED_SOURCES = "local,project"  # Decision 7: its CLAUDE.md, its .claude agents and its settings load
NOT_A_PATH = "Give the folder's full path"
GONE = "That folder isn't there: it was deleted, renamed or unplugged"
NOT_A_FOLDER = "That's a file, not a folder"
WHOLE_DISK = "That's the whole disk: pick a project folder"
WHOLE_HOME = "That's your whole home folder: pick a project folder in it"
IT_IS = "That folder is {what}: pick a project folder"
IT_HOLDS = "That folder holds {what}: pick a project folder"
CLAUDE_FOLDER = "Claude Code's own folder, with your logins"
SYSTEM_FOLDER = "a system folder"
SYSTEM_INSIDE = ("/System", "/Library", "/bin", "/sbin", "/usr", "/etc", "/private/etc", "/dev", "/Applications",
                 "/cores")  # refused, and everything in them
SYSTEM_EXACT = ("/Users", "/Volumes", "/private", "/var", "/tmp", "/opt", "/Network", "/home")  # these alone
WINDOWS_SYSTEM = ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData")


def rule_label(rule: str) -> str:
    """A rule in Settings → Permissions' words."""
    if rule == "Edit":
        return "Edit and write files in this folder"
    if rule == "WebSearch":
        return "Search the web"
    if rule.startswith("Bash(") and rule.endswith(":*)"):
        return f"Run commands that start with: {rule[5:-3]}"
    if rule.startswith("WebFetch(domain:") and rule.endswith(")"):
        return f"Fetch pages from {rule[16:-1]}"
    return rule


def _valid(entry: dict) -> list[str]:
    rules = entry.get("rules")
    return [rule for rule in rules if isinstance(rule, str) and _RULE.fullmatch(rule)] if isinstance(rules, list) \
        else []


class Rules:
    """The user's answers per folder (its real path), in <home>/permissions.json (mode 0600):
    {"folders": {"<real path>": {"trusted": true | false, "rules": ["Bash(npm test:*)", …], "used": <seconds>}}}.
    A missing or damaged file reads as no folders and never raises; a write keeps every folder and key it doesn't
    change. A folder that was deleted, renamed or unplugged keeps its entry until the user removes it (Review Focus
    4)."""

    def __init__(self, home):
        self.path = Path(home) / FILE

    def _whole(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _folders(self) -> dict[str, dict]:
        folders = self._whole().get("folders")
        if not isinstance(folders, dict):
            return {}
        return {path: entry for path, entry in folders.items() if isinstance(path, str) and isinstance(entry, dict)}

    def _change(self, folder, change) -> None:
        """One folder's entry changed by `change(entry)` and written back; `change` returning False forgets it."""
        whole, folders, key = self._whole(), self._folders(), real_path(folder)
        entry = dict(folders.get(key) or {})
        if change(entry) is False:
            folders.pop(key, None)
        else:
            folders[key] = entry
        whole["folders"] = folders
        write_atomic(self.path, (json.dumps(whole, indent=1, ensure_ascii=False) + "\n").encode("utf-8"), 0o600)

    def _entry(self, folder) -> dict:
        return self._folders().get(real_path(folder)) or {}

    def allowed(self, folder) -> list[str]:
        return _valid(self._entry(folder))

    def add(self, folder, rule) -> None:
        if not isinstance(rule, str) or not _RULE.fullmatch(rule):
            raise ValueError(f"Not a rule AI Browser keeps: {rule!r}")

        def change(entry):
            rules = _valid(entry)
            entry["rules"] = rules if rule in rules else [*rules, rule]

        self._change(folder, change)

    def remove(self, folder, rule) -> None:
        self._change(folder, lambda entry: entry.update(rules=[kept for kept in _valid(entry) if kept != rule]))

    def trusted(self, folder) -> bool | None:
        value = self._entry(folder).get("trusted")
        return value if isinstance(value, bool) else None

    def trust(self, folder) -> None:
        self._change(folder, lambda entry: entry.update(trusted=True))

    def untrust(self, folder) -> None:
        self._change(folder, lambda entry: entry.update(trusted=False))

    def note_used(self, folder) -> None:
        self._change(folder, lambda entry: entry.update(used=time.time()))

    def forget(self, folder) -> None:
        self._change(folder, lambda entry: False)

    def folders(self) -> list[dict]:
        """Every folder the user answered for, newest first: for Settings → Permissions and the picker's recents."""
        rows = []
        for path, entry in self._folders().items():
            trusted, used = entry.get("trusted"), entry.get("used")
            rows.append({"path": path, "name": Path(path).name or path,
                         "trusted": trusted if isinstance(trusted, bool) else None, "missing": not os.path.isdir(path),
                         "used": used if isinstance(used, (int, float)) and not isinstance(used, bool) else 0,
                         "rules": [{"rule": rule, "label": rule_label(rule)} for rule in _valid(entry)]})
        return sorted(rows, key=lambda row: row["used"], reverse=True)

    def claude_rules(self, folder) -> list[str]:
        """The rules handed to Claude Code as --allowedTools: a site's only (plan decision 1)."""
        return [rule for rule in self.allowed(folder) if rule.startswith("WebFetch(domain:")]


def _protected(home, claude_dirs: Iterable) -> tuple[list[tuple[str, str]], list[str]]:
    """(folders refused with everything in them, and what each is), and the system's folders refused alone."""
    user = user_home()
    inside_rows = [(user / "Library", "your Library folder, where apps keep their data"),
                   (user / ".claude", CLAUDE_FOLDER), (Path(home), "AI Browser's own folder")]
    inside_rows += [(Path(folder), CLAUDE_FOLDER) for folder in claude_dirs if folder]
    exact: list[str] = []
    if os.name == "nt":
        inside_rows += [(Path(os.environ[name]), SYSTEM_FOLDER) for name in WINDOWS_SYSTEM if os.environ.get(name)]
        inside_rows += [(user / "AppData", "your AppData folder, where apps keep their data")]
    else:
        inside_rows += [(Path(folder), SYSTEM_FOLDER) for folder in SYSTEM_INSIDE]
        exact = [_real(folder) for folder in SYSTEM_EXACT]
    return [(_real(path), what) for path, what in inside_rows], exact


def check_folder(path, *, home, claude_dirs: Iterable = ()) -> str | None:
    """Why `path` can't be a task's folder (Decision 6), or None. `home` is AI Browser's own; `claude_dirs` are Claude
    Code's folders (the environment's CLAUDE_CONFIG_DIR and each account's). Compared after realpath, so a symlink to
    a refused folder is refused too; a folder that holds a refused one is refused as well."""
    if not isinstance(path, str) or not path.strip() or len(path) > 4096 or "\x00" in path:
        return NOT_A_PATH
    given = Path(os.path.expanduser(path.strip()))
    if not given.is_absolute():
        return NOT_A_PATH
    if not given.exists():
        return GONE
    if not given.is_dir():
        return NOT_A_FOLDER
    real = _real(given)  # compared as text and by identity, so a case variant is the folder it names (F1)
    if _same(real, _real(Path(real).anchor or os.sep)):
        return WHOLE_DISK
    if _same(real, _real(user_home())):
        return WHOLE_HOME
    rows, exact = _protected(home, claude_dirs)
    if any(_same(real, folder) for folder in exact):
        return IT_IS.format(what=SYSTEM_FOLDER)
    for folder, what in rows:
        if _same(real, folder) or _under(real, folder):
            return IT_IS.format(what=what)
        if _under(folder, real):
            return IT_HOLDS.format(what=what)
    return None


def setting_sources(trusted: bool) -> str:
    """--setting-sources for the task's folder (Decision 7, plan decision 2)."""
    return TRUSTED_SOURCES if trusted else UNTRUSTED_SOURCES


def sandbox_on() -> bool:
    """Whether commands run in Claude Code's sandbox: where Task 1's probe saw it hold (R1), on macOS only."""
    return SANDBOX and sys.platform == "darwin"


def claude_settings(sandbox: bool) -> dict:
    """The agent's --settings: every command, read and edit asked of the app (R3, plan decision 3), and the Bash
    sandbox where it holds (R1). A sandboxed command is still asked (plan decision 9)."""
    settings: dict = {}
    if ASK_ALL:
        settings["permissions"] = {"ask": list(ASKED)}
    if sandbox:
        settings["sandbox"] = {"enabled": True, "autoAllowBashIfSandboxed": False, "allowUnsandboxedCommands": True}
    return settings
