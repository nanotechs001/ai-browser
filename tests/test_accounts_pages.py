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
