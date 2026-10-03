"""What differs between macOS, Windows and Linux, tested on any OS through `system` and a fake `env`."""

import os
import sys
from pathlib import Path

import pytest

from ai_browser import platforms

WINDOWS_ENV = {"LOCALAPPDATA": "C:\\Users\\me\\AppData\\Local", "APPDATA": "C:\\Users\\me\\AppData\\Roaming",
               "ProgramFiles": "C:\\Program Files", "ProgramFiles(x86)": "C:\\Program Files (x86)"}


def test_browser_folders_for_each_system():
    home, support = Path.home(), Path.home() / "Library" / "Application Support"
    assert platforms.user_data_dir("chrome", "darwin") == support / "Google" / "Chrome"
    assert platforms.user_data_dir("brave", "darwin") == support / "BraveSoftware" / "Brave-Browser"
    local = "C:\\Users\\me\\AppData\\Local"
    assert platforms.user_data_dir("chrome", "win32", WINDOWS_ENV) == Path(local, "Google", "Chrome", "User Data")
    assert platforms.user_data_dir("brave", "win32", WINDOWS_ENV) == Path(local, "BraveSoftware", "Brave-Browser",
                                                                        "User Data")
    assert platforms.user_data_dir("chrome", "linux") == home / ".config" / "google-chrome"
    assert platforms.user_data_dir("brave", "linux") == home / ".config" / "BraveSoftware" / "Brave-Browser"
    with pytest.raises(ValueError):
        platforms.user_data_dir("firefox", "darwin")


def test_the_usual_install_places():
    assert platforms.browser_candidates("chrome", "darwin") == [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    assert platforms.browser_candidates("brave", "darwin") == [
        Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")]
    assert platforms.browser_candidates("chrome", "win32", WINDOWS_ENV) == [
        Path(root, "Google", "Chrome", "Application", "chrome.exe")
        for root in ("C:\\Program Files", "C:\\Program Files (x86)", "C:\\Users\\me\\AppData\\Local")]
    assert platforms.browser_candidates("brave", "win32", {"LOCALAPPDATA": "C:\\L"}) == [
        Path("C:\\L", "BraveSoftware", "Brave-Browser", "Application", "brave.exe")]
    assert platforms.browser_candidates("chrome", "linux") == []


def test_the_claude_desktop_folder():
    assert platforms.claude_desktop_dir("darwin") == Path.home() / "Library" / "Application Support" / "Claude"
    assert platforms.claude_desktop_dir("win32", WINDOWS_ENV) == Path("C:\\Users\\me\\AppData\\Roaming", "Claude")
    assert platforms.claude_desktop_dir("linux") == Path.home() / ".config" / "Claude"


def test_words_for_each_system():
    systems = ("darwin", "win32", "linux")
    assert [platforms.file_manager(s) for s in systems] == ["Finder", "File Explorer", "your file manager"]
    assert [platforms.this_computer(s) for s in systems] == ["this Mac", "this PC", "this computer"]
    assert [platforms.shortcut("⌘⇧Y", "Ctrl+Shift+Y", s) for s in systems] == ["⌘⇧Y", "Ctrl+Shift+Y", "Ctrl+Shift+Y"]


def test_the_defaults_are_read_at_call_time(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Elsewhere")
    assert platforms.this_computer() == "this PC"
    assert platforms.user_data_dir("brave") == Path("C:\\Elsewhere", "BraveSoftware", "Brave-Browser", "User Data")


def test_reveal_commands(monkeypatch):
    assert platforms.reveal_command("/Users/me/x", "darwin") == ["open", "-R", "/Users/me/x"]
    assert platforms.reveal_command("C:\\Users\\a b\\x", "win32") == 'explorer /select,"C:\\Users\\a b\\x"'
    assert platforms.reveal_command("C:\\Users\\José & Ana\\x", "win32") == 'explorer /select,"C:\\Users\\José & Ana\\x"'
    monkeypatch.setattr(platforms.shutil, "which", lambda name: "/usr/bin/xdg-open" if name == "xdg-open" else None)
    assert platforms.reveal_command("/home/me/x/extension", "linux") == ["xdg-open", "/home/me/x"]
    monkeypatch.setattr(platforms.shutil, "which", lambda name: None)
    assert platforms.reveal_command("/home/me/x/extension", "linux") is None


def test_reveal_says_whether_a_folder_window_could_open(monkeypatch, tmp_path):
    if platforms.reveal_command(str(tmp_path)) is None:
        pytest.skip("this system has no file manager command")
    started = []
    monkeypatch.setattr(platforms.subprocess, "Popen", lambda command, **options: started.append(command) or object())
    assert platforms.reveal(str(tmp_path)) is True and started == [platforms.reveal_command(str(tmp_path))]

    def cannot_start(command, **options):
        raise OSError("no file manager")

    monkeypatch.setattr(platforms.subprocess, "Popen", cannot_start)
    assert platforms.reveal(str(tmp_path)) is False


def test_windows_is_read_from_os_name():
    assert platforms.WINDOWS == (os.name == "nt") and platforms.O_BINARY == getattr(os, "O_BINARY", 0)


def test_replace_retries_a_held_file_on_windows_only(tmp_path, monkeypatch):
    real, failures, waits = platforms.os.replace, [], []

    def held_twice(src, dst):
        if len(failures) < 2:
            failures.append(src)
            raise PermissionError(13, "in use by another process")
        real(src, dst)

    (tmp_path / "a").write_bytes(b"new")
    monkeypatch.setattr(platforms.os, "replace", held_twice)
    monkeypatch.setattr(platforms.time, "sleep", waits.append)
    monkeypatch.setattr(platforms, "WINDOWS", True)  # only the retry loop changes: no Win32 call is made
    platforms.replace(tmp_path / "a", tmp_path / "b")
    assert (tmp_path / "b").read_bytes() == b"new" and waits == [0.05, 0.1]
    failures.clear()
    monkeypatch.setattr(platforms, "WINDOWS", False)
    (tmp_path / "a").write_bytes(b"again")
    with pytest.raises(PermissionError):
        platforms.replace(tmp_path / "a", tmp_path / "b")
    assert waits == [0.05, 0.1]  # elsewhere it fails at once, as before


def test_replace_gives_up_after_five_tries(tmp_path, monkeypatch):
    tries, waits = [], []

    def always_held(src, dst):
        tries.append(src)
        raise PermissionError(13, "in use by another process")

    monkeypatch.setattr(platforms.os, "replace", always_held)
    monkeypatch.setattr(platforms.time, "sleep", waits.append)
    monkeypatch.setattr(platforms, "WINDOWS", True)
    with pytest.raises(PermissionError):
        platforms.replace(tmp_path / "a", tmp_path / "b")
    assert len(tries) == 5 and waits == [0.05, 0.1, 0.2, 0.4]


def test_unlink_and_rmtree_wait_out_a_short_hold(tmp_path, monkeypatch):
    real_unlink, real_rmtree, holds = Path.unlink, platforms.shutil.rmtree, []

    def busy_unlink(self, missing_ok=False):
        if "unlink" not in holds:
            holds.append("unlink")
            raise PermissionError(13, "being scanned")
        return real_unlink(self, missing_ok=missing_ok)

    def busy_rmtree(path, *args, **kwargs):
        if "rmtree" not in holds:
            holds.append("rmtree")
            raise PermissionError(13, "in use")
        return real_rmtree(path, *args, **kwargs)

    (tmp_path / "file").write_bytes(b"x")
    (tmp_path / "folder" / "inside").mkdir(parents=True)
    monkeypatch.setattr(Path, "unlink", busy_unlink)
    monkeypatch.setattr(platforms.shutil, "rmtree", busy_rmtree)
    monkeypatch.setattr(platforms.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(platforms, "WINDOWS", True)
    platforms.unlink(tmp_path / "file")
    platforms.rmtree(tmp_path / "folder")
    platforms.unlink(tmp_path / "file", missing_ok=True)  # already gone: fine
    assert holds == ["unlink", "rmtree"]
    assert not (tmp_path / "file").exists() and not (tmp_path / "folder").exists()


def test_pid_alive():
    import subprocess

    assert platforms.pid_alive(os.getpid())
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=30)
    assert not platforms.pid_alive(child.pid)  # exited and waited for
    assert not platforms.pid_alive(0) and not platforms.pid_alive(-1)


def test_a_second_lock_on_the_same_file_waits_for_the_first(tmp_path):
    first = platforms.lock_file(tmp_path / "lock")
    assert first is not None
    assert platforms.lock_file(tmp_path / "lock") is None
    first.close()
    again = platforms.lock_file(tmp_path / "lock")
    assert again is not None
    again.close()


def test_a_lock_held_by_a_crashed_app_is_free_again(tmp_path):
    import subprocess
    import time

    code = ("import sys, time\nfrom ai_browser.platforms import lock_file\nheld = lock_file(sys.argv[1])\n"
            "print(held is not None, flush=True)\ntime.sleep(60)\n")
    child = subprocess.Popen([sys.executable, "-c", code, str(tmp_path / "lock")], stdout=subprocess.PIPE,
                             encoding="utf-8")
    try:
        assert child.stdout.readline().strip() == "True"
        assert platforms.lock_file(tmp_path / "lock") is None  # another process holds it
    finally:
        child.kill()  # like ending it in Task Manager: no close(), no unlock
        child.wait(timeout=10)
        child.stdout.close()
    again = None
    for _ in range(20):  # the OS releases a dead process's lock, on Windows maybe a moment later
        again = platforms.lock_file(tmp_path / "lock")
        if again is not None:
            break
        time.sleep(0.1)
    assert again is not None and (tmp_path / "lock").exists()  # the file left behind doesn't block the next start
    again.close()


def test_a_held_port_is_never_bound_twice():
    from ai_browser.live import _bind

    first = _bind("127.0.0.1", 0)
    first.listen()
    try:
        assert _bind("127.0.0.1", first.getsockname()[1]) is None
    finally:
        first.close()


def _sockets(socket_class):
    """live.py's view of the socket module, with another socket class in it."""
    import socket as real
    from types import SimpleNamespace

    return SimpleNamespace(socket=socket_class, AF_INET=real.AF_INET, SOCK_STREAM=real.SOCK_STREAM,
                           SOL_SOCKET=real.SOL_SOCKET, SO_REUSEADDR=real.SO_REUSEADDR,
                           SO_EXCLUSIVEADDRUSE=getattr(real, "SO_EXCLUSIVEADDRUSE", -5))


def test_windows_binds_ports_for_exclusive_use(monkeypatch):
    from ai_browser import live

    options = []

    class Recorder:
        def __init__(self, *args):
            pass

        def setsockopt(self, level, option, value):
            options.append((level, option, value))

        def bind(self, address):
            pass

        def close(self):
            pass

    sockets = _sockets(Recorder)
    monkeypatch.setattr(live, "socket", sockets)
    monkeypatch.setattr(platforms, "WINDOWS", True)  # only the socket option changes: no Win32 call is made
    assert isinstance(live._bind("127.0.0.1", 8770), Recorder)
    assert options == [(sockets.SOL_SOCKET, sockets.SO_EXCLUSIVEADDRUSE, 1)]  # and no SO_REUSEADDR


async def test_a_reserved_port_is_skipped_like_a_taken_one(monkeypatch):
    import socket as real

    from ai_browser import live

    probe = real.socket()
    probe.bind(("127.0.0.1", 0))
    reserved = probe.getsockname()[1]
    probe.close()

    class Reserving(real.socket):  # Hyper-V's reserved ranges answer WinError 10013, a PermissionError
        def bind(self, address):
            if address[1] == reserved:
                raise PermissionError(13, "forbidden by its access permissions (WinError 10013)")
            return super().bind(address)

    monkeypatch.setattr(live, "socket", _sockets(Reserving))
    assert live._bind("127.0.0.1", reserved) is None
    view = live.LiveView(ports=range(reserved, reserved + 20))
    url = await view.start()
    try:
        assert f":{reserved}/" not in url  # the next port was tried
    finally:
        await view.stop()


@pytest.mark.windows_only
def test_a_port_bind_holds_cant_be_taken_with_reuseaddr():
    import socket

    from ai_browser.live import _bind

    held = _bind("127.0.0.1", 0)
    held.listen()
    second = socket.socket()
    second.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        with pytest.raises(OSError):
            second.bind(("127.0.0.1", held.getsockname()[1]))
    finally:
        second.close()
        held.close()


async def test_the_claude_ai_skills_come_from_the_desktop_apps_folder(tmp_path, monkeypatch):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.engine import Engine

    synced = tmp_path / "appdata" / "Claude" / "local-agent-mode-sessions" / "skills-plugin" / "s1" / "p1" / "skills"
    (synced / "summarize").mkdir(parents=True)
    (synced / "summarize" / "SKILL.md").write_text("---\nname: summarize\ndescription: Sums things up\n---\nBody\n",
                                                   encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path / "user"))  # no personal skills or plugins from this machine
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    home = tmp_path / "home"
    engine, server = Engine(home=home), AppServer(home, AgentManager(home))
    monkeypatch.setattr(sys, "platform", "win32")  # %APPDATA%\Claude, where the Claude app keeps them on Windows
    for skills in (engine.catalog.all(), server._skills()):
        assert "anthropic-skills:summarize" in {skill.ref for skill in skills}


# platforms' own functions, taken when this file is imported, before any fixture runs. A conftest fixture may replace
# app_folders, launch_services_file or the registry readers to keep other tests off this computer (wave B does); the
# tests below check the real ones.
UNPATCHED = vars(platforms).copy()


def test_browser_folders_for_every_known_browser():
    rows = {row.id: row for row in platforms.KNOWN_BROWSERS}
    local = "C:\\Users\\me\\AppData\\Local"
    assert platforms.browser_data_dir(rows["chrome-canary"], "win32", WINDOWS_ENV) == Path(
        local, "Google", "Chrome SxS", "User Data")
    assert platforms.browser_data_dir(rows["brave-nightly"], "darwin") == Path.home().joinpath(
        "Library", "Application Support", "BraveSoftware", "Brave-Browser-Nightly")
    assert platforms.browser_data_dir(rows["arc"], "win32", WINDOWS_ENV) is None  # an MSIX package there
    assert platforms.browser_data_dir(rows["brave"], "linux") == platforms.user_data_dir("brave", "linux")
    assert platforms.browser_data_dir(rows["edge"], "linux") is None
    for name in ("brave", "chrome"):  # the older helper is a view of the same rows
        for system, env in (("darwin", None), ("win32", WINDOWS_ENV), ("linux", None)):
            assert platforms.browser_data_dir(rows[name], system, env) == platforms.user_data_dir(name, system, env)
    with pytest.raises(ValueError):
        platforms.user_data_dir("chrome-beta", "darwin")  # still only brave and chrome


def test_app_folders():
    app_folders = UNPATCHED["app_folders"]
    assert app_folders("darwin") == [Path("/Applications"), Path.home() / "Applications"]
    assert app_folders("win32", WINDOWS_ENV) == [
        Path("C:\\Program Files"), Path("C:\\Program Files (x86)"), Path("C:\\Users\\me\\AppData\\Local")]
    assert app_folders("win32", {"LOCALAPPDATA": "C:\\L", "ProgramFiles": ""}) == [Path("C:\\L")]
    assert app_folders("linux") == []


def test_lock_names_and_the_launch_services_file():
    assert [platforms.lock_name(s) for s in ("win32", "darwin", "linux")] == ["lockfile", "SingletonLock",
                                                                              "SingletonLock"]
    assert UNPATCHED["launch_services_file"]() == Path.home().joinpath(
        "Library", "Preferences", "com.apple.LaunchServices", "com.apple.launchservices.secure.plist")


def test_open_shared_lets_the_browser_replace_the_file(tmp_path):
    path, backup, new = tmp_path / "Local State", tmp_path / "Local State.bak", tmp_path / "Local State.new"
    path.write_bytes(b"old")
    new.write_bytes(b"new")
    with platforms.open_shared(path) as held:  # what ReplaceFile with a backup name does, while we read
        os.rename(path, backup)
        os.rename(new, path)
        assert held.read() == b"old"
    assert path.read_bytes() == b"new" and backup.read_bytes() == b"old"
    with pytest.raises(OSError):
        platforms.open_shared(tmp_path / "missing")
    if platforms.WINDOWS:  # a plain open doesn't share delete access: the browser's save would fail
        with open(path, "rb"):
            with pytest.raises(PermissionError):
                os.rename(path, tmp_path / "again")


def test_the_registry_readers_never_raise(monkeypatch):
    commands_of, progid_of = UNPATCHED["windows_browser_commands"], UNPATCHED["windows_https_progid"]
    commands, progid = commands_of(), progid_of()
    if platforms.WINDOWS:  # the real registry, read only
        assert isinstance(commands, list) and all(isinstance(command, str) for command in commands)
        assert progid is None or isinstance(progid, str)
        monkeypatch.setattr(platforms, "WINDOWS", False)
        commands, progid = commands_of(), progid_of()
    assert (commands, progid) == ([], None)  # the Mac has no winreg: it is imported only in the Windows branch


class FakeWinreg:
    """A stand-in for winreg: keys are {(root, path in lower case): {value name: value}}. Writing fails the test."""

    HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE, KEY_READ = "HKCU", "HKLM", 0x20019

    def __init__(self, keys, broken=()):
        self.keys = {(root, path.lower()): values for (root, path), values in keys.items()}
        self.broken = {(root, path.lower()) for root, path in broken}
        self.access = []

    class Key:
        def __init__(self, root, path):
            self.root, self.path = root, path

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def OpenKey(self, root, path, reserved=0, access=None):
        self.access.append(access)
        where = (root, path.lower())
        if where in self.broken:
            raise PermissionError(5, "Access is denied")
        if where not in self.keys and not any(r == root and p.startswith(where[1] + "\\") for r, p in self.keys):
            raise FileNotFoundError(2, "The system cannot find the file specified")
        return self.Key(root, where[1])

    def EnumKey(self, key, index):
        children = sorted({p[len(key.path) + 1:].split("\\")[0] for r, p in self.keys
                           if r == key.root and p.startswith(key.path + "\\")})
        if index >= len(children):
            raise OSError(259, "No more data is available")
        return children[index]

    def QueryValueEx(self, key, name):
        values = self.keys.get((key.root, key.path), {})
        if name not in values:
            raise FileNotFoundError(2, "The system cannot find the file specified")
        return values[name], 1

    def CreateKey(self, *args):
        pytest.fail("the registry was written: CreateKey")

    def SetValueEx(self, *args):
        pytest.fail("the registry was written: SetValueEx")

    def DeleteKey(self, *args):
        pytest.fail("the registry was written: DeleteKey")

    def DeleteValue(self, *args):
        pytest.fail("the registry was written: DeleteValue")


APP_PATHS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
HTTPS = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https"


def test_the_registry_readers_with_a_fake_winreg(monkeypatch):
    fake = FakeWinreg({
        ("HKCU", APP_PATHS + r"\chrome.exe"): {
            "": "C:\\Users\\Alex\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"},
        ("HKLM", APP_PATHS + r"\chrome.exe"): {"": "\"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\""},
        ("HKLM", APP_PATHS + r"\msedge.exe"): {"": 42},  # not a string: skipped
        ("HKLM", r"SOFTWARE\Clients\StartMenuInternet\Brave\shell\open\command"): {
            "": "\"C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe\""},
        ("HKLM", r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet\Brave\shell\open\command"): {
            "": "\"C:\\Program Files (x86)\\BraveSoftware\\Brave-Browser\\Application\\brave.exe\""},
        ("HKLM", r"SOFTWARE\Clients\StartMenuInternet\Locked\shell\open\command"): {"": "C:\\locked.exe"},
    }, broken=[("HKLM", r"SOFTWARE\Clients\StartMenuInternet\Locked\shell\open\command")])
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.setattr(platforms, "WINDOWS", True)
    commands_of, progid_of = UNPATCHED["windows_browser_commands"], UNPATCHED["windows_https_progid"]
    assert commands_of() == [
        "C:\\Users\\Alex\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe",
        "\"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\"",
        "\"C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe\"",
        "\"C:\\Program Files (x86)\\BraveSoftware\\Brave-Browser\\Application\\brave.exe\""]
    assert progid_of() is None  # neither key exists
    fake.keys[("HKCU", (HTTPS + r"\UserChoice").lower())] = {"ProgId": "ChromeHTML"}
    assert progid_of() == "ChromeHTML"
    fake.keys[("HKCU", (HTTPS + r"\UserChoiceLatest\ProgId").lower())] = {"ProgId": "BraveHTML"}
    assert progid_of() == "BraveHTML"  # Windows 11 25H2 no longer updates UserChoice
    assert fake.access and set(fake.access) == {FakeWinreg.KEY_READ}  # every key opened for reading only
