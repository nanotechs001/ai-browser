"""Hearing: the pinned speech model and its download, the speech engine, and push-to-talk turns. No test downloads or
loads Whisper: the model is a tiny pinned stand-in served locally (fake_engine.TINY), and the engine is a fake."""

import asyncio
import importlib.util
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
from types import SimpleNamespace

import pytest

from fake_engine import CONFIG, TINY, WEIGHTS, FakeEngine, install, tiny_store


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


# ---- the engine, the status and the download -------------------------------------------------------------------------

async def eventually(check, seconds=8.0):
    for _ in range(int(seconds * 20)):
        if check():
            return True
        await asyncio.sleep(0.05)
    return bool(check())


def hearing_for(tmp_path, present=True, **engine):
    """A HearingService over the tiny model (in place unless present=False) and a FakeEngine. Every status it
    broadcasts is kept, with the time it was sent ("at")."""
    from ai_browser.hearing.service import HearingService

    fake = FakeEngine(**engine)
    store = tiny_store(tmp_path / "models", present=present)
    hearing = HearingService(store, fake, platform="darwin")
    statuses = []
    hearing.on_status = lambda status: statuses.append({**status, "at": time.monotonic()})
    return hearing, fake, store, statuses


def test_the_states_say_what_is_missing(tmp_path):
    from ai_browser.hearing.service import platform_name, unavailable_status

    hearing, engine, store, _ = hearing_for(tmp_path, present=False, available=False)
    status = hearing.status()
    assert status["state"] == "no_engine" and "`uv sync --extra voice`" in status["reason"]
    engine.installed = True
    assert hearing.status() == {"state": "no_model", "reason": "The speech model isn't on this computer yet",
                                "size_bytes": TINY.size_bytes, "done_bytes": 0,
                                "folder": str(tmp_path / "models" / "faster-whisper-tiny.en"),
                                "model": "Whisper tiny.en", "max_seconds": 30, "platform": "mac", "loaded": False}
    install(store)
    assert hearing.status()["state"] == "ready" and hearing.status()["reason"] == ""
    assert engine.loads == [] and store.fetch.urls == []  # a status never loads the model or touches the network
    assert [platform_name(name) for name in ("darwin", "win32", "linux")] == ["mac", "windows", "linux"]
    assert unavailable_status()["state"] == "no_engine" and unavailable_status()["max_seconds"] == 30


def test_the_real_engine_imports_nothing_heavy_until_it_loads():
    code = ("import sys; from ai_browser.hearing.engine import WhisperEngine; "
            "from ai_browser.hearing.service import HearingService; WhisperEngine().available(); "
            "print('faster_whisper' in sys.modules, 'numpy' in sys.modules)")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert result.stdout.split() == ["False", "False"], result.stderr


@pytest.mark.skipif(importlib.util.find_spec("faster_whisper") is None, reason="the voice extra isn't installed")
def test_the_real_engine_loads_only_from_its_folder(tmp_path):
    from ai_browser.hearing.engine import WhisperEngine

    engine = WhisperEngine()
    assert engine.available()
    with pytest.raises(FileNotFoundError, match="^no model folder at "):
        engine.load(tmp_path / "missing")  # never a name faster-whisper would look up on Hugging Face


async def test_a_download_ends_ready_with_progress_at_most_twice_a_second(tmp_path):
    hearing, engine, store, statuses = hearing_for(tmp_path, present=False)
    store.fetch.delay = 0.3  # before each read of a 1 MB piece
    hearing.start_download()
    hearing.start_download()  # a second click while it runs does nothing
    assert hearing.status()["state"] == "downloading"
    assert await eventually(lambda: hearing.status()["state"] == "ready", 15)
    downloading = [status for status in statuses if status["state"] == "downloading"]
    assert statuses[-1]["state"] == "ready" and any(status["done_bytes"] > 0 for status in downloading)
    done = [status["done_bytes"] for status in downloading]
    assert done == sorted(done)
    assert all(later["at"] - earlier["at"] >= 0.45 for earlier, later in zip(downloading, downloading[1:]))
    assert len(store.fetch.urls) == 2 and store.present() and not store.part.exists()


async def test_a_bad_download_fails_and_the_next_click_clears_it(tmp_path):
    hearing, engine, store, statuses = hearing_for(tmp_path, present=False)
    store.fetch.corrupt = {"model.bin"}
    hearing.start_download()
    assert await eventually(lambda: hearing.status()["state"] == "failed")
    assert hearing.status()["reason"] == "The download didn't match the expected file: nothing was kept"
    assert statuses[-1]["state"] == "failed" and not store.folder.exists() and not store.part.exists()
    store.fetch.corrupt = set()
    hearing.start_download()
    assert hearing.status()["state"] == "downloading"  # the click clears the failure
    assert await eventually(lambda: hearing.status()["state"] == "ready")


async def test_cancel_mid_download_leaves_no_model(tmp_path):
    hearing, engine, store, statuses = hearing_for(tmp_path, present=False)
    store.fetch.delay = 0.3
    hearing.start_download()
    assert await eventually(lambda: store.part.exists())
    hearing.cancel_download()
    assert await eventually(lambda: hearing.status()["state"] == "no_model")
    assert not store.part.exists() and not store.folder.exists()


async def test_stopping_mid_download_keeps_nothing(tmp_path):
    from ai_browser.hearing.service import HearingService

    hearing, engine, store, statuses = hearing_for(tmp_path, present=False)
    store.fetch.delay = 0.3
    hearing.start_download()
    assert await eventually(lambda: hearing.status()["done_bytes"] > 0)
    await hearing.stop()  # the app closes mid-download
    assert not store.part.exists() and not store.folder.exists()
    again = HearingService(tiny_store(tmp_path / "models", present=False), FakeEngine())
    assert again.status()["state"] == "no_model"  # the next start offers Download again


async def test_download_is_offered_only_for_a_missing_or_broken_model(tmp_path):
    hearing, engine, store, statuses = hearing_for(tmp_path)
    hearing.start_download()
    assert hearing.status()["state"] == "ready" and store.fetch.urls == []  # never over a model that is there
    missing, engine2, store2, _ = hearing_for(tmp_path / "other", present=False, available=False)
    missing.start_download()
    assert missing.status()["state"] == "no_engine" and store2.fetch.urls == []
