"""Task 1 of docs/superpowers/plans/2026-10-05-native-app-b-extension-jobs.md (part b of AI Browser's own app): a
probe in a throwaway Chrome only, never the user's Brave or Chrome, never ~/.ai-browser.

Question 1: can CDP put a later tab into the window of an earlier one? An AI window W1 is opened with
Target.createTarget(newWindow, background) beside the "user's" window W0. Then each way of opening a tab from a tab in
W1 is tried: a middle click and a Ctrl/Cmd click on a link AI Browser puts there (Input.dispatchMouseEvent), and
window.open with a user gesture (Runtime.evaluate). For each: the window the new tab lands in, whether W1 became the
window Chrome used last (a plain Target.createTarget then lands in W1, not W0: in a visible browser that means W1 was
brought forward), the new tab's opener, and whether W0's tab still has the focus.

Question 2 (with --profiles, a visible browser only): how long after Chrome's defaultBrowserContextId changes does
Local State's profile.last_used follow?

Run: uv run python tests/probe_ai_window.py            (headless: placement only; focus can't be seen)
     uv run python tests/probe_ai_window.py --headful  (Chrome windows show for about a minute)
     uv run python tests/probe_ai_window.py --headful --profiles
It prints one JSON object last. Not a test: pytest doesn't collect it."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

from ai_browser.cdp import CDP
from ai_browser.chrome import chrome_binary, find_ws_url, launch

LINK = ("(() => { const a = document.createElement('a'); a.href = %s; a.textContent = 'x'; a.id = 'aib-probe-link';"
        " Object.assign(a.style, {position: 'fixed', left: '0', top: '0', width: '8px', height: '8px',"
        " display: 'block', zIndex: '2147483647'}); document.documentElement.append(a);"
        " return document.elementFromPoint(2, 2) === a; })()")


async def pages(cdp) -> dict:
    return {info["targetId"]: info for info in (await cdp.send("Target.getTargets"))["targetInfos"]
            if info["type"] == "page"}


async def window_of(cdp, target) -> int:
    return (await cdp.send("Browser.getWindowForTarget", {"targetId": target}))["windowId"]


async def evaluate(cdp, target, expression, world=False, gesture=False):
    session = (await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]
    try:
        params = {"expression": expression, "returnByValue": True, "userGesture": gesture}
        if world:
            frame = (await cdp.send("Page.getFrameTree", session_id=session))["frameTree"]["frame"]["id"]
            params["contextId"] = (await cdp.send("Page.createIsolatedWorld", {"frameId": frame,
                                                                               "worldName": "aib-probe"},
                                                  session_id=session))["executionContextId"]
        return (await cdp.send("Runtime.evaluate", params, session_id=session)).get("result", {}).get("value")
    finally:
        await cdp.send("Target.detachFromTarget", {"sessionId": session})


async def click(cdp, target, button, modifiers=0):
    session = (await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]
    try:
        for kind in ("mousePressed", "mouseReleased"):
            await cdp.send("Input.dispatchMouseEvent", {"type": kind, "x": 2, "y": 2, "button": button,
                                                        "clickCount": 1, "modifiers": modifiers}, session_id=session)
    finally:
        await cdp.send("Target.detachFromTarget", {"sessionId": session})


async def new_page(cdp, before, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        fresh = [info for target, info in (await pages(cdp)).items() if target not in before]
        if fresh:
            return fresh[0]
        await asyncio.sleep(0.1)
    return None


async def last_active(cdp, names) -> str:
    """The window a plain Target.createTarget lands in now: the one Chrome used last."""
    target = (await cdp.send("Target.createTarget", {"url": "about:blank", "background": True}))["targetId"]
    window = await window_of(cdp, target)
    await cdp.send("Target.closeTarget", {"targetId": target})
    return names.get(window, str(window))


async def placement(cdp) -> dict:
    user = next(iter(await pages(cdp)))
    await cdp.send("Target.activateTarget", {"targetId": user})
    await asyncio.sleep(0.5)
    w0 = await window_of(cdp, user)
    first = (await cdp.send("Target.createTarget", {"url": "about:blank", "newWindow": True,
                                                    "background": True}))["targetId"]
    w1 = await window_of(cdp, first)
    names = {w0: "W0", w1: "W1"}
    result = {"new_window": w1 != w0, "after_new_window": {"last_active": await last_active(cdp, names),
                                                           "user_focus": await evaluate(cdp, user,
                                                                                        "document.hasFocus()")}}
    mac = sys.platform == "darwin"
    ways = (("middle_click", "middle", 0), ("modifier_click", "left", 4 if mac else 2), ("window_open", None, 0),
            ("middle_click_behind", "middle", 0))  # the last: window.open put a tab in front of the anchor
    for name, button, modifiers in ways:
        await cdp.send("Target.activateTarget", {"targetId": user})  # W0 is the window in use again
        await asyncio.sleep(0.5)
        anchor = first  # the AI window's first tab: in front in W1 for the first way, behind a later tab after
        url = f"about:blank#aib-probe-{name}"
        before = await pages(cdp)
        if button is None:
            await evaluate(cdp, anchor, f"window.open({json.dumps(url)}, '_blank'); true", world=True, gesture=True)
        else:
            on_top = await evaluate(cdp, anchor, LINK % json.dumps(url), world=True)
            await click(cdp, anchor, button, modifiers)
            await evaluate(cdp, anchor, "document.getElementById('aib-probe-link')?.remove(); true", world=True)
            if not on_top:
                result[name] = {"error": "the link wasn't on top"}
                continue
        made = await new_page(cdp, before)
        if made is None:
            result[name] = {"lands": None}
            continue
        result[name] = {"lands": names.get(await window_of(cdp, made["targetId"]), "elsewhere"),
                        "opener": "anchor" if made.get("openerId") == anchor else made.get("openerId") or None,
                        "last_active": await last_active(cdp, names),
                        "user_focus": await evaluate(cdp, user, "document.hasFocus()")}
    return result


def local_state_last_used(folder: Path) -> str | None:
    try:
        return json.loads((folder / "Local State").read_text(encoding="utf-8"))["profile"]["last_used"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


async def profiles(folder: Path, cdp) -> dict:
    """A second profile in the same Chrome (a second launch hands its window over to the running one), then each
    profile in turn brought forward: how many seconds until Local State's profile.last_used names it."""
    import subprocess

    first = {info["browserContextId"] for info in (await pages(cdp)).values()}
    subprocess.Popen([chrome_binary(), f"--user-data-dir={folder}", "--profile-directory=Profile 2",
                      "--no-first-run", "--no-default-browser-check", "about:blank"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    targets: dict[str, str] = {}
    for _ in range(100):
        targets = {info["browserContextId"]: target for target, info in (await pages(cdp)).items()}
        if len(targets) >= 2:
            break
        await asyncio.sleep(0.2)
    second = next((context for context in targets if context not in first), None)
    if second is None or len(first) != 1:
        return {"error": "the second profile didn't open"}
    folders = {next(iter(first)): "Default", second: "Profile 2"}
    lags: list[float | None] = []
    for _ in range(2):
        for context in (next(iter(first)), second):
            await cdp.send("Target.activateTarget", {"targetId": targets[context]})
            began = time.monotonic()
            while time.monotonic() - began < 60:
                if local_state_last_used(folder) == folders[context]:
                    lags.append(round(time.monotonic() - began, 1))
                    break
                await asyncio.sleep(0.25)
            else:
                lags.append(None)  # not within a minute
            await asyncio.sleep(1)
    seen = [lag for lag in lags if lag is not None]
    return {"lags_seconds": lags, "max_lag_seconds": max(seen) if seen else None}


async def main() -> None:
    headful = "--headful" in sys.argv
    folder = Path(tempfile.mkdtemp(prefix="aib-probe-"))
    process = launch(folder, headless=not headful)
    try:
        cdp = await CDP.connect(find_ws_url(folder, timeout=20))
        version = (await cdp.send("Browser.getVersion"))["product"]
        result = {"chrome": version, "headful": headful, "placement": await placement(cdp)}
        if "--profiles" in sys.argv:
            result["profiles"] = await profiles(folder, cdp) if headful else {"error": "needs --headful"}
        await cdp.close()
    finally:
        process.terminate()
        process.wait(timeout=15)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
