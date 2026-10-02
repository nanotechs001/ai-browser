"""Parse `act` steps such as `click e5` or `type e4 "About us"`."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

ID_OPS = frozenset({"click", "dblclick", "hover", "type", "append", "select", "check", "uncheck", "drag", "upload"})

_ID = re.compile(r"^e\d+$")
_URL = re.compile(r"^(https?://|about:|file://)", re.IGNORECASE)


@dataclass(frozen=True)
class Step:
    op: str
    target: str | None = None
    target2: str | None = None
    value: str | None = None
    amount: int | None = None
    raw: str = ""


class StepError(ValueError):
    """A step that cannot be parsed; the message says how to fix it."""


def parse_step(text: str) -> Step:
    raw = text.strip()
    if not raw:
        raise StepError("empty step")
    try:
        parts = shlex.split(raw)
    except ValueError as exc:
        raise StepError(f"{raw!r}: {exc} (check the quotes)") from None
    op, args = parts[0].lower(), parts[1:]
    # shlex drops quotes, so look at the raw text to tell `type "e5"` from `type e5`.
    quoted = raw[len(parts[0]):].lstrip()[:1] in {'"', "'"}

    def usage(form: str) -> StepError:
        return StepError(f"{raw!r}: expected `{form}`")

    def element(token: str) -> str:
        if not _ID.match(token):
            raise StepError(f"{raw!r}: expected an element id like e5, got {token!r}")
        return token

    if op in {"click", "dblclick", "hover", "check", "uncheck"}:
        if len(args) != 1:
            raise usage(f"{op} e5")
        return Step(op, target=element(args[0]), raw=raw)
    if op == "type":
        if len(args) == 2:
            return Step(op, target=element(args[0]), value=args[1], raw=raw)
        if len(args) == 1 and quoted:
            return Step(op, value=args[0], raw=raw)
        raise usage('type e4 "text"` or `type "text"')
    if op in {"append", "select"}:
        if len(args) != 2:
            raise usage(f'{op} e4 "text"')
        return Step(op, target=element(args[0]), value=args[1], raw=raw)
    if op == "drag":
        if len(args) != 2:
            raise usage("drag e7 e12")
        return Step(op, target=element(args[0]), target2=element(args[1]), raw=raw)
    if op == "upload":
        if len(args) != 2:
            raise usage("upload e5 file.png")
        return Step(op, target=element(args[0]), value=args[1], raw=raw)
    if op == "key":
        if len(args) != 1:
            raise usage("key Enter")
        return Step(op, value=args[0], raw=raw)
    if op == "scroll":
        return _scroll(args, raw, usage, element)
    if op == "wait":
        if len(args) != 1:
            raise usage('wait 500` or `wait "text"')
        if quoted:
            return Step(op, value=args[0], raw=raw)
        if not args[0].isdigit():
            raise usage('wait 500` or `wait "text"')
        return Step(op, amount=int(args[0]), raw=raw)
    if op == "goto":
        if len(args) != 1 or not _URL.match(args[0]):
            raise usage("goto https://example.com")
        return Step(op, value=args[0], raw=raw)
    if op in {"back", "forward", "reload"}:
        if args:
            raise usage(op)
        return Step(op, raw=raw)
    raise StepError(
        f"{raw!r}: unknown step {op!r}; use click, dblclick, hover, type, append, key, select, "
        "check, uncheck, drag, upload, scroll, wait, goto, back, forward or reload"
    )


def _scroll(args, raw, usage, element) -> Step:
    form = "scroll down|up [px]` or `scroll top|bottom` or `scroll e40"
    if len(args) == 1 and _ID.match(args[0]):
        return Step("scroll", target=element(args[0]), raw=raw)
    if len(args) == 1 and args[0] in {"down", "up", "top", "bottom"}:
        return Step("scroll", value=args[0], raw=raw)
    if len(args) == 2 and args[0] in {"down", "up"} and args[1].isdigit():
        return Step("scroll", value=args[0], amount=int(args[1]), raw=raw)
    raise usage(form)


def parse_steps(items: list[str]) -> list[Step]:
    if not items:
        raise StepError("no steps given")
    steps = []
    for number, item in enumerate(items, 1):
        if not isinstance(item, str):
            raise StepError(f"step {number}: expected text like 'click e5'")
        try:
            steps.append(parse_step(item))
        except StepError as exc:
            raise StepError(f"step {number}: {exc}") from None
    return steps
