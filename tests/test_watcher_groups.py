"""The AI's tabs in the user's Brave, put in groups by the watcher. A throwaway headless Chrome with the watcher loaded
over the pipe stands in for Brave (the `watcher` fixture of test_watcher.py), next to a real app server."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from test_home import evaluate, until
from test_watcher import watcher  # noqa: F401  (fixture)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
MARKER = "about:blank#aib-0123456789abcdef"


async def group_of(watcher, url):  # noqa: F811
    """[title, color, the group's window, the tab's window] for the tab showing exactly `url`, or None if ungrouped."""
    return await watcher.worker_js(
        f"chrome.tabs.query({{}}).then(tabs => tabs.find(tab => (tab.url || tab.pendingUrl) === {json.dumps(url)}))"
        ".then(tab => tab && tab.groupId !== -1 ? chrome.tabGroups.get(tab.groupId)"
        ".then(group => [group.title, group.color, group.windowId, tab.windowId]) : null)")


@CHROME
async def test_the_watcher_sees_the_marker_and_may_group(watcher):  # noqa: F811
    target = (await watcher.cdp.send("Target.createTarget", {"url": MARKER, "background": True}))["targetId"]
    found = f"chrome.tabs.query({{}}).then(tabs => tabs.find(tab => (tab.url || tab.pendingUrl) === {json.dumps(MARKER)}))"
    assert await until(watcher.worker_js, f"{found}.then(tab => !!tab)")  # fact 1: the marker is the tab's address
    assert await watcher.worker_js("typeof chrome.tabGroups === 'object' && typeof chrome.tabs.group === 'function'")
    title = await watcher.worker_js(f"{found}.then(tab => chrome.tabs.group({{tabIds: [tab.id]}}))"
                                    ".then(group => chrome.tabGroups.update(group, {title: 'probe', color: 'blue'}))"
                                    ".then(group => group.title)")
    assert title == "probe"  # fact 2: headless Chrome groups, given the tabGroups permission
    session = (await watcher.cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]

    async def page(expression):
        return await evaluate(watcher.cdp, session, expression)

    await watcher.cdp.send("Page.enable", session_id=session)
    await watcher.cdp.send("Page.navigate", {"url": watcher.base + "form.html"}, session_id=session)
    assert await until(page, "location.pathname.endsWith('form.html') && document.readyState === 'complete'")
    history = await watcher.cdp.send("Page.getNavigationHistory", session_id=session)
    assert history["entries"][0]["url"] == MARKER  # fact 3: Back from the first page shows the blank page
    assert await page("document.referrer") == ""  # the first page loads with no referrer
    await asyncio.sleep(0)
