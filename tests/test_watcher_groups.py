"""The AI's tabs in the user's Brave, put in groups by the watcher. A throwaway headless Chrome with the watcher loaded
over the pipe stands in for Brave (the `watcher` fixture of test_watcher.py), next to a real app server."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from ai_browser.engine import Engine
from ai_browser.skills import Catalog
from fake_brave import add_agent
from test_home import evaluate, open_page, until
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


async def groups_on(watcher):  # noqa: F811
    assert await watcher.until(lambda: watcher.server.groups.available() == "on"), "watcher_caps never said yes"


def agent_engine(watcher, tmp_path, monkeypatch, agent="a1"):  # noqa: F811
    """An engine in own mode, set up the way ai-browser app sets up an agent's (AIB_APP_* from the app)."""
    monkeypatch.setenv("AIB_BROWSER", "chrome")
    monkeypatch.setenv("AIB_CHROME_DIR", str(tmp_path / "profile"))  # the watcher fixture's throwaway Chrome
    monkeypatch.setenv("AIB_APP_AGENT", agent)
    monkeypatch.setenv("AIB_APP_EVENTS", watcher.server.url + "/agent-events")
    monkeypatch.setenv("AIB_APP_AGENT_TOKEN", watcher.server.token_for(agent))
    monkeypatch.setenv("AIB_APP_CDP", watcher.server.url.replace("http://", "ws://", 1) + "/cdp")
    return Engine(home=tmp_path / f"engine-{agent}", catalog=Catalog([], set()))


ACTIVE = "chrome.tabs.query({active: true, lastFocusedWindow: true}).then(([tab]) => tab && tab.id)"


@CHROME
async def test_an_agents_tabs_go_in_its_group_without_taking_the_focus(watcher, tmp_path, monkeypatch):  # noqa: F811
    base = watcher.base
    add_agent(watcher.server.agents, "a1", "Fix the footer", "blue")
    await groups_on(watcher)
    await open_page(watcher.cdp, base + "form.html")  # the user's own page, in front, with the same address later
    front = await watcher.worker_js(ACTIVE)
    engine = agent_engine(watcher, tmp_path, monkeypatch)
    try:
        page = (await engine.open(base + "popup.html")).text
        assert 'page  "Popup test"' in page
        first = engine.browser.current.target
        title, color, group_window, window = await group_of(watcher, base + "popup.html")
        assert (title, color) == ("Fix the footer", "blue") and group_window == window
        assert (await engine.js("document.referrer")).text.startswith('""')
        assert await watcher.worker_js(ACTIVE) == front  # the user's focus never moved
        link = next(line.split()[0] for line in page.splitlines() if '"Preview in new tab"' in line)
        await engine.act([f"click {link}"])
        for _ in range(30):  # a tab its page opened joins its group
            if await group_of(watcher, base + "privacy.html"):
                break
            await asyncio.sleep(0.1)
        assert (await group_of(watcher, base + "privacy.html"))[:2] == ["Fix the footer", "blue"]
        popup = next(tab.target for tab in engine.browser.owned.values() if tab.target != first)
        assert watcher.brave.relay.grants("a1", popup)  # the relay made it a1's own when the engine attached
        assert await watcher.until(lambda: any(tab["target"] == popup and tab["owner"].get("name") == "Fix the footer"
                                               for tab in watcher.brave.tabs()))  # and AI Home's chip says so
        await engine.tabs("new", url=base + "form.html")
        user_form = await watcher.worker_js(
            f"chrome.tabs.query({{}}).then(tabs => tabs.filter(tab => tab.url === {json.dumps(base + 'form.html')})"
            ".map(tab => tab.groupId))")
        assert sorted(user_form)[0] == -1 and len(user_form) == 2  # the user's tab with that address stays out
        assert await watcher.worker_js(ACTIVE) == front
    finally:
        await engine.close()


@CHROME
async def test_two_agents_two_groups_and_a_tab_in_another_window_moves_to_its_group(watcher, tmp_path,  # noqa: F811
                                                                                      monkeypatch):
    base = watcher.base
    add_agent(watcher.server.agents, "a1", "Fix the footer", "blue")
    add_agent(watcher.server.agents, "a2", "Check prices", "green")
    await groups_on(watcher)
    first = agent_engine(watcher, tmp_path, monkeypatch, "a1")
    await first.open(base + "popup.html")
    second = agent_engine(watcher, tmp_path, monkeypatch, "a2")
    try:
        await second.open(base + "report.html")
        one, two = await group_of(watcher, base + "popup.html"), await group_of(watcher, base + "report.html")
        assert one[:2] == ["Fix the footer", "blue"] and two[:2] == ["Check prices", "green"]
        await watcher.cdp.send("Target.createTarget", {"url": base + "textonly.html", "newWindow": True})
        await asyncio.sleep(0.5)  # the user now works in another window
        await first.tabs("new", url=base + "long.html")
        title, _, group_window, window = await group_of(watcher, base + "long.html")
        assert title == "Fix the footer" and window == group_window == one[2]  # moved to the agent's group
    finally:
        await first.close()
        await second.close()


@CHROME
async def test_a_closed_group_is_made_again_and_the_users_move_stands(watcher, tmp_path, monkeypatch):  # noqa: F811
    base = watcher.base  # Review Focus 2
    add_agent(watcher.server.agents, "a1", "Fix the footer", "blue")
    await groups_on(watcher)
    engine = agent_engine(watcher, tmp_path, monkeypatch)
    try:
        await engine.open(base + "popup.html")
        assert await group_of(watcher, base + "popup.html")
        await watcher.worker_js(f"chrome.tabs.query({{}}).then(tabs => tabs.find(tab => tab.url === "
                                f"{json.dumps(base + 'popup.html')})).then(tab => chrome.tabs.ungroup(tab.id))"
                                ".then(() => true)")  # the user dissolves the group (its only tab leaves it)
        await engine.tabs("new", url=base + "report.html")
        assert (await group_of(watcher, base + "report.html"))[:2] == ["Fix the footer", "blue"]
        assert await group_of(watcher, base + "popup.html") is None  # the tab the user took out stays out
    finally:
        await engine.close()


@CHROME
async def test_without_the_watcher_the_page_still_loads_ungrouped(watcher, tmp_path, monkeypatch):  # noqa: F811
    base = watcher.base
    add_agent(watcher.server.agents, "a1", "Fix the footer", "blue")
    await groups_on(watcher)
    engine = agent_engine(watcher, tmp_path, monkeypatch)
    try:
        await engine.open(base + "popup.html")  # the engine learns groups are on (kept for 10 s)
        watcher.server._watcher_origins.clear()  # from now on the watcher can't be the app's watcher again
        await watcher.server._watcher[0].close()
        assert await watcher.until(lambda: watcher.server.groups.available() == "no_watcher")
        page = (await engine.tabs("new", url=base + "report.html")).text
        assert 'page  "' in page and await group_of(watcher, base + "report.html") is None
    finally:
        await engine.close()


@CHROME
async def test_a_claude_code_session_joins_while_the_app_runs(watcher, tmp_path, monkeypatch):  # noqa: F811
    from ai_browser import grouping

    base = watcher.base
    monkeypatch.setattr(grouping, "REREAD_EVERY", 0)
    monkeypatch.setenv("AIB_BROWSER", "chrome")
    monkeypatch.setenv("AIB_CHROME_DIR", str(tmp_path / "profile"))
    await groups_on(watcher)
    home = tmp_path / "session-home"
    (home / "app").mkdir(parents=True)
    from ai_browser.app.run import write_link

    link = write_link(home, watcher.server.url, watcher.server.session_token,
                      watcher.server.url.replace("http://", "ws://", 1) + "/cdp", tmp_path / "profile")
    engine = Engine(home=home, catalog=Catalog([], set()))
    try:
        await engine.open(base + "form.html")
        title, color, _, form_window = await group_of(watcher, base + "form.html")
        assert (title, color) == ("Claude Code", "orange") and f"cc-{engine.task_id}" in watcher.server.sessions
        link.unlink()  # the app has quit
        await engine.tabs("new", url=base + "report.html")
        assert await group_of(watcher, base + "report.html") is None
        report_window = await watcher.worker_js(
            f"chrome.tabs.query({{}}).then(tabs => tabs.find(tab => tab.url === {json.dumps(base + 'report.html')}))"
            ".then(tab => tab.windowId)")
        assert report_window != form_window  # a window of its own
    finally:
        await engine.close()


@CHROME
async def test_the_brains_threads_go_in_its_group_and_ai_home_marks_them(watcher, tmp_path):  # noqa: F811
    brave = watcher.brave  # the fixture's: the throwaway Chrome as the user's Brave, through the relay
    verdicts = [{"id": "gmail:t1", "kind": "needs_reply", "summary": "Maria asks to move the launch",
                 "why": "a client", "suggest": "draft"}]
    watcher.script.write_text(json.dumps({"default": [{"result": "[]"}],
                                          "You sort new messages": [{"result": json.dumps(verdicts)}],
                                          "You draft a reply": [{"result": "Monday works for us."}]}),
                              encoding="utf-8")
    await watcher.watch("gmail", "brain/gmail.html")
    assert await watcher.until(lambda: "t1" in watcher.raw_ids())
    await watcher.brain.draft("gmail:t1")
    thread = watcher.brain.store.get("gmail:t1").url
    assert (await group_of(watcher, thread))[:2] == ["Brain", "purple"]
    assert await watcher.until(lambda: any(tab["url"] == thread and tab["owner"]["kind"] == "brain"
                                           for tab in brave.tabs()))


async def brave_for(watcher, tmp_path):  # noqa: F811
    return watcher.brave  # the fixture's: attached and connected, with the server's tokens


async def hand(watcher, verb, **message):  # noqa: F811
    """What AI Home's Hand over / Take back sends, as the app handles it."""
    queue = asyncio.Queue()
    await watcher.server._brave_command(queue, verb, message)
    assert queue.empty(), queue.get_nowait()


@CHROME
async def test_a_handed_tab_is_used_taken_back_and_left_open(watcher, tmp_path, monkeypatch):  # noqa: F811
    base = watcher.base
    brave = await brave_for(watcher, tmp_path)
    add_agent(watcher.server.agents, "a1", "Fix the footer", "blue")
    await groups_on(watcher)
    engine = agent_engine(watcher, tmp_path, monkeypatch)
    try:
        await engine.open(base + "form.html")
        first_window = (await group_of(watcher, base + "form.html"))[2]
        user = (await watcher.cdp.send("Target.createTarget", {"url": base + "privacy.html", "newWindow": True}))
        user = user["targetId"]
        assert await watcher.until(lambda: any(tab["target"] == user for tab in brave.tabs()))
        await hand(watcher, "hand_tab", id="a1", target=user)
        for _ in range(30):
            if await group_of(watcher, base + "privacy.html"):
                break
            await asyncio.sleep(0.1)
        title, color, group_window, window = await group_of(watcher, base + "privacy.html")
        assert (title, color) == ("Fix the footer", "blue")
        assert group_window == window != first_window  # never moved: a second group in its own window
        await asyncio.sleep(1.1)  # the engine reads the handed tabs at most once a second (open just read them)
        listing = (await engine.tabs("list")).text
        assert "h1" in listing and "(handed to you by the user)" in listing
        assert 'page  "Privacy"' in (await engine.tabs("switch", "h1")).text
        assert 'page  "Privacy"' in (await engine.observe()).text
        await hand(watcher, "take_back", target=user)
        for _ in range(30):
            if await group_of(watcher, base + "privacy.html") is None:
                break
            await asyncio.sleep(0.1)
        assert await group_of(watcher, base + "privacy.html") is None  # out of the agent's group
        await asyncio.sleep(1.1)  # the engine reads the handed tabs at most once a second
        taken = (await engine.observe()).text
        assert "(the user took back tab t2)" in taken
        await hand(watcher, "hand_tab", id="a1", target=user)
        await asyncio.sleep(1)
        await watcher.server.agents.close("a1")
        assert await watcher.until(lambda: any(tab["target"] == user and tab["owner"] == {"kind": "you"}
                                               for tab in brave.tabs()))  # still open, the user's again
        for _ in range(30):
            if await group_of(watcher, base + "privacy.html") is None:
                break
            await asyncio.sleep(0.1)
        assert await group_of(watcher, base + "privacy.html") is None  # and ungrouped
    finally:
        await engine.close()


@CHROME
async def test_take_back_during_a_bot_check_skips_the_site(watcher, tmp_path, monkeypatch):  # noqa: F811
    base = watcher.base
    brave = await brave_for(watcher, tmp_path)
    agent = add_agent(watcher.server.agents, "a1", "Fix the footer", "blue")
    await groups_on(watcher)
    engine = agent_engine(watcher, tmp_path, monkeypatch)
    try:
        user = (await watcher.cdp.send("Target.createTarget", {"url": base + "checks/unusual.html"}))["targetId"]
        assert await watcher.until(lambda: any(tab["target"] == user for tab in brave.tabs()))
        await hand(watcher, "hand_tab", id="a1", target=user)
        handed = (await engine.tabs("switch", "h1")).text
        assert "⛔ bot check" in handed
        assert await watcher.until(lambda: agent.check is not None)
        assert agent.check["adopted"] is True  # the user's own tab: the card offers no Skip this site
        await hand(watcher, "take_back", target=user)
        await asyncio.sleep(1.1)  # the engine reads the handed tabs at most once a second
        ended = (await engine.observe()).text
        assert "off-limits" in ended and engine.gate.held is None  # the take-back counts as closing it
        assert "off-limits" in (await engine.open(base + "form.html")).text  # the site stays skipped
        assert user in {tab["target"] for tab in brave.tabs()}  # the user's tab stays open
    finally:
        await engine.close()
