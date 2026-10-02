"""Hearing: the pinned speech model and its download, the speech engine, and push-to-talk turns. No test downloads or
loads Whisper: the model is a tiny pinned stand-in served locally (fake_engine.TINY), and the engine is a fake."""

import socket
import ssl
import urllib.error
from types import SimpleNamespace

import pytest

from fake_engine import CONFIG, TINY, WEIGHTS, tiny_store


def test_the_pin_is_whisper_base_en_at_one_revision():
    from ai_browser.hearing.model import MODEL

    assert (MODEL.name, MODEL.repo) == ("base.en", "Systran/faster-whisper-base.en")
    assert MODEL.revision == "3d3d5dee26484f91867d81cb899cfcf72b96be6c"
    assert [(file.name, file.size, file.sha256, file.git_sha1) for file in MODEL.files] == [
        ("config.json", 2_227, None, "594369787efe617005d199b03739ee0ead7e3ab7"),
        ("model.bin", 145_216_508, "2a166925539a16005f14ff328359f9b9adb9dc4fb631bb3b227526862e93e2ef", None),
        ("tokenizer.json", 2_128_466, None, "15d7bdf9ba25718ca2504eec6a8f02bc55af0a6a"),
        ("vocabulary.txt", 422_309, None, "ee695b8d3e3c10d488304e04468efec4ca27554a")]
    assert MODEL.size_bytes == 147_769_510  # "148 MB" on the page
    assert MODEL.url(MODEL.files[1]) == ("https://huggingface.co/Systran/faster-whisper-base.en/resolve/"
                                         "3d3d5dee26484f91867d81cb899cfcf72b96be6c/model.bin")


def test_a_download_fills_the_folder_and_leaves_no_part(tmp_path):
    store = tiny_store(tmp_path / "models", present=False)
    seen = []
    assert not store.present()
    store.download(seen.append)
    assert store.present() and not store.part.exists()
    assert (store.folder / "config.json").read_bytes() == CONFIG
    assert (store.folder / "model.bin").read_bytes() == WEIGHTS
    assert seen == sorted(seen) and seen[-1] == TINY.size_bytes  # progress only rises, up to the total
    assert store.fetch.urls == [f"https://huggingface.co/test/tiny/resolve/{'0' * 40}/{name}"
                                for name in ("config.json", "model.bin")]


def test_a_file_that_doesnt_match_keeps_nothing(tmp_path):
    from ai_browser.hearing.model import MISMATCH, DownloadError

    store = tiny_store(tmp_path / "models", present=False)
    store.fetch.corrupt = {"model.bin"}  # one changed byte: its SHA-256 differs
    with pytest.raises(DownloadError) as error:
        store.download()
    assert str(error.value) == MISMATCH == "The download didn't match the expected file: nothing was kept"
    assert not store.folder.exists() and not store.part.exists()
    store.fetch.corrupt = {"config.json"}  # a small file: its git blob id differs
    with pytest.raises(DownloadError, match="didn't match"):
        store.download()
    store.fetch.corrupt, store.fetch.extra = set(), b"!"  # one byte too many
    with pytest.raises(DownloadError, match="didn't match"):
        store.download()
    assert not store.folder.exists() and not store.part.exists()


def test_an_old_folder_stays_until_the_new_one_is_checked(tmp_path):
    from ai_browser.hearing.model import DownloadError

    store = tiny_store(tmp_path / "models", present=False)
    store.folder.mkdir(parents=True)
    (store.folder / "old.txt").write_text("old", encoding="utf-8")
    store.fetch.corrupt = {"model.bin"}
    with pytest.raises(DownloadError):
        store.download()
    assert (store.folder / "old.txt").exists()  # a failed download changes nothing
    store.fetch.corrupt = set()
    store.download()
    assert store.present() and not (store.folder / "old.txt").exists()


def test_cancel_keeps_nothing(tmp_path):
    from ai_browser.hearing.model import DownloadCancelled

    store = tiny_store(tmp_path / "models", present=False)
    seen = []
    with pytest.raises(DownloadCancelled):
        store.download(seen.append, cancelled=lambda: bool(seen))  # Cancel once the first piece is in
    assert seen and not store.part.exists() and not store.folder.exists()


def test_low_disk_fails_before_any_fetch(tmp_path, monkeypatch):
    import ai_browser.hearing.model as model

    monkeypatch.setattr(model.shutil, "disk_usage", lambda path: SimpleNamespace(free=1_000))
    store = tiny_store(tmp_path / "models", present=False)
    with pytest.raises(model.DownloadError) as error:
        store.download()
    assert str(error.value) == "Not enough free disk space: 52 MB is needed" and store.fetch.urls == []
    with pytest.raises(model.DownloadError, match="^Not enough free disk space: 198 MB is needed$"):
        model.ModelStore(tmp_path / "real").download()  # the real model and 50 MB to spare: never fetched here


def test_network_problems_are_plain_words(tmp_path):
    from ai_browser.hearing.model import DownloadError

    store = tiny_store(tmp_path / "models", present=False)
    store.fetch.fail = urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided"))
    with pytest.raises(DownloadError, match="^No internet connection$"):
        store.download()
    store.fetch.fail = urllib.error.HTTPError("https://huggingface.co/test/tiny", 404, "Not Found", {}, None)
    with pytest.raises(DownloadError, match="^The download failed: Hugging Face answered 404$"):
        store.download()
    store.fetch.fail = urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed"))
    with pytest.raises(DownloadError, match="couldn't be checked"):
        store.download()
    assert not store.part.exists() and not store.folder.exists()


def test_present_means_every_file_at_its_size(tmp_path):
    store = tiny_store(tmp_path / "models")
    assert store.present()
    (store.folder / "model.bin").write_bytes(WEIGHTS[:-1])
    assert not store.present()
    (store.folder / "model.bin").unlink()
    assert not store.present()


def test_certificates_are_always_checked():
    from ai_browser.hearing.model import tls_context

    context = tls_context()
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert type(context).__module__.startswith("truststore")  # the computer's own certificate store
