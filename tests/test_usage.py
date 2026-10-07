"""How much of a limit is used (the new look, Decision 7): read only under the key Task 1's probe names, kept per
account for this run, and shown in the accounts' rows. Without that key, never a number (Review Focus 3). On the fake
claude, in a throwaway home."""

import time

import pytest

from test_agents_powers import manager
from test_app_server import started, wait_for
from test_bridge import EVENTS

RESETS = int(time.time()) + 3 * 3600
INIT = EVENTS[0]


def event(**info):
    return {"type": "rate_limit_event", "rate_limit_info": info}


def test_without_a_named_key_no_percentage_is_ever_read(monkeypatch):  # Review Focus 3
    from ai_browser import limits

    monkeypatch.setattr(limits, "USAGE_KEY", None)
    for info in ({"status": "allowed", "utilization": 0.64}, {"status": "allowed_warning", "used_percentage": 64},
                 {"surpassedThreshold": 0.5, "resetsAt": RESETS}):
        assert limits.usage_from_event(event(**info)) is None


@pytest.mark.parametrize(("scale", "value", "used"), [(100.0, 0.64, 64.0), (1.0, 64, 64.0), (100.0, 0, 0.0),
                                                      (1.0, 100, 100.0)])
def test_the_named_key_reads_a_percentage(monkeypatch, scale, value, used):
    from ai_browser import limits

    monkeypatch.setattr(limits, "USAGE_KEY", "utilization")
    monkeypatch.setattr(limits, "USAGE_SCALE", scale)
    read = limits.usage_from_event(event(status="allowed", utilization=value, resetsAt=RESETS,
                                         rateLimitType="five_hour"))
    assert read == limits.Usage(used, float(RESETS), "five_hour")


def test_anything_but_a_percentage_is_dropped(monkeypatch):
    from ai_browser import limits

    monkeypatch.setattr(limits, "USAGE_KEY", "utilization")
    for value in (True, "64", None, float("nan"), float("inf"), -0.1, 1.5, [0.5], {"v": 1}):
        assert limits.usage_from_event(event(utilization=value)) is None, value
    assert limits.usage_from_event({"type": "result", "utilization": 0.5}) is None


def test_a_reported_usage_lasts_until_its_reset(tmp_path):
    from ai_browser.accounts import Accounts

    accounts = Accounts(tmp_path)
    for nothing in (None, True, "64", -1, 101, float("nan")):
        accounts.set_usage("default", nothing, RESETS)
        assert accounts.usage("default") is None
    accounts.set_usage("default", 64.0, RESETS, "five_hour")
    assert accounts.usage("default") == {"used": 64.0, "resets_at": float(RESETS), "kind": "five_hour"}
    row = accounts.rows()[0]
    assert (row["used"], row["used_resets_at"], row["used_kind"]) == (64.0, float(RESETS), "five_hour")
    accounts._usage["default"]["resets_at"] = time.time() - 1  # its time came
    assert accounts.usage("default") is None and accounts.rows()[0]["used"] is None
    assert Accounts(tmp_path).usage("default") is None  # this app run only: never written down


async def test_an_agents_turn_reports_its_accounts_usage(fake_claude, tmp_path, monkeypatch):
    from ai_browser import limits
    from ai_browser.accounts import Accounts

    monkeypatch.setattr(limits, "USAGE_KEY", "utilization")
    info = {"status": "allowed", "utilization": 0.64, "resetsAt": RESETS, "rateLimitType": "five_hour"}
    agents, _ = manager(fake_claude, tmp_path, [INIT, {"rate_limit": info}, *EVENTS[1:]])
    agents.accounts = Accounts(tmp_path / "home", claude=fake_claude[0])
    told = []
    agents.on_usage = told.append
    try:
        agent = await agents.create("look around")
        await wait_for(lambda: agent.state == "your_turn")
        row = agents.accounts.rows()[0]
        assert (row["used"], row["used_resets_at"], row["used_kind"]) == (64.0, float(RESETS), "five_hour")
        assert told == ["default"]
        assert all(one["type"] != "usage" for one in agents.events_of(agent.id))  # never in the chat
    finally:
        await agents.close_all()


async def test_every_page_hears_a_new_usage(fake_claude, tmp_path):
    from ai_browser.accounts import Accounts

    server, _ = await started(fake_claude, tmp_path, EVENTS,
                              accounts=Accounts(tmp_path / "home", claude=fake_claude[0]))
    try:
        heard = []
        server._send_all = heard.append
        server.accounts.set_usage("default", 50.0)
        server.agents.on_usage("default")
        assert heard[-1]["type"] == "accounts" and heard[-1]["accounts"][0]["used"] == 50.0
    finally:
        await server.stop()
