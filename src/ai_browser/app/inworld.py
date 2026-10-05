"""Running AI Browser's own page scripts in a tab of the user's Brave, in an isolated world (Page.createIsolatedWorld)
through the relay's one connection: the page's own scripts can't see or change them, and what comes back is plain
JSON (returnByValue). Chromium keeps one world per frame and name, so every call meets the same world for as long as
the page stays (measured in Chrome 154, from a new session too); a new page gets a new world, and the scripts go in
again. Each call attaches, runs and detaches. Which tab may be read is BraveLink's to decide: this module only runs."""

from __future__ import annotations

import contextlib

from ..cdp import CDPError

WORLD = "ai-browser"
SCRIPT_WAIT = 10.0  # seconds for one call


class WorldError(RuntimeError):
    """The script couldn't run there: Brave isn't connected, the tab is gone, the page broke it, or it took too long.
    Its text is plain words."""


async def run(cdp, target: str, expression: str, install: str | None = None, missing: str | None = None,
              timeout: float = SCRIPT_WAIT):
    """`expression`'s value in the tab's isolated world. When it answers `missing`, `install` goes in first, then
    `expression` again."""
    if cdp is None or cdp.closed:
        raise WorldError("Brave isn't connected")
    try:
        session = (await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True},
                                  timeout=timeout))["sessionId"]
    except (CDPError, KeyError, TypeError):
        raise WorldError("that tab is gone") from None
    try:
        context = await _world(cdp, session, timeout)
        value = await _evaluate(cdp, session, context, expression, timeout)
        if missing is not None and install is not None and value == missing:
            await _evaluate(cdp, session, context, install, timeout)
            value = await _evaluate(cdp, session, context, expression, timeout)
        return value
    finally:
        with contextlib.suppress(CDPError):
            await cdp.send("Target.detachFromTarget", {"sessionId": session}, timeout=5)


async def _world(cdp, session: str, timeout: float) -> int:
    try:
        tree = await cdp.send("Page.getFrameTree", session_id=session, timeout=timeout)
        made = await cdp.send("Page.createIsolatedWorld", {"frameId": tree["frameTree"]["frame"]["id"],
                                                           "worldName": WORLD}, session_id=session, timeout=timeout)
        return made["executionContextId"]
    except (CDPError, KeyError, TypeError):
        raise WorldError("that page isn't ready") from None


async def _evaluate(cdp, session: str, context: int, expression: str, timeout: float):
    try:
        answer = await cdp.send("Runtime.evaluate", {"expression": expression, "contextId": context,
                                                     "returnByValue": True, "awaitPromise": True},
                                session_id=session, timeout=timeout)
    except CDPError as exc:
        raise WorldError("the page went away" if "context" in str(exc).lower() else "the page didn't answer") \
            from None
    if "exceptionDetails" in answer:
        raise WorldError("the page script failed")
    return (answer.get("result") or {}).get("value")
