"""Guards that keep ai-browser portable. They run on every OS and cover every sub-project's code."""

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "ai_browser"


def test_platform_markers_skip_with_their_reason():
    import tomllib

    from conftest import PIPE_FIXTURES, POSIX_ONLY, WINDOWS_ONLY, platform_skip

    def item(*markers, fixtures=()):
        return SimpleNamespace(keywords={name: True for name in markers}, fixturenames=list(fixtures))

    assert PIPE_FIXTURES == {"stack", "watcher", "app_browser", "app_engine"}
    assert platform_skip(item("posix_only"), windows=True) == POSIX_ONLY
    assert platform_skip(item("posix_only"), windows=False) is None
    for fixture in sorted(PIPE_FIXTURES):  # they launch AI Browser over the DevTools pipe
        assert platform_skip(item(fixtures=["tmp_path", fixture]), windows=True) == POSIX_ONLY
        assert platform_skip(item(fixtures=[fixture]), windows=False) is None
    assert platform_skip(item("windows_only"), windows=False) == WINDOWS_ONLY
    assert platform_skip(item("windows_only"), windows=True) is None
    assert platform_skip(item(fixtures=["fake_claude", "tmp_path"]), windows=True) is None
    with (ROOT / "pyproject.toml").open("rb") as handle:
        markers = tomllib.load(handle)["tool"]["pytest"]["ini_options"]["markers"]
    assert f"posix_only: {POSIX_ONLY}" in markers and f"windows_only: {WINDOWS_ONLY}" in markers


def test_the_test_helpers_work_on_this_system(tmp_path):
    from conftest import file_mode, symlink_or_skip

    target = tmp_path / "target.txt"
    target.write_bytes(b"x")
    target.chmod(0o600)
    assert file_mode(target) == (None if os.name == "nt" else 0o600)
    symlink_or_skip(target, tmp_path / "link.txt")  # skips, with the reason, where links can't be made
    assert (tmp_path / "link.txt").is_symlink()
