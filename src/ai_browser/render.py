"""Turn reader state into the compact page table Claude reads, and diff two tables."""

from __future__ import annotations

import json
import re
from functools import lru_cache

NO_ROWS_HINT = '(no interactive elements in view — scroll, use observe find="…", or take a screenshot)'
DIFF_TEXT_LIMIT = 500
BOX_TAG = "[bot check box: the user ticks it]"  # a reCAPTCHA, hCaptcha or Turnstile box in a form: never the agent's


def _quote(text: str) -> str:
    return json.dumps(" ".join(str(text).split()), ensure_ascii=False)


def _states(row: dict) -> str:
    out = []
    checked = row.get("checked")
    if checked in (True, "true"):
        out.append("checked")
    elif checked == "mixed":
        out.append("mixed")
    expanded = row.get("expanded")
    if expanded in (True, "true"):
        out.append("expanded")
    elif expanded in (False, "false"):
        out.append("collapsed")
    if row.get("selected") in (True, "true"):
        out.append("selected")
    if row.get("disabled"):
        out.append("disabled")
    if row.get("editable"):
        out.append("editable")
    return "".join(f" [{state}]" for state in out)


def render_row(row: dict) -> str:
    line = f"{row['id']:<4} {row['role']:<8} "
    if row.get("frame"):
        line += f"[{row['frame']}] "
    line += _quote(row.get("name") or "")
    if row.get("value") is not None:
        line += f" = {_quote(row['value'])}"
    options = row.get("options")
    if options:
        more = f"|+{row['more']} more" if row.get("more") else ""
        line += " (" + "|".join(str(option) for option in options) + more + ")"
    if row.get("href"):
        line += f" → {row['href']}"
    line += _states(row)
    if row.get("risky"):
        line += " ⚠"
    return line


def _header(state: dict) -> list[str]:
    view = (
        f"view  {state['w']}×{state['h']} · y {int(state['scrollY'])}/{int(state['scrollH'])}"
        f" · {state['above']} above · {state['below']} below"
    )
    frames = state.get("frames") or []
    if frames:
        tags = [
            BOX_TAG if frame.get("box") else
            f"[{frame['label']} (cross-site, not readable)]" if frame.get("cross") else f"[{frame['label']}]"
            for frame in frames
        ]
        view += " · frames: " + " ".join(tags)
    return [f"page  {_quote(state.get('title') or '')}  {state['url']}", view]


def render_page(state: dict, ms: int | None = None) -> str:
    lines = _header(state)
    rows = state.get("rows") or []
    if state.get("find") is not None:
        count = len(rows)
        lines.append(f"find  {_quote(state['find'])} · {count} match{'' if count == 1 else 'es'}")
    lines.extend(render_row(row) for row in rows)
    if state.get("truncated"):
        lines.append(f'… {state["truncated"]} more rows (use observe find="…")')
    if not rows:
        lines.append(NO_ROWS_HINT)
    if state.get("text"):
        lines.append("text:\n" + state["text"])
    if ms is not None:
        lines.append(f"⏱ {ms} ms")
    return "\n".join(lines)


def diff_rows(old_rows: list[dict], new_rows: list[dict]) -> dict[str, list]:
    old = {row["id"]: row for row in old_rows}
    new = {row["id"]: row for row in new_rows}
    return {
        "added": [row for row in new_rows if row["id"] not in old],
        "removed": [row for row in old_rows if row["id"] not in new],
        "changed": [row for row in new_rows if row["id"] in old and old[row["id"]] != row],
    }


def render_diff(diff: dict, state: dict, ms: int | None = None, old_text: str | None = None) -> str:
    lines = _header(state)
    lines.extend("+ " + render_row(row) for row in diff["added"])
    lines.extend("- " + render_row(row) for row in diff["removed"])
    lines.extend("~ " + render_row(row) for row in diff["changed"])
    if not (diff["added"] or diff["removed"] or diff["changed"]):
        lines.append("(no visible change)")
    text = state.get("text") or ""
    if old_text is not None and text and text != old_text:
        lines.append("text:\n" + text[:DIFF_TEXT_LIMIT])
    if ms is not None:
        lines.append(f"⏱ {ms} ms")
    return "\n".join(lines)


@lru_cache(maxsize=8)
def _risky(words: tuple[str, ...]) -> re.Pattern:
    alternatives = [r"[\s\-]+".join(map(re.escape, word.split())) for word in words if word.strip()]
    return re.compile(r"\b(?:" + "|".join(alternatives) + r")\b", re.IGNORECASE)


def risky_regex(words: list[str]) -> re.Pattern:
    """Whole-word, case-insensitive matcher; its .pattern also works as a JS RegExp with flag 'i'."""
    return _risky(tuple(words))


def is_risky(name: str, words: list[str]) -> bool:
    return bool(name) and bool(risky_regex(words).search(name))


def render_check(check, tab_key: str, live_url: str | None = None) -> str:
    """The hand-off when a page is a bot check (`check` is a checks.Check): no elements, no page text, nothing to
    click. The live view is named only in the sandbox, where the user can't see the tab otherwise."""
    front = "The tab is now in front."
    if live_url:
        front += f" The user can solve it in the live view: {live_url}"
    return "\n".join([
        f"⛔ bot check in tab {tab_key} ({check.site}): {check.what}.",
        "It is for the user to solve, never you. Stop and tell the user. Don't reload, retry, wait it out, or reach "
        "the site another way (another tab, browser, profile, tool or the shell).",
        front,
        "When the user says it's done, call observe. If they'd rather skip this site, they close the tab, or ask "
        f"you to (tabs close {tab_key}): the site is then off-limits for the rest of this task.",
    ])
