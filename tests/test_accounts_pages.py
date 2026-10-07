"""AI accounts on AI Browser's own pages, in a throwaway headless Chrome against a real app server (agents on the fake
claude): Settings → Accounts, the Account pickers, an agent's ask at a limit, and the Brain's card. Every name stays
text, and no email or organisation ever reaches a page."""

import asyncio
import json
import time
from pathlib import Path

import pytest

from ai_browser.chrome import chrome_binary
from fake_accounts import EMAIL, ORG_ID, ORG_NAME, sign_in
from test_bridge import EVENTS
from test_home import home, open_page, stack, until  # noqa: F401

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
HOSTILE_NAME = '<img src=x onerror="alert(1)">'  # an account name is the user's text: it stays text
ROWS = "[...document.querySelectorAll('#accounts .account')]"


async def eventually(predicate, seconds=10):
    for _ in range(int(seconds * 20)):
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


async def open_settings(stack):
    """Settings by itself, with the window's cookie (in the window it is a tab: tests/test_tab_menu.py)."""
    _, settings = await open_page(stack["cdp"], stack["url"] + "/settings")
    assert await until(settings, "document.getElementById('status').dataset.state === 'connected'")
    return settings


@CHROME
async def test_settings_lists_the_accounts_as_text_and_never_an_email(home):
    _, stack = home
    accounts = stack["accounts"]
    work = accounts.add("Work")
    sign_in(work.folder, plan="max")
    accounts.add(HOSTILE_NAME)  # not signed in
    settings = await open_settings(stack)
    assert await until(settings, f"{ROWS}.length === 3 && "
                                 f"{ROWS}.every((row) => row.querySelector('.status').textContent !== 'Checking…')")
    assert await settings(f"{ROWS}.map((row) => row.querySelector('.name').textContent)") == [
        "Default", "Work", HOSTILE_NAME]
    assert await settings(f"{ROWS}.map((row) => row.querySelector('.status').textContent)") == [
        "Signed in · Pro", "Signed in · Max", "Not signed in"]
    first = await settings(f"{ROWS}[0].textContent")
    assert "Used for new agents" in first and "Used by the Brain" in first
    page = await settings("document.documentElement.outerHTML")
    for secret in (EMAIL, ORG_ID, ORG_NAME):
        assert secret not in page
    assert await settings("document.querySelectorAll('#accounts img').length") == 0


@CHROME
async def test_add_sign_in_and_remove_from_settings(home, monkeypatch):
    from ai_browser.app import server as server_module

    _, stack = home
    monkeypatch.setattr(server_module, "SIGNIN_EVERY", 0.2)
    opened = []
    stack["server"].open_terminal = lambda claude, folder, env=None, system=None: opened.append((folder, env)) or True
    accounts = stack["accounts"]
    settings = await open_settings(stack)
    await settings("document.getElementById('account-name').value = 'Work';"
                   "document.getElementById('account-add').click(); true")
    assert await eventually(lambda: len(accounts.list()) == 2)
    work = accounts.list()[1]
    row = f"document.querySelector('#accounts .account[data-id=\"{work.id}\"]')"
    assert await until(settings, f"!!{row}?.querySelector('.command')")  # its Sign in, unfolded
    command = await settings(f"{row}.querySelector('.command').textContent")
    assert "CLAUDE_CONFIG_DIR" in command and work.folder in command  # a shell's words, or PowerShell's on Windows
    await settings(f"{row}.querySelector('.terminal').click(); true")
    assert await eventually(lambda: opened)
    assert opened[0][0] == work.folder and opened[0][1]["CLAUDE_CONFIG_DIR"] == work.folder
    assert await until(settings, f"{row}.querySelector('.waiting')?.textContent === 'Waiting for you to sign in…'")
    sign_in(work.folder)  # the user signs in, in that terminal and their browser
    assert await until(settings, f"{row}.querySelector('.status').textContent === 'Signed in · Pro'", 10)
    assert await settings(f"{row}.querySelector('.signin')") is None
    await settings(f"{row}.querySelector('.remove').click(); true")
    assert await until(settings, f"{row} === null")
    assert accounts.get(work.id) is None and Path(work.folder).is_dir()  # forgotten; its folder stays


@CHROME
async def test_an_existing_folder_is_added_and_a_browsers_data_refused(home, tmp_path):
    _, stack = home
    browser, mine = tmp_path / "claude-desktop-data", tmp_path / "claude-work"
    browser.mkdir()
    (browser / "Local State").write_text("{}", encoding="utf-8")
    mine.mkdir()
    settings = await open_settings(stack)
    assert await settings("document.getElementById('account-folder').hidden") is True
    await settings("document.getElementById('account-existing').click(); true")
    assert await settings("document.getElementById('account-folder').hidden") is False
    await settings("document.getElementById('account-name').value = 'Desktop';"
                   f"document.getElementById('account-folder').value = {json.dumps(str(browser))};"
                   "document.getElementById('account-add').click(); true")
    assert await until(settings, "document.getElementById('accounts-error').textContent.includes(\"a browser's data\")")
    await settings(f"document.getElementById('account-folder').value = {json.dumps(str(mine))};"
                   "document.getElementById('account-add').click(); true")
    assert await eventually(lambda: len(stack["accounts"].list()) == 2)
    assert stack["accounts"].list()[1].folder == str(mine)


@CHROME
async def test_the_default_and_the_brains_account_are_picked_here(home):
    _, stack = home
    accounts = stack["accounts"]
    work = accounts.add("Work")
    settings = await open_settings(stack)
    for pick, chosen in (("account-default", accounts.default_id), ("account-brain", accounts.brain_id)):
        select = f"document.getElementById('{pick}')"
        assert await until(settings, f"{select}.options.length === 2")
        await settings(f"{select}.value = {json.dumps(work.id)}; {select}.dispatchEvent(new Event('change')); true")
        assert await eventually(lambda chosen=chosen: chosen() == work.id)


RESETS = int(time.time()) + 3 * 3600
SESSION_INIT = {**EVENTS[0], "session_id": "$session"}
LIMIT_SCRIPT = {  # the task hits its account's limit; once moved, "Continue the task." goes on
    "Continue the task": [SESSION_INIT, *EVENTS[1:-1], {**EVENTS[-1], "session_id": "$session"}],
    "default": [SESSION_INIT, EVENTS[1], {"usage_limit": f"Claude AI usage limit reached|{RESETS}"}]}


def reset_words(seconds):
    """accountui.js's resetTime() in Python, in this computer's time zone: "3:00 pm", or "Tue 3:00 pm"."""
    when, now = time.localtime(seconds), time.localtime()
    clock = f"{when.tm_hour % 12 or 12}:{when.tm_min:02d} {'am' if when.tm_hour < 12 else 'pm'}"
    if (when.tm_year, when.tm_yday) == (now.tm_year, now.tm_yday):
        return clock
    return f"{('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[when.tm_wday]} {clock}"


AGENT_ROW = "document.querySelector('#agents .agent[data-id=\"a1\"]')"
SHOWN = f"[...{AGENT_ROW}.querySelectorAll('.account-ask button')].filter((b) => !b.hidden).map((b) => b.textContent)"


@CHROME
async def test_ai_home_picks_the_account_for_a_new_task(home):
    js, stack = home
    server, accounts = stack["server"], stack["accounts"]
    pick = "document.getElementById('task-account')"
    assert await until(js, f"{pick}.hidden === true")  # one account: nothing to pick
    work, other = accounts.add("Work"), accounts.add(HOSTILE_NAME)
    sign_in(work.folder)
    accounts.set_limit(work.id, RESETS)
    await server._refresh_accounts()
    assert await until(js, f"{pick}.hidden === false && {pick}.options.length === 3")
    options = await js(f"[...{pick}.options].map((option) => [option.value, option.textContent, option.disabled])")
    assert options == [["default", "Default", False],
                       [work.id, f"Work · at its limit until {reset_words(RESETS)}", False],
                       [other.id, f"{HOSTILE_NAME} · Sign in first", True]]  # a name stays text
    assert await js(f"{pick}.value") == "default"
    await js(f"{pick}.value = {json.dumps(work.id)}; document.getElementById('task').value = 'check the shop';"
             "document.getElementById('start').click(); true")
    assert await eventually(lambda: "a1" in server.agents.agents)
    assert server.agents.agents["a1"].account == {"id": work.id, "name": "Work"}
    assert await until(js, f"{pick}.value === 'default'")  # back to the default for the next task


@CHROME
async def test_the_row_names_its_account_and_asks_at_a_limit(home):
    js, stack = home
    server, accounts = stack["server"], stack["accounts"]
    stack["script"].write_text(json.dumps(LIMIT_SCRIPT), encoding="utf-8")
    work = accounts.add("Work")
    sign_in(work.folder)
    await server._refresh_accounts()
    agent = await server.agents.create("check the shop")  # on Default: it hits Default's limit
    assert await until(js, f"!!{AGENT_ROW}?.querySelector('.account-ask')", 15)
    assert await js(f"{AGENT_ROW}.querySelector('.chip.account').textContent") == "Default"
    assert await js(f"{AGENT_ROW}.querySelector('.head .chip').textContent") == "paused"
    assert await js(f"{AGENT_ROW}.querySelector('.account-ask-head').textContent") == (
        f"Default hit its usage limit (resets {reset_words(RESETS)}).")
    assert await js(SHOWN) == ["Continue on Work", "Wait for the reset"]
    await js(f"{AGENT_ROW}.querySelector('.account-ask .wait').click(); true")
    assert await js(SHOWN) == ["Continue on Work"]  # it stays paused, and Continue stays
    await js(f"{AGENT_ROW}.querySelector('.account-ask .continue').click(); true")
    assert await until(js, f"{AGENT_ROW}.querySelector('.moved').textContent === "
                           "'Moved to Work with its conversation'", 15)
    assert await js(f"{AGENT_ROW}.querySelector('.chip.account').textContent") == "Work"
    assert agent.account["id"] == work.id
    assert await until(js, f"{AGENT_ROW}.querySelector('.account-move .continue')?.textContent === "
                           "'Continue on Default'")  # idle: it can be moved back


@CHROME
async def test_with_no_other_signed_in_account_only_wait_shows(home):
    js, stack = home
    server, accounts = stack["server"], stack["accounts"]
    stack["script"].write_text(json.dumps(LIMIT_SCRIPT), encoding="utf-8")
    accounts.add("Personal")  # not signed in
    await server._refresh_accounts()
    await server.agents.create("check the shop")
    assert await until(js, f"!!{AGENT_ROW}?.querySelector('.account-ask')", 15)
    assert await js(SHOWN) == ["Wait for the reset"]
    assert await js(f"{AGENT_ROW}.querySelector('.account-ask .add-account').textContent") == (
        "Add an account in Settings")


@CHROME
async def test_the_brains_card_continues_on_another_account(home):
    js, stack = home
    server, accounts = stack["server"], stack["accounts"]
    work = accounts.add("Work")
    sign_in(work.folder)
    await server._refresh_accounts()
    server._brain_limit_hit({"account": "default", "resets_at": None})
    card = "document.getElementById('brain-limit')"
    assert await until(js, f"{card}.hidden === false")
    assert await js(f"{card}.querySelector('.account-ask-head').textContent") == (
        "The Brain hit its limit on Default. Continue on Work?")
    await js(f"{card}.querySelector('.continue').click(); true")
    assert await eventually(lambda: accounts.brain_id() == work.id)
    assert await until(js, f"{card}.hidden === true")


HOLD_BRAIN = ("(() => { const send = WebSocket.prototype.send;"  # Continue's account_brain never leaves the page
              " WebSocket.prototype.send = function (data) {"
              "   if (typeof data === 'string' && data.includes('\"account_brain\"')) return;"
              "   return send.call(this, data); }; })(); true")


@CHROME
async def test_usage_readings_never_redraw_the_brains_card(home):  # the polish's follow-up: its pick and its wait stay
    js, stack = home
    server, accounts = stack["server"], stack["accounts"]
    work, personal = accounts.add("Work"), accounts.add("Personal")
    sign_in(work.folder)
    sign_in(personal.folder)
    await server._refresh_accounts()
    server._brain_limit_hit({"account": "default", "resets_at": None})
    card = "document.getElementById('brain-limit')"
    pick = f"{card}.querySelector('.continue-on')"
    assert await until(js, f"{card}.hidden === false && {pick}?.options.length === 2")
    await js(f"window.kept = {pick}; {pick}.value = {json.dumps(personal.id)};"
             f" {pick}.dispatchEvent(new Event('change')); {HOLD_BRAIN}")
    await js(f"{card}.querySelector('.continue').click(); true")  # it waits for the app: disabled
    assert await js(f"{card}.querySelector('.continue').disabled") is True
    for used in (10.0, 11.0, 12.0):  # an agent at work: a reading with each request, and every page hears it
        accounts.set_windows("default", {"five_hour": {"used": used, "resets_at": time.time() + 3600}})
        server.agents.on_usage("default")
        await asyncio.sleep(0.3)
    assert await js(f"window.kept === {pick} && {pick}.value === {json.dumps(personal.id)}")
    assert await js(f"{card}.querySelector('.continue').disabled") is True
    assert await js(f"{card}.querySelector('.account-ask-head').textContent") == (
        "The Brain hit its limit on Default. Continue on Personal?")
    assert accounts.brain_id() == "default"


@CHROME
async def test_the_tools_section_shows_one_accounts_tools_at_a_time(home):
    js, stack = home
    server, accounts = stack["server"], stack["accounts"]
    work = accounts.add("Work")
    (Path(work.folder) / ".claude.json").write_text(json.dumps({"mcpServers": {
        "jira": {"type": "http", "url": "https://mcp.example/jira"}}}), encoding="utf-8")
    await server._refresh_accounts()
    await js("document.getElementById('tools-section').open = true;"
             "document.getElementById('tools-section').dispatchEvent(new Event('toggle')); true")
    pick = "document.querySelector('#tools .tools-account')"
    assert await until(js, f"{pick}?.hidden === false && {pick}.options.length === 2")
    await js(f"{pick}.value = {json.dumps(work.id)}; {pick}.dispatchEvent(new Event('change')); true")
    assert await until(js, "document.querySelector('#tools .tool-server')?.dataset.name === 'jira'")
    await js("document.querySelector('#tools .tool-server .on').click(); true")
    assert await eventually(lambda: server.agents.tools_for(work.id).enabled() == {"jira"})
    assert stack["tools"].enabled() == set()  # Default's switches are its own


@CHROME
async def test_mission_control_picks_the_account_and_its_drawer_asks_at_a_limit(stack):
    from test_mission import open_drawer, open_mission, station

    server, accounts = stack["server"], stack["accounts"]
    stack["script"].write_text(json.dumps(LIMIT_SCRIPT), encoding="utf-8")
    work = accounts.add("Work")
    sign_in(work.folder)
    js = await open_mission(stack)
    pick = "document.getElementById('task-account')"
    assert await until(js, f"{pick}.hidden === false && {pick}.options.length === 2")
    await js("document.getElementById('task').value = 'check the shop';"
             "document.getElementById('start').click(); true")
    assert await eventually(lambda: "a1" in server.agents.agents)
    assert server.agents.agents["a1"].account["id"] == "default"  # the picker's default
    assert await until(js, f"{station('a1')} !== null")
    await js(open_drawer("a1"))
    drawer = "document.querySelector('#drawer:not([hidden])')"
    assert await until(js, f"!!{drawer}?.querySelector('.account-ask')", 15)
    assert await js(f"{drawer}.querySelector('.chip.account').textContent") == "Default"
    assert await js(f"{drawer}.querySelector('.account-ask-head').textContent") == (
        f"Default hit its usage limit (resets {reset_words(RESETS)}).")
    await js(f"{drawer}.querySelector('.account-ask .continue').click(); true")
    assert await until(js, f"{drawer}.querySelector('.moved').textContent === "
                           "'Moved to Work with its conversation'", 15)
    assert await js(f"{drawer}.querySelector('.chip.account').textContent") == "Work"


@CHROME
async def test_the_open_drawer_follows_a_new_account_list_at_once(stack):
    from test_mission import open_drawer, open_mission, station

    server = stack["server"]
    stack["script"].write_text(json.dumps(LIMIT_SCRIPT), encoding="utf-8")
    await server.agents.create("check the shop")  # only Default: it has nowhere to continue
    js = await open_mission(stack)
    assert await until(js, f"{station('a1')} !== null")
    await js(open_drawer("a1"))
    drawer = "document.querySelector('#drawer:not([hidden])')"
    assert await until(js, f"{drawer}?.querySelector('.add-account') !== null", 15)
    assert await js(f"{drawer}.querySelector('.continue') === null")
    work = {**server._account_rows()[0], "id": "work", "name": "Work", "signed_in": True, "default": False,
            "brain": False, "checked": True}
    server._send_all({"type": "accounts", "accounts": [*server._account_rows(), work]})  # one message, the new list
    ask = f"{drawer}.querySelector('.account-ask .continue')"
    assert await until(js, f"{ask}?.textContent === 'Continue on Work'", 5)  # drawn from the list it came with


@CHROME
async def test_usage_readings_never_redraw_settings_accounts(home):  # the polish's review, F2
    _, stack = home
    accounts, server = stack["accounts"], stack["server"]
    work = accounts.add("Work")  # not signed in: Sign in and Remove
    settings = await open_settings(stack)
    row = f"document.querySelector('#accounts .account[data-id=\"{work.id}\"]')"
    assert await until(settings, f"{ROWS}.length === 2 && {row}.querySelector('.status').textContent !== 'Checking…'")
    await settings(f"{row}.querySelector('.signin').click(); true")  # its Sign in, unfolded: the command to select
    assert await until(settings, f"!!{row}?.querySelector('.command')")
    await settings(f"window.kept = {row}; window.kept.querySelector('.remove').focus();"
                   " getSelection().selectAllChildren(window.kept.querySelector('.command')); true")
    for used in (10.0, 11.0, 12.0):  # an agent at work: a reading with each request, and every page hears it
        accounts.set_windows("default", {"five_hour": {"used": used, "resets_at": time.time() + 3600}})
        server.agents.on_usage("default")
        await asyncio.sleep(0.3)
    assert await settings(f"window.kept === {row} && window.kept.isConnected")  # the list wasn't drawn again
    assert await settings("document.activeElement === window.kept.querySelector('.remove')")  # its focus stays
    assert await settings("getSelection().toString()") == await settings(f"{row}.querySelector('.command').textContent")
