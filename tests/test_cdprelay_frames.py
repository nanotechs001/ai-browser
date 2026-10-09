"""The relay and a tab's frames (the frames spec, 3): Target.setAutoAttach on a client's own session, for frames only;
each frame's session is the tab's owner's, with the page's policy; nobody else's. In front of the fake debugging port
(tests/fake_brave.py), which emits the browser's attach events as Chrome does in flatten mode."""

import asyncio

import pytest

from ai_browser.app.cdprelay import allowed
from ai_browser.cdp import CDPError
from fake_brave import FakePort, until
from test_cdprelay import own_tab, rig  # noqa: F401  (rig: a fixture)

FRAMES_ONLY = {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True, "filter": [{"type": "iframe"}]}


async def frame(rig, parent, child, kind="iframe", url="https://builder.example/canvas"):
    """The browser attaches a frame of the tab under `parent` (its session `child`), as auto-attach does."""
    await rig.port.emit("Target.attachedToTarget", {
        "sessionId": child, "waitingForDebugger": False,
        "targetInfo": {"targetId": f"F-{child}", "type": kind, "url": url, "title": "", "attached": True,
                       "canAccessOpener": False, "browserContextId": "C1"}}, parent)


def test_auto_attach_and_letting_go_pass_on_a_session_only():
    for method in ("Target.setAutoAttach", "Target.detachFromTarget"):
        assert allowed(method, "session"), method
    assert not allowed("Target.setAutoAttach", "browser")  # at the browser's level it would attach every tab
    for method in ("Target.createTarget", "Target.attachToTarget", "Target.setDiscoverTargets",
                   "Target.autoAttachRelated", "Target.getTargets", "Target.sendMessageToTarget"):
        assert not allowed(method, "session"), method


async def test_auto_attach_is_for_the_tabs_frames_only(rig):
    await rig.relay.open("start")
    a1, a2 = await rig.client("a1"), await rig.client("a2")
    _, session = await own_tab(a1)
    with pytest.raises(CDPError) as refused:
        await a1.send("Target.setAutoAttach", FRAMES_ONLY)  # never at the browser's level
    assert refused.value.code == -32601
    with pytest.raises(CDPError, match="Session with given id not found"):
        await a2.send("Target.setAutoAttach", FRAMES_ONLY, session_id=session)  # never on another client's tab
    await a1.send("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": False,
                                           "filter": [{}], "extra": 1}, session_id=session)
    await a1.send("Target.setAutoAttach", {"autoAttach": False}, session_id=session)
    sent = [(sid, params) for name, sid, params, _ in rig.port.received if name == "Target.setAutoAttach"]
    # whatever the client asks: frames only, flattened, never paused at their start
    assert sent == [(session, FRAMES_ONLY), (session, {**FRAMES_ONLY, "autoAttach": False})]


async def test_a_frames_session_is_its_tabs_owners_with_the_pages_policy(rig):
    await rig.relay.open("start")
    a1, a2 = await rig.client("a1"), await rig.client("a2")
    _, session = await own_tab(a1)
    seen = {"a1": [], "a2": []}
    for name, cdp in (("a1", a1), ("a2", a2)):
        cdp.on("Target.attachedToTarget", lambda params, sid, name=name: seen[name].append((sid, params["sessionId"])))
        cdp.on("Page.lifecycleEvent", lambda params, sid, name=name: seen[name].append(("event", sid)))
    await frame(rig, session, "K1")
    assert await until(lambda: (session, "K1") in seen["a1"])
    assert await a1.send("Runtime.evaluate", {"expression": "1"}, session_id="K1") == {"result": {"value": "page text"}}
    await rig.port.emit("Page.lifecycleEvent", {"name": "load"}, "K1")
    assert await until(lambda: ("event", "K1") in seen["a1"])
    await frame(rig, "K1", "K2")  # a frame inside the frame: still a1's
    assert await until(lambda: ("K1", "K2") in seen["a1"])
    assert (await a1.send("Runtime.evaluate", {"expression": "2"}, session_id="K2"))["result"]["value"] == "page text"
    before = len(rig.port.received)
    for method, params in (("Network.getCookies", {}), ("Target.setDiscoverTargets", {"discover": True}),
                           ("Target.createTarget", {"url": "about:blank"}), ("Storage.getCookies", {})):
        with pytest.raises(CDPError) as refused:
            await a1.send(method, params, session_id="K1")
        assert refused.value.code == -32601, method
    with pytest.raises(CDPError, match="only web pages"):
        await a1.send("Page.navigate", {"url": "file:///etc/passwd"}, session_id="K1")  # the page's address check
    for child in ("K1", "K2"):
        with pytest.raises(CDPError, match="Session with given id not found"):
            await a2.send("Runtime.evaluate", {"expression": "3"}, session_id=child)
    assert len(rig.port.received) == before  # none of it reached the browser
    await asyncio.sleep(0.2)
    assert seen["a2"] == []


async def test_only_frames_are_handed_on(rig):
    await rig.relay.open("start")
    a1 = await rig.client("a1")
    _, session = await own_tab(a1)
    attached = []
    a1.on("Target.attachedToTarget", lambda params, sid: attached.append(params["sessionId"]))
    await frame(rig, session, "W1", kind="worker")
    await frame(rig, session, "P1", kind="page")
    await frame(rig, session, "K1")
    assert await until(lambda: attached == ["K1"])
    for child in ("W1", "P1"):
        with pytest.raises(CDPError, match="Session with given id not found"):
            await a1.send("Runtime.evaluate", {"expression": "1"}, session_id=child)


async def test_a_frame_is_let_go_of_only_on_its_parents_session(rig):
    await rig.relay.open("start")
    a1, a2 = await rig.client("a1"), await rig.client("a2")
    _, session = await own_tab(a1)
    _, other = await own_tab(a1)
    _, theirs = await own_tab(a2)
    await frame(rig, session, "K1")
    assert await until(lambda: "K1" in rig.relay._sessions)
    for cdp, sid, child in ((a1, other, "K1"), (a1, session, session), (a1, session, "nope"), (a2, theirs, "K1")):
        with pytest.raises(CDPError, match="Session with given id not found"):
            await cdp.send("Target.detachFromTarget", {"sessionId": child}, session_id=sid)
    assert [sid for name, sid, _, _ in rig.port.received if name == "Target.detachFromTarget"] == []
    await a1.send("Target.detachFromTarget", {"sessionId": "K1", "targetId": "F-K1"}, session_id=session)
    assert [(sid, params) for name, sid, params, _ in rig.port.received if name == "Target.detachFromTarget"] == [
        (session, {"sessionId": "K1"})]


async def test_a_frames_session_ends_with_its_frame_or_its_tab(rig):
    await rig.relay.open("start")
    a1 = await rig.client("a1")
    _, session = await own_tab(a1)
    detached = []
    a1.on("Target.detachedFromTarget", lambda params, sid: detached.append(params["sessionId"]))
    await frame(rig, session, "K1")
    await frame(rig, "K1", "K2")
    await frame(rig, session, "K3")
    assert await until(lambda: {"K1", "K2", "K3"} <= set(rig.relay._sessions))
    await rig.port.emit("Target.detachedFromTarget", {"sessionId": "K2", "targetId": "F-K2"}, session)  # not its own
    await asyncio.sleep(0.2)
    assert "K2" in rig.relay._sessions and detached == []
    await rig.port.emit("Target.detachedFromTarget", {"sessionId": "K1", "targetId": "F-K1"}, session)  # removed
    assert await until(lambda: detached == ["K1"])
    for child in ("K1", "K2"):  # with the frames inside it: the browser ends those with it
        with pytest.raises(CDPError, match="Session with given id not found"):
            await a1.send("Runtime.evaluate", {"expression": "1"}, session_id=child)
    await a1.send("Target.detachFromTarget", {"sessionId": session})  # the tab's own session ends
    assert await until(lambda: session in detached)
    with pytest.raises(CDPError, match="Session with given id not found"):
        await a1.send("Runtime.evaluate", {"expression": "1"}, session_id="K3")
    assert not {"K1", "K2", "K3"} & set(rig.relay._sessions) and not {"K1", "K2", "K3"} & a1_sessions(rig)


def a1_sessions(rig) -> set:
    return {sid for client in rig.relay._clients if getattr(client, "identity", "") == "a1" for sid in client.sessions}


async def test_take_back_cuts_the_handed_tabs_frames_too(rig):
    await rig.relay.open("start")
    rig.handed["a1"] = {"U1"}
    a1 = await rig.client("a1")
    session = (await a1.send("Target.attachToTarget", {"targetId": "U1", "flatten": True}))["sessionId"]
    await frame(rig, session, "K1")
    assert await until(lambda: "K1" in rig.relay._sessions)
    rig.port.hold = {"Target.detachFromTarget"}  # the browser is slow to let go
    cutting = asyncio.ensure_future(rig.relay.cut("a1", "U1"))
    assert await until(lambda: {"sessionId": session} in rig.sent("Target.detachFromTarget"))
    before = len(rig.port.received)
    with pytest.raises(CDPError, match="Session with given id not found"):
        await a1.send("Runtime.evaluate", {"expression": "1"}, session_id="K1")  # refused at once
    assert len(rig.port.received) == before
    rig.port.hold = set()
    await rig.port.answer_held()
    await cutting


async def test_a_client_that_left_is_handed_no_frames(rig):
    await rig.relay.open("start")
    a1 = await rig.client("a1")
    _, session = await own_tab(a1)
    await a1.close()
    assert await until(lambda: {"sessionId": session} in rig.sent("Target.detachFromTarget"))
    await frame(rig, session, "K1")  # the browser's note, still on its way as the session ended
    await asyncio.sleep(0.2)
    assert "K1" not in rig.relay._sessions
