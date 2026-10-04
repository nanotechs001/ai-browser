"""AI Browser's window (app/window.py): which browser draws it, its exact command line, starting it and ending only
what it started. No test opens a visible window: the launch tests record Popen, and the one real launch (Task 13) is
headless."""

import subprocess
import sys

import pytest

from ai_browser.app import window
from ai_browser.chrome import chrome_binary

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")

MAC_BOTH = {"chrome": "/x/Google Chrome", "brave": "/x/Brave Browser"}
ALL_THREE = {"edge": "C:\\Edge\\msedge.exe", "chrome": "C:\\Chrome\\chrome.exe", "brave": "C:\\Brave\\brave.exe"}


def picked(setting, system, installed, default=None):
    found = window.pick(setting, system=system, installed=installed, os_default=default)
    return None if found is None else (found.browser.id, found.browser.binary, found.note)


def test_auto_skips_the_everyday_browser_on_macos():
    assert picked("auto", "darwin", MAC_BOTH, "brave") == ("chrome", "/x/Google Chrome", "")  # this Mac's case
    assert picked("auto", "darwin", MAC_BOTH, "chrome")[0] == "brave"
    assert picked("auto", "darwin", {"brave": "/x/Brave Browser"}, "brave")[0] == "brave"  # nothing else to use
    assert picked("auto", "darwin", MAC_BOTH, None)[0] == "chrome"


def test_auto_on_windows_is_edge_first_with_no_skip():
    assert picked("auto", "win32", ALL_THREE, "chrome")[0] == "edge"
    assert picked("auto", "win32", ALL_THREE, "edge")[0] == "edge"  # no skip there
    assert picked("auto", "win32", {"chrome": "C:\\Chrome\\chrome.exe", "brave": "C:\\Brave\\brave.exe"})[0] == "chrome"


def test_auto_on_linux_is_chrome_then_brave():
    assert picked("auto", "linux", {"chrome": "/usr/bin/google-chrome", "brave": "/usr/bin/brave"})[0] == "chrome"
    assert picked("auto", "linux", {"brave": "/usr/bin/brave"})[0] == "brave"


def test_a_choice_that_cant_be_used_falls_back_to_auto_with_a_note():
    assert picked("brave", "darwin", {"chrome": "/x/Google Chrome"}) == (
        "chrome", "/x/Google Chrome", "Brave isn't installed: the window uses Google Chrome. Change it in Settings.")
    found = picked("edge", "darwin", MAC_BOTH, "brave")
    assert found[0] == "chrome" and found[2] == ("Microsoft Edge draws the window only on Windows: the window uses "
                                                 "Google Chrome. Change it in Settings.")
    assert picked("brave", "darwin", MAC_BOTH, "brave") == ("brave", "/x/Brave Browser", "")  # the user's choice wins
    assert picked("chrome", "win32", ALL_THREE)[0] == "chrome"
    assert picked("nonsense", "darwin", MAC_BOTH, "brave")[0] == "chrome"  # an unknown setting is Auto
    assert picked("auto", "darwin", {}) is None and picked("chrome", "win32", {}) is None


def test_offered_choices_per_system():
    assert window.offered("darwin") == ("auto", "chrome", "brave") == window.offered("linux")
    assert window.offered("win32") == ("auto", "edge", "chrome", "brave")
    assert set(window.offered("win32")) == set(window.WINDOW_CHOICES)


def test_choices_name_auto_after_its_pick():
    assert window.choices(system="darwin", installed={"chrome": "/x/c"}, os_default="brave") == [
        {"id": "auto", "name": "Auto (Google Chrome)", "installed": True},
        {"id": "chrome", "name": "Google Chrome", "installed": True},
        {"id": "brave", "name": "Brave", "installed": False}]
    rows = window.choices(system="win32", installed=ALL_THREE)
    assert [(row["id"], row["name"]) for row in rows] == [("auto", "Auto (Microsoft Edge)"), ("edge", "Microsoft Edge"),
                                                          ("chrome", "Google Chrome"), ("brave", "Brave")]
    assert window.choices(system="darwin", installed={})[0] == {"id": "auto", "name": "Auto", "installed": False}


def test_the_command_line_is_exactly_this(tmp_path):
    profile = tmp_path / "home" / "app" / "window" / "chrome"
    url = "http://127.0.0.1:8792/open?code=abc"
    args = window.window_args("/x/Google Chrome", profile, url)
    assert args == ["/x/Google Chrome", f"--user-data-dir={profile}", f"--app={url}", "--no-first-run",
                    "--no-default-browser-check", "--disable-search-engine-choice-screen", "--window-size=1440,960",
                    "--autoplay-policy=no-user-gesture-required"]
    banned = ("--remote-debugging", "--enable-automation", "--load-extension", "--headless", "--user-agent",
              "--disable-infobars", "--silent-debugger-extension-api")
    assert not [arg for arg in args if arg.startswith(banned)]
    assert window.window_profile(tmp_path / "home", "brave") == tmp_path / "home" / "app" / "window" / "brave"


def test_detection_never_reads_this_computers_apps(monkeypatch):
    from ai_browser import browsers

    monkeypatch.delenv("AIB_CHROME_BINARY", raising=False)
    for system in (None, "darwin", "win32"):
        assert browsers.installed(system=system) == [], system
    assert browsers.os_default() is None and browsers.os_default(system="darwin") is None


def test_aib_chrome_binary_is_chromes_program(tmp_path, monkeypatch):
    program = tmp_path / "chrome-bin"
    program.write_bytes(b"")
    monkeypatch.setenv("AIB_CHROME_BINARY", str(program))
    found = window.pick("auto")  # nothing is installed: the conftest fixture keeps detection off this computer
    assert (found.browser.id, found.browser.name, found.browser.binary) == ("chrome", "Google Chrome", str(program))
    monkeypatch.setenv("AIB_CHROME_BINARY", str(tmp_path / "missing"))
    if sys.platform in ("darwin", "win32"):  # on Linux the PATH finders still look
        assert window.pick("auto") is None


CHROME_ROW = window.WindowBrowser("chrome", "Google Chrome", "/x/Google Chrome")
START = "http://127.0.0.1:8792/open?code=abc"


class FakeProcess:
    """A browser process that ignores terminate (as a hung one would), or one that has already exited."""

    def __init__(self, exited=False):
        self.pid = 4242
        self.calls = []
        self.returncode = 0 if exited else None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.calls.append("terminate")

    def kill(self):
        self.calls.append("kill")
        self.returncode = -9

    def wait(self, timeout=None):
        self.calls.append("wait")
        if self.returncode is None:
            raise subprocess.TimeoutExpired("browser", timeout)
        return self.returncode


@pytest.fixture
def recorded(monkeypatch):
    """Popen and subprocess.run recorded, nothing started; no browser runs on any profile."""
    seen = {"popen": [], "run": [], "process": FakeProcess()}

    def popen(args, **options):
        seen["popen"].append((list(args), options))
        return seen["process"]

    def run(args, **options):
        seen["run"].append(list(args))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(window.subprocess, "Popen", popen)
    monkeypatch.setattr(window.subprocess, "run", run)
    monkeypatch.setattr(window, "QUIT_WAIT", 0.01)
    monkeypatch.setattr(window.browsers, "running", lambda profile, system=None: False)
    return seen


def test_launch_starts_exactly_the_window_command(tmp_path, recorded):
    app = window.AppWindow(tmp_path / "home", CHROME_ROW)
    app.launch(START)
    [(args, options)] = recorded["popen"]
    profile = tmp_path / "home" / "app" / "window" / "chrome"
    assert args == window.window_args("/x/Google Chrome", profile, START)
    assert options["stdout"] == options["stderr"] == subprocess.DEVNULL and profile.is_dir()
    assert (app.id, app.name, app.note, app.handed_off) == ("chrome", "Google Chrome", "", False)


def test_a_browser_that_cannot_start_is_said_plainly(tmp_path, monkeypatch, recorded):
    def broken(args, **options):
        raise OSError("No such file or directory")

    monkeypatch.setattr(window.subprocess, "Popen", broken)
    with pytest.raises(window.WindowError, match="^AI Browser's window could not start: No such file or directory"):
        window.AppWindow(tmp_path / "home", CHROME_ROW).launch(START)


def test_close_asks_then_kills_what_it_started(tmp_path, recorded):
    app = window.AppWindow(tmp_path / "home", CHROME_ROW, system="darwin")
    app.launch(START)
    assert app.close() == ""
    assert recorded["process"].calls == ["terminate", "wait", "kill", "wait"] and recorded["run"] == []


def test_on_windows_close_is_a_click_on_its_x_first(tmp_path, recorded):
    edge = window.WindowBrowser("edge", "Microsoft Edge", "C:\\Edge\\msedge.exe")
    app = window.AppWindow(tmp_path / "home", edge, system="win32")
    app.launch(START)
    assert app.close() == ""
    assert recorded["run"] == [["taskkill", "/PID", "4242"]]  # no /F: Edge closes as if its × was clicked
    assert recorded["process"].calls == ["wait", "kill", "wait"]  # never terminate(): Windows counts that a crash


def test_a_failing_taskkill_still_ends_the_window(tmp_path, monkeypatch, recorded):  # Review Focus 5
    def missing(args, **options):
        raise FileNotFoundError(2, "The system cannot find the file specified", "taskkill")

    monkeypatch.setattr(window.subprocess, "run", missing)
    app = window.AppWindow(tmp_path / "home", CHROME_ROW, system="win32")
    app.launch(START)
    assert app.close() == "" and recorded["process"].calls == ["wait", "kill", "wait"]


def test_a_hand_off_ends_nothing(tmp_path, monkeypatch, recorded):
    monkeypatch.setattr(window.browsers, "running", lambda profile, system=None: True)  # left from a crashed run
    app = window.AppWindow(tmp_path / "home", CHROME_ROW, system="darwin")
    app.launch(START)
    assert len(recorded["popen"]) == 1  # still started: it hands its command line to the running browser
    assert app.handed_off and app.close() == ("AI Browser's window was opened by a browser already running on its "
                                              "profile: quit it yourself (⌘Q)")
    assert recorded["process"].calls == []
    other = window.AppWindow(tmp_path / "home", CHROME_ROW, system="win32")
    other.launch(START)
    assert other.close().endswith("quit it yourself (close its windows)") and recorded["run"] == []


def test_a_window_that_already_ended_is_left_alone(tmp_path, recorded):
    recorded["process"] = FakeProcess(exited=True)  # Ctrl-C reached the browser too
    app = window.AppWindow(tmp_path / "home", CHROME_ROW, system="darwin")
    app.launch(START)
    assert app.close() == "" and recorded["process"].calls == []


def test_the_profile_is_never_a_real_browsers_folder(tmp_path, monkeypatch, recorded):
    data = tmp_path / "Google" / "Chrome"
    data.mkdir(parents=True)
    monkeypatch.setattr(window.browsers, "all_data_dirs", lambda system=None, env=None: [data])
    with pytest.raises(window.WindowError, match="a browser's own data folder"):
        window.AppWindow(data / "inside", CHROME_ROW, system="darwin").launch(START)  # <data>/inside/app/window/…
    inside = window.AppWindow(tmp_path / "home", CHROME_ROW, system="darwin")
    monkeypatch.setattr(window.browsers, "all_data_dirs", lambda system=None, env=None: [inside.profile])
    with pytest.raises(window.WindowError, match="a browser's own data folder"):
        inside.launch(START)  # the profile is itself a real one
    assert recorded["popen"] == []


def test_the_default_launcher_picks_or_says_why(tmp_path, monkeypatch):
    monkeypatch.delenv("AIB_CHROME_BINARY", raising=False)
    if sys.platform in ("darwin", "win32"):  # on Linux the PATH finders may still find a browser
        with pytest.raises(window.WindowError, match="^AI Browser needs Google Chrome, Brave or Microsoft Edge"):
            window.default_launcher(tmp_path)("auto")  # nothing installed: the conftest fixture
    program = tmp_path / "chrome-bin"
    program.write_bytes(b"")
    monkeypatch.setenv("AIB_CHROME_BINARY", str(program))
    app = window.default_launcher(tmp_path)("brave")
    assert (app.id, app.browser.binary, app.profile) == ("chrome", str(program),
                                                         tmp_path / "app" / "window" / "chrome")
    if sys.platform in ("darwin", "win32"):
        assert app.note == "Brave isn't installed: the window uses Google Chrome. Change it in Settings."


@CHROME
async def test_the_real_window_connects_with_no_debugging_port_and_ends(fake_claude, tmp_path):
    import asyncio

    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer

    runner, _, _ = fake_claude
    home = tmp_path / "home"
    server = AppServer(home, AgentManager(home, claude=runner))
    url = await server.start()
    app = None
    try:
        start = f"{url}/open?code={server.new_launch_code()}"
        # Headless Chrome opens --app=<url> as the window would (measured by the plan's review): one page, so one
        # window socket. --headless=new is the test's only extra argument; the product never passes one.
        app = window.AppWindow(home, window.WindowBrowser("chrome", "Google Chrome", chrome_binary()),
                               extra_args=("--headless=new",))
        app.launch(start)
        for _ in range(200):
            if server.window_count >= 1:
                break
            await asyncio.sleep(0.1)
        assert server.window_count == 1  # AI Home's page, over http, with the window's cookie
        assert not (app.profile / "DevToolsActivePort").exists()  # no debugging port: nothing can drive it
        assert await asyncio.to_thread(app.close) == ""
        assert app.process.poll() is not None
    finally:
        if app is not None and app.process is not None and app.process.poll() is None:
            app.process.kill()
        await server.stop()
