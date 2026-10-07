"""Workspaces (the new look, Decision 6): the store in <home>/workspaces.json (Task 5), and the messages that change it
(Task 6). In a throwaway home; the messages over a real socket, on the fake claude."""

import json

import pytest

from conftest import file_mode


def store(tmp_path):
    from ai_browser.app.workspaces import Workspaces

    return Workspaces(tmp_path / "home")


def test_a_workspace_is_created_renamed_and_deleted(tmp_path):
    workspaces = store(tmp_path)
    assert workspaces.list() == []
    research = workspaces.create("  Research \n")
    assert research["name"] == "Research" and research["templates"] == []
    assert research["id"].startswith("w") and len(research["id"]) == 9
    marketing = workspaces.create("Marketing")
    assert [row["name"] for row in workspaces.list()] == ["Research", "Marketing"]
    workspaces.rename(research["id"], "Deep research")
    assert workspaces.get(research["id"])["name"] == "Deep research"
    assert workspaces.delete(marketing["id"]) is True and workspaces.delete(marketing["id"]) is False
    path = tmp_path / "home" / "workspaces.json"
    assert file_mode(path) in (None, 0o600)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "workspaces": [{"id": research["id"], "name": "Deep research", "templates": []}]}


@pytest.mark.parametrize(("name", "words"), [("", "a name"), ("   ", "a name"), (None, "a name"), (7, "a name"),
                                             ("x" * 41, "at most 40")])
def test_a_name_is_one_short_line(tmp_path, name, words):
    with pytest.raises(ValueError, match=words):
        store(tmp_path).create(name)


def test_a_direction_mark_can_never_reorder_a_name(tmp_path):
    assert store(tmp_path).create("‮evil​ one")["name"] == "evil one"


def test_a_name_is_taken_once_whatever_its_case(tmp_path):
    workspaces = store(tmp_path)
    research = workspaces.create("Research")
    other = workspaces.create("Product")
    with pytest.raises(ValueError, match="named research already"):
        workspaces.create("research")
    with pytest.raises(ValueError, match="already"):
        workspaces.rename(other["id"], "RESEARCH")
    workspaces.rename(research["id"], "research")  # its own name, in another case: fine
    with pytest.raises(ValueError, match="was deleted"):
        workspaces.rename("w00000000", "Gone")


def test_at_most_fifty(tmp_path):
    workspaces = store(tmp_path)
    for number in range(50):
        workspaces.create(f"Group {number}")
    with pytest.raises(ValueError, match="At most 50"):
        workspaces.create("One more")


def test_a_template_is_in_at_most_one_workspace(tmp_path):
    workspaces = store(tmp_path)
    one, two = workspaces.create("One"), workspaces.create("Two")
    workspaces.assign_template("weekly-report", one["id"])
    workspaces.assign_template("weekly-report", two["id"])
    assert workspaces.get(one["id"])["templates"] == [] and workspaces.get(two["id"])["templates"] == ["weekly-report"]
    workspaces.assign_template("weekly-report", None)
    assert workspaces.get(two["id"])["templates"] == []
    for slug, where, words in (("../x", one["id"], "Not a template"), ("ok\n", one["id"], "Not a template"),
                               ("ok", "w00000000", "was deleted")):
        with pytest.raises(ValueError, match=words):
            workspaces.assign_template(slug, where)


def test_a_broken_file_reads_as_none_and_a_broken_row_is_skipped(tmp_path):
    path = tmp_path / "home" / "workspaces.json"
    path.parent.mkdir(parents=True)
    workspaces = store(tmp_path)
    for text in ("{", "[]", '{"workspaces": 7}', ""):
        path.write_text(text, encoding="utf-8")
        assert workspaces.list() == []
    path.write_text(json.dumps({"workspaces": [
        {"id": "w1234abcd", "name": "Fine", "templates": ["a", "../b", 7, "a", "c\n"]},
        {"id": "nope", "name": "Bad id"}, {"id": "w1234abcd", "name": "Twice"}, {"id": "wabcdef01", "name": ""},
        {"id": "wabcdef02\n", "name": "Line"}, "not a row"]}), encoding="utf-8")
    assert workspaces.list() == [{"id": "w1234abcd", "name": "Fine", "templates": ["a"]}]
