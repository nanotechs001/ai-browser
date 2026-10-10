"""The Brain's kept chats (the chat-panel spec, 4-6; brain/chats.py): Mission Control's chat panel keeps the last 50
chats, each a private file of the user's words and the Brain's answers, written only by the app for ids it made; a
reopened chat gives the Brain only its last few exchanges, and its cards come back as text, never re-armed. Unit tests
first, then over the socket against a real app server (the fake claude)."""

import json
from datetime import UTC, datetime, timedelta
from itertools import count

from conftest import file_mode
from test_bridge import EVENTS

START = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
TITLE = "Find the cheapest flight to Manila next month, with one sto…"


def ticking():
    """A clock for Chats: a second later at each call, so "least recently updated" is the test's to say."""
    seconds = count()
    return lambda: (START + timedelta(seconds=next(seconds))).isoformat()


def test_a_kept_chat_is_a_private_file_with_its_title_and_times(tmp_path):
    from ai_browser.brain.chats import Chats

    chats = Chats(tmp_path / "home", clock=ticking())
    chat_id = chats.new()
    assert chats.kept(chat_id) and chats.list() == []  # made: nothing is written until its first exchange
    said = "  Find the cheapest flight\nto Manila next month, with one stop at most and a window seat please  "
    chats.add(chat_id, said, "On it.")
    chats.add(chat_id, "and a hotel", "Noted.")
    path = tmp_path / "home" / "brain" / "chats" / f"{chat_id}.json"
    assert file_mode(path) in (None, 0o600)  # the user's words: only they can read it
    assert chats.get(chat_id) == {
        "id": chat_id, "title": TITLE,  # the first words, one line, 60 characters at most
        "created": "2026-10-10T09:00:00+00:00", "updated": "2026-10-10T09:00:01+00:00",
        "exchanges": [{"said": said, "answer": "On it.", "time": "2026-10-10T09:00:00+00:00"},
                      {"said": "and a hotel", "answer": "Noted.", "time": "2026-10-10T09:00:01+00:00"}]}
    assert chats.list() == [{"id": chat_id, "title": TITLE, "updated": "2026-10-10T09:00:01+00:00", "count": 2}]
    assert chats.last(chat_id, 1) == [("and a hotel", "Noted.")]
    assert chats.delete(chat_id) is True and not path.exists() and chats.list() == []
    assert chats.delete(chat_id) is False


def test_the_last_50_chats_and_200_exchanges_are_kept(tmp_path):
    from ai_browser.brain.chats import KEEP_CHATS, KEEP_EXCHANGES, Chats

    chats = Chats(tmp_path / "home", clock=ticking())
    made = []
    for number in range(KEEP_CHATS):
        made.append(chats.new())
        chats.add(made[-1], f"chat {number}", "Noted.")
    chats.add(made[0], "the first one, again", "Noted.")  # now the most recently updated
    newest = chats.new()
    chats.add(newest, "chat 50", "Noted.")  # a 51st: the least recently updated goes
    listed = [row["id"] for row in chats.list()]
    assert len(listed) == KEEP_CHATS == 50 and made[1] not in listed
    assert listed[:2] == [newest, made[0]]  # newest first
    assert not (tmp_path / "home" / "brain" / "chats" / f"{made[1]}.json").exists()
    for number in range(KEEP_EXCHANGES + 5):
        chats.add(newest, f"question {number}", "Noted.")
    chat = chats.get(newest)
    assert len(chat["exchanges"]) == KEEP_EXCHANGES == 200  # the newest 200
    assert chat["exchanges"][0]["said"] == "question 5" and chat["title"] == "chat 50"  # the first words, still


def test_only_ids_the_app_made_are_kept_and_a_damaged_file_is_skipped(tmp_path):  # Review Focus 1
    from ai_browser.brain.chats import Chats

    home = tmp_path / "home"
    chats = Chats(home)
    folder = home / "brain" / "chats"
    for stranger in ("k1", "../x", "c" + "0" * 16, "C" + "a" * 16, "c" + "a" * 17, "c" + "a" * 16 + "\n", None, 7):
        assert chats.kept(stranger) is False and chats.get(stranger) is None and chats.delete(stranger) is False
        chats.add(stranger, "hello", "Noted.")  # a talk the app didn't make: never written
    assert not folder.exists() or list(folder.iterdir()) == []
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ("c" + "1" * 16 + ".json")).write_text("{ not json", encoding="utf-8")
    other = "c" + "2" * 16
    (folder / f"{other}.json").write_text(json.dumps({"id": other, "title": ["a"], "exchanges": [
        "a line", {"said": 7, "answer": "kept", "card": {"id": "p1", "kind": 3}}]}), encoding="utf-8")
    deep = "c" + "3" * 16
    (folder / f"{deep}.json").write_text("[" * 100_000, encoding="utf-8")  # nested past the parser's depth
    assert chats.get(deep) is None
    assert [row["id"] for row in chats.list()] == [other]  # the broken one is skipped
    assert chats.get(other)["exchanges"] == [{"said": "", "answer": "kept", "time": ""}]  # only what it should hold
    assert chats.get(other)["title"] == ""


def test_a_folder_that_cant_be_written_leaves_the_talk_going(tmp_path):  # Review Focus 4
    from ai_browser.brain.chats import Chats

    home = tmp_path / "home"
    (home / "brain").mkdir(parents=True)
    (home / "brain" / "chats").write_text("a file where the folder should be", encoding="utf-8")
    chats = Chats(home)
    chat_id = chats.new()
    chats.add(chat_id, "hello", "Noted.")  # no error: the talk goes on, unkept
    chats.card(chat_id, {"id": "p1", "kind": "start_agent"})
    chats.settle("p1", "Cancelled")
    assert chats.kept(chat_id) and chats.get(chat_id) is None and chats.list() == []


def test_a_card_is_kept_as_text_and_ends_once(tmp_path):
    from ai_browser.brain.chats import Chats

    chats = Chats(tmp_path / "home")
    chat_id = chats.new()
    chats.add(chat_id, "check the shop", "I can start an agent.")
    chats.card(chat_id, {"id": "p1", "kind": "start_agent", "task": "check the shop", "expires_in": 120})
    assert chats.get(chat_id)["exchanges"][-1]["card"] == {"id": "p1", "kind": "start_agent", "outcome": None}
    chats.settle("p1", "Started: 1 · check the shop")
    chats.settle("p1", "Cancelled")  # it ended once: a second word changes nothing
    assert chats.get(chat_id)["exchanges"][-1]["card"]["outcome"] == "Started: 1 · check the shop"
    chats.add(chat_id, "tell agent 2 too", "Giving your words to 2 · Research.")
    chats.card(chat_id, {"id": "h1", "kind": "give", "instruction": "tell agent 2 too"})
    again = Chats(tmp_path / "home")  # the app restarted: this run's cards ended with it
    again.settle("h1", "Sent to agent 2")
    assert again.get(chat_id)["exchanges"][-1]["card"] == {"id": "h1", "kind": "give", "outcome": None}


def test_a_restored_talk_gives_the_brain_only_its_last_exchanges():
    from ai_browser.brain.talk import KEEP, Talks

    talks = Talks()
    added = []
    talks.on_add = lambda talk, said, answer: added.append((talk, said, answer))
    talks.restore("c1", [(f"q{number}", f"a{number}") for number in range(10)])
    assert talks.history("c1") == [(f"q{number}", f"a{number}") for number in range(10 - KEEP, 10)]
    talks.restore("c1", [("other", "x")])  # a talk still in memory keeps its own
    assert talks.history("c1")[-1] == ("q9", "a9")
    talks.add("c1", "q10", "a10")
    assert added == [("c1", "q10", "a10")]  # a restore is no exchange: only add is heard


async def test_the_brain_says_how_each_card_ended(tmp_path):
    from ai_browser.brain.chats import CARD_CANCELLED
    from ai_browser.brain.handoffs import CANCELLED
    from test_brain_handoffs import brain_with, row

    brain, agents, _, _ = brain_with(tmp_path, [row()])
    ended = []
    brain.card_ended = lambda card, outcome: ended.append((card, outcome))
    cancelled = brain.talks.propose("c1", "start_agent", task="check the shop", model="sonnet")
    brain.dismiss("c1", cancelled.id)
    brain.dismiss("c1", cancelled.id)  # a second Cancel: nothing more
    started = brain.talks.propose("c1", "start_agent", task="check the cart", model="sonnet")
    answer = await brain.confirm("c1", started.id)
    one = brain.give(row(), "Check the footer too", "you")
    brain.cancel_handoff(one.id)
    two = brain.give(row(), "Check the header too", "you")
    await brain.send_handoff(two.id)
    assert answer["say"].startswith("Started: ")
    assert ended == [(cancelled.id, CARD_CANCELLED), (started.id, answer["say"]), (one.id, CANCELLED),
                     (two.id, "Sent to agent 2")]


# ---- over the socket: the panel's four messages, app-only (Task 2) ---------------------------------------------------

def test_the_chat_messages_are_app_only_rows():
    from ai_browser.app.server import MESSAGE_RULES, may_send

    for kind in ("brain_chats", "brain_chat_open", "brain_chat_new", "brain_chat_delete"):
        assert MESSAGE_RULES[kind].app and may_send("app", {"type": kind})
        assert not may_send("watcher", {"type": kind}) and not may_send("none", {"type": kind})


async def test_the_panels_chats_are_kept_reopened_after_a_restart_and_deleted(fake_claude, tmp_path):
    from ai_browser.brain.talk import KEEP, START_SAY
    from test_app_server import TALKING, hello, until, with_hearing
    from test_oneshot import oneshots
    from ui_socket import ui_socket

    _, log, _ = fake_claude
    script = {"default": EVENTS, TALKING: [
        {"result": json.dumps({"say": "I can start an agent.", "action": "start_agent"})},
        {"result": json.dumps({"say": "Noted.", "action": "none"})}]}
    server, url, _ = await with_hearing(fake_claude, tmp_path, script)
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            await ws.send(json.dumps({"type": "brain_chat_new", "request": "n1"}))
            made = (await until(ws, lambda m: m["type"] == "brain_chat"))[-1]
            chat_id = made["chat"]["id"]
            assert made == {"type": "brain_chat", "request": "n1",
                            "chat": {"id": chat_id, "title": "", "exchanges": []}}
            await ws.send(json.dumps({"type": "brain_chats"}))
            assert (await until(ws, lambda m: m["type"] == "brain_chats"))[-1]["chats"] == []  # empty: never listed
            for number in range(KEEP + 2):
                await ws.send(json.dumps({"type": "brain_ask", "talk": chat_id, "request": f"t{number}",
                                          "text": f"question {number}"}))
                answer = (await until(ws, lambda m: m["type"] == "brain_answer"
                                      and m["request"] == f"t{number}"))[-1]
                if number == 0:  # a card: Cancel on it
                    assert answer["say"] == START_SAY
                    card = answer["proposal"]["id"]
                    await ws.send(json.dumps({"type": "brain_dismiss", "talk": chat_id, "proposal": card}))
            await ws.send(json.dumps({"type": "brain_ask", "talk": "k1", "request": "f1", "text": "a floating one"}))
            await until(ws, lambda m: m["type"] == "brain_answer" and m["request"] == "f1")  # a talk the app didn't make
            await ws.send(json.dumps({"type": "brain_chats"}))
            [row] = (await until(ws, lambda m: m["type"] == "brain_chats"))[-1]["chats"]
            assert (row["id"], row["title"], row["count"]) == (chat_id, "question 0", KEEP + 2)
    finally:
        await server.stop()
    path = tmp_path / "home" / "brain" / "chats" / f"{chat_id}.json"
    assert file_mode(path) in (None, 0o600) and [one.name for one in path.parent.iterdir()] == [path.name]
    first = json.loads(path.read_text(encoding="utf-8"))["exchanges"][0]
    assert first["card"] == {"id": card, "kind": "start_agent", "outcome": "Cancelled"}  # kept as text
    server, url, _ = await with_hearing(fake_claude, tmp_path, script)  # the app again, on the same home
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            await ws.send(json.dumps({"type": "brain_chat_open", "id": chat_id, "request": "o1"}))
            reopened = (await until(ws, lambda m: m["type"] == "brain_chat"))[-1]
            assert reopened["request"] == "o1"
            assert [one["said"] for one in reopened["chat"]["exchanges"]] == [f"question {n}" for n in range(KEEP + 2)]
            asked = len(oneshots(log))
            await ws.send(json.dumps({"type": "brain_ask", "talk": chat_id, "request": "t9", "text": "and now?"}))
            await until(ws, lambda m: m["type"] == "brain_answer" and m["request"] == "t9")
            prompt = [call["oneshot"] for call in oneshots(log)[asked:] if TALKING in call["oneshot"]][-1]
            assert "- The user: question 1\n" not in prompt  # the Brain gets its last KEEP exchanges only
            assert "- The user: question 2\n" in prompt and f"- The user: question {KEEP + 1}\n" in prompt
            await ws.send(json.dumps({"type": "brain_ask", "talk": chat_id, "request": "t10", "text": "yes",
                                      "proposal": card}))  # Review Focus 5: a yes to the old card runs nothing
            said = (await until(ws, lambda m: m["type"] == "brain_answer" and m["request"] == "t10"))[-1]
            assert "proposal" not in said and "created" not in said and server.agents.agents == {}
            for bad in ("../../x", "k1", "c" + "0" * 16, 7):
                await ws.send(json.dumps({"type": "brain_chat_open", "id": bad, "request": "o2"}))
                gone = (await until(ws, lambda m: m["type"] == "error" and m.get("request") == "o2"))[-1]
                assert gone["text"] == "That chat is gone"
            await ws.send(json.dumps({"type": "brain_chat_delete", "id": chat_id, "request": "d1"}))
            assert (await until(ws, lambda m: m["type"] == "brain_chats"))[-1]["chats"] == []
            assert not path.exists()
            asked = len(oneshots(log))
            await ws.send(json.dumps({"type": "brain_ask", "talk": chat_id, "request": "t11", "text": "still there?"}))
            await until(ws, lambda m: m["type"] == "brain_answer" and m["request"] == "t11")
            assert not path.exists()  # Review Focus 2: an answer for the deleted chat writes nothing back
            prompt = [call["oneshot"] for call in oneshots(log)[asked:] if TALKING in call["oneshot"]][-1]
            assert "- The user: question" not in prompt and "- The user: and now?" not in prompt  # its words never reach the Brain again
    finally:
        await server.stop()


async def test_a_reopened_chat_never_re_arms_its_card_in_the_same_run(fake_claude, tmp_path):  # fix round 1
    from ai_browser.brain.talk import START_SAY
    from test_app_server import TALKING, hello, until, with_hearing
    from ui_socket import ui_socket

    script = {"default": EVENTS, TALKING: [
        {"result": json.dumps({"say": "I can start an agent.", "action": "start_agent"})},
        {"result": json.dumps({"say": "Noted.", "action": "none"})}]}
    server, url, _ = await with_hearing(fake_claude, tmp_path, script)
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            ids = []
            for name in ("a", "b"):
                await ws.send(json.dumps({"type": "brain_chat_new", "request": f"n{name}"}))
                ids.append((await until(ws, lambda m: m["type"] == "brain_chat"))[-1]["chat"]["id"])
                await ws.send(json.dumps({"type": "brain_ask", "talk": ids[-1], "request": f"q{name}",
                                          "text": "start one"}))
                answer = (await until(ws, lambda m: m["type"] == "brain_answer" and m["request"] == f"q{name}"))[-1]
                if name == "a":
                    assert answer["say"] == START_SAY
                    card = answer["proposal"]["id"]
            for chat_id, request in ((ids[1], "ob"), (ids[0], "oa")):  # another chat, then the first one again
                await ws.send(json.dumps({"type": "brain_chat_open", "id": chat_id, "request": request}))
                await until(ws, lambda m: m["type"] == "brain_chat" and m["request"] == request)
            await ws.send(json.dumps({"type": "brain_ask", "talk": ids[0], "request": "y1", "text": "yes",
                                      "proposal": card}))
            said = (await until(ws, lambda m: m["type"] == "brain_answer" and m["request"] == "y1"))[-1]
            assert "proposal" not in said and "created" not in said and server.agents.agents == {}
            first = json.loads((tmp_path / "home" / "brain" / "chats" / f"{ids[0]}.json")
                               .read_text(encoding="utf-8"))["exchanges"][0]
            assert first["card"] == {"id": card, "kind": "start_agent", "outcome": "Not answered"}

            def refuse(chat_id):
                raise PermissionError(13, "Permission denied", "/private/home/brain/chats/x.json")

            server.chats.delete = refuse
            await ws.send(json.dumps({"type": "brain_chat_delete", "id": ids[0], "request": "d1"}))
            failed = (await until(ws, lambda m: m["type"] == "error" and m.get("request") == "d1"))[-1]
            assert failed["text"] == "Couldn't delete that chat."  # fixed words: never a path
    finally:
        await server.stop()


# ---- the README (Task 7) --------------------------------------------------------------------------------------------

def test_the_readme_explains_the_brains_chat_and_the_profile_dot():
    from pathlib import Path

    text = " ".join((Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8").split())
    for needed in ("### The Brain's chat (Ask AI)", "the office, the desks and the drawers stay clickable around it",
                   "**×** or **Esc** closes it", "It opens by itself when the Brain needs you",
                   "count down only while it is open", "**History ▾** lists your last 50 chats",
                   "the Brain reads its last 6 exchanges again", "never run again", "**Delete** asks first",
                   "`~/.ai-browser/brain/chats/<id>.json`", "The floating chat and the inbox's talks are not kept",
                   "**Ready** (green), **Open it once** (amber", "**Brave not connected** (grey)",
                   "Nothing opens Brave by itself", "with **History ▾** open, the first **Esc** closes the list",
                   "A chat deleted meanwhile says \"That chat is gone\"", "**Ready** once a Brave window is open",
                   "When Brave connects again, each profile is learned again",
                   # the final review's fixes
                   "it moves aside for an open drawer and for an agent's settings",
                   "then opens over it, and its cards wait for your **Send**", "An agent with **No web** shows none",
                   "the last 6 exchanges of a chat you reopen go to Claude, as the Brain's context"):
        assert needed in text, needed
    for gone in ("a short strip", "turns solid and scrolls", "**Ask AI**, in the composer", "beside Start",
                 "they go nowhere but AI Browser's own pages."):
        assert gone not in text, gone
