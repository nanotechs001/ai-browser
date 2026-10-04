"""BraveLink, the app's one connection to the user's Brave: a fake debugging port stands in for Brave here (it records
every WebSocket session and every CDP method), and a throwaway Chrome at the end."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import FakePort, relay_client, serve_relay, until

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


AGENT = {"kind": "agent", "id": "a1", "name": "Fix the footer", "color": "blue"}
HANDED = {"kind": "handed", "id": "a1", "name": "Fix the footer", "color": "blue"}
WATCHER_ID = "abcdefghijklmnopabcdefghijklmnop"  # the watcher's extension id (run.py computes it from its folder)
WORKER = {"target": "SW1", "url": f"chrome-extension://{WATCHER_ID}/worker.js", "context": "W"}
PROFILES = [  # W: the watcher's profile; P: another profile, the one used last; X: a private window
    {"target": "U1", "url": "https://mail.example/", "title": "SECRET-W", "context": "W"},
    {"target": "U2", "url": "https://bank.example/", "title": "SECRET-P", "context": "P"},
    {"target": "U3", "url": "https://private.example/", "title": "SECRET-X", "context": "X"},
    {"target": "A1", "url": "https://shop.example/", "title": "Agent page", "context": "P"},
    {"target": "H1", "url": "https://docs.example/", "title": "Handed page", "context": "W"},
]


def targets(link):
    return sorted(tab["target"] for tab in link.tabs())


async def connected(folder, watcher_id=WATCHER_ID):
    from ai_browser.app.bravelink import BraveLink

    link = BraveLink(folder, watcher_id=watcher_id, every=0.1)
    await link.start()
    await link.connect()
    assert link.state == "connected"
    return link


async def test_the_states_follow_the_switch_and_the_users_answer(tmp_path):
    from ai_browser.app.bravelink import BraveLink

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder)
    link = BraveLink(folder, allow_wait=2, every=0.1)
    states = []
    link.on_state(states.append)
    await link.start()
    try:
        assert link.state == "off" and link.name == "Brave"
        await port.start()  # the user ticks the switch
        assert await until(lambda: link.state == "ready")
        await asyncio.sleep(1)  # ten looks at the switch
        assert port.sessions == 0  # TCP checks only: no debugging session, so Brave would ask nothing
        await link.connect()
        assert link.state == "connected" and port.sessions == 1
        await port.stop()  # Brave quits
        assert await until(lambda: link.state == "lost")
        assert states == ["ready", "asking", "connected", "lost"]
    finally:
        await link.close()


async def test_deny_is_refused_and_never_retried(tmp_path):
    from ai_browser.app.bravelink import BraveLink

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, answer="refuse")
    await port.start()
    link = BraveLink(folder, allow_wait=0.5, every=0.1)
    await link.start()
    try:
        assert link.state == "ready"
        await link.connect()
        assert link.state == "refused" and port.sessions == 1
        await asyncio.sleep(0.5)
        assert link.state == "refused" and port.sessions == 1  # it never asks again by itself
    finally:
        await link.close()
        await port.stop()


async def test_no_answer_keeps_the_one_question_open(tmp_path):
    """Nobody answers yet: the question stays (cdprelay never gives up on it), and Connect pressed again joins it
    instead of asking a second time."""
    from ai_browser.app.bravelink import BraveLink

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, answer="silent")
    await port.start()
    link = BraveLink(folder, allow_wait=0.5, every=0.1)
    await link.start()
    try:
        first = asyncio.ensure_future(link.connect())
        assert await until(lambda: link.state == "asking")
        await asyncio.sleep(1.5)  # three times allow_wait
        again = asyncio.ensure_future(link.connect())  # AI Home's Connect, pressed again
        await asyncio.sleep(0.3)
        assert link.state == "asking" and port.sessions == 1 and not first.done() and not again.done()
        port.answer = "accept"
        port.release.set()  # the user clicks Allow
        await asyncio.wait_for(asyncio.gather(first, again), 10)
        assert link.state == "connected" and port.sessions == 1
    finally:
        await link.close()
        await port.stop()


async def test_the_users_tabs_are_listed_but_never_attached(tmp_path):
    from ai_browser.app.bravelink import BraveLink

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=[{"target": "U1", "url": "https://mail.example/", "title": "SECRET-7f3a"},
                                   {"target": "A1", "url": "https://shop.example/", "title": "Shop"},
                                   {"target": "B0", "url": "about:blank#aib-0123456789abcdef", "title": ""},
                                   {"target": "X", "url": "brave://settings", "title": "Settings"}])
    await port.start()
    link = BraveLink(folder, every=0.1)
    changes = []
    link.on_change(changes.append)
    await link.start()
    await link.connect()
    try:
        assert await until(lambda: len(link.tabs()) == 2)  # web pages only: no brave:// page, no stranger's blank tab
        assert all("context" not in tab for tab in link.tabs())  # context ids never leave BraveLink
        assert [(tab["target"], tab["owner"]) for tab in link.tabs()] == [("U1", {"kind": "you"}),
                                                                          ("A1", {"kind": "you"})]
        link.set_owner("A1", AGENT)
        link.set_owner("B0", AGENT)
        assert [tab["target"] for tab in link.tabs()] == ["U1", "A1", "B0"]  # the AI's own blank tab too
        assert changes and changes[-1] == link.tabs()
        assert await link.thumbnail("U1") is None and await link.page_text("U1") == ""
        assert port.attached == []  # the user's tab: never attached to
        assert await link.thumbnail("A1") == b"\xff\xd8jpeg"
        assert await link.page_text("U1", picked=True) == "page text"  # the page the user picked in the Train form
        assert port.attached == ["A1", "U1"]
        link.release("a1")
        assert link.tabs()[1]["owner"] == {"kind": "you"}
        link.mark_brain("https://mail.example/")
        assert link.tabs()[0]["owner"] == {"kind": "brain", "name": "Brain", "color": "purple"}
    finally:
        await link.close()
        await port.stop()


async def test_the_brain_is_marked_only_when_one_tab_matches(tmp_path):
    from ai_browser.app.bravelink import BraveLink

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    same = "https://mail.example/#t1"
    port = FakePort(folder, pages=[{"target": "U1", "url": same, "title": "A"}, {"target": "U2", "url": same,
                                                                                 "title": "B"}])
    await port.start()
    link = BraveLink(folder, every=0.1)
    await link.start()
    await link.connect()
    try:
        assert await until(lambda: len(link.tabs()) == 2)
        link.mark_brain(same)
        assert {tab["owner"]["kind"] for tab in link.tabs()} == {"you"}  # two candidates: nobody is guessed
    finally:
        await link.close()
        await port.stop()


async def test_the_tab_list_and_an_agent_share_one_connection(tmp_path):
    from ai_browser.app.bravelink import BraveLink

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=[{"target": "U1", "url": "https://mail.example/", "title": "Mail"}])
    await port.start()
    link = BraveLink(folder, every=0.1)
    url, stop = await serve_relay(link.relay)
    await link.start()
    try:
        await link.connect()
        assert link.state == "connected"
        assert await until(lambda: [tab["target"] for tab in link.tabs()] == ["U1"])
        agent = await relay_client(url, link.relay.tokens.mint("a1"))
        tab = (await agent.send("Target.createTarget", {"url": "https://shop.example/"}))["targetId"]
        assert await until(lambda: tab in [listed["target"] for listed in link.tabs()])
        link.set_owner(tab, AGENT)
        assert await link.thumbnail(tab) == b"\xff\xd8jpeg"
        await link.close_targets([tab])  # closing an agent closes its own tabs, through the same connection
        assert await until(lambda: tab not in [listed["target"] for listed in link.tabs()])
        assert port.sessions == 1 and link.relay.upstream_opens == 1
        await agent.close()
    finally:
        await link.close()
        await stop()
        await port.stop()


async def test_a_session_that_connects_first_starts_the_tab_list_too(tmp_path):
    from ai_browser.app.bravelink import BraveLink

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=[{"target": "U1", "url": "https://mail.example/", "title": "Mail"}])
    await port.start()
    link = BraveLink(folder, every=0.1)
    url, stop = await serve_relay(link.relay)
    await link.start()
    try:
        session = await relay_client(url, link.relay.tokens.mint("cc-1"))  # its call asks Brave (Decision 10)
        assert link.state == "connected"
        assert await until(lambda: [tab["target"] for tab in link.tabs()] == ["U1"])
        assert port.sessions == 1
        await session.close()
    finally:
        await link.close()
        await stop()
        await port.stop()


async def test_only_the_agents_profile_is_listed_and_the_rest_is_counted(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, workers=[WORKER], default="P")
    await port.start()
    link = await connected(folder)
    try:
        link.set_owner("A1", AGENT)
        link.set_owner("H1", HANDED)
        assert await until(lambda: link.scope()["profile"] == "watcher")
        assert targets(link) == ["A1", "H1", "U1"]  # the watcher's profile, and the AI's tabs wherever they are
        listed = json.dumps(link.tabs())
        assert "context" not in listed and "SECRET-P" not in listed and "SECRET-X" not in listed
        assert link.scope() == {"profile": "watcher", "elsewhere": 2}  # U2 (another profile), U3 (a private window)
        assert link.agents_context() == ("W", "watcher")
        assert port.sessions == 1  # no new connection to Brave
    finally:
        await link.close()
        await port.stop()


async def test_without_the_watcher_the_profile_used_last_is_listed(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, default="P")
    await port.start()
    link = await connected(folder)
    try:
        assert await until(lambda: targets(link) == ["A1", "U2"])
        assert link.scope() == {"profile": "last_used", "elsewhere": 3}
        port.set_default("W")  # the user used the other profile last
        assert await until(lambda: targets(link) == ["H1", "U1"])
        assert link.scope() == {"profile": "last_used", "elsewhere": 3}
        await port.add_worker(WORKER)
        assert await until(lambda: link.scope()["profile"] == "watcher")
        await port.add_worker({**WORKER, "target": "SW2", "context": "X"})  # one watcher folder in two profiles
        assert await until(lambda: link.scope()["profile"] == "last_used")  # which one groups? the fallback
    finally:
        await link.close()
        await port.stop()


async def test_the_watchers_profile_outlives_its_sleeping_worker_but_not_the_connection(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, workers=[WORKER], default="P")
    await port.start()
    link = await connected(folder)
    try:
        assert await until(lambda: link.scope()["profile"] == "watcher")
        await port.destroy("SW1")  # the worker sleeps
        await asyncio.sleep(2)  # past a refresh round
        assert link.agents_context() == ("W", "watcher") and targets(link) == ["H1", "U1"]
        await port.stop()  # Brave quits
        assert await until(lambda: link.state == "lost")
        port = FakePort(folder, pages=PROFILES, default="P")  # Brave again: the worker hasn't woken yet
        await port.start()
        await link.connect()
        assert link.state == "connected"
        assert await until(lambda: link.scope()["profile"] == "last_used")
        assert await until(lambda: targets(link) == ["A1", "U2"])
        await port.add_worker(WORKER)  # it wakes within half a minute (its reconnect alarm)
        assert await until(lambda: link.scope()["profile"] == "watcher")
    finally:
        await link.close()
        await port.stop()


async def test_with_no_profile_known_no_tab_of_the_users_is_listed(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, default=None)  # Target.getBrowserContexts answers an error
    await port.start()
    link = await connected(folder)
    try:
        link.set_owner("A1", AGENT)
        assert await until(lambda: targets(link) == ["A1"])  # only the AI's
        assert link.scope() == {"profile": "none", "elsewhere": 4}
    finally:
        await link.close()
        await port.stop()


async def test_a_hidden_tab_cannot_be_read_or_marked(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, default="W")
    await port.start()
    link = await connected(folder, watcher_id="")
    try:
        assert await until(lambda: targets(link) == ["H1", "U1"])
        assert await link.page_text("U2", picked=True) == ""  # another profile: not listed, never read
        assert "U2" not in port.attached
        link.mark_brain("https://bank.example/")  # nothing in the list shows it: nothing is marked
        assert await link.page_text("U1", picked=True) == "page text"  # a listed tab still can be (control)
        assert "U1" in port.attached
        port.set_default("P")
        assert await until(lambda: "U2" in targets(link))
        assert next(tab for tab in link.tabs() if tab["target"] == "U2")["owner"] == {"kind": "you"}
    finally:
        await link.close()
        await port.stop()


async def test_a_waking_and_sleeping_worker_doesnt_resend_the_list(tmp_path):  # Review Focus 3
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, workers=[WORKER], default="P")
    await port.start()
    link = await connected(folder)
    changes = []
    link.on_change(changes.append)
    try:
        assert await until(lambda: link.scope()["profile"] == "watcher")
        await asyncio.sleep(2)  # settled, past a refresh round
        settled = len(changes)
        for _ in range(3):
            await port.destroy("SW1")
            await asyncio.sleep(0.3)
            await port.add_worker(WORKER)
            await asyncio.sleep(0.3)
        await asyncio.sleep(2)
        assert len(changes) == settled  # neither the rows nor the scope changed
    finally:
        await link.close()
        await port.stop()


async def test_a_tab_let_go_in_another_profile_leaves_the_list_for_the_count(tmp_path):  # Review Focus 4
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, default="P")  # no watcher: the profile used last, P
    await port.start()
    link = await connected(folder, watcher_id="")
    try:
        assert await until(lambda: link.scope() == {"profile": "last_used", "elsewhere": 3})
        link.set_owner("H1", HANDED)  # handed to a1, in profile W
        link.set_owner("U1", AGENT)
        assert targets(link) == ["A1", "H1", "U1", "U2"] and link.scope()["elsewhere"] == 1
        link.forget("H1")  # Take back
        assert "H1" not in targets(link) and link.scope()["elsewhere"] == 2
        link.release("a1")  # the agent closed
        assert targets(link) == ["A1", "U2"] and link.scope()["elsewhere"] == 3
        assert "SECRET-W" not in json.dumps(link.tabs())
    finally:
        await link.close()
        await port.stop()


@CHROME
async def test_brave_link_in_a_throwaway_chrome(throwaway_chrome):
    from ai_browser import testpages
    from ai_browser.app.bravelink import BraveLink

    base, _, stop_pages = testpages.serve_host()
    link = BraveLink(throwaway_chrome, every=0.1)
    url, stop = await serve_relay(link.relay)
    await link.start()
    try:
        assert link.state == "ready"
        await link.connect()
        assert link.state == "connected"
        agent = await relay_client(url, link.relay.tokens.mint("a1"))
        target = (await agent.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
        assert await until(lambda: any(tab["target"] == target and tab["title"] == "Privacy" for tab in link.tabs()))
        link.set_owner(target, AGENT)
        assert (await link.thumbnail(target))[:2] == b"\xff\xd8"
        await link.close_targets([target, "no-such-target"])  # closing an agent closes its own tabs
        assert await until(lambda: not any(tab["target"] == target for tab in link.tabs()))
        await agent.close()
    finally:
        await link.close()
        await stop()
        stop_pages()


@CHROME
async def test_a_private_window_is_never_listed_in_a_throwaway_chrome(tmp_path):
    from ai_browser import testpages
    from ai_browser.app.bravelink import BraveLink
    from ai_browser.app.tabs import TabWatch
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url, launch

    base, _, stop_pages = testpages.serve_host()
    folder = tmp_path / "private-profile"
    process = launch(folder, headless=True, extra_args=("--incognito",))  # its only window: private
    link = BraveLink(folder, every=0.1)  # no watcher: the profile used last
    try:
        ws_url = find_ws_url(folder, timeout=20)
        watch = TabWatch(ws_url, "")
        await watch.start()
        cdp = await CDP.connect(ws_url)
        try:
            # Headless Chrome takes one start address and launch() gives it about:blank: the test itself points the
            # private window's start page at a web page.
            for _ in range(100):
                start = next((info["targetId"] for info in (await cdp.send("Target.getTargets"))["targetInfos"]
                              if info["type"] == "page"), None)
                if start is not None:
                    break
                await asyncio.sleep(0.1)
            session = (await cdp.send("Target.attachToTarget", {"targetId": start, "flatten": True}))["sessionId"]
            await cdp.send("Page.navigate", {"url": base + "privacy.html"}, session_id=session)
            await cdp.send("Target.detachFromTarget", {"sessionId": session})
            assert await until(lambda: any(row["url"] == base + "privacy.html" for row in watch.pages()), 10)
            private = next(row for row in watch.pages() if row["url"] == base + "privacy.html")
            regular = (await cdp.send("Target.createTarget", {"url": base + "form.html"}))["targetId"]  # no context
            assert await until(lambda: any(row["target"] == regular for row in watch.pages()), 10)
            context = next(row["context"] for row in watch.pages() if row["target"] == regular)
            assert private["context"] and context and private["context"] != context
            assert await until(lambda: watch.default_context == context)  # never the private window's
            await link.start()
            await link.connect()
            assert link.state == "connected"
            assert await until(lambda: [tab["target"] for tab in link.tabs()] == [regular], 10)
            assert link.scope() == {"profile": "last_used", "elsewhere": 1}
            listed = json.dumps(link.tabs())
            assert private["target"] not in listed and "Privacy" not in listed
        finally:
            await cdp.close()
            await watch.close()
    finally:
        await link.close()
        process.terminate()
        process.wait(timeout=15)
        stop_pages()


async def test_brave_link_leaves_out_the_apps_own_pages(tmp_path, monkeypatch):
    from ai_browser.app import bravelink
    from ai_browser.app.tabs import TabWatch
    from fake_brave import FakePort

    made = []

    class Recording(TabWatch):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

    monkeypatch.setattr(bravelink, "TabWatch", Recording)
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder)
    await port.start()
    link = bravelink.BraveLink(folder, allow_wait=2, every=0.1, app_origin="http://127.0.0.1:8792")
    await link.start()
    try:
        await link.connect()
        assert link.app_origin == "http://127.0.0.1:8792"
        assert made and made[-1].hidden_origin == "http://127.0.0.1:8792"  # a 403 page the user opened in Brave
    finally:
        await link.close()
        await port.stop()
