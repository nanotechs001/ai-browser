"""localbox.py (the no-Docker spec): the sandbox's browser without Docker, a separate headless browser on this
computer with a profile of its own, under a throwaway AI Browser home. Each test stops every browser it started."""

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from ai_browser import localbox
from ai_browser.chrome import ChromeError
from conftest import file_mode, symlink_or_skip

BROWSER = pytest.mark.skipif(localbox.sandbox_binary() is None, reason="neither Google Chrome nor Brave is installed")


@pytest.fixture
def boxes(tmp_path):
    made = localbox.LocalSandboxes(tmp_path / "home")
    yield made
    for name in made.running():
        made.stop(name)


def record(boxes, profile: str) -> dict:
    return json.loads((boxes.home / "sandboxes" / profile / "browser.json").read_text(encoding="utf-8"))


@BROWSER
def test_a_browser_of_its_own_answers_on_loopback(boxes):
    info = boxes.start("pytest")
    folder = boxes.home / "sandboxes" / "pytest"
    assert (info.name, info.profile, info.local, info.created, info.fresh) == ("aib-pytest", "pytest", True, True,
                                                                                False)
    assert info.work_host == folder / "work" and info.work_host.is_dir()
    assert file_mode(folder / "profile") in (0o700, None) and file_mode(folder / "browser.json") in (0o600, None)
    assert info.http.startswith("http://127.0.0.1:")
    assert boxes.ws_url(info).startswith(info.http.replace("http://", "ws://") + "/devtools/browser/")
    with urllib.request.urlopen(info.http + "/json/version", timeout=5) as answer:
        assert "HeadlessChrome" in json.load(answer)["User-Agent"]  # headless, and nothing about it faked
    assert boxes.running() == ["aib-pytest"] and boxes.is_running("aib-pytest")
    assert record(boxes, "pytest")["binary"] == localbox.sandbox_binary()


@BROWSER
def test_every_session_on_a_profile_shares_its_one_browser(boxes):
    first = boxes.start("pytest")
    started = time.monotonic()
    second = boxes.start("pytest")
    assert second.created is False and second.http == first.http and time.monotonic() - started < 1.5
    assert boxes.running() == ["aib-pytest"]


@BROWSER
@pytest.mark.posix_only
def test_its_browser_outlives_the_process_that_started_it(boxes):
    boxes.start("pytest")
    pid = record(boxes, "pytest")["pid"]
    assert os.getsid(pid) == pid != os.getsid(0)  # a session of its own: ending this one doesn't end it


@BROWSER
def test_stop_ends_the_browser_and_keeps_its_profile(boxes):
    info = boxes.start("pytest")
    folder = boxes.home / "sandboxes" / "pytest"
    pid = record(boxes, "pytest")["pid"]
    boxes.stop(info.name)
    assert not localbox._alive(pid) and boxes.running() == [] and not boxes.is_running(info.name)
    assert not (folder / "browser.json").exists() and not (folder / "profile" / "DevToolsActivePort").exists()
    assert (folder / "profile").is_dir()  # its logins stay
    boxes.stop(info.name)  # twice is fine
    assert boxes.start("pytest").created is True


@BROWSER
def test_its_downloads_never_land_in_the_users_downloads_folder(boxes):
    info = boxes.start("pytest")  # (checked by hand: a download after its session left lands in the pref's folder)
    boxes.stop(info.name)  # the browser rewrites its preferences as it closes: the folder must survive that
    folder = boxes.home / "sandboxes" / "pytest"
    prefs = json.loads((folder / "profile" / "Default" / "Preferences").read_text(encoding="utf-8"))
    assert prefs["download"]["default_directory"] == prefs["savefile"]["default_directory"] == str(folder / "downloads")
    assert prefs["download"]["prompt_for_download"] is False


@BROWSER
def test_a_throwaway_profile_is_removed_when_it_stops(boxes):
    info = boxes.start(fresh=True)
    folder = boxes.home / "sandboxes" / info.profile
    assert re.fullmatch(r"fresh-[0-9a-f]{6}", info.profile) and info.fresh and (folder / "profile").is_dir()
    (info.work_host / "keep.txt").write_text("x", encoding="utf-8")
    boxes.stop(info.name)
    assert not (folder / "profile").exists() and (info.work_host / "keep.txt").is_file()  # its work stays, as in Docker


@BROWSER
@pytest.mark.posix_only
def test_stale_lock_files_are_cleared_once_their_browser_is_gone(boxes):
    folder = boxes.home / "sandboxes" / "pytest"
    profile = folder / "profile"
    profile.mkdir(parents=True)
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()  # a browser that crashed: its lock names a process that ended, its port file a port nobody holds
    symlink_or_skip(f"{socket.gethostname()}-{gone.pid}", profile / "SingletonLock")
    (profile / "DevToolsActivePort").write_text("1\n/devtools/browser/old\n", encoding="utf-8")
    (folder / "browser.json").write_text(json.dumps({"pid": gone.pid, "binary": "x", "fresh": False}),
                                         encoding="utf-8")
    info = boxes.start("pytest")
    assert info.created and boxes.ws_url(info) and record(boxes, "pytest")["pid"] != gone.pid


@BROWSER
@pytest.mark.posix_only
def test_a_profile_a_running_browser_holds_is_never_cleared(boxes, monkeypatch):
    monkeypatch.setattr(localbox, "ANSWER_WAIT", 0.5)
    profile = boxes.home / "sandboxes" / "pytest" / "profile"
    profile.mkdir(parents=True)
    holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", f"--user-data-dir={profile}"])
    try:
        symlink_or_skip(f"{socket.gethostname()}-{holder.pid}", profile / "SingletonLock")
        with pytest.raises(ChromeError, match="runs but doesn't answer"):
            boxes.start("pytest")
        assert os.path.lexists(profile / "SingletonLock") and holder.poll() is None  # untouched
        assert boxes.running() == ["aib-pytest"]  # and stop --all finds it
    finally:
        holder.kill()
        holder.wait()
    assert boxes.start("pytest").created  # gone now: its lock was stale


@BROWSER
def test_two_sessions_starting_a_profile_at_once_share_one_browser(boxes):  # Review Focus 2
    import threading

    infos, errors = [], []

    def start():
        try:
            infos.append(boxes.start("pytest"))
        except Exception as exc:  # reported below
            errors.append(exc)

    threads = [threading.Thread(target=start) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert not errors and len(infos) == 2 and infos[0].http == infos[1].http
    assert sorted(info.created for info in infos) == [False, True]  # one browser started, the other start shared it


def test_on_windows_a_pid_that_isnt_the_browser_is_never_ended(boxes, monkeypatch):  # Review Focus 5
    from ai_browser import platforms

    folder = boxes.home / "sandboxes" / "pytest"
    (folder / "profile").mkdir(parents=True)
    stranger = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:  # the record names a browser that ended, and Windows gave its pid to another program
        (folder / "browser.json").write_text(json.dumps({"pid": stranger.pid, "binary": "x", "fresh": False}),
                                             encoding="utf-8")
        monkeypatch.setattr(platforms, "WINDOWS", True)
        monkeypatch.setattr(platforms, "pid_alive", lambda pid: pid == stranger.pid)  # no Win32 call is made here
        assert not boxes.is_running("aib-pytest") and boxes.running() == []  # its port doesn't answer: not ours
        boxes.stop("aib-pytest")
        assert stranger.poll() is None and not (folder / "browser.json").exists()  # untouched; the stale record went
    finally:
        stranger.kill()
        stranger.wait()


def test_names_are_checked_before_anything_starts(boxes, monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("a browser started")

    monkeypatch.setattr(localbox, "launch", never)
    for name, words in (("chrome", "reserved"), ("app", "reserved"), ("Bad Name!", "lowercase letters")):
        with pytest.raises(ValueError, match=words):
            boxes.start(name)


def test_without_chrome_or_brave_it_says_what_to_install(boxes, monkeypatch):
    monkeypatch.setattr(localbox, "sandbox_binary", lambda: None)
    with pytest.raises(ChromeError, match="needs Google Chrome or Brave"):
        boxes.start("pytest")


def test_the_browser_is_chrome_else_brave(monkeypatch):
    monkeypatch.setattr(localbox, "chrome_binary", lambda: None)
    monkeypatch.setattr(localbox, "brave_binary", lambda: "/opt/brave.com/brave/brave")
    assert localbox.sandbox_binary() == "/opt/brave.com/brave/brave"
    monkeypatch.setattr(localbox, "chrome_binary", lambda: "/usr/bin/google-chrome")
    assert localbox.sandbox_binary() == "/usr/bin/google-chrome"
