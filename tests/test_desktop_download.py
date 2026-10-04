"""Electron's zip (desktop/download.py): fetched from the pinned release only, and checked twice. The release's
SHASUMS256.txt must list the pinned checksum, and the zip must have the pinned size and that checksum. It is written
as a .part file and keeps its name only once checked. A cut, a mismatch, an error or Ctrl-C keeps nothing. The
release is served from memory (tests/fake_electron_zip.py)."""

import inspect
import socket
import ssl
import urllib.error
from types import SimpleNamespace

import pytest

from fake_electron_zip import ReleaseFetch, checksum

DATA = bytes(range(256)) * 9000  # 2,304,000 bytes: two pieces of 1 MiB and a short one


def release(tmp_path):
    from ai_browser.desktop.release import Asset

    asset = Asset("darwin", "arm64", "electron-test.zip", len(DATA), checksum(DATA), "a test Mac")
    return asset, ReleaseFetch(asset, DATA), tmp_path / "download"


def test_a_checked_zip_keeps_its_name_and_nothing_else_is_left(tmp_path):
    from ai_browser.desktop.download import download
    from ai_browser.desktop.release import SHASUMS

    asset, fetch, folder = release(tmp_path)
    seen = []
    path = download(asset, folder, fetch, seen.append)
    assert path == folder / "electron-test.zip" and path.read_bytes() == DATA
    assert sorted(item.name for item in folder.iterdir()) == ["electron-test.zip"]  # no .part left
    assert fetch.urls == [SHASUMS, asset.url]  # the checksums first, then the zip
    assert seen == sorted(seen) and seen[-1] == len(DATA)


def test_a_download_cut_halfway_keeps_nothing(tmp_path):  # Review Focus 2
    from ai_browser.desktop.download import CUT, SetupError, download

    asset, fetch, folder = release(tmp_path)
    fetch.cut_at = len(DATA) // 2
    with pytest.raises(SetupError) as error:
        download(asset, folder, fetch)
    assert str(error.value) == CUT == "The download stopped before the end: nothing was kept"
    assert list(folder.iterdir()) == []
    fetch.cut_at, fetch.short = None, True  # the connection ends early, with no error
    with pytest.raises(SetupError, match="^The download stopped before the end"):
        download(asset, folder, fetch)
    assert list(folder.iterdir()) == []


def test_a_zip_that_doesnt_match_keeps_nothing(tmp_path):  # Review Focus 2
    from ai_browser.desktop.download import MISMATCH, NOT_LISTED, SetupError, download

    asset, fetch, folder = release(tmp_path)
    fetch.corrupt = True  # one changed byte: the same size, another checksum
    with pytest.raises(SetupError) as error:
        download(asset, folder, fetch)
    assert str(error.value) == MISMATCH == "The download didn't match Electron's checksum: nothing was kept"
    fetch.corrupt, fetch.extra = False, b"!"  # one byte too many
    with pytest.raises(SetupError, match="didn't match"):
        download(asset, folder, fetch)
    assert list(folder.iterdir()) == []
    fetch.extra, fetch.listed = b"", "f" * 64  # the release lists another checksum: the zip is never fetched
    fetch.urls.clear()
    with pytest.raises(SetupError) as error:
        download(asset, folder, fetch)
    assert str(error.value) == NOT_LISTED == ("Electron's SHASUMS256.txt doesn't list the expected checksum: nothing "
                                              "was downloaded")
    assert len(fetch.urls) == 1 and list(folder.iterdir()) == []


def test_ctrl_c_keeps_nothing(tmp_path):
    from ai_browser.desktop.download import download

    asset, fetch, folder = release(tmp_path)

    def stop(done):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        download(asset, folder, fetch, stop)
    assert list(folder.iterdir()) == []


def test_network_problems_are_plain_words(tmp_path):
    from ai_browser.desktop.download import SetupError, download

    asset, fetch, folder = release(tmp_path)
    for fail, said in (
            (urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided")), "^No internet connection$"),
            (urllib.error.HTTPError("https://github.com/x", 404, "Not Found", {}, None),
             "^The download failed: GitHub answered 404$"),
            (urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed")), "couldn't be checked"),
            (TimeoutError("timed out"), "^The download stopped: the connection timed out$")):
        fetch.fail = fail
        with pytest.raises(SetupError, match=said):
            download(asset, folder, fetch)
    assert list(folder.iterdir()) == []


def test_low_disk_fails_before_anything_is_fetched(tmp_path, monkeypatch):
    import ai_browser.desktop.download as module

    asset, fetch, folder = release(tmp_path)
    monkeypatch.setattr(module.shutil, "disk_usage", lambda path: SimpleNamespace(free=1_000))
    with pytest.raises(module.SetupError, match="^Not enough free disk space: 1 GB is needed$"):
        module.download(asset, folder, fetch)
    assert fetch.urls == []


def test_the_checksum_list_is_read_as_sha256sum_writes_it():
    from ai_browser.desktop.download import listed

    text = f"{'a' * 64} *electron-v44.5.1-darwin-arm64.zip\n{'b' * 64}  electron-v44.5.1-win32-x64.zip\nnot a line\n"
    assert listed(text, "electron-v44.5.1-darwin-arm64.zip") == "a" * 64
    assert listed(text, "electron-v44.5.1-win32-x64.zip") == "b" * 64
    assert listed(text, "electron-v44.5.1-darwin-x64.zip") is None and listed("", "x") is None


def test_the_network_is_the_checked_one():
    from ai_browser.desktop.download import download
    from ai_browser.hearing.model import urlopen_fetch

    assert inspect.signature(download).parameters["fetch"].default is urlopen_fetch  # certificates always checked
