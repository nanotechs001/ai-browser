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
    )
    cfg = config.load_config(tmp_path)
    assert cfg.blocked_skills == ["ecc:x"]
    assert cfg.risky_words == ["nuke"]


def test_load_config_invalid_json_falls_back(tmp_path):
    (tmp_path / "config.json").write_text("{not json")
    assert config.load_config(tmp_path) == config.Config()


def test_project_root_points_at_repo():
    assert (config.project_root() / "pyproject.toml").exists()
