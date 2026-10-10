"""Where agents browse (app/place.py and Settings): Brave's profiles by name and colour, never an email; the chosen
profile's live context, learned only when Brave's two records of the profile it used last agree for SETTLE seconds;
the setting, which takes only a listed profile; and the Settings section, which says plainly when the profile isn't
open or Brave isn't connected."""

import asyncio
import json

from test_app_server import recv, started
from test_app_server import until as told
from test_bravelink import local_state
from test_bridge import EVENTS
from test_home import CHROME, page, open_settings, stack  # noqa: F401  (fixtures)
from test_home import until as page_until
from ui_socket import ui_socket


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_the_profiles_are_names_and_colours_never_an_email(tmp_path):
    from ai_browser.app.place import ProfilePlace

    local_state(tmp_path)
    listed = ProfilePlace(tmp_path).profiles()
    assert listed == [{"folder": "Default", "name": "Work", "color": "#008000"},
                      {"folder": "Profile 1", "name": "Home", "color": None}]
    assert "example" not in json.dumps(listed)  # the accounts' emails stay in Local State


def test_a_profile_is_learned_only_when_both_records_agree_long_enough(tmp_path):
    from ai_browser.app.place import ProfilePlace

    clock, connection = Clock(), object()
    place = ProfilePlace(tmp_path, settle=12, clock=clock)
    place.chosen = "Default"  # Work
    local_state(tmp_path, last_used="Profile 1")
    assert place.look(connection, "P") is False and place.context("P") == (None, "not_open")
    clock.now = 13
    assert place.look(connection, "P") is True  # Home is P: learned, but Work is still not open
    assert place.context("P") == (None, "not_open")
    clock.now = 14
    assert place.look(connection, "W") is False  # the live record moved to Work; the file still says Home
    clock.now = 20
    local_state(tmp_path, last_used="Default")  # Brave writes its file, late
    assert place.look(connection, "W") is False  # (Home, W) never held: nothing wrong was learned
    clock.now = 33
    assert place.look(connection, "W") is True and place.context("P") == ("W", "chosen")
    local_state(tmp_path, last_used="Profile 1")  # a later pair that says otherwise replaces it
    assert place.look(connection, "W") is False
    clock.now = 46
    assert place.look(connection, "W") is True and place.context("W") == (None, "not_open")


def test_one_profile_needs_no_wait_and_a_new_connection_forgets(tmp_path):
    from ai_browser.app.place import ProfilePlace

    (tmp_path / "Default").mkdir()
    (tmp_path / "Local State").write_text(json.dumps({"profile": {"info_cache": {"Default": {"name": "Me"}}}}),
                                          encoding="utf-8")
    place = ProfilePlace(tmp_path, settle=12, clock=Clock())
    place.chosen = "Default"
    first = object()
    assert place.look(first, "C1") is True and place.context("C1") == ("C1", "chosen")  # no wait
    assert place.look(object(), None) is False and place.context("C1") == (None, "not_open")  # forgotten
    place.chosen = None
    assert place.context("C9") == ("C9", "last_used") and place.context(None) == (None, "none")


async def test_settings_lists_the_profiles_and_takes_only_one_of_them(fake_claude, tmp_path):
    from ai_browser.settings import read_settings
    from fake_brave import FakeBrave

    server, url = await started(fake_claude, tmp_path, EVENTS)
    brave = FakeBrave([])
    brave.place.listed = [{"folder": "Default", "name": "Work", "color": "#008000"},
                          {"folder": "Profile 1", "name": "Home", "color": None}]
    server.attach_brave(brave)
    try:
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "settings"}))
            assert (await recv(page))["settings"]["profiles"] == brave.place.listed
            await page.send(json.dumps({"type": "settings_set", "key": "agents_profile", "value": "Profile 9",
                                        "request": "place"}))
            refused = (await told(page, lambda m: m["type"] == "error"))[-1]
            assert refused["text"] == "Pick one of the profiles listed" and brave.place.chosen is None
            await page.send(json.dumps({"type": "settings_set", "key": "agents_profile", "value": ["Profile 1"],
                                        "request": "odd"}))  # not a folder name: refused, and the socket goes on
            refused = (await told(page, lambda m: m["type"] == "error" and m.get("request") == "odd"))[-1]
            assert refused["text"] == "Pick one of the profiles listed" and brave.place.chosen is None
            await page.send(json.dumps({"type": "settings_set", "key": "agents_profile", "value": "Profile 1",
                                        "request": "place"}))
            assert (await told(page, lambda m: m["type"] == "settings"))[-1]["agents_profile"] == "Profile 1"
            assert brave.place.chosen == "Profile 1" and read_settings(server.home)["agents_profile"] == "Profile 1"
            await page.send(json.dumps({"type": "settings_set", "key": "agents_profile", "value": None,
                                        "request": "place"}))
            assert (await told(page, lambda m: m["type"] == "settings" and m["agents_profile"] is None))
            assert brave.place.chosen is None
    finally:
        await server.stop()


@CHROME
async def test_settings_where_agents_browse_names_the_profiles_and_says_what_it_cant_do(page):  # Review Focus 1
    _, stack = page
    brave, server = stack["brave"], stack["server"]
    brave.place.listed = [{"folder": "Default", "name": "Work", "color": "#008000"},
                          {"folder": "Profile 1", "name": "Home", "color": None}]
    brave.set_scope("last_used", 0)
    settings = await open_settings(stack)
    labels = "[...document.querySelectorAll('#place-choices label')].map((label) => label.textContent)"
    assert await page_until(settings, f"{labels}.length === 3")
    assert await settings(labels) == ["The profile you used last in Brave", "Work", "Home"]
    assert await settings("getComputedStyle(document.querySelectorAll('#place-choices .swatch')[1]).backgroundColor"
                          ) == "rgb(0, 128, 0)"
    assert await settings("document.querySelector('#place-choices input[value=\"\"]').checked") is True
    state = "document.getElementById('place-state').textContent"
    assert await settings(state) == "Agents browse in the profile you used last in Brave."
    await settings("document.querySelector('#place-choices input[value=\"Default\"]').click()")
    for _ in range(50):
        if server.settings.get()["agents_profile"] == "Default":
            break
        await asyncio.sleep(0.1)
    assert brave.place.chosen == "Default"
    brave.set_scope("not_open", 2)
    assert await page_until(settings, f"{state} === \"Work isn't open in Brave yet: open a window of it, and click "
                                      f"in it once.\"")
    brave.set_scope("chosen", 2)
    assert await page_until(settings, f"{state} === 'Agents browse in Work.'")
    brave.place.listed = [{"folder": "Profile 1", "name": "Home", "color": None}]  # Work is gone from Brave's list
    settings = await open_settings(stack)
    assert await page_until(settings, f"{state} === 'Agents browse in the profile you picked (not found in Brave).'")
    brave.set_state("lost")  # Brave quit: said plainly, and nothing asks it anything
    assert await page_until(settings, f"{state} === \"Brave isn't connected: connect it at the top of Mission "
                                      "Control.\"")
    assert brave.connects == 0
