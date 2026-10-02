"""The engine's app mode: driving AI Browser (the agent's own Chrome) — visible tabs, the user's tabs, extension pages."""

import asyncio
import contextlib

import pytest

from ai_browser.cdp import CDPError
from ai_browser.chrome import chrome_binary

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


def test_app_mode_url_rules():
    from ai_browser.browser import url_problem

    assert url_problem("chrome-extension://abc/options.html", "app")  # AI Browser's pages, password managers...
    assert url_problem("https://example.com", "app") is None
    assert url_problem("file:///etc/hosts", "app") and url_problem("chrome://settings", "app")


@pytest.fixture
async def app_engine(tmp_path, monkeypatch):
    from ai_browser import testpages
    from ai_browser.appbrowser import launch_app_browser, prepare_extension
    from ai_browser.engine import Engine
    from ai_browser.skills import Catalog

    app = launch_app_browser(tmp_path / "profile", prepare_extension(tmp_path, "http://127.0.0.1:1", "t"),
                             headless=True)
    await settled(app)
    monkeypatch.setenv("AIB_BROWSER", "app")
    monkeypatch.setenv("AIB_APP_PROFILE", str(tmp_path / "profile"))
    monkeypatch.setenv("AIB_APP_EXTENSION", app.extension_id)

    async def no_sandbox(self, profile, fresh):  # app mode must never fall back to a Docker sandbox
        raise AssertionError("fell back to the Docker sandbox")

    monkeypatch.setattr(Engine, "_start", no_sandbox)
    base, _, stop = testpages.serve_host()
    engine = Engine(home=tmp_path / "home", default_profile="pytest-app", catalog=Catalog([], set()))
    yield engine, base, app
    await engine.close()
    stop()
    app.close()


async def settled(app) -> None:
    """Wait for the AI Home tab the extension opens in front when it is installed: arriving later, it would take the
    front from the tabs a test opens."""
    from ai_browser.cdp import CDP

    cdp = await CDP.connect(app.ws_url)
    try:
        for _ in range(50):
            if any("/home.html" in info["url"] for info in (await cdp.send("Target.getTargets"))["targetInfos"]):
                return
            await asyncio.sleep(0.1)
    finally:
        await cdp.close()


async def targets_of(app) -> set[str]:
    from ai_browser.cdp import CDP

    cdp = await CDP.connect(app.ws_url)
    try:
        return {t["targetId"] for t in (await cdp.send("Target.getTargets"))["targetInfos"]}
    finally:
        await cdp.close()


@CHROME
async def test_app_mode_works_in_the_visible_browser_and_adopts_user_tabs(app_engine):
    engine, base, app = app_engine
    opened = await engine.open(base + "form.html")
    assert 'page  "Form test"' in opened.text
    assert "AI Browser" in (await engine.sandbox_status()).text
    user_tab = (await engine.cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
    listing = (await engine.tabs("list")).text
    assert "u1" in listing and "privacy.html" in listing and app.extension_id not in listing
    assert 'page  "Privacy"' in (await engine.tabs("switch", "u1")).text
    panel = await engine.open(f"chrome-extension://{app.extension_id}/panel.html")
    assert panel.text.startswith("error")  # AI Browser's own pages are off limits
    assert (await engine.open("file:///etc/hosts")).text.startswith("error")
    await engine.close()
    assert user_tab in await targets_of(app)  # the user's tab stays open


@CHROME
async def test_sandbox_start_keeps_the_app_browser(app_engine):
    engine, base, _ = app_engine
    started = await engine.sandbox_start()
    assert "AI Browser" in started.text and engine.browser.mode == "app"


@CHROME
async def test_a_dead_session_never_takes_the_users_tab_with_it(app_engine, tmp_path):
    import json
    import subprocess
    import sys

    from ai_browser.engine import Engine
    from ai_browser.skills import Catalog

    engine, base, app = app_engine
    await engine.open(base + "form.html")
    user_tab = (await engine.cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
    await engine.tabs("list")
    await engine.tabs("switch", "u1")
    gone = int(subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                              capture_output=True, text=True).stdout)
    records = list((tmp_path / "home" / "sandboxes").glob("*/sessions/*.json"))
    assert not records  # in AI Browser the app, not the next session, cleans up after a session
    for record in records:  # (kept: had there been one, it must not hold the user's tab)
        record.write_text(json.dumps({**json.loads(record.read_text()), "pid": gone}))
    following = Engine(home=tmp_path / "home", default_profile="pytest-app", catalog=Catalog([], set()))
    try:
        await following.tabs("list")  # the next session cleans up after the dead one
        assert user_tab in await targets_of(app)
    finally:
        await following.close()


@CHROME
async def test_tabs_opened_from_an_adopted_tab_stay_the_users(app_engine):
    import asyncio

    from ai_browser.cdp import CDP
    from ai_browser.steps import parse_step

    engine, base, app = app_engine
    user = await CDP.connect(app.ws_url)  # stands in for the user's own clicks
    try:
        user_tab = (await user.send("Target.createTarget", {"url": base + "popup.html"}))["targetId"]
        await engine.tabs("list")
        await engine.tabs("switch", "u1")
        session = (await user.send("Target.attachToTarget", {"targetId": user_tab, "flatten": True}))["sessionId"]
        await user.send("Runtime.evaluate", {"expression": f"window.open('{base}form.html', '_blank'); 1",
                                             "userGesture": True}, session_id=session)
        await asyncio.sleep(1)
        pages = {t["targetId"]: t["url"] for t in (await user.send("Target.getTargets"))["targetInfos"]}
        users_own = [target for target, url in pages.items() if url.endswith("form.html")]
        assert users_own and not {tab.target for tab in engine.browser.owned.values()} & set(users_own)
        link = next(row["id"] for row in (await engine.browser.state())["rows"] if row["name"] == "Preview in new tab")
        followed = await engine.browser.act([parse_step(f"click {link}")])
        assert "opened new tab" in followed  # Claude's own click is followed...
        preview = engine.browser.current.target
        await engine.close()
        alive = {t["targetId"] for t in (await user.send("Target.getTargets"))["targetInfos"]}
        assert {user_tab, preview, *users_own} <= alive  # ...and every tab that came from the user's tab stays open
    finally:
        await user.close()


@CHROME
async def test_claude_lets_go_of_the_users_tab_instead_of_closing_it(app_engine):
    engine, base, app = app_engine
    await engine.open(base + "form.html")
    user_tab = (await engine.cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
    await engine.tabs("list")
    await engine.tabs("switch", "u1")
    adopted = engine.browser.current.key
    closed = (await engine.tabs("close", adopted)).text
    assert user_tab in await targets_of(app) and "u1" in closed  # released, still open, listed as the user's again
    await engine.tabs("switch", "u1")
    ours = next(key for key, tab in engine.browser.owned.items() if not tab.adopted)
    await engine.tabs("switch", ours)
    await engine.tabs("close", ours)  # Claude's own working tab: the fallback must not slip into the user's tab
    assert not engine.browser.current.adopted


async def front_url(app, cdp) -> str:
    """The URL of the tab in front, as Chrome itself sees it (asked from one of the extension's pages)."""
    page = (await cdp.send("Target.createTarget", {"url": f"chrome-extension://{app.extension_id}/panel.html",
                                                   "background": True}))["targetId"]
    session = (await cdp.send("Target.attachToTarget", {"targetId": page, "flatten": True}))["sessionId"]
    ask = {"expression": "location.protocol === 'chrome-extension:' && document.readyState === 'complete' && "
                         "chrome.tabs.query({active: true, lastFocusedWindow: true}).then(tabs => tabs[0].url)",
           "awaitPromise": True, "returnByValue": True}
    try:
        for _ in range(100):  # until the new tab has left about:blank for the extension page
            with contextlib.suppress(CDPError):
                value = (await cdp.send("Runtime.evaluate", ask, session_id=session))["result"].get("value")
                if value:
                    return value
            await asyncio.sleep(0.05)
        raise AssertionError("the extension page never answered")
    finally:
        await cdp.send("Target.closeTarget", {"targetId": page})


@CHROME
async def test_claude_keeps_the_users_page_in_front_until_it_works_somewhere(app_engine):
    from ai_browser.cdp import CDP

    engine, base, app = app_engine
    user = await CDP.connect(app.ws_url)
    try:
        await user.send("Target.createTarget", {"url": base + "privacy.html"})
        await user.send("Target.createTarget", {"url": base + "form.html"})
        pages = lambda infos: {t["targetId"] for t in infos if t["type"] == "page"}
        before = pages((await user.send("Target.getTargets"))["targetInfos"])
        listing = (await engine.tabs("list")).text  # the session's first call opens no blank tab over the page
        assert pages((await user.send("Target.getTargets"))["targetInfos"]) == before
        assert (await front_url(app, user)).endswith("form.html")
        privacy = next(line.split()[0] for line in listing.splitlines() if "privacy.html" in line)
        await engine.tabs("switch", privacy)  # the tab Claude works in comes to the front
        assert (await front_url(app, user)).endswith("privacy.html")
    finally:
        await user.close()


@pytest.fixture
def receiver():
    """A local stand-in for the app's /agent-events: (url, events list)."""
    import http.server
    import json
    import threading

    events = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            events.append({**body, "token": self.headers.get("X-AIB-Agent-Token")})
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/agent-events", events
    server.shutdown()


def as_agent(monkeypatch, url, adopt=None):
    for key, value in {"AIB_APP_AGENT": "a1", "AIB_APP_EVENTS": url, "AIB_APP_AGENT_TOKEN": "tok"}.items():
        monkeypatch.setenv(key, value)
    if adopt:
        monkeypatch.setenv("AIB_APP_ADOPT", adopt)


def reported(events):
    return [(e["kind"], e["target"]) for e in events if e["agent"] == "a1" and e["token"] == "tok"]


@CHROME
async def test_a_background_agent_reports_its_tabs_and_never_takes_focus(app_engine, receiver, monkeypatch):
    from ai_browser.cdp import CDP

    engine, base, app = app_engine
    url, events = receiver
    as_agent(monkeypatch, url)
    user = await CDP.connect(app.ws_url)
    try:
        await user.send("Target.createTarget", {"url": base + "privacy.html"})
        await engine.open(base + "form.html")
        assert (await front_url(app, user)).endswith("privacy.html")  # the user's page stays in front
        working = engine.browser.current.target
        await engine.close()
        await asyncio.sleep(0.3)
        assert ("tab_opened", working) in reported(events) and ("working_tab", working) in reported(events)
        assert working in {t["targetId"] for t in (await user.send("Target.getTargets"))["targetInfos"]}  # left open
    finally:
        await user.close()


@CHROME
async def test_an_agent_started_in_the_users_tab_works_there_in_front(app_engine, receiver, monkeypatch):
    from ai_browser.cdp import CDP

    engine, base, app = app_engine
    url, events = receiver
    user = await CDP.connect(app.ws_url)
    try:
        mine = (await user.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
        await user.send("Target.createTarget", {"url": base + "form.html"})  # another tab is in front now
        as_agent(monkeypatch, url, adopt=mine)
        assert 'page  "Privacy"' in (await engine.observe()).text
        assert (await front_url(app, user)).endswith("privacy.html")
        await asyncio.sleep(0.3)
        assert any(e["kind"] == "tab_opened" and e["target"] == mine and e["adopted"] for e in events)
    finally:
        await user.close()


@CHROME
async def test_app_mode_leaves_downloads_and_session_records_alone(app_engine, receiver, monkeypatch, tmp_path):
    from ai_browser.cdp import CDP

    engine, base, _ = app_engine
    sent = []
    original = CDP.send

    async def spy(self, method, *args, **kwargs):
        sent.append(method)
        return await original(self, method, *args, **kwargs)

    monkeypatch.setattr(CDP, "send", spy)
    as_agent(monkeypatch, receiver[0])
    await engine.open(base + "form.html")
    assert "Browser.setDownloadBehavior" not in sent  # the user's downloads keep going to their Downloads folder
    assert not list((tmp_path / "home" / "sandboxes").glob("*/sessions/*.json"))


@CHROME
async def test_the_agent_carries_on_when_the_user_closes_its_tab(app_engine, receiver, monkeypatch):
    from ai_browser.cdp import CDP

    engine, base, app = app_engine
    url, events = receiver
    as_agent(monkeypatch, url)
    user = await CDP.connect(app.ws_url)
    try:
        await user.send("Target.createTarget", {"url": base + "privacy.html"})
        await engine.open(base + "form.html")
        old = engine.browser.current.target
        await user.send("Target.closeTarget", {"targetId": old})  # the user closes the agent's tab
        await asyncio.sleep(0.3)
        assert "new tab" in (await engine.observe()).text
        new = engine.browser.current.target
        await asyncio.sleep(0.3)
        tail = reported(events)[-3:]
        assert ("tab_closed", old) in tail and ("tab_opened", new) in tail and ("working_tab", new) in tail
        assert (await front_url(app, user)).endswith("privacy.html")  # still the user's page in front
    finally:
        await user.close()


@CHROME
async def test_a_tab_the_user_opens_from_an_agents_tab_stays_theirs(app_engine, receiver, monkeypatch):
    from ai_browser.cdp import CDP
    from ai_browser.steps import parse_step

    engine, base, app = app_engine
    url, events = receiver
    as_agent(monkeypatch, url)
    user = await CDP.connect(app.ws_url)  # stands in for the user's own clicks
    try:
        await engine.open(base + "popup.html")  # the agent's own (background) tab
        own = engine.browser.current.target
        session = (await user.send("Target.attachToTarget", {"targetId": own, "flatten": True}))["sessionId"]
        await user.send("Runtime.evaluate", {"expression": f"window.open('{base}form.html', '_blank'); 1",
                                             "userGesture": True}, session_id=session)
        await asyncio.sleep(1)
        users = [t["targetId"] for t in (await user.send("Target.getTargets"))["targetInfos"]
                 if t["url"].endswith("form.html")]
        assert users and not {tab.target for tab in engine.browser.owned.values()} & set(users)
        reply = await engine.browser.act([parse_step("scroll down")])
        assert "opened new tab" not in reply and engine.browser.current.target == own  # no jump into the user's tab
        await asyncio.sleep(0.3)
        assert not any(target in users for kind, target in reported(events) if kind == "tab_opened")
    finally:
        await user.close()


def test_the_engine_needs_no_development_packages():
    import subprocess
    import sys

    code = "import sys; sys.modules['httpx'] = None; import ai_browser.engine, ai_browser.server"  # httpx is dev-only
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr[-500:]
