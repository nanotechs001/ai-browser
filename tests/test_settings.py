"""<home>/settings.json: one reader and one writer, and the typed view on top (the window's browser, the model,
Voice, the shortcut, reading the user's tabs, where agents browse and the old extension's note). Nothing here ever
raises on a bad file."""

import json

import pytest

from conftest import file_mode


def test_read_settings_never_raises(tmp_path):
    from ai_browser.settings import read_settings

    path = tmp_path / "settings.json"
    assert read_settings(tmp_path) == {}  # missing
    path.write_text("{not json", encoding="utf-8")
    assert read_settings(tmp_path) == {}
    path.write_text("[1, 2]", encoding="utf-8")  # JSON, but not an object
    assert read_settings(tmp_path) == {}
    path.unlink()
    path.mkdir()  # a folder where the file should be
    assert read_settings(tmp_path) == {}


def test_write_setting_keeps_the_other_keys(tmp_path):
    from ai_browser.settings import read_settings, write_setting

    place = {"id": "brave", "user_data_dir": "/x/Brave-Browser", "profile": "Default"}
    write_setting(tmp_path, "agents_browser", place)  # as wave C writes it
    write_setting(tmp_path, "model", "opus")
    assert read_settings(tmp_path) == {"agents_browser": place, "model": "opus"}
    assert file_mode(tmp_path / "settings.json") in (0o600, None)


def test_the_defaults_and_a_bad_value_for_one_key(tmp_path):
    from ai_browser.settings import DEFAULTS, Settings

    settings = Settings(tmp_path, system="darwin")
    assert settings.path == tmp_path / "settings.json"
    assert settings.get() == DEFAULTS == {"window_browser": "auto", "model": None, "voice": False,
                                       "shortcut": "Alt+Space",
                                       "read_tabs": False, "agents_profile": None, "watcher_note": True,
                                       "sandbox": "auto"}
    (tmp_path / "settings.json").write_text(json.dumps({"model": "gpt", "voice": True, "window_browser": "brave"}),
                                            encoding="utf-8")
    assert settings.get() == {"window_browser": "brave", "model": None, "voice": True,
                              "shortcut": "Alt+Space",  # only the model falls back
                              "read_tabs": False, "agents_profile": None, "watcher_note": True, "sandbox": "auto"}


def test_a_broken_file_gives_the_defaults_and_stays_until_the_next_set(tmp_path):
    from ai_browser.settings import DEFAULTS, Settings

    path = tmp_path / "settings.json"
    path.write_text('{"model": "opus",', encoding="utf-8")  # half-written
    settings = Settings(tmp_path, system="darwin")
    assert settings.get() == DEFAULTS
    assert path.read_text(encoding="utf-8") == '{"model": "opus",'  # reading never rewrites it
    assert settings.set("model", "haiku")["model"] == "haiku"
    assert json.loads(path.read_text(encoding="utf-8")) == {"model": "haiku"}


def test_set_checks_each_value(tmp_path):
    from ai_browser.settings import Settings

    mac = Settings(tmp_path, system="darwin")
    for key, value in (("window_browser", "edge"), ("window_browser", 3), ("model", "gpt"), ("voice", "yes"),
                       ("colour", "red"), ("shortcut", "F5"), ("shortcut", ["Alt+Space"])):
        with pytest.raises(ValueError):
            mac.set(key, value)
    assert not (tmp_path / "settings.json").exists()  # nothing written for a refused value
    assert Settings(tmp_path, system="win32").set("window_browser", "edge")["window_browser"] == "edge"
    assert mac.set("model", None)["model"] is None and mac.set("voice", True)["voice"] is True
    assert mac.set("shortcut", None)["shortcut"] is None
    assert mac.set("shortcut", "Control+Shift+Space")["shortcut"] == "Control+Shift+Space"


def test_an_unknown_key_survives_a_set(tmp_path):
    from ai_browser.settings import Settings, read_settings

    (tmp_path / "settings.json").write_text(json.dumps({"from_a_newer_build": [1, 2]}), encoding="utf-8")
    Settings(tmp_path, system="darwin").set("voice", True)
    assert read_settings(tmp_path) == {"from_a_newer_build": [1, 2], "voice": True}
    assert file_mode(tmp_path / "settings.json") in (0o600, None)


def test_a_file_from_another_computer_falls_back_key_by_key(tmp_path):  # Review Focus 2
    from ai_browser.settings import Settings, read_settings

    (tmp_path / "settings.json").write_text(json.dumps({"window_browser": "edge", "model": "opus",
                                                        "agents_browser": {"id": "brave"}}), encoding="utf-8")
    mac = Settings(tmp_path, system="darwin")
    assert mac.get() == {"window_browser": "auto", "model": "opus", "voice": False,
                         "shortcut": "Alt+Space",  # Edge draws it on Windows only
                         "read_tabs": False, "agents_profile": None, "watcher_note": True, "sandbox": "auto"}
    mac.set("voice", True)
    assert read_settings(tmp_path)["window_browser"] == "edge"  # kept for the Windows computer that wrote it
    assert Settings(tmp_path, system="win32").get()["window_browser"] == "edge"


def test_the_apps_shortcut_is_one_of_the_offered_ones_or_off(tmp_path):
    from ai_browser.settings import Settings

    (tmp_path / "settings.json").write_text(json.dumps({"shortcut": "F5"}), encoding="utf-8")
    assert Settings(tmp_path, system="darwin").get()["shortcut"] == "Alt+Space"  # not offered: the default
    (tmp_path / "settings.json").write_text(json.dumps({"shortcut": None}), encoding="utf-8")
    assert Settings(tmp_path, system="darwin").get()["shortcut"] is None  # Off stays off


def test_reading_the_users_tabs_where_agents_browse_and_the_old_extensions_note(tmp_path):
    from ai_browser.settings import Settings

    mac = Settings(tmp_path, system="darwin")
    assert {key: mac.get()[key] for key in ("read_tabs", "agents_profile", "watcher_note")} == {
        "read_tabs": False, "agents_profile": None, "watcher_note": True}  # reading is off until the user turns it on
    for key, value in (("read_tabs", "yes"), ("read_tabs", 1), ("watcher_note", None), ("agents_profile", ""),
                       ("agents_profile", "../Default"), ("agents_profile", "a/b"), ("agents_profile", 3),
                       ("agents_profile", "me@example.com")):
        with pytest.raises(ValueError):
            mac.set(key, value)
    assert not (tmp_path / "settings.json").exists()  # nothing written for a refused value
    assert mac.set("read_tabs", True)["read_tabs"] is True
    assert mac.set("agents_profile", "Profile 1")["agents_profile"] == "Profile 1"
    assert mac.set("agents_profile", None)["agents_profile"] is None
    assert mac.set("watcher_note", False)["watcher_note"] is False
