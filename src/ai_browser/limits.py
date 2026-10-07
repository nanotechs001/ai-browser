"""Usage limits, as Claude Code reports them in stream-json (AI accounts Decision 7). Nothing documents them, so they
are read defensively.

Two signs of a limit hit count:
- a failed result whose text is a usage-limit text: "usage limit reached", "reached your weekly usage limit", or
  "limit reached|<seconds since 1970>" (older versions);
- a rate_limit_event whose status is "rejected". Of it, only status, resetsAt and rateLimitType are read (in its
  rate_limit_info, or in the event itself), and only when they are well-typed.

And how much of each limit is used (the Usage card, the new look): every request's rate_limit_event carries
rate_limit_info.unifiedWindows (the probe of 2026-10-07, Claude Code 2.1.292), e.g.
{"five_hour": {"utilization": 0, "resetsAt": 1791372600}, "seven_day": {"utilization": 0.14, "resetsAt": 1791810000}}:
five_hour is the current session's limit, seven_day the week's. Only a known window's utilization, a fraction from 0 to
1, makes a percentage, and nothing else is ever read as one."""

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


def seconds(value) -> float | None:
    """A time in seconds since 1970, as a float, if it is a sane one (EARLIEST to LATEST); else None."""
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
        return Limit(seconds(int(timed.group(1))))
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
    return Limit(seconds(info.get("resetsAt")), kind if isinstance(kind, str) and _KIND.fullmatch(kind) else "")


KNOWN_WINDOWS = ("five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet")  # the limits Claude Code names
SHOWN_WINDOWS = ("five_hour", "seven_day")  # the Usage card's: the current session, and the week


def percent(fraction) -> float | None:
    """A utilization (a fraction from 0 to 1) as a percentage, to a tenth; None for anything else (a bool, a string,
    NaN, infinity, below 0 or above 1)."""
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not math.isfinite(fraction) \
            or not 0 <= fraction <= 1:
        return None
    return round(fraction * 100, 1)


def windows_from_event(event) -> dict[str, dict]:
    """How much of each limit is used, from a rate_limit_event's rate_limit_info.unifiedWindows:
    {"five_hour": {"used": <percent>, "resets_at": <seconds since 1970> | None}, …}, a known window only with a
    utilization that makes a percentage. {} for anything else: no number is ever made up (Review Focus 3)."""
    if not isinstance(event, dict) or event.get("type") != "rate_limit_event":
        return {}
    info = event.get("rate_limit_info")
    windows = info.get("unifiedWindows") if isinstance(info, dict) else None
    if not isinstance(windows, dict):
        return {}
    found = {}
    for name in KNOWN_WINDOWS:
        window = windows.get(name)
        used = percent(window.get("utilization")) if isinstance(window, dict) else None
        if used is not None:
            found[name] = {"used": used, "resets_at": seconds(window.get("resetsAt"))}
    return found
