import time

import pytest

from ai_browser import browser as browser_module
from ai_browser import testpages
from ai_browser.browser import Browser
from ai_browser.cdp import CDP
from ai_browser.config import Config
from ai_browser.steps import parse_steps
from ai_browser.workfs import WorkDir

pytestmark = pytest.mark.docker


@pytest.fixture(scope="session")
async def env(sandbox):
    boxes, info = sandbox
    base, _ = testpages.serve(boxes, info)
    cdp = await CDP.connect(boxes.ws_url(info))
    browser = Browser(cdp, WorkDir(info.work_host, "pytest-act"), Config())
    await browser.start()
    yield browser, base
    await browser.close()
    await cdp.close()


async def ids(browser) -> dict[str, str]:
    return {row["name"]: row["id"] for row in (await browser.state())["rows"]}


async def run(browser, *steps, confirmed=False) -> str:
    return await browser.act(parse_steps(list(steps)), confirmed=confirmed)


async def js(browser, expression):
    return await browser._eval(expression)


async def test_click_increments_counter(env):
    browser, base = env
    await browser.open(base + "form.html")
    out = await run(browser, f"click {(await ids(browser))['Increment']}")
    assert out.startswith("✓ click")
    assert await js(browser, "document.getElementById('count').textContent") == "1"


async def test_dblclick(env):
    browser, base = env
    await browser.open(base + "menu.html")
    await run(browser, f"dblclick {(await ids(browser))['Double me']}")
    assert await js(browser, "document.getElementById('dbl').textContent") == "Double clicked"


async def test_hover_reveals_menu_in_the_diff(env):
    browser, base = env
    await browser.open(base + "menu.html")
    out = await run(browser, f"hover {(await ids(browser))['Products']}")
    assert '"Alpha"' in out
    assert any(line.startswith("+ ") and '"Alpha"' in line for line in out.splitlines())


async def test_type_replaces_value(env):
    browser, base = env
    await browser.open(base + "form.html")
    name = (await ids(browser))["Full name"]
    out = await run(browser, f'type {name} "Bob"')
    assert await js(browser, "document.getElementById('name').value") == "Bob"
    assert f'~ {name}' in out and '"Bob"' in out


async def test_append_adds_to_value(env):
    browser, base = env
    await browser.open(base + "form.html")
    await run(browser, f'append {(await ids(browser))["Full name"]} " Lovelace"')
    assert await js(browser, "document.getElementById('name').value") == "Ada Lovelace"


async def test_type_unicode_roundtrip(env):
    browser, base = env
    await browser.open(base + "form.html")
    notes = (await ids(browser))["Notes"]
    text = "Zürich – 東京 😀"
    await run(browser, f'type {notes} "{text}"')
    assert await js(browser, "document.getElementById('notes').value") == text
    row = next(row for row in (await browser.state())["rows"] if row["id"] == notes)
    assert row["value"] == text


async def test_type_into_focused_element(env):
    browser, base = env
    await browser.open(base + "form.html")
    await run(browser, f"click {(await ids(browser))['Email']}", 'type "a@b.co"')
    assert await js(browser, "document.getElementById('email').value") == "a@b.co"


async def test_contenteditable_replace_touches_only_that_block(env):
    browser, base = env
    await browser.open(base + "editor.html")
    await run(browser, f'type {(await ids(browser))["Block 1"]} "New text"')
    blocks = await js(browser, "[...document.querySelectorAll('.block')].map((b) => b.innerText.trim())")
    assert blocks == ["New text", "Second block"]


async def test_key_enter_submits_search_form(env):
    browser, base = env
    await browser.open(base + "form.html")
    out = await run(browser, f'type {(await ids(browser))["Search"]} "cats"', "key Enter")
    assert 'page  "Privacy"' in out
    assert "q=cats" in await js(browser, "location.href")


async def test_select_by_label_and_value(env):
    browser, base = env
    await browser.open(base + "form.html")
    size = (await ids(browser))["Size"]
    await run(browser, f'select {size} "Small"')
    assert await js(browser, "document.getElementById('size').selectedOptions[0].label") == "Small"
    await run(browser, f'select {size} "lg"')
    assert await js(browser, "document.getElementById('size').selectedOptions[0].label") == "Large"
    out = await run(browser, f'select {size} "Huge"')
    assert out.startswith("✗ error") and "Small" in out


async def test_check_and_uncheck_are_idempotent(env):
    browser, base = env
    await browser.open(base + "form.html")
    box = (await ids(browser))["Subscribe to newsletter"]
    await run(browser, f"check {box}")
    assert await js(browser, "document.getElementById('news').checked") is True
    out = await run(browser, f"check {box}")
    assert "already" in out
    assert await js(browser, "document.getElementById('news').checked") is True
    await run(browser, f"uncheck {box}")
    assert await js(browser, "document.getElementById('news').checked") is False


async def test_check_visually_hidden_checkbox_through_its_label(env):
    browser, base = env
    await browser.open(base + "form.html")
    await run(browser, f"check {(await ids(browser))['I agree']}")
    assert await js(browser, "document.getElementById('agree').checked") is True


async def test_drag_html5_list(env):
    browser, base = env
    await browser.open(base + "dnd.html")
    found = await ids(browser)
    await run(browser, f"drag {found['A3']} {found['A1']}")
    assert await js(browser, "document.getElementById('order-h5').textContent") == "A3,A1,A2"


async def test_drag_mouse_list(env):
    browser, base = env
    await browser.open(base + "dnd.html")
    found = await ids(browser)
    await run(browser, f"drag {found['B3']} {found['B1']}")
    assert await js(browser, "document.getElementById('order-js').textContent") == "B3,B1,B2"


async def test_upload_to_hidden_file_input(env):
    browser, base = env
    browser.work.to_host("logo.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    await browser.open(base + "upload.html")
    chooser = (await ids(browser))["Choose image"]
    await run(browser, f"upload {chooser} logo.png")
    assert await js(browser, "document.getElementById('names').textContent") == "logo.png"
    out = await run(browser, f"upload {chooser} missing.png")
    assert out.startswith("✗ error") and "missing.png" in out


async def test_scroll_down_top_and_to_element(env):
    browser, base = env
    await browser.open(base + "long.html")
    await run(browser, "scroll down")
    assert (await browser.state())["scrollY"] > 0
    await run(browser, "scroll top")
    assert (await browser.state())["scrollY"] == 0
    target = (await browser.state(find="Footer link 90"))["rows"][0]["id"]
    await run(browser, f"scroll {target}")
    assert target in {row["id"] for row in (await browser.state())["rows"]}


async def test_wait_for_text(env):
    browser, base = env
    await browser.open(base + "form.html")
    out = await run(browser, f"click {(await ids(browser))['Save draft']}", 'wait "Draft saved"')
    assert out.splitlines()[1].startswith('✓ wait "Draft saved"')


async def test_wait_for_text_times_out(env, monkeypatch):
    browser, base = env
    monkeypatch.setattr(browser_module, "WAIT_TEXT_CAP", 1)
    await browser.open(base + "form.html")
    started = time.monotonic()
    out = await run(browser, 'wait "Never appears"')
    assert out.startswith("✗ error") and "1s" in out
    assert time.monotonic() - started < 3


async def test_wait_for_text_survives_a_navigation(env):
    browser, base = env
    await browser.open(base + "delayed.html")
    out = await run(browser, f"click {(await ids(browser))['Log in']}", 'wait "Nothing to see"')
    lines = out.splitlines()
    assert lines[0].startswith("✓ click") and lines[1].startswith('✓ wait "Nothing to see"')
    assert 'page  "Privacy"' in out


async def test_step_results_survive_a_failing_final_read(env, monkeypatch):
    from ai_browser.cdp import CDPError

    browser, base = env
    await browser.open(base + "form.html")
    increment = (await ids(browser))["Increment"]

    async def broken(*args, **kwargs):
        raise CDPError("Inspected target navigated or closed")

    monkeypatch.setattr(browser, "state", broken)
    out = await run(browser, f"click {increment}")
    assert out.startswith("✓ click")
    assert "observe" in out


async def out_text(browser):
    return await js(browser, "document.getElementById('out').textContent")


async def test_alert_is_accepted_and_reported(env):
    browser, base = env
    await browser.open(base + "dialogs.html")
    started = time.monotonic()
    out = await run(browser, f"click {(await ids(browser))['Alert me']}")
    assert time.monotonic() - started < 5
    assert out.startswith("✓ click") and "Hello alert" in out.splitlines()[0]
    assert await out_text(browser) == "after alert"


async def test_confirm_is_dismissed_unless_confirmed(env):
    browser, base = env
    await browser.open(base + "dialogs.html")
    clear = (await ids(browser))["Clear list"]
    started = time.monotonic()
    out = await run(browser, f"click {clear}")
    assert time.monotonic() - started < 5
    assert out.startswith("⛔") and "Really clear the list?" in out and "confirmed=true" in out
    assert await out_text(browser) == "cancelled"
    await run(browser, f"click {clear}", confirmed=True)
    assert await out_text(browser) == "confirmed"


async def test_prompt_gets_its_default_answer_when_confirmed(env):
    browser, base = env
    await browser.open(base + "dialogs.html")
    await run(browser, f"click {(await ids(browser))['Ask name']}", confirmed=True)
    assert await out_text(browser) == "prompt: Ada"


async def test_leaving_unsaved_changes_needs_confirmation(env):
    browser, base = env
    await browser.open(base + "dialogs.html")
    await run(browser, f"click {(await ids(browser))['Make changes']}")
    started = time.monotonic()
    out = await run(browser, f"goto {base}privacy.html")
    assert time.monotonic() - started < 5
    assert out.startswith("⛔") and "leav" in out
    assert await out_text(browser) == "dirty"
    out = await run(browser, f"goto {base}privacy.html", confirmed=True)
    assert 'page  "Privacy"' in out


async def test_goto_back_forward(env):
    browser, base = env
    await browser.open(base + "form.html")
    assert 'page  "Privacy"' in await run(browser, f"goto {base}privacy.html")
    assert 'page  "Form test"' in await run(browser, "back")
    assert 'page  "Privacy"' in await run(browser, "forward")


async def test_changed_element_is_stale_and_not_clicked(env):
    browser, base = env
    await browser.open(base + "form.html")
    save = (await ids(browser))["Save draft"]
    await js(browser, "document.getElementById('save').textContent = 'Renamed'")
    out = await run(browser, f"click {save}")
    assert out.startswith("✗ stale") and "changed" in out
    assert await js(browser, "document.getElementById('status').textContent") == "Ready"


async def test_check_after_a_rename_in_the_same_batch_is_stale(env):
    browser, base = env
    await browser.open(base + "rename.html")
    found = await ids(browser)
    out = await run(browser, f"click {found['Shift']}", f"check {found['Post A']}")
    assert out.splitlines()[1].startswith("✗ stale") and "changed" in out
    assert await js(browser, "document.getElementById('post').checked") is False


async def test_reads_the_model_never_saw_do_not_refresh_identity(env):
    browser, base = env
    await browser.open(base + "rename.html")
    post = (await ids(browser))["Post A"]
    await js(browser, "document.getElementById('label').textContent = 'Post B'")
    await browser.state(find="zzz")  # a search that shows no rows
    out = await run(browser, f"click {post}")
    assert out.startswith("✗ stale") and "changed" in out
    assert await js(browser, "document.getElementById('post').checked") is False


async def test_button_labelled_through_a_slot_is_named_and_clickable(env):
    browser, base = env
    await browser.open(base + "slots.html")
    found = await ids(browser)
    assert "Save changes" in found
    out = await run(browser, f"click {found['Save changes']}")
    assert out.startswith("✓ click")
    assert await js(browser, "document.getElementById('out').textContent") == "Saved via slot"


async def test_sensitive_field_values_are_masked(env):
    browser, base = env
    await browser.open(base + "slots.html")
    await js(browser, "card.value = '4242424242424242'; otp.value = '918273'; shown.value = 'hunter2'")
    state = await browser.state()
    values = {row["name"]: row.get("value") for row in state["rows"]}
    assert values["Card number"] == values["Code"] == values["Shown password"] == "•••"
    assert values["City"] == "Paris"
    page = await browser.observe()
    for secret in ("4242424242424242", "918273", "hunter2"):
        assert secret not in page


async def test_covered_target_is_not_clicked(env):
    browser, base = env
    await browser.open(base + "covered.html")
    out = await run(browser, f"click {(await ids(browser))['Hidden behind overlay']}")
    assert out.startswith("✗ stale") and "covered" in out
    assert await js(browser, "document.getElementById('under').textContent") == "Hidden behind overlay"


async def test_unknown_id_is_reported(env):
    browser, base = env
    await browser.open(base + "form.html")
    out = await run(browser, "click e9999")
    assert out.startswith("✗ stale") and "gone" in out


async def test_risky_click_needs_confirmation(env):
    browser, base = env
    await browser.open(base + "form.html")
    submit = (await ids(browser))["Submit order"]
    out = await run(browser, f"click {submit}")
    assert out.startswith("⛔ blocked") and "confirmed=true" in out
    assert await js(browser, "document.getElementById('status').textContent") == "Ready"
    await run(browser, f"click {submit}", confirmed=True)
    assert await js(browser, "document.getElementById('status').textContent") == "Order sent"


async def test_navigation_mid_batch_skips_id_steps(env):
    browser, base = env
    await browser.open(base + "form.html")
    found = await ids(browser)
    out = await run(browser, f"click {found['Privacy']}", f'type {found["Full name"]} "x"')
    assert "skipped 1 step" in out
    assert 'page  "Privacy"' in out


async def test_batch_on_one_page_returns_a_diff(env):
    browser, base = env
    await browser.open(base + "form.html")
    found = await ids(browser)
    out = await run(
        browser,
        f'type {found["Full name"]} "Bob"',
        f'type {found["Email"]} "bob@example.com"',
        f'select {found["Size"]} "Large"',
        f"check {found['Subscribe to newsletter']}",
        f"click {found['Increment']}",
    )
    assert sum(line.startswith("✓ ") for line in out.splitlines()) == 5
    assert any(line.startswith("~ ") for line in out.splitlines())
    assert '"Submit order"' not in out


async def test_autocomplete_options_arrive_in_the_same_result(env):
    browser, base = env
    await browser.open(base + "autocomplete.html")
    out = await run(browser, f'type {(await ids(browser))["City"]} "Lo"')
    assert any(line.startswith("+ ") and 'option   "London"' in line for line in out.splitlines())
    await run(browser, f"click {(await ids(browser))['London']}")
    assert await js(browser, "document.getElementById('picked').textContent") == "Picked London"


async def test_type_and_click_inside_same_origin_frame(env):
    browser, base = env
    await browser.open(base + "frames.html")
    # the canvas's own rows: the map, a frame from another site with the same page in it, is read too now
    found = {row["name"]: row["id"] for row in (await browser.state())["rows"] if row.get("frame") == "canvas"}
    await run(browser, f'type {found["Inner name"]} "hi"', f"click {found['Inner button']}")
    frame = "document.querySelector('iframe[name=canvas]').contentDocument"
    assert await js(browser, f"{frame}.getElementById('inner').value") == "hi"
    assert await js(browser, f"{frame}.getElementById('ib').textContent") == "Inner clicked"


async def test_click_inside_shadow_dom(env):
    browser, base = env
    await browser.open(base + "shadow.html")
    await run(browser, f"click {(await ids(browser))['Shadow button']}")
    out = "document.querySelector('x-widget').shadowRoot.getElementById('out').textContent"
    assert await js(browser, out) == "Shadow clicked"
