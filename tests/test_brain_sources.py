"""What the Brain listens to (the brain-delegation spec, 4): Settings → Brain's checkboxes, each on by default. An
unchecked source never reaches Claude: an inbox site or a watched part isn't read at all, agents' chats and results
are left out of what the Brain reads, and the floating chat's questions aren't asked. Claude is faked in Python (`Ask`)
or by the fake claude; Brave by tests/fake_reading.py."""

import asyncio
import json

import pytest

from fake_brave import until
from fake_reading import GMAIL, ReadingBrave, row
from test_app_server import started
from test_app_server import until as told_until
from test_bridge import EVENTS
from ui_socket import ui_socket

SLACK = "https://app.slack.com/client/T1/C1"
EVERY = {"agents": True, "gmail": True, "slack": True, "asana": True, "pages": True, "chat": True}


class Ask:
    """Claude, faked: each prompt is kept, and the first of `answers` whose key is in the prompt answers it."""

    def __init__(self, answers=None):
        self.prompts, self.answers = [], dict(answers or {})

    async def __call__(self, prompt, **options):
        from ai_browser.brain.oneshot import OneShot

        self.prompts.append(prompt)
        answer = next((answer for key, answer in self.answers.items() if key in prompt), "[]")
        return OneShot(text=answer if isinstance(answer, str) else json.dumps(answer))


def brain_with(tmp_path, ask, agents=None):
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore

    brain = BrainService(BrainStore(tmp_path / "home"), agents, ask=ask, batch_wait=0.05)
    brain.outbox = lambda message: True
    brain.broadcast = lambda message: None
    return brain


def test_each_source_is_a_checkbox_on_by_default(tmp_path):
    from ai_browser.settings import Settings

    settings = Settings(tmp_path)
    assert settings.get()["brain_sources"] == EVERY and settings.get()["auto_hand"] is True
    assert settings.get()["read_tabs"] is False  # the switch that reads the user's tabs at all stays as it was
    assert settings.set("brain_sources", {"gmail": False, "chat": False})["brain_sources"] == {
        **EVERY, "gmail": False, "chat": False}  # a source the file doesn't name is on
    assert Settings(tmp_path).get()["brain_sources"]["gmail"] is False  # kept
    for wrong in ({"gmail": "no"}, {"facebook": True}, ["gmail"], None, True):
        with pytest.raises(ValueError, match="Pick what the Brain listens to"):
            settings.set("brain_sources", wrong)
    with pytest.raises(ValueError):
        settings.set("auto_hand", "yes")
    assert settings.set("auto_hand", False)["auto_hand"] is False


async def test_an_unchecked_inbox_site_is_never_read_nor_sorted(tmp_path):
    from ai_browser.brain.inbox import InboxReader

    ask = Ask()
    brain = brain_with(tmp_path, ask)
    brain.set_sources({**EVERY, "gmail": False})
    brave = ReadingBrave([{"target": "U1", "url": GMAIL, "site": "gmail"},
                          {"target": "U2", "url": SLACK, "site": "slack"}])
    brave.answers[("U1", "read")] = lambda kind, config: {"known": True, "items": [row("t1")]}
    brave.answers[("U2", "read")] = lambda kind, config: {"known": True, "items": [row("s1")]}
    reader = InboxReader(brain, brave, every=0.05)
    reader.set_on(True)
    try:
        assert await until(lambda: [call[0] for call in brave.reads()].count("U2") >= 2)
        await brain.settle()
        assert "U1" not in [call[0] for call in brave.reads()]  # Gmail's tab isn't read at all
        assert len(ask.prompts) == 1 and "s1" in ask.prompts[0] and "t1" not in ask.prompts[0]
        await brain.on_items("gmail", [row("t9")])  # even what a reader hands over is dropped
        await asyncio.sleep(0.2)
        await brain.settle()
        assert len(ask.prompts) == 1 and brain.store.get("gmail:t9") is None
    finally:
        await reader.stop()


async def test_unchecking_drops_what_waits_to_be_sorted(tmp_path):
    ask = Ask()
    brain = brain_with(tmp_path, ask)
    brain.batch_wait = 0.3
    await brain.on_items("gmail", [row("t1"), row("t2")])
    brain.set_sources({**EVERY, "gmail": False})  # while the batch waits
    await asyncio.sleep(0.5)
    await brain.settle()
    assert ask.prompts == [] and brain.snapshot()["items"] == []
    assert brain.snapshot()["sources"] == {**EVERY, "gmail": False}  # Settings → Brain's lines read it


async def test_unchecking_while_claude_sorts_keeps_nothing_of_that_batch(tmp_path):  # Review Focus 5
    from ai_browser.brain.oneshot import OneShot

    brain = None

    async def ask(prompt, **options):  # the user unchecks Gmail while Claude reads the batch
        brain.set_sources({**EVERY, "gmail": False})
        return OneShot(text=json.dumps([{"id": "gmail:t1", "kind": "needs_reply", "summary": "x", "why": "",
                                         "suggest": "draft"}]))

    brain = brain_with(tmp_path, ask)
    shown = []
    brain.outbox = lambda message: shown.append(message) or True
    await brain.on_items("gmail", [row("t1")])
    await asyncio.sleep(0.2)
    await brain.settle()
    assert brain.snapshot()["items"] == [] and shown == []  # nothing kept, nothing notified


async def test_the_talk_reads_only_what_the_brain_listens_to(tmp_path):
    from ai_browser.brain.store import Item
    from test_brain_service import FakeAgents

    rows = [{"id": "a1", "number": 1, "name": "Fix the footer", "color": "blue", "state": "working",
             "status": "open https://secret.example/admin", "last_action": "click e4 · 30 ms", "created": 1.0}]
    ask = Ask({"talking with the user": {"say": "Two things.", "action": "none"}})
    brain = brain_with(tmp_path, ask, FakeAgents(rows))
    for site, sender in (("gmail", "Maria Santos"), ("slack", "Dev channel")):
        brain.store.put(Item(id=f"{site}:t1", site=site, raw_id="t1", sender=sender, subject="Launch",
                             summary="asks about the launch", kind="needs_reply"))
    await brain.respond("k1", "what's going on?")
    assert "secret.example" in ask.prompts[-1] and "Maria Santos" in ask.prompts[-1]  # all on: as today
    brain.set_sources({**EVERY, "agents": False, "gmail": False})
    await brain.respond("k1", "and now?")
    prompt = ask.prompts[-1]
    assert "secret.example" not in prompt and "click e4" not in prompt  # agents' chats stay out
    assert "Fix the footer" in prompt  # its number, name and state are the app's
    assert "Maria Santos" not in prompt and "Dev channel" in prompt  # an unchecked site's messages stay out


async def test_a_draft_or_a_tell_about_an_unchecked_sites_message_reads_nothing(tmp_path):
    from ai_browser.brain.service import NOT_LISTENING
    from ai_browser.brain.store import Item

    asked, ask = [], Ask()
    brain = brain_with(tmp_path, ask)
    brain.outbox = lambda message: asked.append(message) or True
    brain.store.put(Item(id="gmail:t1", site="gmail", raw_id="t1", sender="Maria", subject="Launch",
                         url="https://mail.google.com/mail/u/0/#inbox/t1", kind="needs_reply"))
    brain.set_sources({**EVERY, "gmail": False})
    await brain.draft("gmail:t1")
    assert brain.store.get("gmail:t1").note == NOT_LISTENING.format(name="Gmail") == \
        "Gmail is unchecked in Settings → Brain: the Brain doesn't read it"
    await brain.tell("gmail:t1", "draft a polite no")
    assert asked == [] and ask.prompts == []  # no thread opened, nothing asked


async def test_the_gate_lets_no_reader_run_where_the_brain_doesnt_listen(fake_claude, tmp_path):
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore

    home = tmp_path / "home"
    brain = BrainService(BrainStore(home), ask=Ask())
    assert brain.set_watch({"site": "custom:shop.example", "url_match": "https://shop.example/orders*",
                            "selector": "#orders", "enabled": True}) == ""
    server, _ = await started(fake_claude, tmp_path, EVENTS, brain=brain)
    try:
        assert server._brain_site(GMAIL) == "gmail"
        assert server._brain_site("https://shop.example/orders/1") == "custom:shop.example"
        server.settings.set("brain_sources", {"gmail": False, "pages": False})
        brain.set_sources(server.settings.get()["brain_sources"])
        assert server._brain_site(GMAIL) is None and server._brain_site(SLACK) == "slack"
        assert server._brain_site("https://shop.example/orders/1") is None
    finally:
        await server.stop()


async def test_the_floating_chat_is_heard_only_while_it_is_checked(fake_claude, tmp_path):
    from ai_browser.app.server import CHAT_OFF
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore

    ask = Ask({"talking with the user": {"say": "It opens at 9.", "action": "none"}})
    brain = BrainService(BrainStore(tmp_path / "home"), ask=ask)
    server, url = await started(fake_claude, tmp_path, EVENTS, brain=brain)
    try:
        async with ui_socket(server, url) as chat, ui_socket(server, url) as mission:
            for ws, view in ((chat, "chat"), (mission, "mission")):
                await ws.send(json.dumps({"type": "hello", "view": view}))
                await told_until(ws, lambda m: m["type"] == "snapshot")
            await chat.send(json.dumps({"type": "settings_set", "key": "brain_sources",
                                        "value": {**EVERY, "chat": False}, "request": "s1"}))
            settings = await told_until(chat, lambda m: m["type"] == "settings")
            assert settings[-1]["brain_sources"]["chat"] is False
            ask_it = {"type": "brain_ask", "talk": "k1", "request": "r1", "text": "when does it open?"}
            await chat.send(json.dumps(ask_it))
            answer = await told_until(chat, lambda m: m["type"] == "brain_answer")
            assert answer[-1]["error"] == CHAT_OFF and ask.prompts == []  # the chat's words never reach Claude
            await mission.send(json.dumps({**ask_it, "talk": "k2"}))  # Mission Control's Ask AI is the user's own
            answer = await told_until(mission, lambda m: m["type"] == "brain_answer")
            assert answer[-1]["say"] == "It opens at 9." and len(ask.prompts) == 1
    finally:
        await server.stop()


def test_a_newer_builds_source_never_turns_an_unchecked_one_back_on(tmp_path):  # review, fix round 1
    from ai_browser.settings import Settings

    (tmp_path / "settings.json").write_text(json.dumps({"brain_sources": {"gmail": False, "calendar": True}}),
                                            encoding="utf-8")
    settings = Settings(tmp_path)
    assert settings.get()["brain_sources"] == {**EVERY, "gmail": False}  # read leniently: Gmail stays unchecked
    with pytest.raises(ValueError, match="Pick what the Brain listens to"):
        settings.set("brain_sources", {"gmail": False, "calendar": True})  # set stays strict


async def test_the_saved_boxes_hold_from_the_start(fake_claude, tmp_path):
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore
    from ai_browser.settings import write_setting

    home = tmp_path / "home"
    write_setting(home, "brain_sources", {"gmail": False})  # saved by an earlier run
    brain = BrainService(BrainStore(home), ask=Ask())
    server, _ = await started(fake_claude, tmp_path, EVENTS, brain=brain)
    try:
        assert brain.listens("gmail") is False and brain.listens("slack") is True
        assert server._brain_site(GMAIL) is None and server._brain_site(SLACK) == "slack"
    finally:
        await server.stop()


async def test_a_box_unchecked_while_a_thread_opens_reads_nothing_of_it(tmp_path):
    from ai_browser.brain.inbox import OFF_SITE
    from ai_browser.brain.service import NOT_LISTENING
    from ai_browser.brain.store import Item

    sent, ask = [], Ask()
    brain = brain_with(tmp_path, ask)
    brain.outbox = lambda message: sent.append(message) or True
    brain.store.put(Item(id="gmail:t1", site="gmail", raw_id="t1", sender="Maria", subject="Launch",
                         url="https://mail.google.com/mail/u/0/#inbox/t1", kind="needs_reply"))
    for answer in ({"text": "Maria: can we move the launch?"}, {"error": OFF_SITE}):  # its text, or the gate's no
        brain.set_sources(EVERY)
        drafting = asyncio.ensure_future(brain.draft("gmail:t1"))
        assert await until(lambda: sent and sent[-1]["type"] == "open_thread" and brain.store.get("gmail:t1").state
                           == "drafting")
        brain.set_sources({**EVERY, "gmail": False})  # while the thread opens
        brain.on_thread(sent[-1]["request"], **answer)
        await drafting
        item = brain.store.get("gmail:t1")
        assert ask.prompts == [] and item.state == "open"  # the thread never reaches Claude
        assert item.note == NOT_LISTENING.format(name="Gmail")  # not "its link leads off its site"
        sent.clear()


async def test_use_draft_fills_nothing_while_its_site_is_unchecked(tmp_path):
    from ai_browser.brain.service import NOT_LISTENING
    from ai_browser.brain.store import Item

    sent = []
    brain = brain_with(tmp_path, Ask())
    brain.outbox = lambda message: sent.append(message) or True
    brain.store.put(Item(id="gmail:t1", site="gmail", raw_id="t1", sender="Maria", subject="Launch",
                         url="https://mail.google.com/mail/u/0/#inbox/t1", kind="needs_reply", state="draft_ready",
                         draft="Monday works.", draft_version=1))
    brain.set_sources({**EVERY, "gmail": False})
    await brain.approve("gmail:t1", "Monday works.", 1)
    item = brain.store.get("gmail:t1")
    assert sent == [] and item.state == "draft_ready" and item.note == NOT_LISTENING.format(name="Gmail")


async def test_a_message_an_uncheck_dropped_comes_back_when_it_is_checked_again(tmp_path):
    from ai_browser.brain.inbox import InboxReader

    ask = Ask()
    brain = brain_with(tmp_path, ask)
    brain.batch_wait = 1.0  # the batch waits while the box goes off and on
    brave = ReadingBrave([{"target": "U1", "url": GMAIL, "site": "gmail"}])
    brave.answers[("U1", "read")] = lambda kind, config: {"known": True, "items": [row("t1")]}
    reader = InboxReader(brain, brave, every=0.05)
    reader.set_on(True)
    try:
        assert await until(lambda: len(brave.reads()) >= 2)  # t1 was handed over, and waits to be sorted
        brain.set_sources({**EVERY, "gmail": False})
        brain.set_sources(EVERY)  # within one round
        assert await until(lambda: ask.prompts)
        await brain.settle()
        assert len(ask.prompts) == 1 and "t1" in ask.prompts[0]  # it came back, and was sorted once
        brain.set_sources({**EVERY, "gmail": False})
        brain.set_sources(EVERY)
        reads = len(brave.reads())
        assert await until(lambda: len(brave.reads()) >= reads + 3)
        await brain.settle()
        assert len(ask.prompts) == 1  # what was sorted isn't sorted again
    finally:
        await reader.stop()


async def test_an_uncheck_drops_the_waiting_batch_at_once(tmp_path):
    ask = Ask()
    brain = brain_with(tmp_path, ask)
    brain.batch_wait = 0.3
    await brain.on_items("gmail", [row("t1")])
    brain.set_sources({**EVERY, "gmail": False})
    brain.set_sources(EVERY)  # checked again before the batch is sorted: what the uncheck dropped stays dropped
    await asyncio.sleep(0.5)
    await brain.settle()
    assert ask.prompts == []
    await brain.on_items("gmail", [row("t1")])  # handed over again (the reader forgot it): it is taken, and sorted
    await asyncio.sleep(0.5)
    await brain.settle()
    assert len(ask.prompts) == 1 and "t1" in ask.prompts[0]


async def test_a_closed_pages_view_is_forgotten(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "chat"}))
            await told_until(ws, lambda m: m["type"] == "snapshot")
            assert list(server._views.values()) == ["chat"]
        assert await until(lambda: not server._views)
    finally:
        await server.stop()
