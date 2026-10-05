"""`ai-browser app` with AI Browser's own app (app/run.py).
- It opens the app when the app is set up.
- It opens a browser window when the app isn't set up, with --window, or when the app can't start. In that last
  case it says why, and keeps the reason for Settings.
- Quit in the app ends everything, and so does Ctrl-C.
The app is a fake (tests/fake_desktop.py), and so is the browser window (tests/fake_window.py)."""

import asyncio

from fake_desktop import FakeDesktop
from fake_window import SocketWindow
from test_app_run import quiet, servers  # noqa: F401  (a fixture)


async def test_the_app_opens_and_its_quit_ends_everything(fake_claude, tmp_path, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    app, lines, asked, given = FakeDesktop(servers=servers), [], [], []

    async def ready(url, opened):
        assert opened is app and servers[0].desktop is app
        app.quits()  # Quit, from the menu-bar icon

    def desktop(home, shortcut):
        given.append(shortcut)
        return app

    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=ready, out=lines.append,
                                              launcher=asked.append, desktop=desktop), 60)
    assert code == 0 and asked == [] and app.closed  # no browser window, and the app was told to go
    assert given == ["Alt+Space"]  # the shortcut from Settings, for the app to hold as it starts
    assert app.launched[0].startswith(servers[0].url + "/open?code=")
    assert run.app_text() in lines and run.APP_ENDED not in lines
    assert servers[0].window_info["using"] == "desktop"


async def test_ctrl_c_quits_the_app(fake_claude, tmp_path, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    app, stop = FakeDesktop(servers=servers), asyncio.Event()
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=lambda url, opened: stop.set(),
                                              stop=stop, out=quiet, desktop=lambda home, shortcut: app), 60)
    assert code == 0 and app.closed and not app.quit_by_user


async def test_the_app_ending_by_itself_ends_the_run_and_says_so(fake_claude, tmp_path, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    app, lines = FakeDesktop(servers=servers), []
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, out=lines.append,
                                              ready=lambda url, opened: app.quits(by_user=False),
                                              desktop=lambda home, shortcut: app), 60)
    assert code == 0 and run.APP_ENDED in lines


async def test_before_the_app_is_set_up_a_browser_window_opens_and_offers_it(fake_claude, tmp_path, servers,
                                                                              monkeypatch):
    from ai_browser.app import run
    from ai_browser.desktop.release import ASSETS, SETUP_COMMAND

    runner, _, _ = fake_claude
    monkeypatch.setattr(run, "asset_for", lambda system=None, machine=None: ASSETS[0])  # a computer the app runs on
    window, lines, stop = SocketWindow(servers), [], asyncio.Event()
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=lambda url, opened: stop.set(),
                                              stop=stop, out=lines.append, launcher=lambda setting: window), 60)
    assert code == 0 and window.closed and servers[0].desktop is None  # default_desktop: none (conftest)
    printed = "\n".join(lines)
    assert run.ready_text() in printed and f"run `{SETUP_COMMAND}` once" in printed


async def test_an_app_that_cant_start_leaves_a_browser_window_and_the_reason(fake_claude, tmp_path,
                                                                             servers):  # Review Focus 2
    from ai_browser.app import run
    from ai_browser.desktop import layout
    from ai_browser.desktop.launch import DesktopError

    runner, _, _ = fake_claude
    home, window, lines, stop = tmp_path / "home", SocketWindow(servers), [], asyncio.Event()
    broken = FakeDesktop(launch_error=DesktopError("AI Browser's app could not start: test"))
    code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=lambda url, opened: stop.set(), stop=stop,
                                              out=lines.append, launcher=lambda setting: window,
                                              desktop=lambda home, shortcut: broken), 60)
    assert code == 0 and window.urls and servers[0].desktop is None
    assert "AI Browser's app could not start: test. AI Browser opens in a browser window this time." in lines
    assert layout.problem(home) == "AI Browser's app could not start: test"  # Settings shows it
    stop = asyncio.Event()
    good = FakeDesktop(servers=servers)
    assert await asyncio.wait_for(run.run_app(home, claude=runner, ready=lambda url, opened: stop.set(), stop=stop,
                                              out=quiet, desktop=lambda home, shortcut: good), 60) == 0
    assert layout.problem(home) == ""  # the next good start forgets it


async def test_window_asks_for_a_browser_window_for_this_run(fake_claude, tmp_path, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    asked, window, stop = [], SocketWindow(servers), asyncio.Event()

    def desktop(home, shortcut):
        asked.append(home)
        return FakeDesktop(servers=servers)

    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=lambda url, opened: stop.set(),
                                              stop=stop, out=quiet, window_browser="chrome",
                                              launcher=lambda setting: window, desktop=desktop), 60)
    assert code == 0 and asked == [] and window.urls


def test_the_app_texts_say_how_to_stop_on_each_computer(tmp_path):
    from ai_browser.app.run import app_text, setup_hint

    mac, windows = app_text("darwin"), app_text("win32")
    assert mac == ("AI Browser is open as its own app: AI Home shows every agent, tab and skill.\n"
                   "Closing its window keeps it running in the menu bar. To stop it, press ⌘Q or choose Quit from its "
                   "menu-bar icon, or press Ctrl-C here.")
    assert "by the clock" in windows and "⌘" not in windows and "Ctrl-C here" in windows
    assert setup_hint(tmp_path, "linux", "x86_64") == ""  # where the app doesn't run, nothing is offered
    assert setup_hint(tmp_path, "darwin", "arm64") == ("\nAI Browser can run as its own app, with a shortcut and "
                                                       "notifications: run `uv run ai-browser doctor --setup` once.")
