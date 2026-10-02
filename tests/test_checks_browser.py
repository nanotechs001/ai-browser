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
