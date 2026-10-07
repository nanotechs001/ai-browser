"""localbox.py (the no-Docker spec): the sandbox's browser without Docker, a separate headless browser on this
computer with a profile of its own, under a throwaway AI Browser home. Each test stops every browser it started."""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from ai_browser import localbox, platforms
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
    assert (boxes.home / "sandboxes" / "pytest" / "downloads").is_dir()  # there before the browser could write to it
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
    folder = boxes.home / "sandboxes" / "pytest"
    (folder / "profile").mkdir(parents=True)
    stranger = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:  # the record names a browser that ended, and Windows gave its pid to another program
        (folder / "browser.json").write_text(json.dumps({"pid": stranger.pid, "binary": "x", "fresh": False}),
                                             encoding="utf-8")
        monkeypatch.setattr(platforms, "WINDOWS", True)
        monkeypatch.setattr(platforms, "lock_file", lambda path: open(path, "a+b"))  # (stop locks; no Win32 call here)
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
    for name, words in (("chrome", "reserved"), ("app", "reserved"), ("fresh-work", "reserved"),
                        ("Bad Name!", "lowercase letters")):
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


# ---- fix round 1 (the review's findings) ----


def _tree(folder: Path) -> dict:
    """Every entry under a folder with its bytes (or its link target) and mode: to see that nothing changed."""
    seen = {}
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            seen[str(path)] = ("link", os.readlink(path))
        elif path.is_file():
            seen[str(path)] = (path.read_bytes(), path.stat().st_mode)
        else:
            seen[str(path)] = ("dir", path.stat().st_mode)
    return seen


def _holder(profile: Path) -> subprocess.Popen:
    """A process whose command line names the profile, as a browser's does."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", f"--user-data-dir={profile}"])


def test_a_profile_named_like_a_throwaway_is_refused_and_a_named_one_survives_stop(boxes):  # I1
    folder = boxes.home / "sandboxes" / "fresh-work"  # one an earlier version could have made: a named profile
    (folder / "profile").mkdir(parents=True)
    (folder / "profile" / "logins").write_text("x", encoding="utf-8")
    (folder / "browser.json").write_text(json.dumps({"pid": 0, "binary": "x", "fresh": False}), encoding="utf-8")
    boxes.stop("aib-fresh-work")
    assert (folder / "profile" / "logins").is_file() and not (folder / "browser.json").exists()


@pytest.mark.posix_only
def test_a_browser_started_for_one_profile_never_vouches_for_another(boxes, monkeypatch):  # I2
    first = boxes.home / "sandboxes" / "pytest" / "profile"
    first.mkdir(parents=True)
    other = boxes.home / "sandboxes" / "other"
    (other / "profile").mkdir(parents=True)
    holder = _holder(first)
    try:
        monkeypatch.setitem(localbox._launched, holder.pid, holder)  # launched here, for "pytest"
        (other / "browser.json").write_text(json.dumps({"pid": holder.pid, "binary": "x", "fresh": False}),
                                            encoding="utf-8")  # a record of another profile that names its pid
        assert localbox._runs_profile(holder.pid, first) and not localbox._runs_profile(holder.pid, other / "profile")
        assert not boxes.is_running("aib-other") and boxes.running() == []
        boxes.stop("aib-other")
        assert holder.poll() is None and not (other / "browser.json").exists()  # untouched; the stale record went
    finally:
        holder.kill()
        holder.wait()


@pytest.mark.posix_only
def test_a_launched_process_that_ended_doesnt_hide_a_live_holder_of_its_pid(boxes, monkeypatch):  # I2
    profile = boxes.home / "sandboxes" / "pytest" / "profile"
    profile.mkdir(parents=True)

    class Ended:
        args: list = []

        def poll(self):
            return 0

    holder = _holder(profile)
    try:
        monkeypatch.setitem(localbox._launched, holder.pid, Ended())  # the pid was a browser of ours that ended
        assert localbox._runs_profile(holder.pid, profile) and holder.pid not in localbox._launched
    finally:
        holder.kill()
        holder.wait()


def never(*args, **kwargs):
    raise AssertionError("a browser started")


@pytest.fixture
def stand_in(tmp_path, monkeypatch):
    """A stand-in for one of the user's own browser folders (with the files a running browser keeps), and no browser
    started or user folder named by anything the test does."""
    monkeypatch.setattr(localbox, "launch", never)
    monkeypatch.setattr(localbox, "own_browser_dirs", lambda: [])
    folder = tmp_path / "UserBrowser"
    (folder / "Default").mkdir(parents=True)
    (folder / "Default" / "Preferences").write_text('{"download": {"default_directory": "/me/Downloads"}}',
                                                    encoding="utf-8")
    (folder / "DevToolsActivePort").write_text("9\n/devtools/browser/x\n", encoding="utf-8")
    (folder / "lockfile").write_text("", encoding="utf-8")
    symlink_or_skip("host-1", folder / "SingletonLock")
    os.chmod(folder, 0o755)
    return folder


@pytest.mark.parametrize("how", ["profile is a link", "folder is a link", "is a browser folder", "Default is a link",
                                 "Preferences is a link"])
def test_a_link_or_the_users_browser_folder_is_refused_before_anything_changes(boxes, tmp_path, monkeypatch, stand_in,
                                                                               how):  # I3, R2
    folder = boxes.home / "sandboxes" / "pytest"
    (boxes.home / "sandboxes").mkdir(parents=True)
    if how == "profile is a link":
        folder.mkdir()
        symlink_or_skip(stand_in, folder / "profile")
        watched = [stand_in]
    elif how == "folder is a link":
        (tmp_path / "elsewhere").mkdir()
        shutil.copytree(stand_in, tmp_path / "elsewhere" / "profile", symlinks=True)
        symlink_or_skip(tmp_path / "elsewhere", folder)
        watched = [tmp_path / "elsewhere"]
    elif how == "is a browser folder":
        shutil.copytree(stand_in, folder / "profile", symlinks=True)
        monkeypatch.setattr(localbox, "own_browser_dirs", lambda: [folder / "profile"])
        watched = [folder / "profile"]
    elif how == "Default is a link":  # a link one level deeper: the user's real Default, Preferences and all
        (folder / "profile").mkdir(parents=True)
        symlink_or_skip(stand_in / "Default", folder / "profile" / "Default")
        watched = [stand_in, folder / "profile"]
    else:
        (folder / "profile" / "Default").mkdir(parents=True)
        symlink_or_skip(stand_in / "Default" / "Preferences", folder / "profile" / "Default" / "Preferences")
        watched = [stand_in, folder / "profile"]
    before = [_tree(path) for path in watched]
    with pytest.raises(ChromeError, match="won't use"):
        boxes.start("pytest")
    with pytest.raises(ChromeError, match="won't use"):
        boxes.stop("aib-pytest")
    assert [_tree(path) for path in watched] == before
    assert not (folder / "work").exists() and not (folder / "start.lock").exists()
    assert (stand_in / "Default" / "Preferences").read_text(encoding="utf-8").count("/me/Downloads") == 1
    assert boxes.running() == [] and not boxes.is_running("aib-pytest")


@pytest.mark.parametrize("how", ["profile", "folder"])
@pytest.mark.parametrize("call", ["start", "stop"])
def test_a_link_that_appears_while_a_start_or_stop_waits_for_the_lock_is_refused(boxes, tmp_path, stand_in, how,
                                                                                 call):  # R1
    name = "fresh-abcdef" if call == "stop" else "pytest"  # a throwaway: stop would remove its profile
    folder = boxes.home / "sandboxes" / name
    (folder / "profile").mkdir(parents=True)
    (folder / "browser.json").write_text(json.dumps({"pid": 0, "binary": "x", "fresh": True}), encoding="utf-8")
    shutil.copytree(stand_in, tmp_path / "elsewhere" / "profile", symlinks=True)
    shutil.copy(folder / "browser.json", tmp_path / "elsewhere" / "browser.json")
    watched = [stand_in] if how == "profile" else [tmp_path / "elsewhere"]
    opened = []
    real = platforms.lock_file

    def lock_file(path):
        if not opened:  # another opener holds the lock; the link appears while this one waits; then it lets go
            opened.append(path)
            if how == "profile":
                shutil.rmtree(folder / "profile")
                symlink_or_skip(stand_in, folder / "profile")
            else:
                shutil.rmtree(folder)
                symlink_or_skip(tmp_path / "elsewhere", folder)
            return None
        return real(path)

    before = [_tree(path) for path in watched]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(platforms, "lock_file", lock_file)
        with pytest.raises(ChromeError, match="won't use"):
            getattr(boxes, call)(name if call == "start" else f"aib-{name}")
    assert [_tree(path) for path in watched] == before


def test_the_end_of_a_stop_refuses_a_link_before_it_clears_or_removes_anything(boxes, tmp_path, stand_in):  # R1
    folder = boxes.home / "sandboxes" / "fresh-abcdef"
    folder.mkdir(parents=True)
    symlink_or_skip(stand_in, folder / "profile")
    (folder / "browser.json").write_text(json.dumps({"pid": 0, "binary": "x", "fresh": True}), encoding="utf-8")
    before = _tree(stand_in)
    with pytest.raises(ChromeError, match="won't use"):
        boxes._end(folder)
    assert _tree(stand_in) == before and (folder / "browser.json").is_file()


@pytest.mark.posix_only
@pytest.mark.parametrize("how", ["Default", "Preferences"])
def test_the_download_folder_is_never_written_through_a_link(tmp_path, stand_in, how):  # R2: swapped in later
    profile = tmp_path / "profile"
    profile.mkdir()
    if how == "Default":
        symlink_or_skip(stand_in / "Default", profile / "Default")
    else:
        (profile / "Default").mkdir()
        symlink_or_skip(stand_in / "Default" / "Preferences", profile / "Default" / "Preferences")
    before = _tree(stand_in)
    with pytest.raises(ChromeError, match="won't use"):
        localbox._keep_downloads_in(profile, tmp_path / "downloads")
    assert _tree(stand_in) == before


def test_a_link_in_place_of_the_sandboxes_folder_is_refused(boxes, tmp_path, stand_in):  # R3
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "pytest").mkdir(parents=True)
    shutil.copytree(stand_in, elsewhere / "pytest" / "profile", symlinks=True)
    boxes.home.mkdir()
    symlink_or_skip(elsewhere, boxes.home / "sandboxes")
    before = _tree(elsewhere)
    with pytest.raises(ChromeError, match="won't use"):
        boxes.start("pytest")
    with pytest.raises(ChromeError, match="won't use"):
        boxes.stop("aib-pytest")
    assert _tree(elsewhere) == before and boxes.running() == [] and not boxes.is_running("aib-pytest")


@pytest.mark.parametrize("how", ["stops as it starts", "can't start"])
def test_a_throwaway_whose_browser_never_ran_keeps_no_profile_but_a_named_one_keeps_its_own(boxes, monkeypatch,
                                                                                          how):  # R4
    # a real launch, of a program that isn't a browser: python refuses --user-data-dir and exits
    binary = sys.executable if how == "stops as it starts" else str(boxes.home / "no-such-browser")
    monkeypatch.setattr(localbox, "sandbox_binary", lambda: binary)
    with pytest.raises((ChromeError, OSError)):
        boxes.start(fresh=True)
    root = boxes.home / "sandboxes"
    (folder,) = list(root.iterdir())
    assert folder.name.startswith("fresh-") and (folder / "work").is_dir() and not (folder / "profile").exists()
    with pytest.raises((ChromeError, OSError)):
        boxes.start("pytest")
    assert (root / "pytest" / "profile").is_dir()  # its logins, if any, stay


def test_a_throwaway_folder_that_is_a_link_is_never_removed_through_the_link(boxes, stand_in, monkeypatch):  # R4
    monkeypatch.setattr(localbox.secrets, "token_hex", lambda n: "abcdef")
    folder = boxes.home / "sandboxes" / "fresh-abcdef"
    folder.mkdir(parents=True)
    symlink_or_skip(stand_in, folder / "profile")
    before = _tree(stand_in)
    with pytest.raises(ChromeError, match="won't use"):
        boxes.start(fresh=True)
    assert _tree(stand_in) == before


@BROWSER
@pytest.mark.posix_only
def test_stopping_a_browser_from_another_process_is_quick_and_never_a_kill(boxes):  # I4
    boxes.start("pytest")  # this process is its parent and doesn't reap it as it ends: a zombie to the other one
    process = localbox._launched[record(boxes, "pytest")["pid"]]
    script = """
import json, os, sys, time
from pathlib import Path
from ai_browser import localbox
calls = []
real_kill = os.kill
os.kill = lambda pid, sig: calls.append(["kill", sig]) if sig else real_kill(pid, sig)
os.killpg = lambda pid, sig: calls.append(["killpg", sig])
started = time.monotonic()
localbox.LocalSandboxes(Path(sys.argv[1])).stop("aib-pytest")
print(json.dumps({"seconds": time.monotonic() - started, "calls": calls}))
"""
    answer = subprocess.run([sys.executable, "-c", script, str(boxes.home)], capture_output=True, text=True,
                            encoding="utf-8", timeout=60)
    result = json.loads(answer.stdout)
    assert result["calls"] == [] and result["seconds"] < localbox.STOP_WAIT / 2, (result, answer.stderr)
    assert process.wait(5) is not None  # it did exit, by itself


@pytest.mark.posix_only
def test_a_browser_that_wont_close_is_ended_with_its_whole_group(boxes, tmp_path, monkeypatch):  # minor (b)
    monkeypatch.setattr(localbox, "STOP_WAIT", 0.5)
    folder = boxes.home / "sandboxes" / "pytest"
    (folder / "profile").mkdir(parents=True)
    pidfile = tmp_path / "helper.pid"
    script = ("import subprocess, sys, time\n"
              "helper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
              "open(sys.argv[1], 'w').write(str(helper.pid))\ntime.sleep(60)")
    leader = subprocess.Popen([sys.executable, "-c", script, str(pidfile), f"--user-data-dir={folder / 'profile'}"],
                              start_new_session=True)
    helper = 0
    try:
        monkeypatch.setitem(localbox._launched, leader.pid, leader)
        (folder / "browser.json").write_text(json.dumps({"pid": leader.pid, "binary": "x", "fresh": False}),
                                             encoding="utf-8")
        for _ in range(100):
            text = pidfile.read_text(encoding="utf-8") if pidfile.exists() else ""
            if text.isdigit():
                helper = int(text)
                break
            time.sleep(0.1)
        assert helper
        boxes.stop("aib-pytest")
        assert leader.poll() is not None
        for _ in range(50):
            if not platforms.pid_alive(helper):
                break
            time.sleep(0.1)
        assert not platforms.pid_alive(helper)  # its helper went with it
    finally:
        for pid in (helper, leader.pid):
            if pid:
                try:
                    os.kill(pid, 9)
                except OSError:
                    pass
        leader.wait()


def test_a_start_or_stop_waits_for_the_start_lock_as_long_as_its_holder_may_need(boxes, monkeypatch):  # minor (e), (f)
    for name in ("READY_TIMEOUT", "ANSWER_WAIT", "STOP_WAIT", "KILL_WAIT"):
        monkeypatch.setattr(localbox, name, 0.2)
    monkeypatch.setattr(localbox, "LOCK_MARGIN", 0.1)
    folder = boxes.home / "sandboxes" / "pytest"
    folder.mkdir(parents=True)
    held = platforms.lock_file(folder / "start.lock")
    try:
        for call in (lambda: boxes.start("pytest"), lambda: boxes.stop("aib-pytest")):
            started = time.monotonic()
            with pytest.raises(ChromeError, match="didn't finish"):
                call()
            assert 0.85 <= time.monotonic() - started < 5  # 4 x 0.2 + 0.1: the holder's worst case, and a margin
    finally:
        held.close()


def test_when_stop_cant_clear_a_held_profile_it_says_how_to_end_the_browser(boxes, monkeypatch):  # minor (d)
    folder = boxes.home / "sandboxes" / "pytest"
    (folder / "profile").mkdir(parents=True)

    def held(path, missing_ok=False):
        raise PermissionError("in use")

    monkeypatch.setattr(platforms, "unlink", held)
    with pytest.raises(ChromeError, match="Task Manager") as caught:
        boxes.stop("aib-pytest")
    assert platforms.command("stop pytest") not in str(caught.value)  # not "run ai-browser stop": just run


def test_two_spellings_of_one_home_are_one_home(tmp_path):  # minor (a)
    (tmp_path / "real").mkdir()
    symlink_or_skip(tmp_path / "real", tmp_path / "link")
    assert localbox.LocalSandboxes(tmp_path / "link").home == (tmp_path / "real").resolve()
