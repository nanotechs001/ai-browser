"""The Brain's hand-offs (the brain-delegation spec, 5): a task the Brain gives an agent that is already working,
shown first on a card with the exact instruction; and a NEW agent it suggests, which only ever starts on the user's
Start.

Whether a hand-off counts down is decided once, when it is made (counts_down), from where it came from: its `source`,
which the code that makes it sets, never Claude's answer, a message or a page.
- "you" (the user's own words: Ask AI, the floating chat) counts down COUNTDOWN seconds and then sends, unless the
  user cancels: only while Settings → Brain's switch is on, one of AI Browser's pages is open to show the card, and
  the agent is still working;
- "agent" (an agent's own result), "gmail", "slack", "asana" and "pages" (a watched part) always wait for Send:
  the instruction may carry someone else's words (agents read web pages).
This run's hand-offs are kept in memory, never saved (agents are numbered from 1 again after a restart): at most KEPT
in all, the oldest that is done going first. An open one is never dropped, so more stay while more than KEPT are
open."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

COUNTDOWN = 15  # seconds a hand-off from the user's own words waits for Cancel
TRUSTED = frozenset({"you"})  # may count down: the user's own words only (2026-10-08)
UNTRUSTED = frozenset({"gmail", "slack", "asana", "pages"})  # always wait for Send
SOURCES = TRUSTED | UNTRUSTED | {"agent"}  # "agent": an agent's result, which waits for Send too (2026-10-08)
WORKING = frozenset({"working", "waiting", "needs_you"})  # the agents a hand-off may go to: never a finished one
OPEN = frozenset({"counting", "waiting"})
KEPT = 20  # hand-offs that are done, kept for the Brain's inbox (the newest)
INSTRUCTION_LIMIT = 2000
FROM_BRAIN = "From the Brain:"  # the first words of what the agent is sent: its chat shows "From the Brain: …"
# The card's notes: the app's own words, with only an agent's number and name filled in
SENT_TO = "Sent to agent {number}"
CANCELLED = "Cancelled: nothing was sent"
STOPPED = "Cancelled: you stopped agent {number}"
NOT_WORKING = "Not sent: {label} isn't working any more"
HELD = "Waiting for your Send"
NOT_SENT = "Couldn't send it: try again from the agent's chat"  # a send failed: never the error's own text
NOT_STARTED = "Couldn't start it: try again from Build a Mission"
TAGS = ("\U000e0000", "\U000e007f")  # the tag block: words no card shows (Cf, and its unassigned rest)


def clean(instruction) -> str:
    """An instruction as its card shows it and its agent gets it, so the card shows all the agent gets: no format
    character (Cf: direction and zero-width marks, tags that can spell hidden words) and no control character but line
    breaks and tabs."""
    if not isinstance(instruction, str):
        return ""
    return "".join(char for char in instruction if char in "\n\t" or (
        unicodedata.category(char) not in ("Cf", "Cc") and not TAGS[0] <= char <= TAGS[1]))


def row_state(row: dict) -> str:
    """An agent's state as the hand-offs read it: "needs_you" while a card waits for the user, else its own."""
    return "needs_you" if row.get("permission") or row.get("check") else str(row.get("state") or "")


def counts_down(source: str, switch: bool, seen: bool, state: str) -> bool:
    """Whether a hand-off counts down and then sends by itself: only from the user's own words (an agent's result
    waits for Send, as inbox and page text do: the user's choice, 2026-10-08), only while Settings → Brain's switch is
    on and a page can show the card, and only to an agent that is working, waiting in line or needs the user.
    Anything else waits for Send."""
    return source in TRUSTED and switch is True and seen is True and state in WORKING


@dataclass
class Handoff:
    id: str
    kind: str  # "give": to a working agent; "start": a NEW agent, a suggestion the user Starts
    source: str  # what led to it (SOURCES), set by the code that made it
    instruction: str  # exactly what the agent gets after FROM_BRAIN, or the new agent's task
    agent: str = ""  # give: the agent's id, and its number and name as the card names it
    number: int = 0
    name: str = ""
    state: str = "waiting"  # counting | waiting | sending | sent | not_sent | cancelled | started
    ends: float = 0.0  # counting: when it sends, on the Brain's clock
    note: str = ""  # what happened, in the app's own words
    item: str = ""  # the inbox item it came from, if any

    def public(self, now: float) -> dict:
        shown = {key: getattr(self, key) for key in ("id", "kind", "source", "instruction", "agent", "number", "name",
                                                       "state", "note", "item")}
        shown["seconds"] = max(0, round(self.ends - now)) if self.state == "counting" else 0
        return shown
