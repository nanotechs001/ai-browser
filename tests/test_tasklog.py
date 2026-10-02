import json
import re

from ai_browser.tasklog import TaskLog, new_task_id


def test_task_id_format():
    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{4}", new_task_id())


def test_record_writes_one_json_line_per_call(tmp_path):
    log = TaskLog(tmp_path, "t1")
    log.record("act", {"steps": ["click e1"]}, 42, "ok", "done")
    log.record("open", {"url": "http://x"}, 7, "error", "boom")
    lines = (tmp_path / "t1" / "log.jsonl").read_text().splitlines()
    first = json.loads(lines[0])
    assert (first["tool"], first["args"], first["ms"], first["outcome"], first["result"]) == (
        "act", {"steps": ["click e1"]}, 42, "ok", "done")
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", first["ts"])
    assert json.loads(lines[1])["outcome"] == "error"


def test_record_truncates_long_results(tmp_path):
    log = TaskLog(tmp_path, "t1")
    log.record("observe", {}, 1, "ok", "x" * 2000)
    entry = json.loads((tmp_path / "t1" / "log.jsonl").read_text())
    assert len(entry["result"]) == 501
    assert entry["result"].endswith("…")


def test_record_truncates_long_args(tmp_path):
    log = TaskLog(tmp_path, "t1")
    log.record("write_file", {"path": "a.txt", "content": "y" * 2000}, 1, "ok", "")
    entry = json.loads((tmp_path / "t1" / "log.jsonl").read_text())
    assert entry["args"]["path"] == "a.txt"
    assert len(entry["args"]["content"]) == 501


def test_save_shot_numbers_files(tmp_path):
    log = TaskLog(tmp_path, "t1")
    first = log.save_shot(b"\xff\xd8a", "desktop")
    second = log.save_shot(b"\xff\xd8b", "mobile view")
    assert (first.name, second.name) == ("001-desktop.jpg", "002-mobile-view.jpg")
    assert first.read_bytes() == b"\xff\xd8a"
