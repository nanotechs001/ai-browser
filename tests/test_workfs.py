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
    (outside / "secret").write_text("x", encoding="utf-8")
    symlink_or_skip(outside, work.host_task / "link")
    with pytest.raises(PathError):
        work.to_host("link/secret")


def test_write_creates_parents_and_returns_sandbox_path(work):
    assert work.write_text("a/b/c.txt", "hi") == "/work/t1/a/b/c.txt"
    assert (work.host_task / "a/b/c.txt").read_text(encoding="utf-8") == "hi"


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
    secret.write_text("TOP SECRET", encoding="utf-8")
    symlink_or_skip(secret, work.host_task / "notes.txt")
    _checks_pass(monkeypatch)
    with pytest.raises(PathError, match="symbolic link"):
        work.read_text("notes.txt", 100)


def test_writes_never_follow_a_link_swapped_in_after_the_check(work, tmp_path, monkeypatch):
    target = tmp_path / "zshrc"
    target.write_text("original", encoding="utf-8")
    (work.host_task / ".shell").mkdir()
    symlink_or_skip(target, work.host_task / ".shell" / "001.log")  # the shell knows the next log name
    _checks_pass(monkeypatch)
    with pytest.raises(PathError, match="symbolic link"):
        work.write_text(".shell/001.log", "replaced")
    assert target.read_text(encoding="utf-8") == "original"


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
        with open(work.host_task / "pipe", "w", encoding="utf-8"):
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


@pytest.mark.parametrize("name", ["CON", "con", "nul.txt", "NUL .txt", "COM1", "lpt3.log", "COM¹", "CONIN$", "a:b",
                                  "x?", 'say"hi"', "a<b", "pipe|", "star*", "back\\slash", "tab\tname", "end.", "end "])
def test_names_windows_cant_hold(name):
    from ai_browser.winfs import windows_name_problem

    assert windows_name_problem(name)


@pytest.mark.parametrize("name", ["report.html", "Ünïcode.txt", "COM10", "console.log", "con-notes.md", ".shell",
                                  "a b.txt", "日本語.md"])
def test_ordinary_names_pass(name):
    from ai_browser.winfs import windows_name_problem

    assert windows_name_problem(name) is None


def test_a_deep_folder_reads_and_writes(work):
    deep = "/".join(f"folder-{number:02d}-name" for number in range(24)) + "/page.html"
    assert len(str(work.host_task / deep)) > 300  # past Windows' old 260-character limit
    assert work.write_text(deep, "<p>deep</p>") == f"/work/t1/{deep}"
    assert work.read_text(deep, 100) == "<p>deep</p>"


@pytest.mark.windows_only
def test_a_junction_to_outside_is_refused_on_windows(work, tmp_path):
    import _winapi

    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_bytes(b"TOP SECRET")
    before = secret.stat()
    _winapi.CreateJunction(str(outside), str(work.host_task / "out"))  # needs no admin rights
    with pytest.raises(PathError, match="symbolic link"):
        work.read_text("out/secret.txt", 100)
    with pytest.raises(PathError, match="symbolic link"):
        work.write_text("out/secret.txt", "replaced")
    with pytest.raises(PathError, match="symbolic link"):
        work.write_text("out/new.txt", "x")
    after = secret.stat()
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    assert not (outside / "new.txt").exists()


@pytest.mark.windows_only
def test_a_symbolic_link_file_is_refused_on_windows(work, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"TOP SECRET")
    symlink_or_skip(secret, work.host_task / "notes.txt")  # the CI runner is an admin, so it can make one
    with pytest.raises(PathError, match="symbolic link"):
        work.read_text("notes.txt", 100)
    with pytest.raises(PathError, match="symbolic link"):
        work.write_text("notes.txt", "x")
    assert secret.read_bytes() == b"TOP SECRET"


@pytest.mark.windows_only
def test_windows_writes_new_folders_and_reads_exact_bytes(work):
    assert work.write_bytes("fresh/sub/ten.bin", b"0123456789") == "/work/t1/fresh/sub/ten.bin"
    assert (work.host_task / "fresh" / "sub" / "ten.bin").read_bytes() == b"0123456789"
    assert work.read_text("fresh/sub/ten.bin", 100) == "0123456789"
    work.write_bytes("fresh/sub/ten.bin", b"1")  # a write truncates, after the checks
    assert (work.host_task / "fresh" / "sub" / "ten.bin").read_bytes() == b"1"
    with pytest.raises(IsADirectoryError):
        work.read_text("fresh", 100)
    with pytest.raises(PathError, match="not a valid file name on Windows"):
        work.write_text("CON", "x")
    with pytest.raises(PathError, match="not a valid file name on Windows"):
        work.write_text("notes:hidden", "x")  # also an alternate data stream
