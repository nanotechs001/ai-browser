"""Atomic writes in binary (so "\n" stays one byte on Windows)."""

import os

import pytest

from ai_browser.syncdir import write_atomic


def test_write_atomic_writes_exactly_the_bytes_given(tmp_path):
    path = tmp_path / "deep" / "file.bin"
    write_atomic(path, b"a\nb\r\n\x00\xff", 0o600)
    assert path.read_bytes() == b"a\nb\r\n\x00\xff"
    assert [entry.name for entry in path.parent.iterdir()] == ["file.bin"]  # no temp file left behind
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_write_atomic_leaves_nothing_behind_when_it_fails(tmp_path, monkeypatch):
    from ai_browser import platforms

    def held(src, dst):
        raise PermissionError(13, "held by another process")

    monkeypatch.setattr(platforms, "replace", held)
    with pytest.raises(PermissionError):
        write_atomic(tmp_path / "x.json", b"{}")
    assert list(tmp_path.iterdir()) == []


