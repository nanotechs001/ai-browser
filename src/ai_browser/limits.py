"""Usage limits, as Claude Code reports them in stream-json (AI accounts Decision 7). Nothing documents them, so they
are read defensively.

Two signs count:
- a failed result whose text is a usage-limit text: "usage limit reached", "reached your weekly usage limit", or
  "limit reached|<seconds since 1970>" (older versions);
- a rate_limit_event whose status is "rejected". Of it, only status, resetsAt and rateLimitType are read (in its
  rate_limit_info, or in the event itself), and only when they are well-typed. Besides them, one more key is read, and
  only if the probe named it: USAGE_KEY, how much of the limit is used (the Usage card's percentage)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

TEXTS = ("usage limit reached", "reached your weekly usage limit")
_TIMED = re.compile(r"limit reached\|(\d{1,20})")
_KIND = re.compile(r"[A-Za-z0-9_-]{1,40}")
EARLIEST, LATEST = 1_500_000_000, 4_000_000_000  # a reset time in seconds since 1970; anything else is no time


@dataclass(frozen=True)
class Limit:
    resets_at: float | None = None  # when the limit resets, if Claude Code said so
    kind: str = ""  # rateLimitType: "five_hour", "seven_day"…, if said


def _seconds(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value) if EARLIEST <= value <= LATEST else None


def from_text(text) -> Limit | None:
    """A usage limit, if this failed result's (or stderr's) text says so."""
    if not isinstance(text, str):
        return None
    lower = text.lower()
    timed = _TIMED.search(lower)
    if timed is not None:
        return Limit(_seconds(int(timed.group(1))))
    return Limit() if any(phrase in lower for phrase in TEXTS) else None


def from_event(event) -> Limit | None:
    """A rate_limit_event that refused the turn (status "rejected"); None for any other event or status."""
    if not isinstance(event, dict) or event.get("type") != "rate_limit_event":
        return None
    info = event.get("rate_limit_info")
    info = info if isinstance(info, dict) else event
    if info.get("status") != "rejected":
        return None
    kind = info.get("rateLimitType")
    return Limit(_seconds(info.get("resetsAt")), kind if isinstance(kind, str) and _KIND.fullmatch(kind) else "")


# Task 1's probe (docs/superpowers/plans/2026-10-05-new-look.md) names the rate_limit_info key that says how much of a
# limit is used, if Claude Code sends one. Until it does, None: no percentage is ever read, and the Usage card says
# "Within limits" or "At its limit until …" (the new look, Decision 7).
USAGE_KEY: str | None = None
USAGE_SCALE = 100.0  # the key's value times this is a percentage: 100 for a fraction (0 to 1), 1 for a percentage


@dataclass(frozen=True)
class Usage:
    used: float  # a percentage, 0 to 100
    resets_at: float | None = None
    kind: str = ""


def usage_from_event(event) -> Usage | None:
    """How much of a limit is used, from a rate_limit_event: only under USAGE_KEY, and only a finite number that makes
    a percentage from 0 to 100. Never guessed from any other key."""
    if USAGE_KEY is None or not isinstance(event, dict) or event.get("type") != "rate_limit_event":
        return None
    info = event.get("rate_limit_info")
    info = info if isinstance(info, dict) else event
    value = info.get(USAGE_KEY)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    used = value * USAGE_SCALE
    if not 0 <= used <= 100:
        return None
    kind = info.get("rateLimitType")
    return Usage(round(used, 1), _seconds(info.get("resetsAt")),
                 kind if isinstance(kind, str) and _KIND.fullmatch(kind) else "")
