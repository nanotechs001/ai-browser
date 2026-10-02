"""The app's side of tab groups: one request at a time per answer, never a hang, never a guess."""

import asyncio
import time


def keeper_on():
    from ai_browser.app.groups import GroupKeeper

    sent = []
    keeper = GroupKeeper(lambda message: sent.append(message) or True)
    keeper.watcher_changed(True)
    keeper.caps_from({"type": "watcher_caps", "groups": True})
    return keeper, sent


async def test_no_watcher_answers_at_once():
    from ai_browser.app.groups import GroupKeeper

    keeper = GroupKeeper(lambda message: False)
    assert keeper.available() == "no_watcher"
    assert await keeper.group("a1", "Fix", "blue", {"marker": "0" * 16}) == {"grouped": False, "reason": "no_watcher"}


def test_a_watcher_that_cant_group_is_old():
    from ai_browser.app.groups import GroupKeeper

    changes = []
    keeper = GroupKeeper(lambda message: True, on_change=lambda: changes.append(1))
    keeper.watcher_changed(True)
    assert keeper.available() == "old_watcher"  # no watcher_caps yet: an older watcher never sends them
    keeper.caps_from({"groups": False})
    assert keeper.available() == "old_watcher"
    keeper.caps_from({"groups": True})
    assert keeper.available() == "on" and len(changes) == 3


async def test_two_claims_answered_out_of_order_get_their_own_answers():  # Review Focus 1
    keeper, sent = keeper_on()
    first = asyncio.ensure_future(keeper.group("a1", "Fix the footer", "blue", {"marker": "a" * 16}))
    second = asyncio.ensure_future(keeper.group("cc-t1", "Claude Code", "orange", {"marker": "b" * 16}))
    await asyncio.sleep(0.05)
    assert [(m["type"], m["request"], m["key"], m["title"]) for m in sent] == [
        ("group_tab", "g1", "a1", "Fix the footer"), ("group_tab", "g2", "cc-t1", "Claude Code")]
    keeper.answered({"type": "tab_grouped", "request": "g2", "ok": True, "tab": 22, "window": 1, "group": 5})
    keeper.answered({"type": "tab_grouped", "request": "g1", "ok": False, "reason": "ambiguous"})
    assert await second == {"grouped": True, "tab": 22}
    assert await first == {"grouped": False, "reason": "ambiguous"}


async def test_the_watcher_leaving_ends_a_waiting_claim_at_once():  # Review Focus 1
    keeper, _ = keeper_on()
    waiting = asyncio.ensure_future(keeper.group("a1", "Fix", "blue", {"marker": "a" * 16}))
    await asyncio.sleep(0.05)
    started = time.monotonic()
    keeper.watcher_changed(False)  # the watcher reloads itself
    assert await waiting == {"grouped": False, "reason": "no_watcher"} and time.monotonic() - started < 0.3


async def test_no_answer_is_a_timeout_and_a_strange_reason_is_not_found(monkeypatch):
    from ai_browser.app import groups

    monkeypatch.setattr(groups, "GROUP_WAIT", 0.2)
    keeper, _ = keeper_on()
    assert await keeper.group("a1", "Fix", "blue", {"marker": "a" * 16}) == {"grouped": False, "reason": "timeout"}
    waiting = asyncio.ensure_future(keeper.group("a1", "Fix", "blue", {"marker": "a" * 16}))
    await asyncio.sleep(0.05)
    keeper.answered({"request": "g2", "ok": False, "reason": "<script>"})
    assert await waiting == {"grouped": False, "reason": "not_found"}


def test_tab_ids_are_remembered_and_ungrouped():
    keeper, sent = keeper_on()
    keeper.remember("T1", 412)
    assert keeper.tab_of("T1") == 412 and keeper.tab_of("T2") is None
    keeper.ungroup([412])
    keeper.ungroup([])
    assert sent == [{"type": "ungroup_tabs", "tabs": [412]}]
