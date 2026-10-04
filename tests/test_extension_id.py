"""The ID Chrome and Brave give an unpacked extension (Brave's watcher), and the folder path it is hashed from."""

import pytest

EXT = "C:\\Users\\me\\.ai-browser\\app\\extension"
WATCH = "C:\\Users\\me\\.ai-browser\\app\\watcher"
JOSE = "C:\\Users\\José & Ana\\.ai-browser\\app\\extension"
DEV = "C:\\dev\\aib-home\\app\\extension"


@pytest.mark.parametrize("folder, shown, expected", [
    (EXT, EXT, "jjdpkibincdinfnjejbcmmghdbgfjpph"),
    ("c:\\Users\\me\\.ai-browser\\app\\extension", EXT, "jjdpkibincdinfnjejbcmmghdbgfjpph"),  # a lower-case drive
    (WATCH, WATCH, "ncapijkcfmdajdlhdhbgnnmkgejiggeg"),
    ("C:/Users/me/.ai-browser/app/extension", EXT, "jjdpkibincdinfnjejbcmmghdbgfjpph"),  # forward slashes
    ("C:\\Users\\me\\.ai-browser\\app\\extension\\", EXT, "jjdpkibincdinfnjejbcmmghdbgfjpph"),  # a trailing separator
    ("c:/dev/aib-home/app/extension/", DEV, "nhhpnkhncgedihejcoolkhbhmnklfgik"),  # all three at once
    (DEV, DEV, "nhhpnkhncgedihejcoolkhbhmnklfgik"),
    (JOSE, JOSE, "lfcipbofoccnodmlbinbgmflefkkgomp"),  # UTF-16LE of the exact path, not UTF-8
])
def test_windows_extension_ids_follow_chromium(folder, shown, expected):
    from ai_browser.extension_id import extension_id_for, extension_path

    assert extension_id_for(folder, system="win32") == expected
    assert extension_path(folder, system="win32") == shown  # one string: hashed, shown, pasted


def test_the_old_utf8_hash_was_wrong_on_windows():
    from ai_browser.extension_id import extension_id_for

    assert extension_id_for(EXT, system="win32") != "mkeihmjkgdgccikkejdhgpoikkjpilll"  # the old UTF-8 code's ID


def test_the_posix_id_is_unchanged(tmp_path):
    import hashlib
    import os

    from ai_browser.extension_id import extension_id_for, extension_path

    folder = tmp_path / "ext"
    folder.mkdir()
    digest = hashlib.sha256(os.path.realpath(folder).encode("utf-8")).hexdigest()[:32]
    assert extension_id_for(folder, system="darwin") == "".join(chr(ord("a") + int(c, 16)) for c in digest)
    assert extension_path(folder, system="darwin") == os.path.realpath(folder)
