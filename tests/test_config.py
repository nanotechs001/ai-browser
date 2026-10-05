import codecs
import json
from pathlib import Path

from ai_browser import config


def test_home_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("AIB_HOME", str(tmp_path / "h"))
    assert config.home() == tmp_path / "h"


def test_home_default_is_dot_ai_browser(monkeypatch):
    monkeypatch.delenv("AIB_HOME", raising=False)
    assert config.home() == Path.home() / ".ai-browser"


def test_load_config_defaults_when_missing(tmp_path):
    cfg = config.load_config(tmp_path)
    assert cfg.blocked_skills == []
    assert "publish" in cfg.risky_words
    assert "sign up" in cfg.risky_words


def test_load_config_reads_blocked_and_risky(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"blocked_skills": ["ecc:x"], "risky_words": ["nuke"], "unknown": 1})
    , encoding="utf-8")
    cfg = config.load_config(tmp_path)
    assert cfg.blocked_skills == ["ecc:x"]
    assert cfg.risky_words == ["nuke"]


def test_load_config_invalid_json_falls_back(tmp_path):
    (tmp_path / "config.json").write_text("{not json", encoding="utf-8")
    assert config.load_config(tmp_path) == config.Config()


def test_load_config_reads_files_saved_by_windows_editors(tmp_path):
    """Notepad's "UTF-8 with BOM" and PowerShell 5.1's `Set-Content -Encoding UTF8` start with a BOM, and its `>`
    writes UTF-16: none of them may silently unblock the user's blocked skills."""
    text = json.dumps({"blocked_skills": ["ecc:x"], "risky_words": ["löschen"]})
    for data in (codecs.BOM_UTF8 + text.encode("utf-8"), text.encode("utf-16"), text.encode("utf-16-be")):
        (tmp_path / "config.json").write_bytes(data)
        cfg = config.load_config(tmp_path)
        assert (cfg.blocked_skills, cfg.risky_words) == (["ecc:x"], ["löschen"]), data[:4]
        assert config.config_problem(tmp_path) is None


def test_a_config_that_cant_be_used_is_reported(tmp_path):
    assert config.config_problem(tmp_path) is None  # no file: the defaults, nothing to report
    for text in ('{"blocked_skills": ["ecc:x"],}', '["ecc:x"]'):
        (tmp_path / "config.json").write_text(text, encoding="utf-8")
        problem = config.config_problem(tmp_path)
        assert problem and str(tmp_path / "config.json") in problem and "defaults" in problem, text
    (tmp_path / "config.json").write_bytes("{\"risky_words\": [\"löschen\"]}".encode("cp1252"))  # an "ANSI" save
    assert "defaults" in config.config_problem(tmp_path)


def test_project_root_points_at_repo():
    assert (config.project_root() / "pyproject.toml").exists()


def test_project_root_is_the_bundle_in_the_packaged_exe(monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)  # AI Browser.exe: docker/ and skills/ are in its bundle
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert config.project_root() == tmp_path
