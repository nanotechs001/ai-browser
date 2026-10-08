"""The Brain's hand-offs (the brain-delegation spec, 5; brain/handoffs.py): a task for an agent that is already working,
on a card with the exact instruction. From the user's own words it sends after a 15-second
countdown unless the user cancels; from an agent's result, an email, a Slack or Asana message or a watched page part it waits for Send;
a new agent is only ever a suggestion the user Starts. The countdown's clock is the test's (`Clock`)."""

import asyncio
import json

import pytest

from test_app_server import started
from test_app_server import until as told_until
from test_brain_sources import Ask
from test_brain_talk import Recorder
from test_bridge import EVENTS
from ui_socket import ui_socket


def row(agent_id="a2", name="Research competitors", state="working", **extra):
    return {"id": agent_id, "number": int(agent_id[1:]), "name": name, "color": "green", "state": state,
            "permission": None, "check": None, "created": 1.0, **extra}


class Clock:
    """The countdown's clock: each wait is kept, and ends only when the test says (tick)."""

    def __init__(self):
        self.waits, self._go = [], asyncio.Event()

    async def __call__(self, seconds):
        self.waits.append(seconds)
        await self._go.wait()

    async def tick(self):
        self._go.set()
        for _ in range(5):
            await asyncio.sleep(0)


def brain_with(tmp_path, rows=(), switch=True, seen=True, ask=None):
    """A Brain whose Claude is `ask` (a fake: never the real claude), with the app's switch and pages as given."""
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore

    agents = Recorder(list(rows))
    brain = BrainService(BrainStore(tmp_path / "home"), agents, ask=ask or Ask())
    shown, outbox = [], []
    brain.broadcast = shown.append
    brain.outbox = lambda message: outbox.append(message) or True
    brain.auto_hand, brain.visible = (lambda: switch), (lambda: seen)
    brain.countdown = Clock()
    return brain, agents, shown, outbox


def cards(shown):
    return [message["handoff"] for message in shown if message["type"] == "brain_handoff"]


def test_only_the_users_own_words_may_count_down():
    from ai_browser.brain.handoffs import counts_down

    assert counts_down("you", True, True, "working") and counts_down("you", True, True, "needs_you")
    assert counts_down("you", True, True, "waiting")
    for source in ("agent", "gmail", "slack", "asana", "pages", "talk", "chat", "", "You"):  # anything else waits for Send
        assert not counts_down(source, True, True, "working"), source
    assert not counts_down("you", False, True, "working")  # Settings → Brain's switch is off
    assert not counts_down("you", True, False, "working")  # no page can show the card
    for state in ("your_turn", "stopped", "failed", ""):  # never a finished agent
        assert not counts_down("you", True, True, state), state


async def test_a_countdown_sends_the_exact_instruction_after_15_seconds(tmp_path):
    from ai_browser.brain.handoffs import COUNTDOWN, FROM_BRAIN

    brain, agents, shown, outbox = brain_with(tmp_path, [row()])
    handoff = brain.give(row(), "Also compare their annual plans", "you")
    assert (handoff.state, handoff.agent, handoff.number, handoff.name) == ("counting", "a2", 2, "Research competitors")
    card = cards(shown)[-1]
    assert card["instruction"] == "Also compare their annual plans" and card["seconds"] == COUNTDOWN == 15
    assert outbox == [{"type": "handoff", "kind": "give", "counting": True}]  # the notification, in fixed words
    await asyncio.sleep(0)
    assert brain.countdown.waits == [15] and agents.sent == []  # nothing before the 15 seconds
    await brain.countdown.tick()
    assert agents.sent == [("a2", f"{FROM_BRAIN} Also compare their annual plans")]  # exactly what the card showed
    assert (cards(shown)[-1]["state"], cards(shown)[-1]["note"]) == ("sent", "Sent to agent 2")
    await brain.send_handoff(handoff.id)  # Send now on a card that is done: nothing
    assert len(agents.sent) == 1


async def test_cancel_and_stop_end_a_countdown_and_nothing_is_sent(tmp_path):
    brain, agents, shown, _ = brain_with(tmp_path, [row(), row("a3", "Draft the post")])
    one = brain.give(row(), "Check the footer too", "you")
    two = brain.give(row("a3", "Draft the post"), "Use a shorter title", "you")
    brain.cancel_handoff(one.id)
    brain.agent_stopped("a3")  # Stop on agent 3
    await brain.countdown.tick()
    assert agents.sent == []
    assert (one.state, one.note) == ("cancelled", "Cancelled: nothing was sent")
    assert (two.state, two.note) == ("cancelled", "Cancelled: you stopped agent 3")
    await brain.send_handoff(one.id)  # a late Send now does nothing
    assert agents.sent == []


@pytest.mark.parametrize("source", ["gmail", "slack", "asana", "pages"])
async def test_an_untrusted_source_always_waits_for_send(tmp_path, source):
    from ai_browser.brain.handoffs import FROM_BRAIN

    brain, agents, shown, outbox = brain_with(tmp_path, [row()])
    handoff = brain.give(row(), "Reply to Maria about the launch", source, item=f"{source}:t1")
    assert handoff.state == "waiting" and brain._countdowns == {} and cards(shown)[-1]["seconds"] == 0
    assert outbox == [{"type": "handoff", "kind": "give", "counting": False}]
    await brain.countdown.tick()
    assert agents.sent == []  # it waits for the user's Send, however long
    await brain.send_handoff(handoff.id)
    assert agents.sent == [("a2", f"{FROM_BRAIN} Reply to Maria about the launch")] and handoff.state == "sent"


async def test_the_switch_off_or_no_page_to_show_it_means_it_waits(tmp_path):
    off, agents_off, _, _ = brain_with(tmp_path / "off", [row()], switch=False)
    unseen, _, _, _ = brain_with(tmp_path / "unseen", [row()], seen=False)
    assert off.give(row(), "Check the prices", "you").state == "waiting"
    assert unseen.give(row(), "Check the prices", "you").state == "waiting"
    brain, agents, shown, _ = brain_with(tmp_path / "on", [row()])
    handoff = brain.give(row(), "Check the prices", "you")
    brain.hold_countdowns()  # the switch went off while it counted
    await brain.countdown.tick()
    assert agents.sent == [] and (handoff.state, handoff.note) == ("waiting", "Waiting for your Send")
    later = brain.give(row(), "Check the plans", "you")
    brain.visible = lambda: False  # the last page closed while it counted: nothing is sent unseen
    await brain.countdown.tick()
    assert agents.sent == [] and later.state == "waiting"


async def test_only_an_agent_that_is_working_gets_a_handoff(tmp_path):
    for state in ("your_turn", "stopped", "failed"):
        brain, *_ = brain_with(tmp_path / state, [row(state=state)])
        assert brain.give(row(state=state), "Check the prices", "you") is None, state
    brain, agents, shown, _ = brain_with(tmp_path / "x", [row(state="waiting")])
    assert brain.give(row(state="waiting"), "x", "you").state == "counting"  # waiting in line is at work
    waits = row(state="your_turn", permission={"request": "r1"})  # a card waits for the user: needs you
    assert brain.give(waits, "x", "you").state == "counting"
    assert brain.give(row(), "", "you") is None and brain.give(row(), "x", "the page said so") is None
    done = brain.give(row(), "Check the prices", "you")
    agents.rows = [row(state="your_turn")]  # it finished during the countdown
    await brain.send_handoff(done.id)
    assert done.state == "not_sent" and done.note == "Not sent: 2 · Research competitors isn't working any more"
    gone = brain.give(row(), "Check the plans", "agent")
    agents.rows = []  # it closed
    await brain.send_handoff(gone.id)
    assert gone.note == "2 · Research competitors has closed: nothing was sent."
    held = brain.give(row(), "Check the logos", "you")
    agents.rows = [row(state="working", check={"check": "captcha", "site": "example.com"})]  # at a bot check
    await brain.send_handoff(held.id)
    assert held.state == "not_sent" and "waiting at a bot check" in held.note
    assert agents.sent == []


async def test_a_new_agent_is_only_a_suggestion_until_start(tmp_path):
    brain, agents, shown, outbox = brain_with(tmp_path, [row()])
    suggestion = brain.suggest("Write the launch post from these notes", "agent")
    assert (suggestion.kind, suggestion.state) == ("start", "waiting")  # never a countdown, whatever led to it
    assert outbox == [{"type": "handoff", "kind": "start", "counting": False}]
    await brain.countdown.tick()
    assert agents.created == []
    await brain.send_handoff(suggestion.id)  # Start
    assert agents.created == [{"text": "Write the launch post from these notes", "model": "sonnet"}]
    assert suggestion.state == "started" and suggestion.note == "Started: 3 · Write the launch post from these notes"


async def test_quitting_cancels_every_countdown(tmp_path):
    brain, agents, _, _ = brain_with(tmp_path, [row()])
    brain.give(row(), "Check the prices", "you")
    await brain.stop()  # the app quits
    await brain.countdown.tick()
    assert agents.sent == []


async def test_send_now_and_the_countdowns_end_send_once(tmp_path):
    brain, agents, _, _ = brain_with(tmp_path, [row()])
    handoff = brain.give(row(), "Check the prices", "you")
    await asyncio.gather(brain.send_handoff(handoff.id), brain.send_handoff(handoff.id), brain.countdown.tick())
    assert len(agents.sent) == 1


async def test_the_inbox_keeps_this_runs_handoffs_and_every_open_one(tmp_path):
    from ai_browser.brain.handoffs import KEPT

    brain, *_ = brain_with(tmp_path, [row()], switch=False)
    first = brain.give(row(), "the first", "you")  # waits for Send
    for number in range(KEPT + 5):
        brain.cancel_handoff(brain.give(row(), f"task {number}", "you").id)
    assert len(brain.handoffs) == KEPT and first.id in brain.handoffs  # an open one always stays
    assert [one["instruction"] for one in brain.snapshot()["handoffs"]][-1] == f"task {KEPT + 4}"


def test_the_notification_names_no_instruction_and_no_agent():
    from ai_browser.desktop.notes import note_for

    assert note_for({"type": "handoff", "kind": "give", "counting": True}) == {
        "kind": "brain", "agent": "", "title": "The Brain is giving an agent a task",
        "body": "It sends in 15 seconds: cancel it in AI Browser."}
    assert note_for({"type": "handoff", "kind": "give", "counting": False})["title"] == \
        "The Brain has a task for an agent"
    assert note_for({"type": "handoff", "kind": "start"})["title"] == "The Brain suggests a new agent"


async def test_the_pages_send_and_cancel_and_stop_cancels(fake_claude, tmp_path):
    from ai_browser.app.server import MESSAGE_RULES, may_send
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore

    for kind in ("handoff_send", "handoff_cancel"):  # app-only, as every message a page sends
        assert kind in MESSAGE_RULES and may_send("app", {"type": kind}) and not may_send("none", {"type": kind})
    agents = Recorder([row()])
    brain = BrainService(BrainStore(tmp_path / "home"), agents, ask=Ask())
    brain.countdown = Clock()
    server, url = await started(fake_claude, tmp_path, EVENTS, brain=brain)
    try:
        assert brain.visible() is False  # no page open: a hand-off would wait
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "mission"}))
            await told_until(ws, lambda m: m["type"] == "snapshot")
            assert brain.visible() is True and brain.auto_hand() is True  # Settings → Brain's switch: on by default
            one = brain.give(row(), "Check the prices", "you")
            two = brain.give(row(), "Check the plans", "you")
            three = brain.give(row(), "Check the logos", "gmail")
            await ws.send(json.dumps({"type": "brain"}))
            snapshot = await told_until(ws, lambda m: m["type"] == "brain_snapshot")
            assert [card["id"] for card in snapshot[-1]["handoffs"]] == [one.id, two.id, three.id]
            await ws.send(json.dumps({"type": "handoff_cancel", "id": one.id}))
            await ws.send(json.dumps({"type": "handoff_send", "id": three.id}))  # Send on the waiting card
            await told_until(ws, lambda m: m["type"] == "brain_handoff" and m["handoff"]["id"] == three.id
                             and m["handoff"]["state"] == "sent")
            assert one.state == "cancelled" and agents.sent == [("a2", "From the Brain: Check the logos")]
            await ws.send(json.dumps({"type": "stop", "id": "a2"}))  # Stop on the agent: its countdown ends
            await told_until(ws, lambda m: m["type"] == "brain_handoff" and m["handoff"]["id"] == two.id)
            assert two.note == "Cancelled: you stopped agent 2"
            await ws.send(json.dumps({"type": "settings_set", "key": "auto_hand", "value": False, "request": "s"}))
            await told_until(ws, lambda m: m["type"] == "settings")
            assert brain.give(row(), "Check the fonts", "you").state == "waiting"  # off: every hand-off waits
    finally:
        await server.stop()
