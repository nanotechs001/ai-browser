import asyncio
import statistics
import time

import pytest

from ai_browser import testpages
from ai_browser.browser import Browser
from ai_browser.cdp import CDP
from ai_browser.config import MAX_ROWS, Config
from ai_browser.workfs import WorkDir

pytestmark = pytest.mark.docker

STATE_KEYS = {"url", "title", "w", "h", "scrollY", "scrollH", "above", "below", "frames", "rows", "text", "doc",
              "truncated", "find"}


@pytest.fixture(scope="session")
async def env(sandbox):
    boxes, info = sandbox
    base, other = testpages.serve(boxes, info)
    cdp = await CDP.connect(boxes.ws_url(info))
    browser = Browser(cdp, WorkDir(info.work_host, "pytest-observe"), Config())
    await browser.start()
    yield browser, base, other
    await browser.close()
    await cdp.close()


def by_name(state, name):
    matches = [row for row in state["rows"] if row["name"] == name]
    assert matches, f"no row named {name!r} in {[r['name'] for r in state['rows']]}"
    return matches[0]


async def test_open_returns_rendered_table(env):
    browser, base, _ = env
    out = await browser.open(base + "form.html")
    assert out.startswith('page  "Form test"')
    assert '"Submit order" ⚠' in out


async def test_state_has_the_render_schema(env):
    browser, base, _ = env
    await browser.open(base + "form.html")
    state = await browser.state()
    assert STATE_KEYS <= set(state)
    assert (state["w"], state["h"]) == (1440, 900)


async def test_form_rows(env):
    browser, base, _ = env
    await browser.open(base + "form.html")
    state = await browser.state()
    assert by_name(state, "Full name")["value"] == "Ada"
    size = by_name(state, "Size")
    assert (size["role"], size["value"], size["options"]) == ("select", "Medium", ["Small", "Medium", "Large"])
    assert by_name(state, "Subscribe to newsletter")["checked"] is False
    assert by_name(state, "Submit order")["risky"] is True
    assert not by_name(state, "Save draft").get("risky")
    assert by_name(state, "Privacy")["href"] == "/privacy.html"
    assert by_name(state, "I agree")["role"] == "checkbox"


async def test_password_value_is_never_shown(env):
    browser, base, _ = env
    await browser.open(base + "form.html")
    await browser.cdp.send("Runtime.evaluate", {"expression": "document.getElementById('pw').value = 'hunter2'"},
                           session_id=browser.session_id)
    state = await browser.state()
    password = by_name(state, "Password")
    assert password["role"] == "password" and password.get("value") is None
    assert "hunter2" not in await browser.observe()


async def test_same_origin_frame_rows_are_tagged(env):
    browser, base, _ = env
    await browser.open(base + "frames.html")
    for _ in range(50):  # the map, a frame from another site, is read once its address has come
        state = await browser.state()
        if any(row.get("frame") == "map" for row in state["rows"]):
            break
        await asyncio.sleep(0.1)
    assert {row.get("frame") for row in state["rows"] if row["name"] == "Inner button"} == {"canvas", "map"}
    assert by_name(state, "Top button").get("frame") is None
    frames = {frame["label"]: frame["cross"] for frame in state["frames"]}
    assert frames == {"canvas": False, "map": True}
    assert "frames: [canvas] [map]" in await browser.observe()


async def test_shadow_dom_controls_are_found(env):
    browser, base, _ = env
    await browser.open(base + "shadow.html")
    state = await browser.state()
    assert by_name(state, "Shadow button")["role"] == "button"
    assert by_name(state, "Shadow input")["role"] == "textbox"


async def test_long_page_counts_and_find(env):
    browser, base, _ = env
    await browser.open(base + "long.html")
    state = await browser.state()
    assert state["below"] > 50
    assert all(row["name"] != "Footer link 90" for row in state["rows"])
    found = await browser.state(find="Footer link 90")
    assert [row["name"] for row in found["rows"]] == ["Footer link 90"]
    assert 'find  "Footer link 90" · 1 match' in await browser.observe(find="Footer link 90")


async def test_ids_are_stable_between_reads(env):
    browser, base, _ = env
    await browser.open(base + "form.html")
    first = {row["name"]: row["id"] for row in (await browser.state())["rows"]}
    second = {row["name"]: row["id"] for row in (await browser.state())["rows"]}
    assert first == second


async def test_open_waits_for_late_content(env):
    browser, base, _ = env
    started = time.monotonic()
    await browser.open(base + "spa.html")
    state = await browser.state()
    assert by_name(state, "Loaded button")
    assert time.monotonic() - started < 3


async def test_text_only_page_opens_without_waiting_for_controls(env):
    browser, base, _ = env
    started = time.monotonic()
    out = await browser.open(base + "textonly.html")
    assert time.monotonic() - started < 1
    assert "Terms of service" in out


async def test_heavy_page_capped_and_fast(env):
    browser, base, _ = env
    await browser.open(base + "heavy.html")
    state = await browser.state()
    assert len(state["rows"]) == MAX_ROWS
    assert state["truncated"] > 0
    timings = []
    for _ in range(5):
        started = time.perf_counter()
        await browser.state()
        timings.append(time.perf_counter() - started)
    assert statistics.median(timings) < 0.3
    assert len(await browser.observe()) < 12_000


async def test_rows_follow_reading_order_on_uneven_lines(env):
    browser, base, _ = env
    await browser.open(base + "heavy.html")
    names = [row["name"] for row in (await browser.state())["rows"]]
    assert names[:3] == ["Item 1", "Item 2", "Item 3"]


async def test_clipping_never_splits_an_emoji(env):
    browser, base, _ = env
    await browser.open(base + "unicode.html")
    state = await browser.state()
    for row in state["rows"]:
        row["name"].encode("utf-8")
        (row.get("value") or "").encode("utf-8")
    state["text"].encode("utf-8")
    (await browser.observe()).encode("utf-8")


async def test_covered_button_is_still_listed(env):
    browser, base, _ = env
    await browser.open(base + "covered.html")
    assert by_name(await browser.state(), "Hidden behind overlay")
