"""BraveLink's gate for AI Browser's page scripts (may_run, brain_tabs, run_reader), and the Train form's page read in
the isolated world: on a fake debugging port (FakePort, which records every command), then the fake Gmail read
through the relay in a throwaway headless Chrome."""

import asyncio

import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import FakePort, until
from fake_sites import inbox_sites  # noqa: F401  (a fixture)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
AGENT = {"kind": "agent", "id": "a1", "name": "Fix the footer", "color": "blue"}
INBOX = "https://mail.google.com/mail/u/0/#inbox"
SLACK = "https://app.slack.com/client/T1/C1"
PAGES = [  # P: the profile where agents browse (the one used last); Q: another profile
    {"target": "U1", "url": INBOX, "title": "Inbox", "context": "P"},
    {"target": "U2", "url": "https://mail.google.com/mail/u/1/#inbox", "title": "SECRET-Q", "context": "Q"},
    {"target": "U3", "url": "https://shop.example/", "title": "Shop", "context": "P"},
    {"target": "U4", "url": SLACK, "title": "Slack", "context": "P"},
    {"target": "A1", "url": INBOX, "title": "An agent's Gmail", "context": "P"},
]


async def linked(tmp_path, connect=True):
    """(FakePort, BraveLink on it; connected unless asked not to), with the Brain's three sites."""
    from ai_browser.app.bravelink import BraveLink
    from ai_browser.brain.sites import inbox_site

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PAGES, default="P")
    await port.start()
    link = BraveLink(folder, every=0.1)
    link.brain_site = inbox_site
    await link.start()
    if connect:
        await link.connect()
        assert await until(lambda: len(link.tabs()) == 4)  # U1, U3, U4, A1: profile P
        link.set_owner("A1", AGENT)
    return port, link


async def test_the_brain_reads_only_the_users_listed_tabs_on_its_sites_and_only_while_on(tmp_path):
    port, link = await linked(tmp_path)
    try:
        assert link.brain_tabs() == [] and not link.may_run("U1", "brain")  # the switch is off
        assert not link.may_run("U3", "pick")
        link.brain_reading = lambda: True
        assert link.brain_tabs() == [{"target": "U1", "url": INBOX, "site": "gmail"},
                                     {"target": "U4", "url": SLACK, "site": "slack"}]
        assert link.may_run("U1", "brain") and link.may_run("U4", "brain")
        assert not link.may_run("U2", "brain")  # another profile: never
        assert not link.may_run("A1", "brain") and not link.may_run("U3", "brain")  # an agent's; not a site it reads
        assert link.may_run("U3", "pick") and not link.may_run("A1", "pick") and not link.may_run("U2", "pick")
        assert not link.may_run("U1", "page") and not link.may_run("U1", "anything")
    finally:
        await link.close()
        await port.stop()


async def test_a_tab_the_gate_refuses_is_never_attached(tmp_path):
    from ai_browser.app.inworld import WorldError

    port, link = await linked(tmp_path)
    link.brain_reading = lambda: True
    try:
        for target in ("U2", "U3", "A1", "NO-SUCH-TAB"):
            with pytest.raises(WorldError, match="AI Browser doesn't read that tab"):
                await link.run_reader(target, "brain", "read", "gmail", {})
        assert port.attached == []  # refused before anything reached Brave
        before = len(port.received)
        assert await link.run_reader("U1", "brain", "read", "gmail", {}) == "page text"  # FakePort's answer
        sent = [(method, params) for method, _, params, _ in port.received[before:]]
        assert [method for method, _ in sent] == ["Target.attachToTarget", "Page.getFrameTree",
                                                  "Page.createIsolatedWorld", "Runtime.evaluate",
                                                  "Target.detachFromTarget"]
        assert sent[2][1]["worldName"] == "ai-browser" and sent[3][1]["contextId"] == 7
        assert sent[3][1]["returnByValue"] is True and port.attached == ["U1"]
    finally:
        await link.close()
        await port.stop()


async def test_nothing_runs_while_brave_isnt_connected_and_nothing_asks_it(tmp_path):  # Review Focus 1
    from ai_browser.app.inworld import WorldError

    port, link = await linked(tmp_path, connect=False)
    link.brain_reading = lambda: True
    try:
        await asyncio.sleep(0.3)  # a few looks at the switch
        assert link.state == "ready" and link.client() is None and link.brain_tabs() == []
        with pytest.raises(WorldError):
            await link.run_reader("U1", "brain", "read", "gmail", {})
        assert await link.page_text("U1", picked=True) == ""
        assert port.sessions == 0  # no connection was opened: Brave asked nothing
    finally:
        await link.close()
        await port.stop()


async def test_the_train_forms_page_read_runs_in_the_isolated_world(tmp_path):
    port, link = await linked(tmp_path)
    try:
        before = len(port.received)
        assert await link.page_text("U1", picked=True) == "page text"  # the page the user picked in the Train form
        evaluate = next(params for method, _, params, _ in port.received[before:] if method == "Runtime.evaluate")
        assert evaluate["contextId"] == 7 and evaluate["expression"] == "document.body ? document.body.innerText : ''"
        assert await link.page_text("U3") == ""  # not picked, not the AI's: never read
    finally:
        await link.close()
        await port.stop()


@CHROME
async def test_a_fake_gmail_is_read_through_the_relay_and_nothing_else(throwaway_chrome, tmp_path, inbox_sites):
    from ai_browser import testpages
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.bravelink import BraveLink
    from ai_browser.app.inworld import WorldError
    from ai_browser.app.server import AppServer
    from ai_browser.brain.sites import inbox_site
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url
    from test_home import open_page

    other, _, stop_pages = testpages.serve_host()  # an address that is no site the Brain reads
    home = tmp_path / "home"
    server = AppServer(home, AgentManager(home))
    await server.start()
    brave = BraveLink(throwaway_chrome, every=0.1, tokens=server.tokens)
    server.attach_brave(brave)
    await brave.start()
    await brave.connect()
    own = await CDP.connect(find_ws_url(throwaway_chrome, timeout=20))  # the user, by hand
    try:
        gmail, page = await open_page(own, inbox_sites["gmail"] + "brain/gmail.html")
        shop, _ = await open_page(own, other + "brain/orders.html")
        brave.brain_site = inbox_site
        assert await until(lambda: {gmail, shop} <= {tab["target"] for tab in brave.tabs()}, 10)
        assert brave.brain_tabs() == []  # the switch is off
        brave.brain_reading = lambda: True
        assert [tab["target"] for tab in brave.brain_tabs()] == [gmail]
        answer = await brave.run_reader(gmail, "brain", "read", "gmail", {})
        assert answer["known"] is True and [item["id"] for item in answer["items"]] == ["t1", "t2"]
        assert await page("typeof globalThis.AIB") == "undefined"  # the page never sees the reader
        with pytest.raises(WorldError):
            await brave.run_reader(shop, "brain", "read", "region", {"selector": "#orders", "url_match": "x"})
        assert brave.relay.upstream_opens == 1  # one connection: Brave asked "Allow remote debugging?" once
    finally:
        await own.close()
        await server.stop()
        await brave.close()
        stop_pages()
