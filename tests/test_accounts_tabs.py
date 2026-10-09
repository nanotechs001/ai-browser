"""AI accounts in AI Browser's window as the user has it: one tab menu (/app) whose pages load once per run. An
account's status that changes after a page loaded (a sign-out an agent runs into, a sign-in made in the user's own
terminal, a move refused) reaches every page without a reload. Drawn in a throwaway headless Chrome against a real
app server (agents on the fake claude, never the user's own Claude Code folder)."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from fake_accounts import sign_in, sign_out
from test_accounts_pages import LIMIT_SCRIPT, eventually
from test_home import stack, until  # noqa: F401  (fixture)
from test_tab_menu import click_in, connected, frame, in_frame, pick, shell  # noqa: F401  (fixture)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
NOT_SIGNED_IN = "Work isn't signed in: sign in from Settings → Accounts"
GONE = "That account isn't in Settings → Accounts any more"


def account_row(account_id: str) -> str:
    """Settings' row for one account, in the Settings tab's page."""
    return f"{frame('/settings')}?.document.querySelector('#accounts .account[data-id=\"{account_id}\"]')"


DRAWER_ASK = f"{frame('/mission')}?.document.querySelector('#drawer:not([hidden]) .account-ask .continue')"
NOTE = f"{frame('/mission')}.document.getElementById('task-note').textContent"  # where a refused Continue on is said


async def limited_agent(js, stack):
    """Default and Work, both signed in; agent a1 on Default has hit Default's usage limit, and its drawer in Mission
    Control asks."""
    server, accounts = stack["server"], stack["accounts"]
    stack["script"].write_text(json.dumps(LIMIT_SCRIPT), encoding="utf-8")
    work = accounts.add("Work")
    sign_in(work.folder)
    await server._refresh_accounts()
    await server.agents.create("check the shop")  # on Default: it hits Default's limit
    assert await until(js, f"{frame('/mission')}.document.querySelector('.station[data-id=\"a1\"]') !== null")
    await js(f"{frame('/mission')}.document.querySelector('.station[data-id=\"a1\"]').click();"
             f" {frame('/mission')}.document.getElementById('current-chat').click(); true")  # pick it, then Chat
    assert await until(js, f"{DRAWER_ASK}?.textContent === 'Continue on Work'", 15)
    return work


@CHROME
async def test_a_sign_out_found_by_an_agent_shows_in_the_settings_tab(shell, monkeypatch):
    from ai_browser import accounts as module

    js, stack = shell
    server, accounts = stack["server"], stack["accounts"]
    work = accounts.add("Work")
    sign_in(work.folder)
    await pick(js, "/settings")  # loaded once
    assert await until(js, connected("/settings"))
    row = account_row(work.id)
    assert await until(js, f"{row}?.querySelector('.status').textContent === 'Signed in · Pro'")
    assert await js(f"!!{row}.querySelector('.signin')") is False
    sign_out(work.folder)  # Work signs out after the page loaded
    monkeypatch.setattr(module, "STATUS_TTL", 0)  # the agent's check asks Claude Code again
    agent = await server.agents.create("check the shop", account=work.id)
    assert await eventually(lambda: agent.status == NOT_SIGNED_IN)
    assert await until(js, f"{row}.querySelector('.status').textContent === 'Not signed in'")  # the same page
    assert await js(f"!!{row}.querySelector('.signin')") is True


@CHROME
async def test_a_sign_in_outside_the_watch_shows_once_the_user_is_back(shell, monkeypatch):
    from ai_browser import accounts as module

    js, stack = shell
    accounts = stack["accounts"]
    monkeypatch.setattr(module, "STATUS_TTL", 0.2)
    await pick(js, "/settings")
    assert await until(js, connected("/settings"))
    await in_frame(js, "/settings", "document.getElementById('account-name').value = 'Work'; true")
    await click_in(js, "/settings", "#account-add")
    assert await eventually(lambda: len(accounts.list()) == 2)
    work = accounts.list()[1]
    row = account_row(work.id)
    assert await until(js, f"{row}?.querySelector('.status').textContent === 'Not signed in'")  # checked at once
    option = f"[...{frame('/mission')}.document.getElementById('task-account').options].find((one) => one.value === " \
             f"{json.dumps(work.id)})"
    assert await until(js, f"{option}?.textContent === 'Work · Sign in first' && {option}.disabled === true")
    sign_in(work.folder)  # in the user's own terminal: no watch runs (neither Open Terminal nor Copy was used)
    await asyncio.sleep(0.3)  # longer than the app keeps a status
    await pick(js, "/mission")  # the user is back: Mission Control's tab is shown, and its page has the focus
    assert await until(js, f"{option}?.textContent === 'Work' && {option}.disabled === false")
    assert await until(js, f"{row}.querySelector('.status').textContent === 'Signed in · Pro'")  # never reloaded


@CHROME
async def test_continue_on_comes_back_once_the_account_is_signed_in_again(shell, monkeypatch):
    from ai_browser import accounts as module

    js, stack = shell
    work = await limited_agent(js, stack)
    sign_out(work.folder)  # Work signs out while the drawer still offers it
    monkeypatch.setattr(module, "STATUS_TTL", 0)  # the move asks Claude Code again
    await click_in(js, "/mission", "#drawer:not([hidden]) .account-ask .continue")
    assert await until(js, f"{NOTE} === {json.dumps(NOT_SIGNED_IN)}")  # refused, and said
    assert stack["server"].agents.agents["a1"].account["id"] == "default"
    sign_in(work.folder)  # signed in again, in the user's own terminal
    await pick(js, "/settings")
    await pick(js, "/mission")  # the user is back on Mission Control's tab
    assert await until(js, f"{DRAWER_ASK}?.textContent === 'Continue on Work' && {DRAWER_ASK}.disabled === false", 8)


@CHROME
async def test_a_refused_continue_on_in_mission_control_can_be_clicked_again(shell):
    js, stack = shell
    work = await limited_agent(js, stack)
    stack["accounts"].remove(work.id)  # forgotten behind this page's back: it still offers it
    await click_in(js, "/mission", "#drawer:not([hidden]) .account-ask .continue")
    assert await eventually(lambda: stack["server"].agents.agents["a1"].account["id"] == "default", 2)
    assert await until(js, f"{DRAWER_ASK}.disabled === false")  # the app said no: it can be clicked again


@CHROME
async def test_each_page_asks_for_the_statuses_again_when_its_tab_is_shown(shell):
    js, stack = shell
    accounts = stack["accounts"]
    asked = []
    refresh = accounts.refresh

    async def counted():
        asked.append(1)
        await refresh()

    accounts.refresh = counted
    await pick(js, "/settings")  # loaded once (Mission Control loaded with the window)
    assert await until(js, connected("/settings"))
    await asyncio.sleep(0.5)
    for key in ("/mission", "/settings"):  # shown again: the user may have signed in meanwhile
        before = len(asked)
        await pick(js, key)
        assert await eventually(lambda before=before: len(asked) > before, 5), key
