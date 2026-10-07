"""Task 1 of docs/superpowers/plans/2026-10-05-agent-powers.md: a hand probe of Claude Code's own tools in `-p`
stream-json mode, run by the main session with the user. Everything happens in a throwaway folder, <probe>:
- <probe>/config is a throwaway Claude Code folder (CLAUDE_CONFIG_DIR), signed in once by hand. Never ~/.claude.
- Each question works in a folder of its own under <probe>. The probe answers every tool request itself: it allows
  only commands that stay in <probe>, and denies the rest.

Before the first run (once): CLAUDE_CONFIG_DIR=<probe>/config claude   then /login in it, then /exit.
Run: uv run python tests/probe_powers.py <probe>
It prints one JSON object last: what each question saw. Not a test: pytest doesn't collect it.

The questions (the plan's rulings R1 to R4):
- q0: the sub-agent tool's name: the init event's tools with --tools Agent, then with --tools Task (R4);
- q1: Claude Code's Bash sandbox, headless: a write inside the folder, one outside it, a network call; and how a
  command asks to run outside the sandbox (R1);
- q2: what --setting-sources "", "local" and "local,project" load of a folder's own hooks and CLAUDE.md (R2);
- q3: which uses reach the app, with no rule and then with a permissions.ask rule: reads inside, a read through a
  symlink that leaves the folder, ls, cat ../outside, a command with &&, and an edit (R3);
- q4: a to-do list, a sub-agent's request (does its tool use come before it?), and the shell's folder after a cd."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from ai_browser.accounts import clean_env
from ai_browser.claudecli import claude_argv

MODEL = "haiku"
WAIT = 300  # seconds one question may take
BUILT_IN = "Bash,Read,Edit,Write,Glob,Grep,WebSearch,WebFetch,TodoWrite"
ASK_ALL = {"permissions": {"ask": ["Bash", "Read", "Glob", "Grep", "Edit", "Write"]}}
SANDBOX = {"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": False, "allowUnsandboxedCommands": True}}
URL = re.compile(r"https?://\S+")
ABSOLUTE = re.compile(r"(?<![\w.-])/[^\s'\";|&)]*")
NO = "The probe said no: go on with the next step."
CONFIG = ""  # the throwaway login's folder, as the user typed it (main sets it)


def refuse(text: str) -> None:
    print(f"probe_powers: {text}", file=sys.stderr)
    sys.exit(2)


def throwaway(argument: str) -> Path:
    """<probe>: a folder that exists and holds config/ (signed in by hand), and is none of the user's own folders."""
    probe = Path(argument).expanduser().resolve()
    home = Path.home().resolve()
    guarded = [home / ".claude", home / ".ai-browser"]
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        guarded.append(Path(os.environ["CLAUDE_CONFIG_DIR"]).expanduser().resolve())
    if not probe.is_dir() or probe == home or probe == Path(probe.anchor) \
            or any(probe == folder or folder in probe.parents or probe in folder.parents for folder in guarded):
        refuse(f"{probe} isn't a throwaway folder: make one, such as /tmp/aib-powers-probe")
    if not (probe / "config").is_dir():
        refuse(f"sign in first: CLAUDE_CONFIG_DIR={probe / 'config'} claude   (then /login, then /exit)")
    return probe


def confined(command, probe: Path) -> bool:
    """A command that names no path outside <probe> (web addresses aside), no ~ and no .., and deletes nothing."""
    if not isinstance(command, str) or any(bad in command for bad in ("~", "..", "sudo", "rm ", "$(", "`")):
        return False
    root = str(probe)
    return all(path == "/dev/null" or path == root or path.startswith(root + "/")
               for path in ABSOLUTE.findall(URL.sub("", command)))


def deny_all(tool: str, data: dict) -> bool:
    return False


def clip(data) -> str:
    return json.dumps(data, ensure_ascii=False)[:300]


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(block.get("text", "")) for block in content if isinstance(block, dict))
    return ""


async def read_events(process, seen: dict, allow) -> None:
    """Claude Code's events until its result: what it used, what it asked, and the answers the probe gave."""
    while line := await process.stdout.readline():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind, parent = event.get("type"), event.get("parent_tool_use_id")
        if kind == "system" and event.get("subtype") == "init":
            seen["init_tools"] = event.get("tools")
        elif kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    data = block.get("input") if isinstance(block.get("input"), dict) else {}
                    seen["uses"].append({"id": block.get("id"), "name": block.get("name"), "parent": parent,
                                         "keys": sorted(data), "input": clip(data)})
                    seen["order"].append(["use", block.get("id")])
        elif kind == "user":
            content = event.get("message", {}).get("content", [])
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    seen["results"].append({"id": block.get("tool_use_id"), "parent": parent,
                                            "error": bool(block.get("is_error")),
                                            "text": text_of(block.get("content"))[:400]})
        elif kind == "control_request" and (event.get("request") or {}).get("subtype") == "can_use_tool":
            request = event["request"]
            data = request.get("input") if isinstance(request.get("input"), dict) else {}
            yes = bool(allow(str(request.get("tool_name", "")), data))
            seen["asks"].append({"tool": request.get("tool_name"), "keys": sorted(request),
                                 "tool_use_id": request.get("tool_use_id"), "input": clip(data), "allowed": yes})
            seen["order"].append(["ask", request.get("tool_use_id")])
            body = {"behavior": "allow", "updatedInput": data} if yes else {"behavior": "deny", "message": NO}
            reply = {"type": "control_response", "response": {"subtype": "success",
                                                              "request_id": event.get("request_id"),
                                                              "response": body}}
            process.stdin.write((json.dumps(reply) + "\n").encode())
            await process.stdin.drain()
        elif kind == "result":
            seen["result"] = {"subtype": event.get("subtype"), "is_error": event.get("is_error"),
                              "text": str(event.get("result") or "")[:600]}
            return


async def ask_claude(probe: Path, cwd: Path, prompt: str, sources: str, settings: dict | None, allow,
                     tools: str = BUILT_IN, subagent: str = "") -> dict:
    """One `claude -p` run in `cwd`, on <probe>/config: everything it showed, asked and was answered."""
    argv = [*claude_argv(None), "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--model", MODEL, "--tools", ",".join(name for name in (tools, subagent) if name), "--strict-mcp-config",
            "--mcp-config", str(probe / "mcp.json"),
            "--allowedTools", ",".join(name for name in ("TodoWrite", subagent) if name),
            "--permission-prompt-tool", "stdio", "--setting-sources", sources, "--no-session-persistence"]
    if settings is not None:
        path = probe / f"settings-{cwd.name}.json"
        path.write_text(json.dumps(settings), encoding="utf-8")
        argv += ["--settings", str(path)]
    env = clean_env()
    # The throwaway login, never ~/.claude, spelled exactly as the user signed in with it: Claude Code keys a login
    # to the folder's path as written (/tmp/… and its real /private/tmp/… are two logins on a Mac).
    env["CLAUDE_CONFIG_DIR"] = CONFIG or str(probe / "config")
    seen = {"sources": sources, "init_tools": None, "uses": [], "asks": [], "order": [], "results": [],
            "result": None, "stderr": ""}
    process = await asyncio.create_subprocess_exec(*argv, cwd=cwd, env=env, stdin=asyncio.subprocess.PIPE,
                                                   stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                   limit=32 * 1024 * 1024)
    stderr = asyncio.ensure_future(process.stderr.read())
    message = {"type": "user", "message": {"role": "user", "content": prompt}}
    process.stdin.write((json.dumps(message) + "\n").encode())
    await process.stdin.drain()
    try:
        await asyncio.wait_for(read_events(process, seen, allow), WAIT)
    except TimeoutError:
        seen["result"] = {"timeout": WAIT}
    finally:
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), 15)
        except TimeoutError:
            process.kill()
            await process.wait()
        seen["stderr"] = (await stderr).decode(errors="replace")[-1500:]
    return seen


def hooks(marker: Path) -> dict:
    """A folder's own settings whose hooks leave a mark when they run."""
    command = {"type": "command", "command": f"touch {marker}"}
    return {"hooks": {"SessionStart": [{"hooks": [command]}], "UserPromptSubmit": [{"hooks": [command]}]}}


def prepare(probe: Path) -> None:
    for name in ("names", "sandbox", "trust", "asks", "agents", "outside"):
        (probe / name).mkdir(exist_ok=True)
    (probe / "outside" / "secret.txt").write_text("probe secret\n", encoding="utf-8")
    (probe / "asks" / "notes.txt").write_text("old notes\n", encoding="utf-8")
    link = probe / "asks" / "link"
    if not link.is_symlink():
        link.symlink_to(probe / "outside", target_is_directory=True)
    (probe / "mcp.json").write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    trust = probe / "trust"
    (trust / ".claude").mkdir(exist_ok=True)
    (trust / "CLAUDE.md").write_text("Begin every reply with the word PINEAPPLE.\n", encoding="utf-8")
    (trust / ".claude" / "settings.local.json").write_text(json.dumps(hooks(trust / "marker-local")), encoding="utf-8")
    (trust / ".claude" / "settings.json").write_text(json.dumps(hooks(trust / "marker-project")), encoding="utf-8")


async def q0_subagent_name(probe: Path) -> dict:
    out = {}
    for name in ("Agent", "Task"):
        seen = await ask_claude(probe, probe / "names", "Reply with the one word: ok", "", None, deny_all, tools="",
                                subagent=name)
        out[name] = {"listed": name in (seen["init_tools"] or []), "init_tools": seen["init_tools"],
                     "result": seen["result"], "stderr": seen["stderr"][-300:]}
    return out


async def q1_sandbox(probe: Path) -> dict:
    work = probe / "sandbox"
    prompt = ("Run these three shell commands with the Bash tool, one call each, exactly as written, then report what "
              f"each printed or why it failed:\n1. touch {work}/inside.txt\n"
              f"2. touch {probe}/outside/from-sandbox.txt\n"
              "3. curl -sS -m 10 -o /dev/null -w '%{http_code}' https://example.com")

    def allow(tool, data):
        return tool == "Bash" and not data.get("dangerouslyDisableSandbox") and confined(data.get("command"), probe)

    seen = await ask_claude(probe, work, prompt, "", SANDBOX, allow)
    return {"inside_written": (work / "inside.txt").exists(),
            "outside_written": (probe / "outside" / "from-sandbox.txt").exists(),
            "asks": seen["asks"], "results": seen["results"], "result": seen["result"], "stderr": seen["stderr"]}


async def q2_sources(probe: Path) -> dict:
    work = probe / "trust"
    out = {}
    for sources in ("", "local", "local,project"):
        for marker in ("marker-local", "marker-project"):
            (work / marker).unlink(missing_ok=True)  # the probe's own marks, in its own folder
        seen = await ask_claude(probe, work, "Reply with one word: ready.", sources, None, deny_all)
        out[sources or "(empty)"] = {
            "local_hook_ran": (work / "marker-local").exists(), "project_hook_ran": (work / "marker-project").exists(),
            "claude_md_loaded": "PINEAPPLE" in str((seen["result"] or {}).get("text", "")).upper(),
            "result": seen["result"], "stderr": seen["stderr"][-500:]}
    return out


async def q3_asks(probe: Path) -> dict:
    work = probe / "asks"
    prompt = ("Do each of these with your tools, one at a time, and report what happened to each:\n"
              f"1. Read the file {work}/notes.txt\n2. Read the file {work}/link/secret.txt\n"
              "3. Run the shell command: ls\n4. Run the shell command: cat ../outside/secret.txt\n"
              "5. Run the shell command: echo one && echo two\n"
              f"6. Edit the file {work}/notes.txt: replace the word old with new")
    out = {}
    for name, settings in (("no_rule", None), ("ask_rule", ASK_ALL)):
        seen = await ask_claude(probe, work, prompt, "", settings, deny_all)
        out[name] = {"asked": [[ask["tool"], ask["input"]] for ask in seen["asks"]],
                     "used": [[use["name"], use["input"]] for use in seen["uses"]], "results": seen["results"],
                     "result": seen["result"]}
    return out


async def q4_agents(probe: Path, name: str) -> dict:
    work = probe / "agents"
    prompt = ("1. Make a to-do list of two steps with your to-do tool: Look around, Report.\n"
              "2. Start one sub-agent with your sub-agent tool, with the description Research, and ask it to run the "
              "shell command ls and report what it printed.\n"
              f"3. Run the shell command cd {probe}, and then, in a separate call, the shell command pwd. Report "
              "both outputs.")

    def allow(tool, data):
        return tool == "Bash" and confined(data.get("command"), probe)

    seen = await ask_claude(probe, work, prompt, "", ASK_ALL, allow, subagent=name)
    return {"subagent_tool": name, "init_tools": seen["init_tools"], "uses": seen["uses"], "asks": seen["asks"],
            "order": seen["order"], "results": seen["results"], "result": seen["result"]}


async def main(argument: str) -> None:
    global CONFIG
    probe = throwaway(argument)
    CONFIG = str(Path(argument).expanduser() / "config")  # as the user typed it when signing in (see ask_claude)
    prepare(probe)
    report = {"q0_subagent_name": await q0_subagent_name(probe)}
    name = "Agent" if report["q0_subagent_name"]["Agent"]["listed"] else "Task"
    report["q1_sandbox"] = await q1_sandbox(probe)
    report["q2_sources"] = await q2_sources(probe)
    report["q3_asks"] = await q3_asks(probe)
    report["q4_agents"] = await q4_agents(probe, name)
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        refuse("usage: uv run python tests/probe_powers.py <a throwaway folder>")
    asyncio.run(main(sys.argv[1]))
