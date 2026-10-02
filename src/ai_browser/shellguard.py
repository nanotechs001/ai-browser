"""The shell's seatbelt: before a command runs, refuse the crawl pattern seen in the task logs.

It refuses a browser's user agent given to curl or wget, curl or wget run in parallel (xargs -P, GNU parallel), and
any host on a site the user skipped after a bot check. It reads the command the way the shell splits it, and the
script given to sh -c or bash -c the same way, but it can't catch every script: the instructions are the rule, this is
a seatbelt."""

from __future__ import annotations

import posixpath
import re
import shlex
from collections.abc import Iterable

from .checks import on_site

USER_AGENT = ("the shell doesn't send a browser's user agent (curl -A \"Mozilla/…\"): use curl's own, or open the "
              "page with open")
PARALLEL = ("the shell doesn't fetch in parallel (xargs -P 10 … curl): fetch one URL at a time, or use qa for a whole "
            "site")
SKIPPED = "the shell doesn't reach {site}: the user skipped it after a bot check. Ask the user if you need it."
FETCHERS = frozenset({"curl", "wget"})
_BROWSER = re.compile(r"mozilla/|chrome/|safari/|firefox/|edg/|opr/|googlebot|bingbot", re.IGNORECASE)
_XARGS_LONG_VALUE = frozenset({"--arg-file", "--delimiter", "--max-args", "--max-chars", "--max-procs"})  # or =value
_XARGS_VALUE = frozenset("adEILnsP")  # short options whose value is the rest of the word, or else the next word
_XARGS_OPTIONAL = frozenset("eil")  # short options whose value, if any, is the rest of the word
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
_SCRIPT_DEPTH = 3  # sh -c 'bash -c "…"': scripts inside scripts, this deep
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")
_URL_HOST = re.compile(r"\b[a-z][a-z0-9+.-]*://([^/\s'\"<>?#]+)", re.IGNORECASE)
_HOST_NAME = re.compile(r"(?<![\w.-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})(?![\w-])",
                        re.IGNORECASE)


def _words(command: str) -> list[str]:
    """The shell's words, with |, ;, && and the like as words of their own; plain splitting if the quoting is broken."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return command.split()


def _commands(words: list[str]) -> list[list[str]]:
    """The simple commands: the words between |, ;, &&, ||, &, ( and )."""
    commands, current = [], []
    for word in words:
        if word and set(word) <= set("|&;()<>"):
            if current:
                commands.append(current)
            current = []
        else:
            current.append(word)
    if current:
        commands.append(current)
    return commands


def _name(word: str) -> str:
    return posixpath.basename(word).lower()


def _scripts(command: list[str]) -> list[str]:
    """The scripts a simple command hands to a shell: the word after -c (or -lc, -ec…) of sh, bash and the like,
    wherever the shell is in the command (xargs -P4 sh -c '…')."""
    scripts = []
    for start, word in enumerate(command):
        if _name(word) not in SHELLS:
            continue
        index = start + 1
        while index < len(command) - 1:
            option = command[index]
            if option in ("-o", "+o", "-O", "+O"):  # set and shopt options: their name is the next word
                index += 2
            elif option.startswith("--") or option.startswith("+"):
                index += 1
            elif not option.startswith("-"):
                break  # the shell's own options end at its script file
            elif "c" in option[1:]:
                scripts.append(command[index + 1])
                break
            else:
                index += 1
    return scripts


def _all_commands(command: str, depth: int = 0) -> list[list[str]]:
    """The simple commands of a command line, with those of the scripts it hands to a shell."""
    commands = _commands(_words(command))
    if depth < _SCRIPT_DEPTH:
        for words in list(commands):
            for script in _scripts(words):
                commands += _all_commands(script, depth + 1)
    return commands


def _short(word: str, following: str, letter: str) -> str | None:
    """The value of a short option such as -A: `-A value`, `-sA value` or `-Avalue`."""
    if re.fullmatch(rf"-[a-zA-Z]*{letter}", word):
        return following
    attached = re.fullmatch(rf"-{letter}(.+)", word)
    return attached.group(1) if attached else None


def _agents(command: list[str]) -> list[str]:
    """The user agents one curl or wget command sets, with its option or with a User-Agent header."""
    start = next((index for index, word in enumerate(command) if _name(word) in FETCHERS), None)
    if start is None:
        return []
    curl = _name(command[start]) == "curl"
    words, agents, headers = command[start + 1:], [], []
    for index, word in enumerate(words):
        following = words[index + 1] if index + 1 < len(words) else ""
        if word.startswith("--"):
            option, equals, attached = word.partition("=")
            if option == "--user-agent":
                agents.append(attached if equals else following)
            elif option == "--header":
                headers.append(attached if equals else following)
            continue
        value = _short(word, following, "A" if curl else "U")
        if value is not None:
            agents.append(value)
        elif curl and (header := _short(word, following, "H")) is not None:
            headers.append(header)
    agents += [header.split(":", 1)[1] for header in headers if header.strip().lower().startswith("user-agent:")]
    return agents


def _program(command: list[str]) -> int | None:
    """Where the program is in a simple command (after any VAR=value words)."""
    return next((index for index, word in enumerate(command) if not _ASSIGNMENT.fullmatch(word)), None)


def _parallel(commands: list[list[str]]) -> bool:
    """xargs running more than one process at a time, or GNU parallel."""
    for command in commands:
        start = _program(command)
        if start is None:
            continue
        name = _name(command[start])
        if name == "parallel":
            return True
        if name != "xargs":
            continue
        words, index = command[start + 1:], 0
        while index < len(words):
            word = words[index]
            following = words[index + 1] if index + 1 < len(words) else ""
            if not word.startswith("-") or word == "-":
                break  # xargs's own options end at the command it runs
            procs = None
            if word.startswith("--"):
                option, equals, attached = word.partition("=")
                if option == "--max-procs":
                    procs = attached if equals else following
                index += 1 if equals or option not in _XARGS_LONG_VALUE else 2  # --eof, --replace: =value only
            else:  # a cluster of short options, such as -0P4 or -rP 8: the first one that takes a value ends it
                index += 1
                for at, letter in enumerate(word[1:], 1):
                    if letter in _XARGS_OPTIONAL:
                        break
                    if letter in _XARGS_VALUE:
                        value = word[at + 1:]
                        if not value:
                            value, index = following, index + 1
                        if letter == "P":
                            procs = value
                        break
            if procs is not None and procs.strip() != "1":
                return True
    return False


def _hosts(command: str) -> set[str]:
    """Every word of the command that looks like a URL's host or a host name."""
    hosts = {match.group(1) for match in _URL_HOST.finditer(command)}
    return hosts | {match.group(1) for match in _HOST_NAME.finditer(command)}


def shell_problem(command: str, skipped: Iterable[str] = ()) -> str | None:
    """Why the shell refuses this command, or None."""
    commands = _all_commands(command)
    if any(_BROWSER.search(agent) for words in commands for agent in _agents(words)):
        return USER_AGENT
    fetches = any(_name(word) in FETCHERS for words in commands for word in words)
    if fetches and _parallel(commands):
        return PARALLEL
    hosts = _hosts(command)
    for site in sorted(skipped):
        if any(on_site(host, site) for host in hosts):
            return SKIPPED.format(site=site)
    return None
