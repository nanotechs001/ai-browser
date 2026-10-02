import os
import threading
from pathlib import Path

import pytest

from ai_browser.workfs import PathError, WorkDir
from conftest import symlink_or_skip


@pytest.fixture
def work(tmp_path):
    return WorkDir(tmp_path / "work", "t1")


def test_task_paths(work, tmp_path):
    assert work.host_task == tmp_path / "work" / "t1"
    assert work.sandbox_task == "/work/t1"
    assert work.host_task.is_dir()


def test_relative_path_maps_into_task_dir(work):
    assert work.to_host("out/data.csv") == work.host_task / "out" / "data.csv"
    assert work.to_sandbox("out/data.csv") == "/work/t1/out/data.csv"


def test_absolute_work_paths(work, tmp_path):
    assert work.to_host("/work/t1/a.txt") == work.host_task / "a.txt"
    assert work.to_host("/work/shared.txt") == tmp_path / "work" / "shared.txt"
    assert work.to_sandbox("/work/shared.txt") == "/work/shared.txt"


@pytest.mark.parametrize("bad", ["../../etc/passwd", "/etc/passwd", "/work/../etc", "/workx/a"])
def test_escapes_are_rejected(work, bad):
    with pytest.raises(PathError):
        work.to_host(bad)


def test_symlink_escape_is_rejected(work, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("x")
    symlink_or_skip(outside, work.host_task / "link")
    with pytest.raises(PathError):
        work.to_host("link/secret")


def test_write_creates_parents_and_returns_sandbox_path(work):
    assert work.write_text("a/b/c.txt", "hi") == "/work/t1/a/b/c.txt"
    assert (work.host_task / "a/b/c.txt").read_text() == "hi"


def test_read_truncates_long_files(work):
    work.write_text("big.txt", "x" * 100)
    out = work.read_text("big.txt", limit=10)
    assert out.startswith("x" * 10)
    assert "[truncated: 90 more chars]" in out


def test_read_missing_file(work):
    with pytest.raises(FileNotFoundError):
        work.read_text("nope.txt", 100)


def _checks_pass(monkeypatch):
    """Pretend the containment check saw a plain file: the sandbox swaps in a link right after it."""
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: self)


def test_reads_never_follow_a_link_swapped_in_after_the_check(work, tmp_path, monkeypatch):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET")
    symlink_or_skip(secret, work.host_task / "notes.txt")
    _checks_pass(monkeypatch)
    with pytest.raises(PathError, match="symbolic link"):
        work.read_text("notes.txt", 100)


def test_writes_never_follow_a_link_swapped_in_after_the_check(work, tmp_path, monkeypatch):
    target = tmp_path / "zshrc"
    target.write_text("original")
    (work.host_task / ".shell").mkdir()
    symlink_or_skip(target, work.host_task / ".shell" / "001.log")  # the shell knows the next log name
    _checks_pass(monkeypatch)
    with pytest.raises(PathError, match="symbolic link"):
        work.write_text(".shell/001.log", "replaced")
    assert target.read_text() == "original"


def test_writes_never_create_files_through_a_linked_folder(work, tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    symlink_or_skip(outside, work.host_task / "out")
    _checks_pass(monkeypatch)
    with pytest.raises(PathError, match="symbolic link"):
        work.write_text("out/new.txt", "x")
    assert not (outside / "new.txt").exists()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="Windows has no FIFOs (NTFS can't hold one)")
def test_a_fifo_is_refused_without_hanging(work):
    os.mkfifo(work.host_task / "pipe")
    outcome = {}

    def read():
        try:
            work.read_text("pipe", 100)
        except Exception as exc:
            outcome["error"] = exc

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    reader.join(timeout=3)
    if reader.is_alive():  # free the blocked reader so the test run can finish
        with open(work.host_task / "pipe", "w"):
            pass
        reader.join(timeout=3)
        pytest.fail("reading a FIFO hung")
    assert isinstance(outcome.get("error"), PathError)


def test_folders_and_missing_files_keep_their_errors(work):
    (work.host_task / "folder").mkdir()
    with pytest.raises(IsADirectoryError):
        work.read_text("folder", 100)
    with pytest.raises(FileNotFoundError):
        work.read_text("missing/deeper.txt", 100)


def test_snapshot_copies_into_a_private_folder(work):
    (work.host_task / "logo.png").write_bytes(b"real")
    copy = work.snapshot("logo.png")
    assert copy.name == "logo.png" and copy.read_bytes() == b"real"
    assert not copy.is_relative_to(work.host_root)  # no container mounts it, so nothing can swap it
    assert work.snapshot("logo.png") != copy  # each upload gets its own copy
    work.drop_snapshots()
    assert not copy.exists()


def test_write_bytes_never_follows_links(work, tmp_path, monkeypatch):
    target = tmp_path / "victim"
    target.write_bytes(b"original")
    symlink_or_skip(target, work.host_task / "shot.jpg")
    _checks_pass(monkeypatch)
    with pytest.raises(PathError, match="symbolic link"):
        work.write_bytes("shot.jpg", b"new")
    assert target.read_bytes() == b"original"
    assert work.write_bytes("shots/a.jpg", b"\xff\xd8") == "/work/t1/shots/a.jpg"
