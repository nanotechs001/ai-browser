"""Attached files (the new look, Decision 9 and its Safety): names cleaned, staged in pieces, placed under attachments/
in the task's folder, never overwriting and never outside it (Review Focus 5). In throwaway folders."""

import base64

import pytest

from conftest import file_mode, symlink_or_skip


@pytest.mark.parametrize(("given", "saved"), [
    ("report.pdf", "report.pdf"), ("../x", "x"), ("../../etc/passwd", "passwd"), ("..\\..\\boot.ini", "boot.ini"),
    ("..", "file"), (".", "file"), ("", "file"), (None, "file"), (".env", "env"), ("a\x00b\x1f.txt", "a_b_.txt"),
    ("‮gnp.exe", "_gnp.exe"), ('bad<>:"|?*.txt', "bad_______.txt"), ("  spaced   out  .md ", "spaced out.md"),
    ("con.txt", "file.txt"), ("NUL", "file"), ("archive.tar.gz", "archive.tar.gz"),
    ("con .txt", "file.txt"), ("nul..txt", "file.txt"), ("con.tar.gz", "file.tar.gz"), ("NUL.txt.bak", "file.txt.bak"),
    ("COM¹.txt", "file.txt"), ("CONIN$.txt", "file.txt"), ("conout$", "file"), ("console.txt", "console.txt"),
    ("x" * 300 + ".png", "x" * 116 + ".png")])
def test_strange_names_are_cleaned(given, saved):  # Review Focus 5
    from ai_browser.app.attachments import clean_name

    assert clean_name(given) == saved


def staged(tmp_path, *contents):
    folder = tmp_path / "staged"
    folder.mkdir(exist_ok=True)
    paths = []
    for index, data in enumerate(contents):
        path = folder / f"{index}.part"
        path.write_bytes(data)
        paths.append(path)
    return paths


def test_files_land_in_attachments_and_a_duplicate_is_renamed_never_overwritten(tmp_path):  # Review Focus 5
    from ai_browser.app.attachments import place

    work = tmp_path / "project"
    (work / "attachments").mkdir(parents=True)
    (work / "attachments" / "notes.txt").write_text("the user's own", encoding="utf-8")
    one, two, three = staged(tmp_path, b"first", b"second", b"\x89PNG")
    assert place(work, [(one, "notes.txt"), (two, "notes.txt"), (three, "shot.png")]) == [
        "notes (2).txt", "notes (3).txt", "shot.png"]
    assert (work / "attachments" / "notes.txt").read_text(encoding="utf-8") == "the user's own"  # never overwritten
    assert (work / "attachments" / "notes (3).txt").read_bytes() == b"second"
    assert file_mode(work / "attachments" / "shot.png") in (None, 0o600)
    assert not one.exists() and not three.exists()  # moved, not copied


def test_a_scratch_folder_is_made_on_the_way(tmp_path):
    from ai_browser.app.attachments import place

    [one] = staged(tmp_path, b"x")
    work = tmp_path / "home" / "app" / "agents" / "a1" / "work"
    assert place(work, [(one, "x.txt")]) == ["x.txt"] and (work / "attachments" / "x.txt").read_bytes() == b"x"
    assert place(work, []) == []


def test_a_symlinked_attachments_folder_is_refused(tmp_path):  # Review Focus 5
    from ai_browser.app.attachments import place

    work, elsewhere = tmp_path / "project", tmp_path / "elsewhere"
    work.mkdir()
    elsewhere.mkdir()
    symlink_or_skip(elsewhere, work / "attachments")
    [one] = staged(tmp_path, b"x")
    with pytest.raises(ValueError, match="leads somewhere else"):
        place(work, [(one, "x.txt")])
    assert list(elsewhere.iterdir()) == [] and one.exists()


def test_a_link_where_a_file_would_go_is_skipped_never_followed(tmp_path):  # Review Focus 5
    from ai_browser.app.attachments import place

    work, target = tmp_path / "project", tmp_path / "outside.txt"
    (work / "attachments").mkdir(parents=True)
    target.write_text("keep", encoding="utf-8")
    symlink_or_skip(target, work / "attachments" / "x.txt")
    [one] = staged(tmp_path, b"new")
    assert place(work, [(one, "x.txt")]) == ["x (2).txt"]
    assert target.read_text(encoding="utf-8") == "keep"


def test_the_note_names_each_file_and_its_pictures():
    from ai_browser.app.attachments import note

    assert note([]) == ""
    text = note(["shot.PNG", "report.pdf"])
    assert text.startswith("\n\nThe user attached these files.")
    assert "- attachments/shot.PNG (a picture: look at it with Read)\n" in text
    assert text.endswith("- attachments/report.pdf")


def piece(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_a_file_comes_in_pieces_and_is_whole_at_its_size(tmp_path):
    from ai_browser.app.attachments import Uploads

    uploads = Uploads(tmp_path / "uploads")
    assert uploads.start("page", "u1", "../notes.txt", 10) == ("notes.txt", "")
    assert file_mode(tmp_path / "uploads") in (None, 0o700)
    assert uploads.add("page", "u1", 0, piece(b"hello")) == (False, "")
    with pytest.raises(ValueError, match="Wait for the attached files"):
        uploads.take("page", ["u1"])
    assert uploads.add("page", "u1", 1, piece(b"world")) == (True, "")
    [(path, name)] = uploads.take("page", ["u1"])
    assert name == "notes.txt" and path.read_bytes() == b"helloworld" and file_mode(path) in (None, 0o600)
    uploads.done("page", ["u1"])
    with pytest.raises(ValueError, match="attach it again"):
        uploads.take("page", ["u1"])
    assert uploads.start("page", "u2", "empty.txt", 0) == ("empty.txt", "") and uploads.whole("page", "u2")


def test_a_huge_out_of_order_or_damaged_file_is_dropped(tmp_path):  # Review Focus 5
    from ai_browser.app.attachments import MAX_BYTES, NOT_OPEN, Uploads

    uploads = Uploads(tmp_path / "uploads")
    assert uploads.start("page", "u1", "big.zip", MAX_BYTES + 1) == ("", "big.zip is over 20 MB")
    assert uploads.start("page", "../u", "x.txt", 1) == ("", "That isn't a file the app can take")
    for upload, seq, data, words in (("u2", 1, piece(b"x"), "out of order"), ("u3", 0, "not base64!", "damaged"),
                                     ("u4", 0, piece(b"too long"), "longer than it said"),
                                     ("u5", 0, "A" * (1_048_576 + 4), "damaged")):
        assert uploads.start("page", upload, "f.txt", 3)[1] == ""
        whole, why = uploads.add("page", upload, seq, data)
        assert not whole and words in why and why.endswith("attach it again"), upload
        assert uploads.add("page", upload, 0, piece(b"abc")) == (False, NOT_OPEN)  # it was dropped
    assert list((tmp_path / "uploads").glob("*.part")) == []


def test_at_most_ten_files_per_page_and_a_closed_page_leaves_nothing(tmp_path):
    from ai_browser.app.attachments import Uploads

    uploads = Uploads(tmp_path / "uploads")
    for number in range(10):
        assert uploads.start("page", f"u{number}", "f.txt", 1)[1] == ""
    assert uploads.start("page", "u10", "f.txt", 1) == ("", "At most 10 files at once")
    assert uploads.start("other", "u0", "f.txt", 1)[1] == ""  # another page's own
    with pytest.raises(ValueError, match="At most 10"):
        uploads.take("page", [f"u{number}" for number in range(11)])
    uploads.drop_all("page")
    assert len(list((tmp_path / "uploads").glob("*.part"))) == 1
    uploads.clear()
    assert list((tmp_path / "uploads").glob("*.part")) == []
