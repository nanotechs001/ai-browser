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
# W: the profile chosen in Settings (Default); P: another (Profile 1), the one used last; X: a private window
PROFILES = [
    {"target": "U1", "url": "https://mail.example/", "title": "SECRET-W", "context": "W"},
    {"target": "U2", "url": "https://bank.example/", "title": "SECRET-P", "context": "P"},
    {"target": "U3", "url": "https://private.example/", "title": "SECRET-X", "context": "X"},
    {"target": "A1", "url": "https://shop.example/", "title": "Agent page", "context": "P"},
    {"target": "H1", "url": "https://docs.example/", "title": "Handed page", "context": "W"},
]


def targets(link):
    return sorted(tab["target"] for tab in link.tabs())


async def connected(folder, chosen=None):
    from ai_browser.app.bravelink import BraveLink

    link = BraveLink(folder, every=0.1, settle=0.3)
    link.set_place(chosen)
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


def local_state(folder, last_used="Profile 1"):
    """Brave's Local State with two profiles, Default (W, Work) and Profile 1 (P, Home), and the one it used last."""
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("Default", "Profile 1"):
        (folder / name).mkdir(exist_ok=True)
    (folder / "Local State").write_text(json.dumps({"profile": {"last_used": last_used, "info_cache": {
        "Default": {"name": "Work", "user_name": "me@work.example", "profile_highlight_color": -16744448},
        "Profile 1": {"name": "Home", "user_name": "me@home.example"}}}}), encoding="utf-8")


async def test_only_the_chosen_profile_is_listed_once_brave_has_shown_it(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    local_state(folder, last_used="Profile 1")
    port = FakePort(folder, pages=PROFILES, default="P")
    await port.start()
    link = await connected(folder, chosen="Default")
    try:
        link.set_owner("A1", AGENT)
        link.set_owner("H1", HANDED)
        assert await until(lambda: link.scope() == {"profile": "not_open", "elsewhere": 3})  # Brave hasn't shown it
        assert targets(link) == ["A1", "H1"]  # only the AI's tabs, wherever they are
        port.set_default("W")  # the user clicks in a window of Work: Brave's live record says so at once...
        await asyncio.sleep(1)
        assert link.scope()["profile"] == "not_open"  # ...but its file doesn't yet: nothing is learned from half
        local_state(folder, last_used="Default")  # Brave writes Local State a few seconds later
        assert await until(lambda: link.scope()["profile"] == "chosen")
        assert targets(link) == ["A1", "H1", "U1"] and link.agents_context() == ("W", "chosen")
        listed = json.dumps(link.tabs())
        assert "context" not in listed and "SECRET-P" not in listed and "SECRET-X" not in listed
        assert link.scope() == {"profile": "chosen", "elsewhere": 2}  # U2 (another profile), U3 (a private window)
        port.set_default("P")  # the user goes back to Home: Work stays known on this connection
        local_state(folder, last_used="Profile 1")
        await asyncio.sleep(1)
        assert link.agents_context() == ("W", "chosen") and targets(link) == ["A1", "H1", "U1"]
        link.set_place("Profile 1")  # the user picks Home in Settings
        assert await until(lambda: link.agents_context() == ("P", "chosen"))
        assert port.sessions == 1  # no new connection: Brave asked nothing
    finally:
        await link.close()
        await port.stop()


async def test_what_was_learned_ends_with_the_connection(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    local_state(folder, last_used="Default")
    port = FakePort(folder, pages=PROFILES, default="W")
    await port.start()
    link = await connected(folder, chosen="Default")
    try:
        assert await until(lambda: link.agents_context() == ("W", "chosen"))
        await port.stop()  # Brave quits
        assert await until(lambda: link.state == "lost")
        assert link.agents_context() == (None, "none") and link.tabs() == []
        port = FakePort(folder, pages=PROFILES, default="W")  # Brave again: its contexts are new ids
        await port.start()
        await link.connect()
        assert link.scope() is None or link.scope()["profile"] in ("not_open", "chosen")
        assert await until(lambda: link.agents_context() == ("W", "chosen"))  # learned again, not kept
    finally:
        await link.close()
        await port.stop()


async def test_with_none_chosen_the_profile_used_last_is_listed(tmp_path):
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
    finally:
        await link.close()
        await port.stop()


async def test_a_thread_never_opens_in_another_profile(tmp_path):  # Review Focus 5
    from ai_browser.app.bravelink import NOT_CONNECTED, OTHER_PROFILE, PlaceError

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    local_state(folder, last_used="Default")
    port = FakePort(folder, pages=PROFILES, default="W")
    await port.start()
    link = await connected(folder, chosen="Default")
    try:
        assert await until(lambda: link.agents_context() == ("W", "chosen"))
        port.set_default("P")  # Brave's last window is now Home's
        assert await until(lambda: link._watch.default_context == "P")
        before = len(port.received)
        with pytest.raises(PlaceError, match="another profile") as refused:
            await link.open_user_tab("https://mail.google.com/mail/u/0/#inbox/t1")
        assert str(refused.value) == OTHER_PROFILE and "Work" not in OTHER_PROFILE and "Home" not in OTHER_PROFILE
        assert "Target.createTarget" not in [method for method, *_ in port.received[before:]]  # nothing opened
        port.set_default("W")
        assert await until(lambda: link._watch.default_context == "W")
        target = await link.open_user_tab("https://mail.google.com/mail/u/0/#inbox/t1")
        assert next(tab for tab in link.tabs() if tab["target"] == target)["owner"]["kind"] == "brain"
    finally:
        await link.close()
        await port.stop()
    with pytest.raises(PlaceError) as gone:
        await link.open_user_tab("https://mail.google.com/")
    assert str(gone.value) == NOT_CONNECTED


async def test_a_tab_never_opens_in_another_profile_even_right_after_a_switch(tmp_path):  # Review Focus 5
    """The tab list reads Brave's profile used last every REFRESH seconds: a tab is checked against a read made just
    before it opens, and against the profile it landed in. One that landed in another profile is closed in Brave."""
    from ai_browser.app.bravelink import OTHER_PROFILE, PlaceError

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    local_state(folder, last_used="Default")
    port = FakePort(folder, pages=PROFILES, default="W")
    await port.start()
    link = await connected(folder, chosen="Default")
    try:
        assert await until(lambda: link.agents_context() == ("W", "chosen"))
        new_tabs = lambda: [page for page in port.pages if page["target"].startswith("T")]  # noqa: E731
        port.set_default("P")  # the user clicks a window of the other profile: the list hasn't read it yet
        assert link._watch.default_context == "W"
        for opening in (link.open_ai_tab("a1"), link.open_user_tab("https://mail.google.com/mail/u/0/#inbox/t1")):
            with pytest.raises(PlaceError) as refused:
                await opening
            assert str(refused.value) == OTHER_PROFILE
        assert new_tabs() == []  # nothing opened in P
        port.set_default("W")
        for open_one in (lambda: link.open_ai_tab("a1"), lambda: link.open_user_tab("https://mail.google.com/")):
            port.hold = {"Target.createTarget"}
            opening = asyncio.ensure_future(open_one())
            assert await until(lambda: port.held)
            port.set_default("P")  # Brave's last window changes between the read and the new tab
            port.hold = set()
            await port.answer_held()
            with pytest.raises(PlaceError) as refused:
                await asyncio.wait_for(opening, 5)
            assert str(refused.value) == OTHER_PROFILE
            assert await until(lambda: new_tabs() == [])  # the tab that landed in P is closed in Brave
            port.set_default("W")
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


async def test_a_hidden_tab_cannot_be_read(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, default="W")
    await port.start()
    link = await connected(folder)
    try:
        assert await until(lambda: targets(link) == ["H1", "U1"])
        assert await link.page_text("U2", picked=True) == ""  # another profile: not listed, never read
        assert "U2" not in port.attached
        assert await link.page_text("U1", picked=True) == "page text"  # a listed tab still can be (control)
        assert "U1" in port.attached
        port.set_default("P")
        assert await until(lambda: "U2" in targets(link))
        assert next(tab for tab in link.tabs() if tab["target"] == "U2")["owner"] == {"kind": "you"}
    finally:
        await link.close()
        await port.stop()


async def test_a_tab_let_go_in_another_profile_leaves_the_list_for_the_count(tmp_path):  # Review Focus 4
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, default="P")  # none chosen: the profile used last, P
    await port.start()
    link = await connected(folder)
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
async def test_brave_link_in_a_throwaway_chrome(throwaway_chrome, patient_thumbnails):
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
    link = BraveLink(folder, every=0.1)  # none chosen: the profile used last
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
