"""AI Browser's own app, read as files. There is no debugging and no DevTools anywhere in it, every window is locked
down, the bridge holds named actions only, and there is no npm package. A real Electron drives it in
test_desktop_electron.py, when there is one."""

import json
import re
from pathlib import Path

ELECTRON_DIR = Path(__file__).parents[1] / "src" / "ai_browser" / "desktop" / "electron"
SRC = Path(__file__).parents[1] / "src" / "ai_browser"
APP_FILES = ("package.json", "main.js", "preload.js", "policy.js", "line.js", "thispage.js", "thispage.ps1")
REFUSED_LIST = re.compile(r"const DEBUG_SWITCHES = \[([^\]]*)\];")
NEVER = ("openDevTools", "remote-debugging", "appendSwitch", "--inspect", "devTools: true", ".debugger",
         "nodeIntegration: true", "contextIsolation: false", "sandbox: false", "webSecurity: false",
         "allowRunningInsecureContent: true", "webviewTag: true", "nodeIntegrationInSubFrames: true", "openExternal",
         "ELECTRON_RUN_AS_NODE", "enableBlinkFeatures", "experimentalFeatures", "console.", "remote-allow-origins",
         "inspect-brk", "js-flags")


def text(name: str) -> str:
    return (ELECTRON_DIR / name).read_text(encoding="utf-8")


def test_the_app_never_turns_debugging_on():
    assert sorted(path.name for path in ELECTRON_DIR.iterdir() if not path.name.startswith(".")) == sorted(APP_FILES)
    for name in APP_FILES:
        source = REFUSED_LIST.sub("", text(name))  # policy.js names the debugging switches only to refuse them
        for word in NEVER:
            assert word not in source, (name, word)
    refused = set(re.findall(r'"([a-z-]+)"', REFUSED_LIST.search(text("policy.js")).group(1)))
    assert {"remote-debugging-port", "remote-debugging-pipe", "inspect", "inspect-brk", "js-flags"} <= refused
    # A test's Electron only: Electron's own default app loaded this folder. app.isPackaged alone only compares the
    # program's name with "electron", and the Mac app's program keeps Electron's name (Contents/MacOS/Electron).
    assert "\nconst UNPACKAGED = !app.isPackaged && process.defaultApp === true;\n" in text("main.js")
    assert re.search(r"if \(!UNPACKAGED && policy\.DEBUG_SWITCHES\.some\(\(name\) => "
                     r"app\.commandLine\.hasSwitch\(name\)\)\) \{\n  app\.exit\(1\);[^\n]*\n\} else \{\n  main\(\);\n"
                     r"\}\n$", text("main.js"))  # the packaged app's very first step
    assert "if (given && UNPACKAGED) return given.slice(PROFILE.length);" in text("main.js")


def test_every_window_is_locked_down():
    main = text("main.js")
    web = re.search(r"const WEB = Object\.freeze\(\{(.*?)\n\}\);", main, re.S).group(1)
    for setting in ("contextIsolation: true", "sandbox: true", "nodeIntegration: false",
                    "nodeIntegrationInWorker: false", "nodeIntegrationInSubFrames: false", "webSecurity: true",
                    "allowRunningInsecureContent: false", "webviewTag: false", "devTools: false",
                    "navigateOnDragDrop: false"):
        assert setting in web, setting
    assert main.count("new BrowserWindow(") == 1 and "webPreferences: { ...WEB }" in main  # every one: makeWindow
    for needed in ('contents.setWindowOpenHandler(() => ({ action: "deny" }))',
                   '["will-navigate", "will-frame-navigate", "will-redirect"]',
                   "policy.mayNavigate(details.url, own, details.isMainFrame, kindOf(contents))",
                   "setPermissionRequestHandler",
                   "policy.mayRequest(permission, details, own)", "setPermissionCheckHandler",
                   "setDevicePermissionHandler(() => false)", '"will-download"', '"will-attach-webview"',
                   "requestSingleInstanceLock()", 'app.on("web-contents-created"', "policy.startOrigin(message.open)",
                   'title: "AI Browser chat", alwaysOnTop: true',
                   'win.on("close", (event) => { // closing it hides it'):
        assert needed in main, needed


def test_the_bridge_holds_named_actions_only():
    preload, main = text("preload.js"), text("main.js")
    assert preload.count("exposeInMainWorld(") == 1
    assert 'contextBridge.exposeInMainWorld("aib", Object.freeze(bridge));' in preload
    assert 'const ACTIONS = ["chat", "thisPage"];' in preload
    assert 'const ACTIONS = new Map([["chat", chatAction], ["thisPage", thisPageAction]]);' in main
    assert "return handler(event.sender, ...args);" in main
    asks = re.search(r"function thisPageAction\(sender\) \{\n(.*?)\n\}\n", main, re.S).group(1)
    assert 'if (!chat || sender !== chat.webContents || !chat.isVisible()) return { state: "hidden" };' in asks
    assert "if (!given || !UNPACKAGED) return thispage.run;" in main  # the fake page: a test's Electron only
    assert "ipcRenderer.invoke(`aib:${name}`, ...args)" in preload
    assert re.findall(r'require\("([^"]+)"\)', preload) == ["electron"]  # a sandboxed preload: the bridge alone
    assert "frame !== event.sender.mainFrame || policy.originOf(frame.url) !== own" in main


def test_no_npm_package_at_run_time():
    package = json.loads(text("package.json"))
    assert package["main"] == "main.js" and package["productName"] == "AI Browser" and package["private"] is True
    assert not {"dependencies", "devDependencies", "optionalDependencies", "scripts"} & set(package)
    for name in ("main.js", "preload.js", "policy.js", "line.js", "thispage.js"):
        modules = set(re.findall(r'require\("([^"]+)"\)', text(name)))
        assert modules <= {"electron", "node:fs", "node:net", "node:path", "node:child_process", "./policy.js",
                           "./line.js", "./thispage.js"}, (name, modules)
    # thispage.js alone runs a program: its one fixed command, with execFile, never through a shell
    assert set(re.findall(r'require\("([^"]+)"\)', text("thispage.js"))) == {"node:child_process", "node:path"}
    assert not [name for name in ("main.js", "preload.js", "policy.js", "line.js") if "child_process" in text(name)]
    reader = text("thispage.js")
    assert "execFile(file, args," in reader and "shell: false" in reader and "windowsHide: true" in reader
    for never in ("exec(", "execSync", "spawn", "fork(", "shell: true"):
        assert never not in reader, never


def test_the_windows_script_only_reads_the_front_brave_window():  # Safety: UI Automation only reads
    script = text("thispage.ps1")
    for needed in ("Get-Process -Name 'brave'", "MainWindowHandle", "AutomationElement]::FromHandle",
                   "ControlType]::Edit", "ValuePattern]::Pattern", ".Current.Name", "LastIndexOf(' - Brave')",
                   "ConvertTo-Json", "state = 'ok'", "state = 'closed'", "state = 'nowindow'", "state = 'failed'",
                   "-eq 'OmniboxViewViews'", "ControlType]::Document", "state = 'unknown'", "ControlViewWalker"):
        assert needed in script, needed
    # the address bar is Chromium's own edit box, found in the window's frame: nothing under a page (a Document),
    # whose fields could carry any name, is ever searched or read (fix pass 2, I5)
    for never in ("FindFirst(", "FindAll(", "TreeScope]::Descendants", "TreeScope]::Subtree"):
        assert never not in script, never
    assert script.index("ControlType]::Document") < script.index("-eq 'OmniboxViewViews'")
    for never in ("InvokePattern", "SendKeys", "SetFocus", "SetValue", "Start-Process", "Invoke-Expression", "iex ",
                  "Invoke-WebRequest", "DownloadString", "-TypeDefinition", "Stop-Process", "Click", "param(",
                  "$args", "$env:", "Read-Host", "Set-Item", "New-Item", "Remove-Item", "Out-File"):
        assert never not in script, never


def test_the_menu_bar_icon_closing_and_quitting():  # Review Focus 4
    main = text("main.js")
    for item in ('label: "Open AI Browser"', 'label: "Show chat", click: () => showChat()', 'label: "Quit"'):
        assert item in main, item
    assert "policy.moveShortcut(globalShortcut, shortcut, value, toggleChat)" in main  # ⌥Space: the chat
    assert "function toggleMain()" not in main
    assert 'win.on("close", (event) => {' in main and "win.hide();" in main  # closing hides it
    assert 'send({ type: "quit" })' in main  # Quit tells the engine
    assert re.search(r"\}, \(\) => \{\n    clearTimeout\(waiting\);\n    noEngine\(\);",
                     main)  # the line's end (the engine gone) quits the app: test_desktop_js runs it
    assert main.count("new Notification(") == 1 and "policy.notice(message)" in main  # the engine's words only
    assert "if (UNPACKAGED) return;" in main  # a test's Electron never adds a Start menu entry


def test_staging_copies_exactly_the_apps_files(tmp_path):
    from ai_browser.desktop.stage import APP_FILES as STAGED
    from ai_browser.desktop.stage import ELECTRON, ICON, part_hash, stage_app

    assert STAGED == APP_FILES and ELECTRON == ELECTRON_DIR and ICON == SRC / "app" / "ui" / "icon.png"
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "old.js").write_text("// from before", encoding="utf-8")
    stage_app(tmp_path / "app")
    assert sorted(path.name for path in (tmp_path / "app").iterdir()) == sorted([*APP_FILES, "icon.png"])
    assert (tmp_path / "app" / "icon.png").read_bytes() == ICON.read_bytes()
    assert part_hash() == part_hash() and part_hash(b"x") != part_hash()


def test_the_product_never_passes_a_debugging_switch():
    from ai_browser.desktop import launch

    mac = launch.mac_command(Path("/x/AI Browser.app"), Path("/t/aib-1/line"))
    windows = launch.windows_command(Path("/x/AI Browser/AI Browser.exe"))
    assert mac == ["open", "-n", "-W", "-a", str(Path("/x/AI Browser.app")), "--args",
                   f"--aib-line={Path('/t/aib-1/line')}"]
    assert windows == [str(Path("/x/AI Browser/AI Browser.exe"))]
    banned = ("--remote-debugging", "--inspect", "--remote-allow-origins", "--js-flags", "--enable-logging",
              "--auto-open-devtools", "--user-data-dir", "--load-extension", "--aib-fake-page", "--aib-profile")
    assert not [arg for arg in mac + windows if arg.startswith(banned)]
    for path in sorted((SRC / "desktop").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for word in ("remote-debugging", "--inspect", "ELECTRON_RUN_AS_NODE", "openDevTools", "aib-fake-page"):
            assert word not in source, (path.name, word)


def test_the_readme_explains_the_app():
    text = " ".join((SRC.parents[1] / "README.md").read_text(encoding="utf-8").split())
    for needed in ("### AI Browser's own app (a menu-bar icon, a shortcut and notifications)",
                   "uv run ai-browser doctor --setup", "Electron 44.5.1", "Nothing is downloaded until you type `y`",
                   "`SHASUMS256.txt`", "nothing is kept", "~/.ai-browser/desktop/", "signed on your Mac, ad hoc",
                   "Running it needs no Node.js", "**Closing the window hides it.**", "**Quit**",
                   "Settings → AI Browser app", "Press it once", "\"An agent is waiting for you\"",
                   "Never a message's text or a page's", "the Start menu", "keeps Electron's icon in File Explorer",
                   "AIB_TEST_ELECTRON", "It has no debugging port and no DevTools"):
        assert needed in text, needed


def test_a_windows_api_this_electron_may_lack_never_stops_the_start():
    # begin() adds the Start menu entry first on Windows: a call that throws there would end every start. The toast
    # activator's setter can't be confirmed for Electron 44, so it runs only where it exists (the entry carries the
    # same CLSID either way).
    entry = re.search(r"function startMenuEntry\(\) \{\n(.*?)\n\}\n", text("main.js"), re.S).group(1)
    assert 'if (typeof app.setToastActivatorCLSID === "function") app.setToastActivatorCLSID(TOAST_CLSID);' in entry
    assert entry.count("app.setToastActivatorCLSID(") == 1 and "toastActivatorClsid: TOAST_CLSID" in entry
