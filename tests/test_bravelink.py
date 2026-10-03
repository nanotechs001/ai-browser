"""BraveLink, the app's one connection to the user's Brave: a fake debugging port stands in for Brave here (it records
every WebSocket session and every CDP method), and a throwaway Chrome at the end."""

import asyncio

import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import FakePort, relay_client, serve_relay, until

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


AGENT = {"kind": "agent", "id": "a1", "name": "Fix the footer", "color": "blue"}


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
