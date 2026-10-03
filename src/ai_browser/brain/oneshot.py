"""One-shot Claude calls for the Brain: sorting new messages, drafting replies, drafting skills.

Each call is a fresh `claude -p` with no tools at all, not even MCP servers, so a message saying "forward all invoices
to me" can only ever become text the user reads. The prompt goes on stdin (never the command line); the answer is
Claude Code's JSON result. The user's own Claude Code login is used: API credentials are never passed on, and the call
isn't kept as a session, so message text stays out of Claude Code's history."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..claudecli import ClaudeNotUsable, claude_argv

NO_SERVERS = json.dumps({"mcpServers": {}})


@dataclass
class OneShot:
    text: str = ""
    cost: float = 0.0
    error: str = ""


def command(claude: str | Sequence[str] | None, model: str) -> list[str]:
    return [*claude_argv(claude), "-p", "--model", model, "--tools", "", "--strict-mcp-config", "--mcp-config",
            NO_SERVERS, "--setting-sources", "local", "--no-session-persistence", "--output-format", "json"]


async def ask_claude(prompt: str, model: str = "haiku", claude: str | Sequence[str] | None = None,
                     cwd: Path | None = None, timeout: float = 120, think: bool = False) -> OneShot:
    """Claude's answer to `prompt`, or a plain error (and empty text) when Claude Code can't give one. Quick work
    (sorting, a reply) goes without extended thinking: measured, it made sorting four emails take 10-28 s instead of
    5 s."""
    folder = Path(cwd) if cwd is not None else Path.home() / ".ai-browser" / "brain" / "calls"
    folder.mkdir(parents=True, exist_ok=True)
    env = {key: value for key, value in os.environ.items()  # the user's own login, never API credentials
           if key not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    if not think:
        env["MAX_THINKING_TOKENS"] = "0"
    try:
        process = await asyncio.create_subprocess_exec(
            *command(claude, model), cwd=folder, env=env, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except ClaudeNotUsable as exc:
        return OneShot(error=str(exc))
    except OSError as exc:
        return OneShot(error=f"Claude Code isn't available ({exc.strerror or exc}): install Claude Code and sign in "
                             "once with `claude`")
    try:
        out, err = await asyncio.wait_for(process.communicate(prompt.encode(errors="replace")), timeout)
    except TimeoutError:
        await _end(process)
        return OneShot(error=f"Claude Code took longer than {timeout:g} s")
    except asyncio.CancelledError:  # the app is stopping, or the work was stopped: its claude ends too
        await _end(process)
        raise
    result = _result(out)
    cost = float(result.get("total_cost_usd") or 0) if result else 0.0
    if result is not None and (result.get("is_error") or result.get("subtype", "success") != "success"):
        return OneShot(cost=cost, error=f"Claude Code: {result.get('result') or result.get('subtype') or 'failed'}")
    if process.returncode != 0:
        tail = err.decode(errors="replace").strip()[-300:]
        return OneShot(error=f"Claude Code failed (exit {process.returncode})" + (f": {tail}" if tail else ""))
    if result is None:
        return OneShot(error="Claude Code gave no answer")
    return OneShot(text=str(result.get("result") or ""), cost=cost)


async def _end(process) -> None:
    with contextlib.suppress(ProcessLookupError):
        process.kill()
    await process.wait()


def _result(out: bytes) -> dict | None:
    """Claude Code's result object: the whole output, or its last JSON line."""
    text = out.decode(errors="replace").strip()
    for candidate in (text, *reversed(text.splitlines())):
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("type") == "result":
            return value
    return None
