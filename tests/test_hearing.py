"""Hearing: the pinned speech model and its download, the speech engine, and push-to-talk turns. No test downloads or
loads Whisper: the model is a tiny pinned stand-in served locally (fake_engine.TINY), and the engine is a fake."""

import asyncio
import base64
import importlib.util
import math
import socket
import ssl
import struct
import subprocess
import sys
import time
import urllib.error
from pathlib import Path
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
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, encoding="utf-8")
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


# ---- turns ---------------------------------------------------------------------------------------------------------

def tone(seconds, freq=440.0, level=0.4):
    """16 kHz mono 16-bit little-endian samples of a sine: what the page sends."""
    count = int(16_000 * seconds)
    return struct.pack(f"<{count}h", *(round(level * 32767 * math.sin(2 * math.pi * freq * n / 16_000))
                                       for n in range(count)))


def chunks(pcm, size=8_000):
    """The page's chunks: 250 ms each, as base64."""
    return [base64.b64encode(pcm[start:start + size]).decode() for start in range(0, len(pcm), size)]


async def spoken(hearing, key, turn, pcm):
    assert hearing.begin(key, turn) == ""
    for seq, piece in enumerate(chunks(pcm)):
        assert hearing.add(key, turn, seq, piece) == ""
    return await hearing.finish(key, turn)


async def test_a_turn_gives_the_engines_words_from_the_chunks_in_order(tmp_path):
    hearing, engine, store, _ = hearing_for(tmp_path, answers=["what is fix the footer doing"])
    pcm = tone(1.0)
    assert await spoken(hearing, "socket-1", "u1", pcm) == ("what is fix the footer doing", "")
    assert engine.heard == [pcm] and engine.loads == [store.folder]
    assert hearing._turns == {}


async def test_refused_chunks_give_plain_errors_and_never_reach_the_engine(tmp_path):
    hearing, engine, store, _ = hearing_for(tmp_path)
    hearing.max_seconds = 1
    quarter = chunks(tone(0.25))[0]
    cases = [
        ([(0, quarter), (1, quarter), (2, quarter), (3, quarter), (4, quarter)], "That was longer than 1 second"),
        ([(0, "not base64!")], "A piece of the audio was damaged"),
        ([(0, base64.b64encode(b"\x01\x02\x03").decode())], "A piece of the audio was damaged"),  # an odd byte count
        ([(0, quarter), (2, quarter)], "The audio arrived out of order"),
        ([(0, "A" * 65_540)], "A piece of the audio was too big"),
    ]
    for number, (pieces, error) in enumerate(cases):
        turn = f"u{number}"
        assert hearing.begin("socket", turn) == ""
        answers = [hearing.add("socket", turn, seq, piece) for seq, piece in pieces]
        assert answers[-1] == error and all(answer == "" for answer in answers[:-1]), (number, answers)
        assert await hearing.finish("socket", turn) == ("", "That turn isn't open")  # the refusal dropped it
    assert hearing.add("socket", "nobody", 0, quarter) == "That turn isn't open"
    assert engine.heard == []


async def test_silence_and_slips_are_not_transcribed(tmp_path):
    hearing, engine, store, _ = hearing_for(tmp_path)
    assert await spoken(hearing, "s", "u1", tone(0.2)) == ("", "I didn't hear anything")  # under 0.3 s
    assert await spoken(hearing, "s", "u2", bytes(32_000)) == ("", "I didn't hear anything")  # a second of silence
    assert await spoken(hearing, "s", "u3", tone(1.0, level=0.002)) == ("", "I didn't hear anything")  # near silence
    assert engine.heard == []
    engine.speech_seconds = 0.0  # the voice detector found no speech in it
    assert await spoken(hearing, "s", "u4", tone(1.0)) == ("", "I didn't hear anything")
    assert len(engine.heard) == 1


async def test_dropped_turns_leave_no_audio_behind(tmp_path):
    hearing, engine, store, _ = hearing_for(tmp_path)
    piece = chunks(tone(0.25))[0]
    for end in ("begin again", "cancel", "drop"):
        assert hearing.begin("s", "u1") == "" and hearing.add("s", "u1", 0, piece) == ""
        kept = hearing._turns["s"].audio
        assert len(kept) == 8_000
        if end == "begin again":
            assert hearing.begin("s", "u2") == ""  # one turn per socket: the first is dropped
        elif end == "cancel":
            hearing.cancel("s", "u1")
        else:
            hearing.drop("s")  # the socket closed
        assert kept == bytearray(), end
        hearing.drop("s")
    assert engine.heard == [] and hearing._turns == {}


async def test_a_turn_left_open_is_dropped(tmp_path, monkeypatch):
    import ai_browser.hearing.service as service

    monkeypatch.setattr(service, "OPEN_GRACE", 0.1)
    hearing, engine, store, _ = hearing_for(tmp_path)
    hearing.max_seconds = 0  # so the turn may stay open 0.1 s
    assert hearing.begin("s", "u1") == ""
    assert await eventually(lambda: "s" not in hearing._turns, 2)


async def test_an_engine_error_is_plain_and_carries_no_audio(tmp_path):
    hearing, engine, store, _ = hearing_for(tmp_path)
    pcm = tone(1.0)
    engine.error = RuntimeError(f"bad input {pcm[:40]!r}")
    assert await spoken(hearing, "s", "u1", pcm) == ("", "Couldn't turn the speech into text (RuntimeError)")


async def test_two_sockets_are_transcribed_one_after_the_other(tmp_path):
    hearing, engine, store, _ = hearing_for(tmp_path, answers=["one", "two"], delay=0.3)
    results = await asyncio.gather(spoken(hearing, "a", "u1", tone(1.0)), spoken(hearing, "b", "u2", tone(1.0)))
    assert sorted(text for text, _ in results) == ["one", "two"] and not engine.overlapped
    assert len(engine.loads) == 1  # loaded once, for both


async def test_a_turn_writes_nothing_to_disk(tmp_path):
    hearing, engine, store, _ = hearing_for(tmp_path)

    def files():
        return sorted((str(path), path.stat().st_size, path.stat().st_mtime_ns) for path in tmp_path.rglob("*"))

    before = files()
    assert await spoken(hearing, "s", "u1", tone(1.0)) == ("hello", "")
    assert files() == before


async def test_the_model_loads_once_at_the_first_turn_and_a_failed_load_offers_download(tmp_path):
    hearing, engine, store, statuses = hearing_for(tmp_path)
    hearing.status()
    assert engine.loads == []  # a status never loads it
    assert hearing.begin("s", "u1") == ""  # the first turn starts loading it, while the user speaks
    assert await eventually(lambda: hearing.status()["loaded"])
    assert statuses[-1]["loaded"] is True  # the pages learn it: no more "the first time takes longer"
    await spoken(hearing, "s", "u2", tone(1.0))
    assert len(engine.loads) == 1
    broken, engine2, store2, _ = hearing_for(tmp_path / "other", load_error=RuntimeError("model.bin is damaged"))
    text, error = await spoken(broken, "s", "u1", tone(1.0))
    assert (text, error) == ("", "The speech model couldn't load: model.bin is damaged")
    assert broken.status()["state"] == "failed" and broken.status()["reason"] == error
    assert broken.begin("s", "u2") == error  # refused until a new Download
    engine2.load_error = None
    broken.start_download()
    assert broken.status()["state"] == "downloading"  # the click clears the failure
    assert await eventually(lambda: broken.status()["state"] == "ready")
    assert await spoken(broken, "s", "u3", tone(1.0)) == ("hello", "")
    assert len(engine2.loads) == 2  # the new files load again


async def test_nothing_touches_the_network_until_the_download_click(tmp_path):
    hearing, engine, store, _ = hearing_for(tmp_path)
    hearing.status()
    await spoken(hearing, "s", "u1", tone(1.0))
    assert store.fetch.urls == []
    store.folder.rename(tmp_path / "moved")
    assert hearing.status()["state"] == "no_model" and store.fetch.urls == []
    hearing.start_download()
    assert await eventually(lambda: hearing.status()["state"] == "ready")
    assert len(store.fetch.urls) == 2


async def test_a_turn_needs_talking_to_be_ready_and_a_valid_id(tmp_path):
    hearing, engine, store, _ = hearing_for(tmp_path, present=False)
    assert hearing.begin("s", "u1") == "The speech model isn't on this computer yet"
    install(store)
    assert hearing.begin("s", "bad id!") == "That turn has no valid id"
    assert hearing.begin("s", "x" * 41) == "That turn has no valid id"
    engine.installed = False
    assert "uv sync --extra voice" in hearing.begin("s", "u1")
    assert hearing._turns == {}


def test_the_voice_extra_is_optional_and_pinned():
    import tomllib

    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["optional-dependencies"]["voice"] == ["faster-whisper>=1.2,<2"]
    assert not any("whisper" in dependency for dependency in project["dependencies"])  # the base install stays light
