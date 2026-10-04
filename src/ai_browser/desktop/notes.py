"""What AI Browser's own app says in a notification: only what needs the user, in fixed words. Never a message's
text, a page's text, a tool's input or a sender's name. A bot check names its site, a plain host name from AI
Browser's own check report. The Brain's notes are counted."""

from __future__ import annotations

import re

SITE = re.compile(r"[a-z0-9.-]{1,253}")  # the server's CHECK_SITE
AGENT = re.compile(r"a[0-9]{1,9}")


def note_for(message: dict) -> dict | None:
    """{"kind", "agent", "title", "body"} for an event that needs the user (a bot check, a tool request, the Brain's
    new notes); None for anything else."""
    kind = message.get("type")
    agent = message.get("agent")
    agent = agent if isinstance(agent, str) and AGENT.fullmatch(agent) else ""
    if kind == "check_request":
        site = message.get("site")
        where = f" on {site}" if isinstance(site, str) and SITE.fullmatch(site) else ""
        return {"kind": "check", "agent": agent, "title": f"A bot check{where}",
                "body": "An agent waits for you to solve it."}
    if kind == "permission_request":
        return {"kind": "permission", "agent": agent, "title": "An agent is waiting for you",
                "body": "It asks to use a tool. Answer in AI Home."}
    if kind == "notify":
        count = message.get("count")
        count = count if isinstance(count, int) and not isinstance(count, bool) and 0 < count < 1000 else 1
        title = "The Brain has a new note" if count == 1 else f"The Brain has {count} new notes"
        return {"kind": "brain", "agent": "", "title": title, "body": "Open AI Home to see what needs you."}
    return None
