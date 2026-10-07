"""The Usage card's two limits (the new look, Decision 7; the probe of 2026-10-07): each request's rate_limit_event
carries rate_limit_info.unifiedWindows, with the current session's (five_hour) and the week's (seven_day) utilization, a
fraction, and its reset time. They are read only there, kept per account in <home>/usage.json across restarts, and
shown in the accounts' rows. Never a made-up number (Review Focus 3). On the fake claude, in a throwaway home."""

import json
import time

import pytest

from conftest import file_mode
from test_agents_powers import manager
from test_app_server import started, wait_for
from test_bridge import EVENTS

SESSION = int(time.time()) + 3 * 3600  # when the current session's limit resets
WEEK = int(time.time()) + 4 * 86400  # and the week's
INIT = EVENTS[0]
# what Claude Code 2.1.292 sent with each request on the user's own login (the probe), with times from now
PROBE = {"status": "allowed", "resetsAt": SESSION, "rateLimitType": "five_hour", "overageStatus": "rejected",
         "overageDisabledReason": "org_level_disabled", "isUsingOverage": False,
         "unifiedWindows": {"five_hour": {"utilization": 0, "resetsAt": SESSION},
                            "seven_day": {"utilization": 0.14, "resetsAt": WEEK}}}
READ = {"five_hour": {"used": 0.0, "resets_at": float(SESSION)}, "seven_day": {"used": 14.0, "resets_at": float(WEEK)}}


def event(info):
    return {"type": "rate_limit_event", "rate_limit_info": info, "uuid": "u-1", "session_id": "s-1"}


def windows(**found):
    return event({"status": "allowed", "unifiedWindows": found})


def test_the_probes_event_reads_as_the_session_and_the_week():
    from ai_browser import limits

    assert limits.windows_from_event(event(PROBE)) == READ
    assert limits.from_event(event(PROBE)) is None  # allowed: no limit was hit
    assert limits.SHOWN_WINDOWS == ("five_hour", "seven_day")


def test_no_percentage_is_ever_made_up():  # Review Focus 3: only unifiedWindows' utilization, never a lookalike
    from ai_browser import limits

    for info in ({"status": "allowed", "utilization": 0.64}, {"status": "allowed_warning", "used_percentage": 64},
                 {"surpassedThreshold": 0.5, "resetsAt": SESSION}, {"five_hour": {"utilization": 0.5}},
                 {"unifiedWindows": "five_hour: 50%"}, {"unifiedWindows": [{"utilization": 0.5}]}, {}):
        assert limits.windows_from_event(event(info)) == {}, info
    outside = {"type": "rate_limit_event", "unifiedWindows": {"five_hour": {"utilization": 0.5}}}  # not in the info
    assert limits.windows_from_event(outside) == {}
    assert limits.windows_from_event({"type": "result", "rate_limit_info": PROBE}) == {}  # another event's
    for nothing in (None, "rate_limit_event", ["rate_limit_event"], event("not an object")):
        assert limits.windows_from_event(nothing) == {}


def test_only_a_fraction_from_0_to_1_makes_a_percentage():
    from ai_browser import limits

    for value in (True, False, "0.5", None, float("nan"), float("inf"), -0.1, 1.5, [0.5], {"v": 1}):
        assert limits.windows_from_event(windows(five_hour={"utilization": value, "resetsAt": SESSION})) == {}, value
    for value, used in ((0, 0.0), (1, 100.0), (0.5, 50.0), (0.14, 14.0), (0.666, 66.6)):
        assert limits.windows_from_event(windows(five_hour={"utilization": value})) == {
            "five_hour": {"used": used, "resets_at": None}}
    for bad_time in (True, "soon", float("nan"), float("inf"), 5, 10**13, None):  # no sane time: none at all
        assert limits.windows_from_event(windows(seven_day={"utilization": 0.2, "resetsAt": bad_time})) == {
            "seven_day": {"used": 20.0, "resets_at": None}}, bad_time
    huge = 10**400  # a number too big for a float: dropped, never an OverflowError that ends the agent's turn
    assert limits.windows_from_event(windows(five_hour={"utilization": huge}, seven_day={"utilization": 0.2,
                                                                                         "resetsAt": huge})) == {
        "seven_day": {"used": 20.0, "resets_at": None}}
    assert limits.from_event(event({"status": "rejected", "resetsAt": huge})) == limits.Limit()
    known = windows(seven_day_opus={"utilization": 0.3}, seven_day_sonnet={"utilization": 0.4},
                    ten_minute={"utilization": 0.5}, five_hour="half", seven_day=None)
    assert limits.windows_from_event(known) == {"seven_day_opus": {"used": 30.0, "resets_at": None},
                                                "seven_day_sonnet": {"used": 40.0, "resets_at": None}}


def test_readings_are_kept_per_account_with_their_time_and_across_a_restart(tmp_path):
    from ai_browser.accounts import Accounts

    accounts = Accounts(tmp_path)
    assert accounts.rows()[0]["windows"] == {}  # no reading yet
    before = time.time()
    accounts.set_windows("default", READ)
    kept = accounts.rows()[0]["windows"]
    assert set(kept) == {"five_hour", "seven_day"}
    for name in kept:
        assert (kept[name]["used"], kept[name]["resets_at"]) == (READ[name]["used"], READ[name]["resets_at"])
        assert before <= kept[name]["at"] <= time.time()
    accounts.set_windows("default", {"seven_day": {"used": 15.0, "resets_at": float(WEEK)}})  # one: the other stays
    assert accounts.windows("default")["seven_day"]["used"] == 15.0
    assert accounts.windows("default")["five_hour"]["used"] == 0.0
    path = tmp_path / "usage.json"
    if file_mode(path) is not None:
        assert file_mode(path) == 0o600
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == {"accounts": {"default": accounts.windows("default")}}  # ids, window names, numbers and times only
    assert Accounts(tmp_path).windows("default") == accounts.windows("default")  # after a restart, as it was


def test_anything_but_a_reading_is_never_kept(tmp_path):
    from ai_browser.accounts import Accounts

    accounts = Accounts(tmp_path)
    for nothing in (None, "64%", [READ], {"five_hour": {"used": True}}, {"five_hour": {"used": 101.0}},
                    {"five_hour": {"used": 10**400}}, {"five_hour": {"used": float("inf")}},
                    {"five_hour": {"used": -1}}, {"five_hour": {"used": float("nan")}}, {"five_hour": "64"},
                    {"ten_minute": {"used": 5.0, "resets_at": None}}):
        accounts.set_windows("default", nothing)
        assert accounts.windows("default") == {}, nothing
    accounts.set_windows("acct-000000", READ)  # an account that isn't listed
    assert accounts.windows("acct-000000") == {}
    assert not (tmp_path / "usage.json").exists()


HUGE = "1" + "0" * 400  # a 400-digit integer: too big for a float
NESTED = '{"accounts": ' + "[" * 100_000 + "]" * 100_000 + "}"  # deeper than Python's recursion limit


@pytest.mark.parametrize("text", ["", "not json", "[1, 2]", '{"accounts": "default"}', '{"accounts": [1]}',
                                  '{"accounts": {"default": "64%"}}', '{"accounts": {"default": {"five_hour": 64}}}',
                                  f'{{"accounts": {{"default": {{"five_hour": {{"used": {HUGE}, "resets_at": null,'
                                  f' "at": 1800000000}}}}}}}}',
                                  f'{{"accounts": {{"default": {{"five_hour": {{"used": 5, "resets_at": {HUGE},'
                                  f' "at": {HUGE}}}}}}}}}', NESTED],
                         ids=["empty", "not-json", "a-list", "accounts-a-string", "accounts-a-list", "a-string",
                              "a-number", "huge-used", "huge-times", "nested"])
def test_an_unreadable_usage_file_reads_as_empty(tmp_path, text):  # never a crash: the app always starts
    from ai_browser.accounts import Accounts

    (tmp_path / "usage.json").write_text(text, encoding="utf-8")
    accounts = Accounts(tmp_path)
    assert accounts.windows("default") == {} and accounts.rows()[0]["windows"] == {}


def test_a_usage_file_keeps_only_sane_readings_of_known_accounts(tmp_path):
    from ai_browser.accounts import Accounts

    at = time.time() - 60
    good = {"used": 14.0, "resets_at": float(WEEK), "at": at}
    (tmp_path / "usage.json").write_text(json.dumps({"accounts": {
        "default": {"seven_day": good, "five_hour": {"used": "64", "resets_at": None, "at": at},
                    "seven_day_opus": {"used": 30.0, "resets_at": True, "at": at},
                    "seven_day_sonnet": {"used": 30.0, "resets_at": None, "at": "now"}, "ten_minute": good},
        "acct-000000": {"seven_day": good}, "../../etc": {"seven_day": good}}}), encoding="utf-8")
    assert Accounts(tmp_path).windows("default") == {"seven_day": good,
                                                     "seven_day_opus": {"used": 30.0, "resets_at": None, "at": at}}
    assert Accounts(tmp_path).windows("acct-000000") == {}  # not an account of this home


def test_removing_an_account_drops_its_readings(tmp_path):
    from ai_browser.accounts import Accounts

    accounts = Accounts(tmp_path)
    work = accounts.add("Work")
    accounts.set_windows(work.id, READ)
    accounts.set_windows("default", READ)
    assert set(json.loads((tmp_path / "usage.json").read_text(encoding="utf-8"))["accounts"]) == {"default", work.id}
    accounts.remove(work.id)
    assert accounts.windows(work.id) == {}
    assert set(json.loads((tmp_path / "usage.json").read_text(encoding="utf-8"))["accounts"]) == {"default"}
    assert Accounts(tmp_path).windows(work.id) == {}


def test_a_reading_whose_reset_passed_is_kept_with_its_time(tmp_path):  # the card says "Reset at …", not a number
    from ai_browser.accounts import Accounts

    accounts = Accounts(tmp_path)
    passed = time.time() - 60
    accounts.set_windows("default", {"five_hour": {"used": 64.0, "resets_at": passed}})
    assert accounts.rows()[0]["windows"]["five_hour"]["resets_at"] == passed


async def test_an_agents_turn_reports_its_accounts_usage(fake_claude, tmp_path):
    from ai_browser.accounts import Accounts

    agents, _ = manager(fake_claude, tmp_path, [INIT, {"rate_limit": PROBE}, *EVENTS[1:]])
    agents.accounts = Accounts(tmp_path / "home", claude=fake_claude[0])
    told = []
    agents.on_usage = told.append
    try:
        agent = await agents.create("look around")
        await wait_for(lambda: agent.state == "your_turn")
        kept = agents.accounts.rows()[0]["windows"]
        assert {name: {key: one[key] for key in ("used", "resets_at")} for name, one in kept.items()} == READ
        assert told == ["default"]  # the account's id: every page then hears its rows
        assert all(one["type"] != "usage" for one in agents.events_of(agent.id))  # never in the chat
    finally:
        await agents.close_all()
    assert Accounts(tmp_path / "home").windows("default")["seven_day"]["used"] == 14.0  # and after a restart


async def test_every_page_hears_a_new_usage(fake_claude, tmp_path):
    from ai_browser.accounts import Accounts

    server, _ = await started(fake_claude, tmp_path, EVENTS,
                              accounts=Accounts(tmp_path / "home", claude=fake_claude[0]))
    try:
        heard = []
        server._send_all = heard.append
        server.accounts.set_windows("default", {"five_hour": {"used": 50.0, "resets_at": float(SESSION)}})
        server.agents.on_usage("default")
        assert heard[-1]["type"] == "accounts"
        assert heard[-1]["accounts"][0]["windows"]["five_hour"]["used"] == 50.0
        assert "used" not in heard[-1]["accounts"][0]  # the one number of before is gone
    finally:
        await server.stop()
