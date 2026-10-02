"""Bot checks in a throwaway Chrome: a check is seen and handed to the user, never touched; pages that only mention one
read normally. The Browser alone first; the Engine's hold follows (Task 7 adds those tests below)."""

import asyncio
import re
import time

import pytest

from ai_browser.checks import KINDS, Check
from ai_browser.chrome import chrome_binary
from ai_browser.render import render_check
from ai_browser.steps import parse_steps

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
CHECK_PAGES = {"checks/unusual.html": "traffic", "checks/px.html": "perimeterx", "checks/akamai.html": "akamai",
               "checks/captcha.html": "captcha"}
ELEMENT = re.compile(r"^e\d+\s")


def record_activations(monkeypatch) -> list[str]:
    """Every Target.activateTarget sent from now on: the tabs brought to the front."""
    from ai_browser.cdp import CDP

    activated, original = [], CDP.send

    async def spy(self, method, params=None, *args, **kwargs):
        if method == "Target.activateTarget":
            activated.append((params or {}).get("targetId"))
        return await original(self, method, params, *args, **kwargs)

    monkeypatch.setattr(CDP, "send", spy)
    return activated


def element_of(page: str, name: str) -> str:
    return next(line.split()[0] for line in page.splitlines() if f'"{name}"' in line)


@CHROME
async def test_each_check_page_is_handed_over_with_nothing_to_click(chrome_browser, monkeypatch):
    browser, base, _ = chrome_browser
    activated = record_activations(monkeypatch)
    for page, kind in CHECK_PAGES.items():
        text = await browser.open(base + page)
        tab = browser.current
        assert text == render_check(Check(kind, "localhost"), tab.key), page
        assert not any(ELEMENT.match(line) for line in text.splitlines()) and "text:" not in text
        assert tab.target in activated, page


@CHROME
async def test_a_batch_stops_where_it_lands_on_a_check(chrome_browser):
    browser, base, _ = chrome_browser
    await browser.open(base + "form.html")
    out = await browser.act(parse_steps([f"goto {base}checks/unusual.html", f"goto {base}checks/counter.html?second"]))
    lines = out.splitlines()
    assert lines[0].startswith(f"✓ goto {base}checks/unusual.html")
    assert lines[1] == "– skipped 1 step (the batch stopped here: see below)"
    assert lines[2] == render_check(Check("traffic", "localhost"), browser.current.key).splitlines()[0]
    assert not any("counter.html?second" in request for request in browser.current.requests.values())  # never sent


@CHROME
async def test_a_check_in_a_popup_stops_the_batch_there(chrome_browser):
    browser, base, _ = chrome_browser
    page = await browser.open(base + "checks/opener.html")
    opener = browser.current
    out = await browser.act(parse_steps([f"click {element_of(page, 'Search flights')}",
                                         f"click {element_of(page, 'Later')}"]))
    popup = browser.current
    assert popup is not opener and f"⛔ bot check in tab {popup.key} (localhost)" in out
    assert "– skipped 1 step (the batch stopped here: see below)" in out and "✓ click" in out.splitlines()[0]


@CHROME
async def test_pages_that_mention_checks_or_carry_a_box_read_normally(chrome_browser):
    browser, base, _ = chrome_browser
    article = await browser.open(base + "checks/article.html")
    assert article.startswith('page  "How sites check for bots (test article)"') and "⛔" not in article
    form = await browser.open(base + "checks/form-box.html")
    assert "frames: [bot check box: the user ticks it]" in form and "⛔" not in form
    assert any('"Your name"' in line for line in form.splitlines())
    state = await browser.state()
    assert state["check"] is None and len(state["boxes"]) == 1


@CHROME
async def test_cloudflares_own_check_gets_a_few_seconds(chrome_browser):
    from ai_browser.browser import CF_WAIT

    browser, base, _ = chrome_browser
    moved = await browser.open(base + "checks/cf-auto")
    assert moved.startswith('page  "Counter"')
    started = time.monotonic()
    stuck = await browser.open(base + "checks/cf")
    assert stuck.startswith(f"⛔ bot check in tab {browser.current.key} (localhost): {KINDS['cloudflare']}")
    assert time.monotonic() - started >= CF_WAIT


@CHROME
async def test_the_engines_hooks_hold_skip_and_wait(chrome_browser):
    browser, base, _ = chrome_browser
    held = []

    async def hold(tab, check):
        held.append((tab.key, check))
        return "HELD"

    browser.on_check(hold)
    assert await browser.open(base + "checks/unusual.html") == "HELD"
    assert held == [(browser.current.key, Check("traffic", "localhost"))]
    browser.skipped_site = lambda url: "SKIPPED" if "/form.html" in url else None
    assert await browser.open(base + "form.html") == "SKIPPED"
    page = await browser.open(base + "checks/counter.html")
    out = await browser.act(parse_steps([f"goto {base}form.html", f"goto {base}checks/counter.html?after"]))
    assert out.splitlines()[-1] == "SKIPPED" and "– skipped 1 step" in out
    page = await browser.open(base + "checks/counter.html")
    browser.waiting = lambda: "WAIT"
    assert await browser.act(parse_steps([f"click {element_of(page, 'Count')}"])) == "WAIT"
    assert await browser._eval("document.getElementById('count').textContent") == "0"


# ---- the Engine: the whole session holds until the user deals with the check ----------------------------------------


async def started(chrome_engine):
    """The Engine on the throwaway Chrome (standing in for the user's own browser): (engine, base)."""
    engine, base, _ = chrome_engine
    assert "your own Chrome" in (await engine.sandbox_start(chrome=True)).text
    return engine, base


async def page_js(engine, tab, expression):
    """A value from the page itself, read through CDP: what the user would see, whatever the engine says."""
    reply = await engine.cdp.send("Runtime.evaluate", {"expression": expression, "returnByValue": True},
                                  session_id=tab.session)
    return reply["result"].get("value")


async def solve(engine, base) -> str:
    """What the user does: the held tab leaves the check (the test navigates it through CDP); then observe."""
    tab = engine.browser.current
    await engine.cdp.send("Page.navigate", {"url": base + "checks/counter.html"}, session_id=tab.session)
    for _ in range(50):
        text = (await engine.observe()).text
        if "is gone: carrying on" in text:
            return text
        await asyncio.sleep(0.1)
    raise AssertionError("the hold never ended")


@CHROME
async def test_the_engine_holds_hands_over_and_logs_a_check(chrome_engine, monkeypatch):
    import json

    engine, base = await started(chrome_engine)
    activated = record_activations(monkeypatch)
    for page, kind in (("checks/unusual.html", "traffic"), ("checks/captcha.html", "captcha")):
        text = (await engine.open(base + page)).text
        tab = engine.browser.current
        assert text.startswith(render_check(Check(kind, "localhost"), tab.key)), text
        assert (engine.gate.held.tab_key, engine.gate.held.check.kind) == (tab.key, kind)
        assert tab.target in activated
        await solve(engine, base)
        assert engine.gate.held is None
    log = [json.loads(line) for line in (engine.log.dir / "log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [entry["outcome"] for entry in log if entry["tool"] == "open"][-2:] == ["check", "check"]


@CHROME
async def test_while_a_check_waits_nothing_else_runs(chrome_engine, monkeypatch):
    engine, base = await started(chrome_engine)
    first = (await engine.open(base + "checks/counter.html")).text
    counter, count = engine.browser.current, element_of(first, "Count")
    handed = (await engine.open(base + "checks/unusual.html", new_tab=True)).text
    held = engine.browser.current
    assert handed.startswith(f"⛔ bot check in tab {held.key} (localhost)")
    activated = record_activations(monkeypatch)
    waiting = f"⏸ waiting for the user: tab {held.key} (localhost) shows a bot check."
    refused = [engine.act([f"click {count}"]), engine.act(["reload"]), engine.act([f"goto {base}checks/counter.html"]),
               engine.js("1 + 1"), engine.screenshot(), engine.extract("links"), engine.tabs("new"),
               engine.tabs("switch", counter.key), engine.tabs("close", counter.key),
               engine.open(base + "checks/counter.html"), engine.qa(base + "qa/index.html"), engine.shell("ls"),
               engine.sandbox_start(chrome=True), engine.sandbox_stop()]
    for call in refused:
        assert (await call).text.startswith(waiting)
    assert activated == []  # a refused call never moves the user's focus
    assert await page_js(engine, counter, "document.getElementById('count').textContent") == "0"
    assert set(engine.browser.owned) == {counter.key, held.key} and engine.browser.current is held
    listing = (await engine.tabs("list")).text
    assert any(line[2:].startswith(f"{held.key}  ") and line.endswith("(bot check: waiting for the user)")
               for line in listing.splitlines())
    assert (await engine.page_log()).text.startswith("page log")
    assert (await engine.write_file("note.txt", "kept")).text.startswith("wrote")
    assert (await engine.read_file("note.txt")).text.startswith("kept")
    assert (await engine.observe()).text.startswith(f"⛔ bot check in tab {held.key}")  # still there: handed over again
    assert held.target in activated


@CHROME
async def test_once_the_user_solves_it_every_tool_works_again(chrome_engine):
    engine, base = await started(chrome_engine)
    await engine.open(base + "checks/unusual.html")
    tab = engine.browser.current
    solved = await solve(engine, base)
    assert solved.startswith(f"(the bot check in tab {tab.key} is gone: carrying on)") and '"Count"' in solved
    assert 'page  "Form test"' in (await engine.open(base + "form.html")).text


@CHROME
async def test_a_closed_check_tab_makes_its_site_off_limits(chrome_engine):
    from urllib.parse import quote

    engine, base = await started(chrome_engine)
    other = base.replace("localhost", "127.0.0.1")
    await engine.open(other + "checks/counter.html")  # the session's own tab, on another site
    await engine.open(base + "checks/unusual.html", new_tab=True)
    held = engine.browser.current
    await engine.cdp.send("Target.closeTarget", {"targetId": held.target})  # the user closes it
    await asyncio.sleep(0.3)
    listing = (await engine.tabs("list")).text
    assert listing.startswith("(the tab with the bot check was closed, so localhost is off-limits for the rest of "
                              "this task)")
    refused = "⛔ localhost is off-limits in this task: the user skipped it after a bot check."
    assert (await engine.open(base + "checks/counter.html")).text.startswith(refused)
    assert (await engine.act([f"goto {base}form.html"])).text.startswith(refused)
    assert (await engine.tabs("new", url=base + "form.html")).text.startswith(refused)
    assert (await engine.qa(base + "qa/index.html")).text.startswith(refused)
    assert (await engine.shell("curl -s http://localhost:8000/")).text.startswith("⛔ the shell doesn't reach localhost")
    await engine.sandbox_stop()
    assert "your own Chrome" in (await engine.sandbox_start(chrome=True)).text  # a new connection, the same Engine
    assert (await engine.open(base + "checks/counter.html")).text.startswith(refused)
    redirected = (await engine.open(other + "checks/go?to=" + quote(base + "checks/counter.html", safe=""))).text
    assert redirected.startswith(refused) and '"Count"' not in redirected


@CHROME
async def test_the_agent_may_close_the_held_tab_when_the_user_asks(chrome_engine):
    engine, base = await started(chrome_engine)
    await engine.open(base + "checks/counter.html")
    await engine.open(base + "checks/akamai.html", new_tab=True)
    held = engine.browser.current
    closed = (await engine.tabs("close", held.key)).text
    assert closed.startswith("(the tab with the bot check was closed, so localhost is off-limits for the rest of "
                             "this task)")
    assert engine.gate.held is None and engine.gate.skipped == {"localhost"} and held.key not in engine.browser.owned


@CHROME
async def test_a_reconnect_that_loses_the_check_tab_skips_its_site(chrome_engine):
    engine, base = await started(chrome_engine)
    await engine.open(base + "checks/unusual.html")
    await engine.cdp.close()  # the connection drops while the check waits
    result = (await engine.observe()).text
    assert "reconnected to your Chrome" in result
    assert "(the tab with the bot check was closed, so localhost is off-limits for the rest of this task)" in result
    assert engine.gate.held is None and "localhost" in engine.gate.skipped


@CHROME
async def test_a_hold_ends_even_after_a_reconnect_that_failed(chrome_engine):
    engine, base = await started(chrome_engine)
    await engine.open(base + "checks/unusual.html")
    await engine._teardown(stop_container=False)  # as after a reconnect that failed: no browser at all, the tab gone
    result = (await engine.observe()).text
    assert "(the tab with the bot check was closed, so localhost is off-limits for the rest of this task)" in result
    assert engine.gate.held is None and "localhost" in engine.gate.skipped
    other = base.replace("localhost", "127.0.0.1")  # another site: every tool works again
    assert 'page  "Counter"' in (await engine.open(other + "checks/counter.html")).text


def never_starts(monkeypatch) -> None:
    """A refused call must start nothing: no Docker sandbox, no browser connection (and no container left behind if
    the test runs before its implementation)."""
    from ai_browser.engine import Engine

    async def refuse(self, *args, **kwargs):
        raise AssertionError("a refused call started a browser")

    monkeypatch.setattr(Engine, "_start", refuse)
    monkeypatch.setattr(Engine, "_start_chrome", refuse)


async def test_in_the_sandbox_the_hand_off_gives_the_live_view(tmp_path):
    from types import SimpleNamespace

    from ai_browser.browser import Tab
    from ai_browser.engine import Engine
    from ai_browser.sandbox import SandboxInfo
    from ai_browser.skills import Catalog

    engine = Engine(home=tmp_path / "home", catalog=Catalog([], set()))
    fronted = []

    async def bring_to_front(tab):
        fronted.append(tab.key)

    engine.browser = SimpleNamespace(bring_to_front=bring_to_front)
    engine.info = SandboxInfo("aib-default", "default", "", tmp_path / "work", False, False)
    engine.live = SimpleNamespace(url="http://127.0.0.1:8770/live?token=abc")
    text = await engine._on_check(Tab("t2", "TARGET", "SESSION"), Check("captcha", "shop.example.com"))
    assert "The tab is now in front. The user can solve it in the live view: http://127.0.0.1:8770/live?token=abc" in text
    assert fronted == ["t2"] and (engine.gate.held.tab_key, engine.gate.held.where) == ("t2", "session")


async def test_the_shell_refuses_the_crawl_pattern_before_anything_starts(tmp_path, monkeypatch):
    from ai_browser.engine import Engine
    from ai_browser.skills import Catalog

    never_starts(monkeypatch)
    engine = Engine(home=tmp_path / "home", catalog=Catalog([], set()))
    result = await engine.shell("cat urls.txt | xargs -P 10 -I{} curl -A 'Mozilla/5.0' {}")
    assert result.text.startswith("⛔ the shell doesn't send a browser's user agent") and engine.browser is None
    engine.gate.skipped.add("google.com")
    result = await engine.shell("curl -s https://www.google.com/search?q=flights")
    assert result.text.startswith("⛔ the shell doesn't reach google.com") and engine.browser is None


async def test_a_refused_qa_starts_nothing(tmp_path, monkeypatch):
    from ai_browser.engine import Engine
    from ai_browser.skills import Catalog

    never_starts(monkeypatch)
    engine = Engine(home=tmp_path / "home", catalog=Catalog([], set()))
    assert (await engine.qa("https://www.google.com/search?q=flights")).text.startswith(
        "⛔ www.google.com is a big site")
    engine.gate.qa_stop("shop.example.com", time.time() + 60, "429, it asked for 1 minute")
    assert (await engine.qa("https://shop.example.com/")).text.startswith("QA stopped on shop.example.com at ")
    assert engine.browser is None and engine.sandboxes is None


@CHROME
async def test_qa_holds_the_session_at_a_check_it_finds(chrome_engine):
    engine, base = await started(chrome_engine)
    text = (await engine.qa(base + "qa2/check.html")).text
    held = engine.gate.held
    assert held is not None and held.where == "session" and held.check == Check("traffic", "localhost")
    assert text.startswith(f"⛔ bot check in tab {held.tab_key} (localhost)") and "\n\nqa " in text
    assert engine.browser.current.key == held.tab_key and held.tab_key in engine.browser.owned
    assert (await engine.open(base + "form.html")).text.startswith("⏸ waiting for the user")
    assert "is gone: carrying on" in await solve(engine, base)


@CHROME
async def test_qa_waits_out_a_hosts_pause_and_can_ignore_robots_when_asked(chrome_engine):
    engine, base = await started(chrome_engine)
    busy = (await engine.qa(base + "qa2/busy.html")).text
    assert "stopped early: localhost answered 429 Too Many Requests" in busy
    again = (await engine.qa(base + "qa-robots/index.html", ignore_robots=True)).text
    assert again.startswith("QA stopped on localhost at ") and \
        "(429, it asked for 2 minutes): qa can run there again from " in again
    assert 'page  "Counter"' in (await engine.open(base + "checks/counter.html")).text  # single pages stay allowed
    engine.gate.qa_stopped.clear()  # as if the two minutes had passed
    ignored = (await engine.qa(base + "qa-robots/index.html", ignore_robots=True)).text
    assert "robots.txt: ignored at the user's request" in ignored
