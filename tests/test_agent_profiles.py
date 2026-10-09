"""A saved agent's Brave profile (the saved-agents spec, 4): its runs open their tabs only in the browser context AI
Browser learned for that profile (app/place.py), the app's own client opens them, and an agent of its own profile
may not open one by itself through the relay. A profile not learned yet gives the user fixed words, and Claude words
that name no profile. Fake Braves only: a fake debugging port, or BraveLink's stand-in."""

import json

import httpx
import pytest

from fake_brave import FakeBrave, FakePort, relay_client, until
from test_app_server import agent_headers, started
from test_bravelink import PROFILES, connected, local_state
from test_bridge import EVENTS
from test_cdprelay import rig  # noqa: F401  (a fixture)
from test_place import Clock
from test_saved_agents import AGENT


def test_each_profile_has_its_own_context_once_learned(tmp_path):
    from ai_browser.app.place import ProfilePlace

    clock, connection = Clock(), object()
    place = ProfilePlace(tmp_path, settle=12, clock=clock)
    local_state(tmp_path, last_used="Profile 1")
    place.look(connection, "P")
    clock.now = 13
    assert place.look(connection, "P") is True  # Home (Profile 1) is P
    assert place.ready("Profile 1") is True and place.ready("Default") is False
    assert place.context("P", "Profile 1") == ("P", "chosen")  # an agent of Home
    assert place.context("P", "Default") == (None, "not_open")  # an agent of Work: not learned yet
    assert place.context("P") == ("P", "last_used")  # Settings' choice: none chosen, the profile used last
    place.chosen = "Default"
    assert place.context("P") == (None, "not_open") and place.context("P", "Profile 1") == ("P", "chosen")


async def test_a_runs_tabs_open_only_in_its_own_profile(tmp_path):
    from ai_browser.app.bravelink import NOT_OPEN, OTHER_PROFILE, PlaceError

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    local_state(folder, last_used="Default")
    port = FakePort(folder, pages=PROFILES, default="W")
    await port.start()
    link = await connected(folder)  # Settings' choice: the profile used last
    try:
        assert await until(lambda: link.place.ready("Default"))  # Work is W
        with pytest.raises(PlaceError) as refused:
            await link.open_ai_tab("a2", profile="Profile 1")  # Home: not learned on this connection
        assert str(refused.value) == NOT_OPEN and "Home" not in NOT_OPEN  # Claude's words name no profile
        target = await link.open_ai_tab("a1", profile="Default")
        assert port.page(target)["context"] == "W"
        port.set_default("P")  # the user clicks a window of Home
        local_state(folder, last_used="Profile 1")
        assert await until(lambda: link.place.ready("Profile 1"))
        assert port.page(await link.open_ai_tab("a2", profile="Profile 1"))["context"] == "P"
        with pytest.raises(PlaceError) as elsewhere:
            await link.open_ai_tab("a1", profile="Default")  # Brave's last window is Home's: nothing opens in it
        assert str(elsewhere.value) == OTHER_PROFILE
        assert sorted(page["context"] for page in port.pages if page["target"].startswith("T")) == ["P", "W"]
    finally:
        await link.close()
        await port.stop()


async def test_an_agent_of_its_own_profile_never_opens_a_tab_by_itself(rig):  # noqa: F811
    from ai_browser.app.cdprelay import OWN_PROFILE
    from ai_browser.cdp import CDPError

    await rig.relay.open("start")
    rig.relay.placed_only = lambda identity: identity == "a1"  # the server's: a run of a saved agent's own profile
    a1, a2 = await rig.client("a1"), await rig.client("a2")
    with pytest.raises(CDPError, match="AI Browser opens this agent's tabs"):
        await a1.send("Target.createTarget", {"url": "about:blank"})
    assert OWN_PROFILE[1] == "AI Browser opens this agent's tabs, in its own Brave profile"
    assert "Target.createTarget" not in rig.port.methods  # nothing reached Brave
    await a2.send("Target.createTarget", {"url": "about:blank"})  # any other agent: as before
    assert len(rig.sent("Target.createTarget")) == 1


async def test_the_app_opens_a_runs_tab_in_its_profile_and_says_when_it_isnt_learned(fake_claude, tmp_path):
    from ai_browser.app.bravelink import NOT_OPEN, PlaceError

    server, url = await started(fake_claude, tmp_path, EVENTS)
    brave = FakeBrave([])
    brave.place.listed = [{"folder": "Profile 1", "name": "Work", "color": None}]
    server.attach_brave(brave)
    saved = server.saved.save({**AGENT, "profile": "Profile 1", "load_at_start": []})
    try:
        run, _ = await server.agents.run_as(saved, "List the prices")
        plain = await server.agents.create("Fix the footer")
        assert run.profile == "Profile 1" and plain.profile is None
        assert brave.relay.placed_only(run.id) is True and brave.relay.placed_only(plain.id) is False
        async with httpx.AsyncClient() as client:
            for agent in (run.id, plain.id):
                answer = await client.post(url + "/agent-tab", headers=agent_headers(server, agent),
                                           json={"agent": agent})
                assert answer.json().get("target")
            assert brave.opened_in == [(run.id, "Profile 1"), (plain.id, None)]  # Settings' choice for a one-off
            brave.ai_tab_error = PlaceError(NOT_OPEN)
            for _ in range(2):
                answer = await client.post(url + "/agent-tab", headers=agent_headers(server, run.id),
                                           json={"agent": run.id})
                assert answer.json() == {"error": NOT_OPEN}  # Claude's words: no profile's name
        notes = [event["text"] for event in server.agents.events_of(run.id) if event["type"] == "note"]
        assert notes == ["Agent 1 browses in Brave's Work profile. Open a window of that profile once; AI Browser "
                         "learns it in about 30 seconds."]  # the user's words, once
        brave.place.learned = {"Profile 1"}
        assert server._saved_snapshot()["profiles"] == [{"folder": "Profile 1", "name": "Work", "color": None,
                                                         "ready": True}]
        assert json.loads(json.dumps(server._settings_payload()["profiles"])) == brave.place.listed  # Settings' own
    finally:
        await server.stop()


async def test_an_agent_shaped_client_the_app_no_longer_knows_never_opens_a_tab(fake_claude, tmp_path, rig):  # noqa: F811
    from ai_browser.app.cdprelay import OWN_PROFILE
    from ai_browser.cdp import CDPError

    server, _ = await started(fake_claude, tmp_path, EVENTS)
    try:
        await rig.relay.open("start")
        rig.relay.placed_only = server._placed_only  # the server's own rule
        plain = await server.agents.create("Fix the footer")
        gone = await rig.client("a7")  # a run's socket still open after AgentManager.close dropped it: fail closed
        with pytest.raises(CDPError, match=OWN_PROFILE[1]):
            await gone.send("Target.createTarget", {"url": "about:blank"})
        assert "Target.createTarget" not in rig.port.methods  # nothing reached Brave
        await (await rig.client(plain.id)).send("Target.createTarget", {"url": "about:blank"})  # a one-off: as before
        await (await rig.client("cc-task-1")).send("Target.createTarget", {"url": "about:blank"})  # a session: too
        assert len(rig.sent("Target.createTarget")) == 2
    finally:
        await server.stop()


async def test_a_new_runs_token_opens_a_tab_as_soon_as_it_is_created(fake_claude, tmp_path):
    """create() registers the run before anything can carry its token: the token is minted and the run listed with no
    await between, and its Claude Code (and so its engine) starts only in the run's turn, after that. Fail closed never
    meets a live run of no profile of its own."""
    from ai_browser.app.bravelink import BraveLink

    server, url = await started(fake_claude, tmp_path, EVENTS)
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder)
    await port.start()
    brave = BraveLink(folder, allow_wait=2, every=0.1, tokens=server.tokens)
    server.attach_brave(brave)
    await brave.start()
    await brave.connect()
    try:
        run = await server.agents.create("Fix the footer")
        token = run.bridge.env["AIB_APP_AGENT_TOKEN"]  # what its engine connects with
        assert run.profile is None and server._placed_only(run.id) is False
        cdp = await relay_client(url.replace("http://", "ws://", 1) + "/cdp", token)
        try:
            assert (await cdp.send("Target.createTarget", {"url": "about:blank"}))["targetId"]
        finally:
            await cdp.close()
        assert port.methods.count("Target.createTarget") == 1  # it reached Brave
    finally:
        await server.stop()
        await brave.close()
        await port.stop()


async def test_the_not_learned_note_names_at_most_60_characters_of_the_profile(fake_claude, tmp_path):
    server, _ = await started(fake_claude, tmp_path, EVENTS)
    brave = FakeBrave([])
    brave.place.listed = [{"folder": "Profile 1", "name": "W" * 500, "color": None}]  # Brave's name: the user's own
    server.attach_brave(brave)
    saved = server.saved.save({**AGENT, "profile": "Profile 1", "load_at_start": []})
    try:
        run, _ = await server.agents.run_as(saved, "List the prices")
        server._not_learned(run)
        notes = [event["text"] for event in server.agents.events_of(run.id) if event["type"] == "note"]
        assert notes == [f"Agent 1 browses in Brave's {'W' * 60} profile. Open a window of that profile once; AI "
                         "Browser learns it in about 30 seconds."]
    finally:
        await server.stop()
