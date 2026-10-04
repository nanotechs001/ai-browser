"""AI accounts: the account list in <home>/accounts.json, each account's folder, and the environment Claude Code runs
with on it. Nothing here starts the real claude or reads the user's own Claude Code folder."""

import json
import os
import re
from pathlib import Path

import pytest

from conftest import file_mode

API = {"ANTHROPIC_API_KEY": "sk-test", "ANTHROPIC_AUTH_TOKEN": "token-test"}


def test_a_missing_or_bad_file_means_default_only(tmp_path):
    from ai_browser.accounts import Accounts

    accounts = Accounts(tmp_path)
    assert [account.id for account in accounts.list()] == ["default"]  # missing
    bad_rows = {"accounts": [{"id": "acct-zzzzzz", "name": "Bad id", "folder": "/x"},
                             {"id": "acct-1a2b3c", "name": " ‮​ ", "folder": "/x"},
                             {"id": "acct-4d5e6f", "name": "Relative", "folder": "work"}, "not a row"],
                "default": "acct-1a2b3c", "brain": "acct-999999"}
    for text in ("{not json", "[1, 2]", '"text"', json.dumps({"accounts": "x", "default": 7}), json.dumps(bad_rows)):
        (tmp_path / "accounts.json").write_text(text, encoding="utf-8")
        assert [account.id for account in accounts.list()] == ["default"], text
        assert accounts.default_id() == accounts.brain_id() == "default"
        assert (tmp_path / "accounts.json").read_text(encoding="utf-8") == text  # reading never rewrites it
    (tmp_path / "accounts.json").unlink()
    (tmp_path / "accounts.json").mkdir()  # a folder where the file should be
    assert [account.id for account in accounts.list()] == ["default"]


def test_accounts_json_round_trip(tmp_path):
    from ai_browser.accounts import Accounts

    home = tmp_path / "home"
    accounts = Accounts(home)
    work, personal = accounts.add("Work"), accounts.add("Personal")
    accounts.set_default(work.id)
    accounts.set_brain(personal.id)
    again = Accounts(home)
    assert [(account.id, account.name, account.folder) for account in again.list()] == [
        ("default", "Default", os.environ["CLAUDE_CONFIG_DIR"]), (work.id, "Work", work.folder),
        (personal.id, "Personal", personal.folder)]
    assert again.default_id() == work.id and again.brain_id() == personal.id
    data = json.loads((home / "accounts.json").read_text(encoding="utf-8"))
    assert data == {"accounts": [{"id": work.id, "name": "Work", "folder": work.folder},
                                 {"id": personal.id, "name": "Personal", "folder": personal.folder}],
                    "default": work.id, "brain": personal.id}
    assert file_mode(home / "accounts.json") in (0o600, None)
    for account in (work, personal):
        assert Path(account.folder) == home / "accounts" / account.id and Path(account.folder).is_dir()
        assert file_mode(account.folder) in (0o700, None)
    assert file_mode(home / "accounts") in (0o700, None)
    data["from_a_newer_build"] = [1]
    (home / "accounts.json").write_text(json.dumps(data), encoding="utf-8")
    again.set_default("default")
    assert json.loads((home / "accounts.json").read_text(encoding="utf-8"))["from_a_newer_build"] == [1]


def test_names_are_cleaned_and_must_differ(tmp_path):
    from ai_browser.accounts import Accounts, clean_name

    assert clean_name("  Work\n\tstuff  ") == "Work stuff"
    assert clean_name("Wo‮rk​\x00") == "Work"  # control, format and bidi characters go
    assert clean_name("x" * 60) == "x" * 40
    assert clean_name("‮ ​") == "" and clean_name(None) == "" and clean_name(7) == ""
    accounts = Accounts(tmp_path)
    hostile = accounts.add('<img src=x onerror="alert(1)">')
    assert hostile.name == '<img src=x onerror="alert(1)">'  # only text: the pages set it with textContent
    accounts.add("Work")
    for bad, why in (("", "Give the account a name"), ("‮​", "Give the account a name"),
                     ("WORK", "There is already an account named WORK"),
                     (" work ", "There is already an account named work"),
                     ("default", "There is already an account named default")):
        with pytest.raises(ValueError) as refused:
            accounts.add(bad)
        assert str(refused.value) == why
    assert [account.name for account in accounts.list()] == ["Default", '<img src=x onerror="alert(1)">', "Work"]


def test_an_existing_folder_is_used_and_a_browsers_data_refused(tmp_path):
    from ai_browser.accounts import Accounts

    accounts = Accounts(tmp_path / "home")
    mine = tmp_path / "claude-work"
    (mine / "projects").mkdir(parents=True)
    for name in ("Local State", "Preferences", "Cookies"):
        browser = tmp_path / f"browser-{name.replace(' ', '-')}"
        browser.mkdir()
        (browser / name).write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="a browser's data"):
            accounts.add_existing("Desktop app", str(browser))
    for bad in ("", "relative/folder", str(tmp_path / "missing"), f"{mine}\n", 7):
        with pytest.raises(ValueError):
            accounts.add_existing("Work", bad)
    with pytest.raises(ValueError, match="Another account already uses that folder"):
        accounts.add_existing("Mine", os.environ["CLAUDE_CONFIG_DIR"])  # Default's own folder
    work = accounts.add_existing("Work", str(mine))
    assert work.folder == str(mine) and sorted(path.name for path in mine.iterdir()) == ["projects"]  # used as it is
    with pytest.raises(ValueError, match="Another account already uses that folder"):
        accounts.add_existing("Again", str(mine))
    assert [account.name for account in accounts.list()] == ["Default", "Work"]


def test_remove_only_forgets(tmp_path):
    from ai_browser.accounts import Accounts

    accounts = Accounts(tmp_path)
    work = accounts.add("Work")
    (Path(work.folder) / "projects").mkdir()
    accounts.set_default(work.id)
    accounts.set_brain(work.id)
    with pytest.raises(ValueError, match="Default can't be removed"):
        accounts.remove("default")
    accounts.remove(work.id)
    assert accounts.get(work.id) is None and (Path(work.folder) / "projects").is_dir()  # its folder stays
    assert accounts.default_id() == accounts.brain_id() == "default"
    with pytest.raises(ValueError, match="isn't in Settings"):
        accounts.remove(work.id)
    for chosen in ("acct-000000", "nobody", None):
        with pytest.raises(ValueError, match="isn't in Settings"):
            accounts.set_default(chosen)


def test_env_for_strips_the_api_variables_and_sets_the_folder(tmp_path, monkeypatch):
    from ai_browser.accounts import Accounts, clean_env

    for key, value in API.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AIB_SOMETHING", "kept")
    accounts = Accounts(tmp_path)
    work = accounts.add("Work")
    default, other = accounts.env_for("default"), accounts.env_for(work.id)
    for env in (default, other, clean_env()):
        assert not set(API) & set(env) and env["AIB_SOMETHING"] == "kept"
    assert default == clean_env()  # Default leaves the environment as it is
    assert other == {**clean_env(), "CLAUDE_CONFIG_DIR": work.folder}
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-test"  # the app's own environment is never changed
    with pytest.raises(KeyError):
        accounts.env_for("acct-000000")


def test_default_is_the_folder_the_environment_names(tmp_path, monkeypatch):  # Review Focus 1
    from ai_browser.accounts import Accounts

    mine = tmp_path / "my-claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(mine))
    accounts = Accounts(tmp_path / "home")
    assert accounts.get("default").folder == str(mine)
    assert accounts.env_for("default")["CLAUDE_CONFIG_DIR"] == str(mine)
    assert accounts.claude_home("default") == mine  # its .claude.json: Claude Code reads it there
    assert accounts.signin_folder("default") == str(mine)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert accounts.get("default").folder == str(Path.home() / ".claude")  # a path only: nothing reads it here
    assert "CLAUDE_CONFIG_DIR" not in accounts.env_for("default")
    assert accounts.claude_home("default") == Path.home() and accounts.signin_folder("default") is None
    work = accounts.add("Work")
    assert accounts.claude_home(work.id) == Path(work.folder) and accounts.signin_folder(work.id) == work.folder


def test_only_ids_made_here_name_folders(tmp_path):
    from ai_browser.accounts import Accounts

    accounts = Accounts(tmp_path)
    made = [accounts.add(name) for name in ("Work", "../../etc", "Café ☕")]
    assert all(re.fullmatch(r"acct-[0-9a-f]{6}", account.id) for account in made)
    assert len({account.id for account in made}) == 3
    assert sorted(path.name for path in (tmp_path / "accounts").iterdir()) == sorted(account.id for account in made)
