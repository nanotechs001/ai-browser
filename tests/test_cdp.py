import asyncio

import pytest

from ai_browser.cdp import CDP, CDPError

pytestmark = pytest.mark.docker


@pytest.fixture
async def cdp(sandbox):
    boxes, info = sandbox
    client = await CDP.connect(boxes.ws_url(info))
    yield client
    await client.close()


async def new_session(cdp: CDP) -> tuple[str, str]:
    target = (await cdp.send("Target.createTarget", {"url": "about:blank"}))["targetId"]
    session = (await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]
    return target, session


async def test_browser_version(cdp):
    version = await cdp.send("Browser.getVersion")
    assert "Chrom" in version["product"]


async def test_evaluate_in_a_tab_session(cdp):
    target, session = await new_session(cdp)
    result = await cdp.send("Runtime.evaluate", {"expression": "1+1", "returnByValue": True}, session_id=session)
    assert result["result"]["value"] == 2
    await cdp.send("Target.closeTarget", {"targetId": target})


async def test_unknown_method_raises_cdp_error(cdp):
    with pytest.raises(CDPError) as caught:
        await cdp.send("Nope.method")
    assert caught.value.method == "Nope.method"


async def test_wait_for_receives_session_event(cdp):
    target, session = await new_session(cdp)
    await cdp.send("Page.enable", session_id=session)
    waiter = asyncio.create_task(cdp.wait_for("Page.loadEventFired", session_id=session, timeout=10))
    await cdp.send("Page.navigate", {"url": "data:text/html,<p>hi</p>"}, session_id=session)
    assert "timestamp" in await waiter
    await cdp.send("Target.closeTarget", {"targetId": target})


async def test_on_and_off_handlers(cdp):
    seen = []

    def handler(params, session_id):
        seen.append(params["targetInfo"]["url"])

    cdp.on("Target.targetCreated", handler)
    await cdp.send("Target.setDiscoverTargets", {"discover": True})
    target = (await cdp.send("Target.createTarget", {"url": "about:blank#on"}))["targetId"]
    await asyncio.sleep(0.2)
    cdp.off("Target.targetCreated", handler)
    assert "about:blank#on" in seen
    count = len(seen)
    other = (await cdp.send("Target.createTarget", {"url": "about:blank#off"}))["targetId"]
    await asyncio.sleep(0.2)
    assert len(seen) == count
    for t in (target, other):
        await cdp.send("Target.closeTarget", {"targetId": t})


async def test_wait_for_times_out(cdp):
    with pytest.raises(asyncio.TimeoutError):
        await cdp.wait_for("Page.neverHappens", timeout=0.2)


async def test_close_fails_pending_calls(sandbox):
    boxes, info = sandbox
    client = await CDP.connect(boxes.ws_url(info))
    target, session = await new_session(client)
    pending = asyncio.create_task(client.send(
        "Runtime.evaluate", {"expression": "new Promise(() => {})", "awaitPromise": True}, session_id=session))
    await asyncio.sleep(0.2)
    await client.close()
    with pytest.raises(CDPError, match="connection closed"):
        await pending
    assert client.closed
    cleanup = await CDP.connect(boxes.ws_url(info))
    await cleanup.send("Target.closeTarget", {"targetId": target})
    await cleanup.close()
