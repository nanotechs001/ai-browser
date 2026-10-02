"""Atomic writes in binary (so "\n" stays one byte on Windows), and folders updated in place."""

import os

import pytest

from ai_browser.syncdir import sync_folder, write_atomic


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


def test_sync_folder_rewrites_only_what_changed(tmp_path):
    folder = tmp_path / "ext"
    sync_folder(folder, {"same.js": b"one", "changed.js": b"old", "stale.js": b"x", "img/icon.png": b"\x89PNG\r\n"},
                set())
    (folder / "config.json").write_bytes(b"{}")
    same, icon = (folder / "same.js").stat(), (folder / "img" / "icon.png").stat()
    sync_folder(folder, {"same.js": b"one", "changed.js": b"new", "img/icon.png": b"\x89PNG\r\n"}, {"config.json"})
    again, icon_again = (folder / "same.js").stat(), (folder / "img" / "icon.png").stat()
    assert (again.st_ino, again.st_mtime_ns) == (same.st_ino, same.st_mtime_ns)  # unchanged: not rewritten
    assert (icon_again.st_ino, icon_again.st_mtime_ns) == (icon.st_ino, icon.st_mtime_ns)
    assert (folder / "changed.js").read_bytes() == b"new"
    assert not (folder / "stale.js").exists() and (folder / "config.json").read_bytes() == b"{}"
    assert (folder / "img" / "icon.png").read_bytes() == b"\x89PNG\r\n"  # one byte per "\n", as given
