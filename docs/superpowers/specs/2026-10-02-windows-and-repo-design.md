# Windows support and the private GitHub repo

Date: 2026-10-02.

Status: the user approved the design in chat and said 'proceed build'; this spec was written and reviewed by agents without a user review round.

**The user chose**, among the plans for this round:
- **Windows:** "Private GitHub repo". Make the project Windows-ready, then put it in a private GitHub repo that the
  Windows laptop clones.
- **Browsing:** "My everyday browser", which is Brave, driven through Brave's own remote-debugging switch. The AI's tabs
  are put in tab groups by the Brain watcher extension the user already loaded; there is no new extension. Without
  the watcher, the AI's tabs go in their own Brave window.
- **Voice input:** "On-device Whisper, English" (faster-whisper `base.en`, about 142 MB, downloaded only after the user
  clicks Download).
- **Visuals:** "Yes, both" (the particle brain and the SVG chibi workers).
- The user then said "yeah then proceed build".

**This is the last of five sub-projects in this round.** The other four are safe-browsing, everyday-brave,
mission-visuals and voice-input. Their specs sit beside this one in `docs/superpowers/specs/`. They are built in waves:
safe-browsing and mission-visuals (wave 1), then everyday-brave and voice-input (wave 2), then this one (wave 3). This
one runs last, so it also covers their new code (Decision 18). Those specs already write their new Python the
Windows-ready way (encodings named, one pid helper, no "this Mac" outside the setup page), as the safe-browsing spec's
last section, **Coordination with the other four specs**, asks; the sweep checks it and fixes what slipped.

**Builds on:**
- the engine and own-Chrome mode;
- the AI Browser app, AI Home, the Brain and Mission Control;
- the investigation of 2026-10-02 (the `windows` findings), which simulated a Windows import and probed the extension-ID
  algorithm.

**Line numbers** (`file.py:12`) are from the baseline commit `1974d2d`. The four sub-projects built before this one move
some of them, so the plan finds each place again by its name.

## Goal and success criteria

The project runs natively on the user's Windows laptop (Windows 10 22H2 or Windows 11, x64), from a private GitHub repo,
with the same safety promises as on the Mac. The Mac keeps working exactly as it does now.

Success means:
1. **Every command starts on Windows:** `mcp`, `app` (with everyday-Brave's `--browser`), `doctor`, `doctor --own`
   (everyday-Brave's name for `doctor --chrome`, which stays), `doctor --setup` (new), `bench`, `live`, `build` and
   `stop`. Today only `build` and `stop` survive the import.
2. **AI Browser opens on Windows:**
   - `ai-browser app` finds Google Chrome and starts it on its own profile;
   - the setup steps talk about File Explorer and Windows keys;
   - after **Load unpacked**, the setup page says **All set**. That proves the Windows extension ID is right.
3. **Brave on Windows:**
   - the Brain watcher in Brave connects, because its ID is right too;
   - everyday-Brave mode finds Brave's profile folder without `AIB_CHROME_DIR`.
4. **Claude Code on Windows:**
   - agents and the Brain's calls run through the native `claude.exe`;
   - an npm `claude.cmd` is refused with a plain message;
   - closing the app leaves no Claude Code process, and no ai-browser MCP process, behind.
5. **The work folder is safe on Windows:**
   - `read_file` and `write_file` never follow a symbolic link, a junction or a WSL link;
   - a name Windows can't hold (`CON`, `a:b`, `x?`) is refused with a plain message.
6. **Text keeps its characters** without `PYTHONUTF8`:
   - page reads and the setup page show `…`, `•••` and `—` correctly;
   - saving a workflow or skill with `→`, an emoji or CJK text works.
7. **Ports:** two ai-browser processes never hold the same port.
8. **Tests:**
   - the suite passes in a manually started GitHub Actions run on `windows-latest`, and on `macos-latest` when asked;
   - every test that can't run on Windows is skipped with a reason, never silently.
9. **The repo:**
   - a private `nanotechs001/ai-browser` exists only after the user says yes in chat;
   - nothing personal is tracked unless the user chose to keep it;
   - the README has the Windows steps.
10. **The Mac is unchanged:** the full suite passes on the Mac as before, and the app behaves the same. Only a few
    words change, such as "this computer" in the extension pages (Decision 11).
11. **The other four sub-projects' code** passes the same portability checks.

## What the user sees

### On the Mac

- **Nothing changes** in how anything works.
- **New: `uv run ai-browser doctor --setup`.** A quick check that needs no Docker. It never opens a DevTools
  connection, so no browser asks Allow:
  ```
  ✓ Python      3.12.12
  ✓ Claude Code /Users/you/.local/bin/claude
  ✓ Chrome      /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
  ✓ Brave       /Applications/Brave Browser.app/Contents/MacOS/Brave Browser
  ✓ everyday    Brave: profile folder found; remote debugging is on
  ✓ ports       app 8792-8811 and live view 8770-8790 have free ports
  - Docker      not checked here: run `uv run ai-browser doctor`
  ```
- **The repo question.** Before any push, the main session asks the user in chat (Decision 17):
  - whether to create the private repo;
  - what to do with `docs/google-flights-cgy-mnl.jpg`.

### On GitHub (only after the user says yes)

- **A private repo, `nanotechs001/ai-browser`**, with the code, the specs and the README.
- **An Actions tab with one workflow, "tests":**
  - it runs only when the user clicks **Run workflow**;
  - it offers a choice of system: `windows` (the default), `macos` or `both`;
  - it never runs on its own, on a push or on a pull request.

### On the Windows laptop

The README's new **Windows** section walks through it. In PowerShell:

1. **Tools, once each.** Each line installs one tool; Windows may ask for permission for some of them.
   ```powershell
   winget install --id Git.Git -e
   winget install --id astral-sh.uv -e
   winget install --id GitHub.cli -e
   winget install --id Google.Chrome -e
   winget install --id Brave.Brave -e
   irm https://claude.ai/install.ps1 | iex      # Claude Code, the native claude.exe
   ```
   Then open a new PowerShell window, so the new commands are on PATH.
2. **Sign in, yourself:**
   - `gh auth login`, for the private repo;
   - `claude` once, to log in to Claude Code in the browser.
3. **The code**, in a short folder outside OneDrive:
   ```powershell
   git clone https://github.com/nanotechs001/ai-browser.git C:\dev\ai-browser
   cd C:\dev\ai-browser
   uv sync                        # Python 3.12 from .python-version; uv fetches it once
   uv run ai-browser doctor --setup
   ```
4. **Claude Code's tools:**
   ```powershell
   claude mcp add ai-browser --scope user -e PYTHONUTF8=1 -- uv run --directory C:\dev\ai-browser ai-browser mcp
   ```
5. **AI Browser:** `uv run ai-browser app`.
   - The setup page and `chrome://extensions` open, and File Explorer shows the `extension` folder, selected.
   - The user drags that folder onto the page, or clicks **Load unpacked** and pastes the path into the address bar
     at the top of the folder window.
   - The page then says **All set**. The chat shortcut is **Ctrl+Shift+Y**.
   - **Google sign-in:** sites can see that AI Browser is automated, and Google refuses to sign in there. For Google
     work, use your everyday Brave (step 6), chosen before the task (the safe-browsing spec).
6. **Brave, once, after step 5** (the first `ai-browser app` makes the watcher's folder):
   - open `brave://extensions`, turn on **Developer mode**, click **Load unpacked** and pick
     `%USERPROFILE%\.ai-browser\app\watcher`;
   - for the everyday-Brave mode, open `brave://inspect/#remote-debugging` and tick **Allow remote debugging for
     this browser instance**. The README repeats the everyday-Brave spec's warning here: while the switch is on, any
     program on this PC can reach your Brave, so untick it when agents aren't working.
7. **Optional, for the sandbox and the shell tool:**
   - run `wsl --install` and reboot;
   - run `winget install --id Docker.DockerDesktop -e`;
   - start Docker Desktop (WSL 2 backend, Linux containers);
   - then run `uv run ai-browser build` and `uv run ai-browser doctor`.
8. **Optional, for voice input:**
   - run `uv sync --extra voice` (the speech packages; plain `uv sync` removes them again, so keep the flag);
   - allow desktop apps to use the microphone (Settings → Privacy & security → Microphone);
   - the voice model itself (148 MB, the size the **Download** button shows; the "about 142 MB" quoted when you chose
     it is the same files counted in MiB) is downloaded from inside the app, only after you click **Download**.

**Troubleshooting**, also in the README:
- **"no free port":**
  - Hyper-V or Docker may have reserved the port range;
  - `netsh interface ipv4 show excludedportrange protocol=tcp` shows the reserved ranges.
- **"Claude Code was found as claude.cmd":** install the native Claude Code (step 1), or set `AIB_CLAUDE` to the full
  path of `claude.exe`.
- **Chrome in an unusual place:** set `AIB_CHROME_BINARY` to the full path of `chrome.exe`.
- **`~` in PowerShell:** native programs don't expand it. Use `$HOME` or `$env:USERPROFILE`.

## Decisions

### 1. One module holds the OS facts: `platforms.py`

**New file: `src/ai_browser/platforms.py`.** It holds:
- **Pure functions.** Each takes `system: str | None = None` and `env: Mapping | None = None`. `None` means
  `sys.platform` (`"darwin"`, `"win32"` or `"linux"`) and `os.environ`, read at call time. So a test passes `system`,
  or monkeypatches `sys.platform` as the everyday-brave tests do, and each function is testable on the Mac for any OS:
  - `user_data_dir(browser) -> Path`, where browser is `"chrome"` or `"brave"`:

    | | Chrome | Brave |
    |---|---|---|
    | macOS | `~/Library/Application Support/Google/Chrome` | `~/Library/Application Support/BraveSoftware/Brave-Browser` |
    | Windows | `%LOCALAPPDATA%\Google\Chrome\User Data` | `%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data` |
    | Linux | `~/.config/google-chrome` | `~/.config/BraveSoftware/Brave-Browser` |

    Note the `User Data` folder on Windows: Chrome and Brave write `DevToolsActivePort` there.

    The everyday-brave spec lists the same folders in `chrome.own_browser_dirs()` (Brave first). To keep one source,
    `own_browser_dirs()` keeps its name, order and behaviour, and takes its paths from `user_data_dir`.
  - `browser_candidates(browser) -> list[Path]`. These are the usual install places:
    - **macOS:** `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` and
      `/Applications/Brave Browser.app/Contents/MacOS/Brave Browser`.
    - **Windows:** under `%ProgramFiles%`, `%ProgramFiles(x86)%` and `%LOCALAPPDATA%`, in that order, the files
      `Google\Chrome\Application\chrome.exe` and `BraveSoftware\Brave-Browser\Application\brave.exe`.
  - `claude_desktop_dir() -> Path`. This is where the Claude desktop app keeps the skills synced from claude.ai:
    - macOS: `~/Library/Application Support/Claude`;
    - Windows: `%APPDATA%\Claude`;
    - Linux: `~/.config/Claude`.
  - `file_manager() -> str`: "Finder", "File Explorer", or "your file manager".
  - `this_computer() -> str`: "this Mac", "this PC", or "this computer". The Python texts that say "this Mac" today
    use it (Decision 11).
  - `shortcut(mac: str, other: str) -> str`, for wording such as `⌘⇧Y` against `Ctrl+Shift+Y`.
  - `reveal_command(path) -> list[str] | str | None`, the command that shows a folder, selected:
    - **macOS:** `["open", "-R", path]`;
    - **Windows:** the string `explorer /select,"<path>"`. It is a string because explorer.exe parses its own command
      line, and a list breaks on spaces in the user name. A path can't contain `"` on Windows.
    - **Linux:** `["xdg-open", <parent>]` when `xdg-open` is on PATH.
- **Functions that use the real OS.** These branch on `WINDOWS = os.name == "nt"`, read at call time, never on
  `sys.platform`. A test may patch `WINDOWS` only where no Win32 API is called (a retry loop, a socket option, a wait),
  so Windows APIs never run on the Mac by accident. Their Win32 calls go through
  `ctypes.WinDLL("kernel32", use_last_error=True)` and read errors with `ctypes.get_last_error()`, because a bare
  `GetLastError()` through ctypes can read a stale value:
  - `reveal(path) -> bool`: True when the reveal command was started.
  - `pid_alive(pid) -> bool` (Decision 7).
  - `lock_file(path) -> IO | None` (Decision 6).
  - `replace(src, dst)`, `unlink(path, missing_ok=False)` and `rmtree(path)` (Decision 12).
  - `KillOnCloseJob` (Decision 10).
  - `O_BINARY = getattr(os, "O_BINARY", 0)`.

**Why one module:**
- the POSIX code paths stay as they are;
- the OS facts (folders, names, wording, Win32 calls) are in one file that the Mac suite tests with
  `system="win32"`. Only `winfs.py` (Decision 2) and `claudecli.py` (Decision 10) add more Windows code;
- a guard test (Decision 16) forbids macOS-only paths anywhere else, so new code can't add them again.

### 2. The work folder on Windows (`workfs.py`)

**Today:** `workfs.py:17` reads `os.O_DIRECTORY` and `os.O_NOFOLLOW` at import, and Windows Python has neither. The
open path (`workfs.py:63-99`) also needs `dir_fd=`, `O_NONBLOCK` and `os.set_blocking`, which Windows lacks.

**Change:**
- **Imports work everywhere:**
  `_FOLDER = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)`.
- **`WorkDir._open` picks a path:**
  - **POSIX:** the current code, unchanged.
  - **Windows:** `winfs.open_in(root, folders, name, writing) -> int`, from a new module.
- **New file: `src/ai_browser/winfs.py`.** It uses ctypes and imports on any OS; it touches `ctypes.windll` only
  inside its functions. Its steps:
  1. **Names.** Each part of the path must be a name Windows can hold. Otherwise `PathError(f"{path}: not a valid
     file name on Windows")`. Refused:
     - the characters `< > : " / \ | ? *` and control characters (`:` also rules out alternate data streams);
     - a trailing dot or space;
     - the device names Python 3.13's `ntpath.isreserved` knows: `CON`, `PRN`, `AUX`, `NUL`, `CONIN$`, `CONOUT$`,
       `COM1`-`COM9`, `COM¹`-`COM³`, `LPT1`-`LPT9` and `LPT¹`-`LPT³`, in any case, with or without an extension
       (`nul.txt` too).

     The check is a pure helper, `windows_name_problem(name) -> str | None`, tested on every OS.
  2. **Folders.** Every path goes to `CreateFileW` as a full path with the `\\?\` prefix, so folders deeper than 260
     characters work. `CreateFileW` can't open a name relative to a held folder, so holding each folder on the way is
     what stops a swap.
     - **The work root** is opened following links, as the POSIX code does (`workfs.py:63`): the app made it, and the
       sandbox can't replace its own mount point.
     - **Each folder below it** is opened with `FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT`, so a link
       is opened as itself and never followed.
     - **Share mode** `FILE_SHARE_READ | FILE_SHARE_WRITE`, with no `FILE_SHARE_DELETE`, so no folder on the path can
       be renamed or swapped while it is held.

     Every handle is held until the file is open, then closed. When writing, a missing folder is created with
     `CreateDirectoryW`, then opened the same way.
  3. **Each folder handle below the root is checked** with `GetFileInformationByHandle`:
     - `FILE_ATTRIBUTE_REPARSE_POINT` (a symbolic link, a junction or a WSL link) gives the POSIX message:
       `PathError("…: is a symbolic link (or inside one); use the file it points to")`;
     - a part that isn't a folder gives `FileNotFoundError`, like the POSIX `ENOTDIR` case.
  4. **The file** is opened with `CreateFileW`, `FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS`, share
     read and write. Backup semantics lets a folder open too, so it can be told apart: without it, Windows answers
     "access denied" for a folder.
     - reads use `OPEN_EXISTING`, writes use `OPEN_ALWAYS`;
     - `GetFileInformationByHandle` then decides: a reparse point gives the link `PathError`, and a folder gives
       `IsADirectoryError`;
     - a write truncates only after these checks (`SetEndOfFile` at 0), never before.
  5. **Belt and braces:** `GetFinalPathNameByHandleW` of the open file must lie inside the work root's final path,
     both read with that same call and compared with `os.path.normcase`. Otherwise `PathError`.
  6. **Handing over:** the handle becomes a binary file descriptor with `msvcrt.open_osfhandle`, and `_open` returns
     `os.fdopen(fd, "rb" or "wb")`.
- **No `set_blocking` on Windows.** NTFS has no FIFOs, so the shell can't leave one behind.
- **Unchanged:** the `to_host` resolve check, `snapshot`, `drop_snapshots` and every message.

**Why:**
- the promise is the same as on POSIX: a link that the sandboxed shell makes can never point a host read or write at
  the user's own files;
- through Docker Desktop's file share, links that the Linux container makes appear on NTFS as reparse points, so
  refusing every reparse point covers them all.

### 3. Launching AI Browser on Windows (`appbrowser.py`)

- **Imports.** `fcntl` (`appbrowser.py:14`) and `select` (`:18`) are imported only inside the POSIX pipe path.
- **The headed launch, the real use.** On Windows it is
  `subprocess.Popen(chrome_args(...), stdout=DEVNULL, stderr=DEVNULL)`.
  - `AppBrowser.process` is then `_Process | subprocess.Popen`; both have `poll`, `wait`, `terminate` and `kill`.
  - `_Process` and `posix_spawn` (`:133-169`, `:219-243`) stay for POSIX.
- **The same flags on every OS.** Windows uses `chrome_args()` (`:77-85`) unchanged; this sub-project adds and removes
  no flag. A test pins that.
- **Pipe install (tests only) is refused on Windows:**
  `AppBrowserError("installing the extension over the DevTools pipe needs macOS or Linux; on Windows, load it once with
  Load unpacked")`.
  - Tests that launch with the pipe are skipped on Windows (Decision 16).
  - `test_a_chrome_that_cannot_run_is_reported_plainly` (`test_appbrowser.py:78`) passes `pipe_install=False`, so it
    runs on every OS and covers the Windows `Popen` error too.
  - Chrome's Windows handle switch (`--remote-debugging-io-pipes`) is out of scope until a Windows CI run can try it.
- **`prepare_extension` updates the folder in place** (`:49-55` today does `rmtree` plus `copytree`).
  - It uses the same sync as the watcher folder (Decision 9's `syncdir.py`): changed files are rewritten, stale files
    removed, and `config.json` written with mode 0600.
  - Reason: on Windows, `rmtree` fails while anything holds a file open, such as a Defender scan or an AI Browser
    left from an earlier run.
- **Wording.** `ALREADY_OPEN` (`:33`) says "(⌘Q in its window)" on macOS and "(close its window)" elsewhere.

### 4. Extension IDs on Windows

**Today:** `extension_id_for` (`appbrowser.py:58-61`) hashes `os.path.realpath(folder)` as UTF-8. Chrome on Windows
hashes the path as UTF-16LE after upper-casing the drive letter (Chromium's `id_util.cc`, `GenerateIdForPath` and
`MaybeNormalizePath`). Three things break with the wrong ID:
- the app server refuses AI Home, the side panel and the Brave watcher (WebSocket close 4403);
- `extension_installed` never matches, so the setup tabs open at every start;
- everyday-brave's tab groups, which go through the watcher, never work.

**Change:**
- **`extension_id_for(folder, system=None)`:**
  - **Windows:** `p = ntpath.abspath(folder)`, then upper-case `p[0]` when `p[1] == ":"`, then
    `sha256(p.encode("utf-16-le"))`.
  - **POSIX:** unchanged (`realpath`, UTF-8).
  - `ntpath` keeps the Windows case testable on the Mac.
- **Test vectors, from the Chromium algorithm:**

  | Path | ID |
  |---|---|
  | `C:\Users\me\.ai-browser\app\extension` | `jjdpkibincdinfnjejbcmmghdbgfjpph` |
  | `c:\Users\me\.ai-browser\app\extension` (lower-case drive) | `jjdpkibincdinfnjejbcmmghdbgfjpph` |
  | `C:\Users\me\.ai-browser\app\watcher` | `ncapijkcfmdajdlhdhbgnnmkgejiggeg` |
  | `C:\Users\me\.ai-browser\app\extension`, old UTF-8 code | `mkeihmjkgdgccikkejdhgpoikkjpilll` (wrong) |

- **Why `abspath`, not `realpath`, on Windows:** Chrome doesn't resolve junctions or OneDrive redirection.
- **One path string for everything: `extension_path(folder, system=None) -> str`.** It is `realpath` on POSIX and
  `ntpath.abspath` on Windows. The ID is hashed from it, and the same string is what the user sees and pastes:
  - the setup page's folders (`app/server.py:191-195` uses `realpath` today);
  - the terminal steps and the reveal (`run.py:132`, `:155`, `:156`).

  Otherwise, on Windows, the user could paste a `realpath` (resolved, with the case on disk) while the app hashed the
  `abspath`, and the IDs would differ.
- **`extension_installed`** (`:64-74`) compares paths with `os.path.normcase(extension_path(...))` on Windows.
- **Making a mismatch visible.** A socket can carry the right token but come from a `chrome-extension://` origin that
  isn't allowed. Only an extension holding our `config.json` has the token, so this means a computed ID is wrong on
  that machine. The app server (`app/server.py:230-233`) then:
  - still refuses it (close 4403), and never allows the origin on its own;
  - records it in `AppServer.origin_mismatch` and prints one line: `An AI Browser extension connected as
    chrome-extension://X, but the app expected chrome-extension://A (AI Browser) or chrome-extension://B (the
    watcher): please report this`;
  - returns it from `/setup/status` as `"mismatch": "chrome-extension://X"`, a key that is there only after a
    mismatch. The setup page shows it with `textContent`.
- **The Brave watcher** gets the same fix through `run.py:142`.

### 5. Finding browsers and profile folders (`chrome.py`)

- **`chrome_binary()`** (`chrome.py:29-36`) looks in this order:
  1. `AIB_CHROME_BINARY`, as given. A wrong path shows up as "AI Browser could not start: …", which an existing test
     already covers.
  2. `platforms.browser_candidates("chrome")`: the first one that exists.
  3. **Windows only:** the registry key
     `HKCU`, then `HKLM`, `SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe` (default value), read with
     `winreg`.
  4. The names on PATH: `chrome` on Windows; `google-chrome`, `google-chrome-stable`, `chromium` and
     `chromium-browser` elsewhere.
- **`brave_binary()` (new)** follows the same order without an override: the candidates, the `App Paths\brave.exe`
  key, then `brave` on Windows or `brave-browser` elsewhere on PATH. Only `doctor --setup` uses it, to say whether
  Brave is installed. **The app never starts the user's Brave.**
- **`default_chrome_dir()`** (`:21-26`) is the everyday-brave spec's: it becomes another name for
  `own_browser_dir()`, which picks `AIB_CHROME_DIR`, then the first candidate whose switch is on, then the first that
  exists (Brave before Chrome). This spec only makes sure the Windows candidates are right, through
  `platforms.user_data_dir`.
- **The real-profile guard in `launch()`** (`:81-83`) is the everyday-brave spec's too. It refuses every candidate
  folder from `own_browser_dirs()`. It doesn't refuse `AIB_CHROME_DIR` as such: the tests point it at a throwaway
  profile and launch that again. An `AIB_CHROME_DIR` that is a real browser folder is refused because it is one of the
  candidates. This spec adds one thing: on Windows the paths are compared resolved and with `normcase`, because Windows
  paths ignore case.
  - Today the guard compares only against the macOS Chrome folder, so on Windows it protects nothing.

### 6. The single-instance lock (`app/run.py`)

- **Today:** `import fcntl` (`run.py:11`) and `fcntl.flock` (`:104-114`).
- **Change:** `_lock` calls `platforms.lock_file(home / "app" / "lock")`:
  - **POSIX:** `fcntl.flock(LOCK_EX | LOCK_NB)`; `BlockingIOError` gives None.
  - **Windows:** open with `"a+b"`, `seek(0)`, then `msvcrt.locking(fd, LK_NBLCK, 1)`; `OSError` gives None.
- **Release:**
  - on POSIX, closing the handle releases the lock;
  - on Windows, the returned handle's `close()` first unlocks the byte (`seek(0)`, `LK_UNLCK`), then closes. Windows
    may release a lock on a closed file late, and the next start must not see it as taken;
  - if the app dies, the OS releases the lock either way.
- **Why it matters beyond the app:** the conftest's autouse fixture imports `ai_browser.app.run`
  (`tests/conftest.py:30-37`). Until this import works, every test on Windows errors at setup.

### 7. Is that process still alive? (`engine._alive`)

- **Today:** `engine.py:48-57` calls `os.kill(pid, 0)`.
  - On Windows, signal 0 is `CTRL_C_EVENT`, so this can send Ctrl-C to a console group.
  - Otherwise it raises an `OSError` that `_close_orphans` (`:236-251`) doesn't catch. `sandbox_start` and own-browser
    start then fail whenever a stale session record exists.
- **Change: `platforms.pid_alive(pid)`:**
  - **Every OS:** a pid of 0 or less is not alive, as today.
  - **POSIX:** the current logic.
  - **Windows:**
    1. `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)`.
    2. If that returns no handle, the process is alive only when `GetLastError()` is `ERROR_ACCESS_DENIED` (5).
    3. Otherwise it is alive when `GetExitCodeProcess` gives `STILL_ACTIVE` (259). The handle is closed after.
  - It never calls `os.kill` on Windows.
- **`_close_orphans`** also catches `OSError` for each record. A record it can't judge is left alone: its tabs are not
  closed.

### 8. Ports: exclusive on Windows (`live.py`)

- **Today:** `_bind` (`live.py:38-47`) sets `SO_REUSEADDR`. The app server uses it too (`app/server.py:34`, `:152`).
- **Change:** on Windows, `_bind` sets `SO_EXCLUSIVEADDRUSE` instead. Elsewhere it keeps `SO_REUSEADDR`.
- **Why:**
  - on Windows, `SO_REUSEADDR` lets a second socket bind a port that is already held;
  - "port taken, try the next" then never moves on, and two MCP servers share 8770;
  - worse, any local program could bind the app's port and receive connections that carry the token.
- **Reserved ranges.** A port that Hyper-V has reserved fails with WinError 10013. `_bind` already treats any `OSError`
  as "taken", so the next port is tried. The README explains the "no free port" case.

### 9. Text is UTF-8 everywhere, and files are written in binary

- **Every text read or write names its encoding:** `read_text`, `write_text`, `open()` and `os.fdopen()` pass
  `encoding="utf-8"`. Today 29 calls in `src/` don't (counted with an AST scan), for example:
  - `browser.py:26` (`reader.js`) and `qa/page.py:20` (`probe.js`);
  - `live.py:124` and `app/server.py:198` (the setup page);
  - `config.py:52`, `chrome.py:56`, `skills.py:81/150/168/179/183`, `engine.py:226/242` and `appbrowser.py:53/69`;
  - `brain/store.py:221`, `brain/tools.py:54/70/180`, `brain/workflows.py:149` and `brain/skillwriter.py:175`.

  `subprocess` text output (`sandbox.py:72`, `text=True`) becomes `encoding="utf-8", errors="replace"`.
- **New file: `src/ai_browser/syncdir.py`.** It holds one atomic writer and the folder sync:
  - `write_atomic(path, data: bytes, mode=0o644)`:
    - a temp file in the same folder, opened `O_WRONLY | O_CREAT | O_TRUNC | O_BINARY` with `mode`;
    - then `chmod` and `platforms.replace`;
    - the temp file is removed on failure.
  - `sync_folder(folder, files: dict[str, bytes], keep: set[str])`: rewrites only the files that changed and removes
    the rest. This is the watcher's current logic, moved here.
  - **Users:**
    - `brain/store.py:243-250`, `brain/tools.py:185-193` and `brain/workflows.py:218-225`, with JSON encoded as UTF-8
      bytes;
    - `brain/skillwriter.py:186-189`;
    - `app/bridge.py:284-286` (an agent's `mcp.json`);
    - `brain/watcher.py:32-38`, `appbrowser.py:52` and `prepare_extension`.
  - **`skillwriter.py:163-165`** keeps its `O_EXCL`, so a new skill never overwrites one. It adds `O_BINARY` and
    writes the text's UTF-8 bytes through `"wb"`. Python's text mode would end each line with `\r\n` on Windows.
- **Why `O_BINARY` matters on Windows.** Without it, `os.open` opens in text mode and turns every `\n` into `\r\n`.
  - That corrupts `watcher/icon.png`, and Brave can refuse to load an extension whose icon doesn't decode.
  - The watcher's "rewrite only what changed" comparison would also never match.
- **Console output.** `cli.main` calls `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`, and the same for
  stderr, for every command except `mcp`. The mcp library writes its own UTF-8 stream.
  - Reason: `doctor > log.txt` would otherwise fail on `✓` under cp1252.
- **`tests/fake_claude.py`** reconfigures its stdin, stdout and stderr to UTF-8 at the top, and opens its logs with
  UTF-8.
- **A backstop, not the fix.** The agents' MCP server env (`bridge.py:276`) and `.mcp.json.example` add
  `"PYTHONUTF8": "1"`. That protects third-party libraries. CI runs without it, to prove that our own code doesn't need
  it.

### 10. Running Claude Code on Windows (`claudecli.py`)

**New file: `src/ai_browser/claudecli.py`.** It holds:
- `class ClaudeNotUsable(OSError)`. Its message is the whole explanation.
- `claude_argv(claude: str | Sequence[str] | None = None, system=None, env=None) -> list[str]`. It looks in this
  order:
  1. **The argument.** A string becomes `[string]`; a list or tuple is used as is. Tests pass
     `[sys.executable, ".../fake_claude.py"]`.
  2. **`AIB_CLAUDE`:** a path to the executable.
  3. **Windows only:** `%USERPROFILE%\.local\bin\claude.exe`, if it exists. The native installer puts it there.
  4. **`shutil.which("claude")`.**
  5. **The fallback:** `~/.local/bin/claude`, or `claude.exe` on Windows.

  On Windows, a result that ends in `.cmd` or `.bat` (any case) raises `ClaudeNotUsable`:
  "Claude Code was found at {path}, a script from the npm install. AI Browser needs the native claude.exe: install it
  with `irm https://claude.ai/install.ps1 | iex` in PowerShell, or set AIB_CLAUDE to the full path of claude.exe."
- **Why refuse `.cmd`:**
  - `CreateProcess` runs it through cmd.exe;
  - cmd.exe cuts the multi-line `--append-system-prompt` at the first newline and mangles quoting. That prompt is
    `PANEL_PROMPT` (`bridge.py:25`), or everyday-brave's `BRAVE_PROMPT`, and it carries the agent's safety rules;
  - stopping it ends only cmd.exe, and the real CLI keeps running.

**Where it is used:**
- `ClaudeBridge._command` (`bridge.py:300`);
- `oneshot.command` and `ask_claude` (`oneshot.py:28-38`);
- `ToolsConfig.probe` (`brain/tools.py:141-149`).

The three copies of `claude or shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")` go. The
`claude` parameters of `AgentManager`, `BrainService`, `SkillWriter`, `run_app` and `ClaudeBridge` accept
`str | Sequence[str] | None` and pass it on unchanged. It is resolved when a process starts, not at construction.

**Errors stay text:**
- `ClaudeBridge.send` (`bridge.py:122-127`) yields `{"type": "error", "text": str(exc)}` for `ClaudeNotUsable`, before
  its generic `OSError` message;
- `ask_claude` returns `OneShot(error=str(exc))`;
- `probe` returns False.

**Ending Claude Code on Windows:**
- **Its own process group.** `create_subprocess_exec(..., creationflags=CREATE_NEW_PROCESS_GROUP)`. Windows turns
  Ctrl-C off for a new process group, and its children inherit that. So a Ctrl-C in the console ends only the app,
  which then closes the agents in order.
- **A clean exit first.** `_end_process` (`bridge.py:326-337`) closes stdin, then waits up to `CLEAN_EXIT = 3` s for
  Claude Code to exit by itself. On its way out, Claude Code closes its own ai-browser MCP server. Only then come
  `terminate()` and `kill()`.
  - Windows only: on POSIX, `terminate()` is SIGTERM, which is already graceful.
  - The reason: on Windows, `terminate()` is `TerminateProcess`, which never ends a process's children.
  - **Stop keeps its `terminate()`** (`_end_if_still_running`, `bridge.py:353-360`): by then Claude Code has ignored
    the interrupt for 5 s. Its ai-browser MCP child then sees its stdin close and exits, and the job below covers
    anything left.
- **`platforms.KillOnCloseJob`.** A job object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
  - **One per app process:** `claudecli.track(process)` adds a Claude Code process to a module-level job, made on
    first use on Windows (a no-op elsewhere). The bridge, the one-shot call and the probe call it right after
    `create_subprocess_exec` returns.
  - **The job's handle is never closed by hand.** It closes when the app's process ends, even by a crash, and Windows
    then ends every Claude Code process in it and their MCP children.
  - **Its limit:** a child started before `track` runs is not in the job. Claude Code takes hundreds of milliseconds
    to start its MCP servers, and `track` runs in the same event-loop step, so in practice nothing starts first.
    asyncio has no way to start a process suspended. A failed `AssignProcessToJobObject` (the process already
    exited) is ignored.
- **No loop change.** The Proactor event loop, the Windows default, runs these subprocesses. uvicorn already runs in
  that loop (`app/server.py:155-157`).

### 11. File Explorer, and Windows wording

- **Revealing a folder.** `app/server.py:56-60` (`reveal_in_finder`) becomes `reveal_folder = platforms.reveal`, and
  `run.py:48` follows.
  - `/setup/reveal` (`app/server.py:202-207`) returns 204 when a reveal started, and 501 when none could.
  - Today it returns 204 even on Windows, where nothing opens, so the page wrongly says "Shown in Finder".
- **The setup page** (`app/setup.html`) gets three placeholders, filled by the server with `html.escape`:
  - `{{FILE_MANAGER}}`: "Finder" or "File Explorer";
  - `{{GOTO}}`: on macOS "press ⌘⇧G, paste the path and press Enter"; on Windows "click the address bar at the top
    of the folder window, paste the path and press Enter";
  - `{{THIS_COMPUTER}}`: "this Mac", "this PC" or "this computer", from `platforms.this_computer()`. The everyday-brave
    spec's warning about the switch ("any program on this Mac can reach your Brave", "this PC" on Windows) uses it.

  The button's result (`setup.html:91`) reads the manager's name from a `data-manager` attribute and sets
  "Shown in File Explorer" or "Couldn't open File Explorer" with `textContent`.

  The page is built by `app/server.setup_page(extension, watcher, key, system=None) -> str`, so a test can render
  the Windows page on the Mac. On the Mac the `⌘⇧G` step loses its key boxes (`<kbd>`) and reads as plain text.
- **The terminal texts** in `run.py:33-47` (`READY`, `SETUP`, `BRAVE`) become functions,
  `ready_text(system=None)`, `setup_text(folder, system=None)` and `brave_text(folder, system=None)`. They use
  `platforms.shortcut` and `platforms.file_manager`:
  - `⌘⇧Y` becomes `Ctrl+Shift+Y` (the manifest already maps it, `extension/manifest.json:15`);
  - "Finder" becomes "File Explorer";
  - the `⌘⇧G` step becomes the address-bar step.
- **Python texts that say "this Mac"** use `platforms.this_computer()`:
  - the work-folder lines the engine returns (`engine.py:315`, `:319`, `:323`, "on this Mac: …");
  - the QA report line (`qa/report.py:80`);
  - the refusals for local files (`browser.py:129`, `:133`).

  Comments and docstrings may keep "this Mac".
- **The extension pages are the same files on every OS**, so their words become neutral:
  - "this Mac" becomes "this computer" (`voice.js:2`, `voice.js:130`, `mission.html:16`, `mission.js:445`);
  - the `⌘⇧Y` comment in `worker.js:11` points to the manifest's shortcut.
- **Fonts need no change.** The lists already name `Segoe UI`, and Chrome on Windows maps the closing `monospace` to
  Consolas.
- **The README** gets the Windows section, and two fixes:
  - `README.md:27` and `README.md:280` still say "This folder has a `.mcp.json`". They now say to copy
    `.mcp.json.example`.
  - The Brave example at `README.md:282` gains its Windows line.

### 12. Replace and unlink, with retries on Windows

- **`platforms.replace(src, dst)`, `platforms.unlink(path, missing_ok)` and `platforms.rmtree(path)`** retry on
  `PermissionError`, on Windows only:
  - up to 5 tries, sleeping 50, 100, 200 and 400 ms between them;
  - then the error is raised as before;
  - on POSIX they are plain `os.replace`, `Path.unlink` and `shutil.rmtree`.
- **Users:**
  - `syncdir.write_atomic`;
  - `brain/store.py:231` (renaming a bad file to `.bad`);
  - `brain/watcher.py:61` (stale files);
  - `brain/workflows.py:229` (deleting a workflow);
  - `appbrowser.py:217` (a stale `DevToolsActivePort`);
  - the voice-input spec's model swap (`hearing/model.py`): removing the old model folder and renaming the `.part`
    folder. Defender scanning the freshly downloaded files is the usual reason Windows refuses that rename.
- **Why:** Windows refuses to replace or delete a file that another process has open, for example:
  - Brave reading the watcher's files;
  - Defender scanning;
  - an editor holding a workflow file.

  Such holds last milliseconds, so a short retry is enough.

### 13. The Claude desktop skills folder

- **Today:** `engine.py:105` and `app/server.py:518` look only in `~/Library/Application Support/Claude`.
- **Change:** both use `platforms.claude_desktop_dir()`.
- **On Windows** the folder is `%APPDATA%\Claude`, where the Claude desktop app's standard installer keeps its data.
  `Catalog.discover` (`skills.py:99`) looks under it for `local-agent-mode-sessions/skills-plugin`, as on the Mac.
- **Unaffected:** personal and plugin skills (`~/.claude`) already work, because `Path.home()` is right on Windows.
- **Not covered:** a Microsoft Store install of the Claude app keeps its data in a redirected folder (Out of scope).
  The laptop check notes whether the claude.ai skills show.

### 14. Docker Desktop

- **No change in `sandbox.py`** apart from the encoding (`sandbox.py:72`):
  - the docker CLI on Windows accepts `C:\...:/work` mounts and list arguments;
  - the "Docker isn't running" markers (`sandbox.py:29-34`) already match Windows' "error during connect" message.
- **The Dockerfile, belt and braces.** After the two `COPY` lines (`docker/Dockerfile:20-21`), add
  `RUN sed -i 's/\r$//' /usr/local/bin/aib-entrypoint /usr/local/bin/aib-cdp-proxy`.
  - Then a copy made without git (a ZIP) still runs.
  - `.gitattributes` already checks these files out with LF.
  - The next `ai-browser build` picks it up; the Mac needs no rebuild now.
- **README notes for Windows:**
  - Docker Desktop with the WSL 2 backend, in Linux-containers mode;
  - the work folder lives on NTFS, so it is slower and case-insensitive (`Report.html` and `report.html` are one
    file);
  - names Windows can't hold are refused (Decision 2).

### 15. Python 3.12, pinned

- **New file: `.python-version`**, containing `3.12`.
- **Why:**
  - on a fresh laptop, `uv sync` would otherwise pick the newest Python it knows;
  - `uv.lock` has no Python 3.15 Windows wheels for `pydantic-core` or `pyyaml`, so uv would try to build them from
    source, which fails.
- **`requires-python` stays `>=3.12`**, so the lock doesn't need re-resolving now, and nothing is downloaded on the Mac.

### 16. Tests that run on Windows

- **The fake claude becomes an argv prefix on every OS:**
  - the `fake_claude` fixture (`tests/conftest.py:95-108`) returns `runner = [sys.executable, str(fake_claude.py)]`
    instead of writing a `#!/bin/sh` script;
  - every place that turns the runner into a string becomes the runner itself: the 51 `claude=str(runner)` calls,
    `tools.probe(str(runner))` (`test_tools.py:245`), `runner_bin` in `test_workflows.py`, `stack["runner"]` in
    `test_home.py` and `watcher.runner` in `test_watcher.py`;
  - Mac and Windows then take the same path.
- **Two markers**, registered in `pyproject.toml` and applied in `conftest.pytest_collection_modifyitems`:
  - `posix_only`: "needs macOS or Linux (file descriptors 3 and 4, or the DevTools pipe)";
  - `windows_only`: "Windows behaviour (junctions, msvcrt, Win32 APIs)".

  Each skip shows its reason in the report.
- **Which tests are `posix_only` on Windows.** The hook skips an item when:
  - it carries the marker, or
  - its `item.fixturenames` include a fixture that launches AI Browser over the pipe: `stack` (`test_home.py`),
    `watcher` (`test_watcher.py`), `app_browser` (`test_tabwatch.py`) or `app_engine` (`test_appmode.py`). That covers
    the tests in `test_panel.py`, `test_mission.py`, `test_brain_ui.py`, `test_ai_home_phase2.py` and
    `test_workflows.py` that use them, and the other sub-projects' tests built on these fixtures. Tests in those
    modules that use none of them still run.

  The marker itself goes on the tests that launch over the pipe directly:
  - in `test_appbrowser.py`, the tests at `:23`, `:48` (which also uses `fcntl` and descriptors 3 and 4) and `:116`;
  - in `test_app_run.py`, every test that calls `run_app(..., headless=True)` or `launch_app_browser(...,
    headless=True)` without `pipe_install=False`. The two with `pipe_install=False` (`:134`, `:164`) run on Windows.
- **Links:**
  - the symlink tests (`test_workfs.py:42, 72, 82, 92, 141`, `test_chrome.py:173`) skip when `os.symlink` raises
    `OSError` (Windows without Developer Mode);
  - new `windows_only` tests make junctions with `_winapi.CreateJunction`, which needs no admin rights.
- **Smaller fixes:**
  - `test_oneshot.py:97` uses `platforms.pid_alive` instead of `os.kill(pid, 0)`;
  - `test_mission.py:322` expects "No voice on this computer" (Decision 11);
  - `test_chrome.py:12` (`REAL_CHROME`): everyday-brave's rewrite of `test_tests_never_reach_the_real_chrome` checks
    every `own_browser_dirs()` candidate instead. Any browser folder still written in the tests comes from
    `platforms.user_data_dir`, for Chrome and Brave;
  - everyday-brave's setup test (its test 11, the switch sentence with "this Mac") renders the page with
    `setup_page(..., system="darwin")` and expects "this Mac", and with `system="win32"` expects "this PC";
  - the conftest's `_no_finder_windows` patches the renamed `reveal_folder` and `run.reveal`;
  - tests that read or write text pass `encoding="utf-8"`. That is about 170 calls today, 7 of them `text=True` runs:
    a mechanical change.
- **New guard tests that run on every OS (`tests/test_portable.py`):**
  1. **`test_text_io_names_its_encoding`.** An AST walk over `src/ai_browser` and `tests` flags:
     - `.read_text()` with no positional argument and no `encoding=`. `WorkDir.read_text(path, limit)` has two, so it
       isn't flagged;
     - `.write_text(x)` with one positional argument and no `encoding=`;
     - `open(...)` and `os.fdopen(...)` in a mode without `b` and with no `encoding=`;
     - `subprocess.*(..., text=True)` or `universal_newlines=True` with no `encoding=`.

     A mode counts as binary when it is a literal with `b`, or an `x if c else y` of such literals (as at
     `workfs.py:100`). Any other mode expression is flagged. The check lists each `file:line`.
  2. **`test_every_module_imports_on_a_windows_like_python`.** A child Python:
     - blocks `fcntl`, `termios`, `resource`, `pwd` and `grp` with a `sys.meta_path` finder;
     - deletes `os.O_DIRECTORY`, `os.O_NOFOLLOW`, `os.O_NONBLOCK`, `os.posix_spawn`, `os.POSIX_SPAWN_OPEN`,
       `os.POSIX_SPAWN_DUP2` and `os.WNOHANG`;
     - then imports every `ai_browser` module (`pkgutil.walk_packages`), `winfs` included.

     This is the investigation's simulation, kept.
  3. **`test_no_macos_paths_outside_platforms`.** Outside `platforms.py`, no Python source under `src/ai_browser`
     contains `Application Support`, `/Applications/`, `"open", "-R"` or a liveness probe `os.kill(<pid>, 0)`. The
     POSIX `os.kill(self.pid, number)` in `appbrowser.py:163`, which sends SIGTERM or SIGKILL, stays allowed.
  4. **`test_no_mac_words_where_windows_shows_them`.** Two checks:
     - the files under `app/extension`, `app/watcher` and `app/setup.html` contain neither "this Mac" nor "⌘";
     - no string in Python code under `src/ai_browser` says "this Mac". An AST walk reads the string constants and
       skips docstrings; comments aren't in the AST.

     There are two kinds of exception:
     - setup wording comes from the placeholders, so it needs none;
     - text shown only on macOS, picked by a platform value (for example voice-input's mic messages, chosen by
       `platform` from `hearing_status`), is allowed when the test's allowlist names it by file and snippet.

     Any other occurrence fails, so each Mac-only phrase is a conscious choice.
  5. **`test_repo_hygiene`.** It skips when this isn't a git checkout. Otherwise:
     - no tracked `.mcp.json`, `.env*`, `*.log` or `.DS_Store`;
     - nothing tracked under `.venv/`, `.superpowers/`, `.pytest_cache/` or `.claude/`;
     - no tracked text file contains the path of the home folder of the machine running the test (the value of
       `str(Path.home())`, such as `/Users/<name>`);
     - `git check-attr eol -- docker/entrypoint.sh` says `lf`;
     - `.python-version` says `3.12` (Decision 15);
     - `docker/Dockerfile` has the line that strips `\r` from the two copied scripts (Decision 14).
  6. **`test_voice_extra_has_windows_wheels`.** It skips when `uv.lock` has no `faster-whisper`, because the user may
     not have chosen the voice extra. Otherwise it reads `uv.lock` with `tomllib` and walks the dependencies from the
     root package's `voice` extra. Dependencies whose marker is false for 64-bit Windows and CPython 3.12 are left out
     (checked with `packaging.markers`, which pytest already brings). Each package reached must have a wheel tagged
     `none-any`, or `win_amd64` with `cp312` or `abi3`. The failure names each package without one.

These guards also cover whatever the other four sub-projects added (Decision 18).

### 17. The private repo: checks, the question, then `gh`

**Already in the baseline commit (`1974d2d`, branch `main`, no remote):**
- `.gitignore`: `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.superpowers/`, `dist/`, `.mcp.json`, `.claude/`,
  `.DS_Store`, `.env*`, `*.log` and `node_modules/`;
- `.gitattributes`: LF for text, `docker/**` and `*.sh`, and binary for images and ZIPs;
- `.mcp.json.example` with placeholders (the user's own `.mcp.json` is ignored).

**What was checked for personal data** (tracked files at the baseline):
- **`docs/google-flights-cgy-mnl.jpg`: flagged.** It shows a signed-out Google Flights search, Cagayan de Oro to Manila,
  one adult, Friday 16 October, with prices. It holds no account, no name and no credentials, but it reveals a personal
  trip. Nothing in the repo links to it.
- **The same trip is named in text,** in `docs/superpowers/specs/2026-10-02-own-chrome-mode-design.md:46` and
  `docs/superpowers/plans/2026-10-02-own-chrome-mode.md:51`, as the real-world test route. That is low risk, but the
  user should know.
- **The commit author's email** (the user's Gmail address) is in every commit. In a private repo, only people the user
  invites see it. If GitHub's "Block command line pushes that expose my email" setting is on, the push is refused with
  GH007, and the user decides then.
- **Fine:** no tokens or keys are tracked, because tokens are made at run time with `secrets.token_urlsafe`. No
  absolute home path is tracked either; `test_chrome.py` uses `/Users/me`.

**Done by the main session, in this order. Nothing is pushed until step 2's yes:**
1. **Checks.** If any fails, it stops and reports:
   - `git status --porcelain` is empty, so everything is committed;
   - `uv run pytest tests/test_portable.py` passes, including the hygiene test;
   - `gh auth status` shows the account `nanotechs001`;
   - `gh repo view nanotechs001/ai-browser` fails, so the name is free. If the name is taken, the main session asks
     the user for another.
2. **The question, in chat.** The main session first shows what would go up:
   - the number of tracked files and their top folders (`git ls-files`);
   - the commit author name and email that every commit carries;
   - the flagged items above.

   Then it asks the user, plainly:
   - "Create a **private** GitHub repo `nanotechs001/ai-browser` and push the code?"
   - "The flights screenshot `docs/google-flights-cgy-mnl.jpg` shows your CGY → MNL search. Keep it, remove it, or
     remove it from the history too?"

   The two ways to remove it:
   - **From the repo:** a normal commit with `git rm --cached` and a `.gitignore` line, so the file stays on the Mac.
   - **From the history too:** it rewrites local commits that were never pushed:
     `git filter-branch --index-filter 'git rm --cached --ignore-unmatch docs/google-flights-cgy-mnl.jpg' -- --all`,
     then the `.gitignore` line, then delete the `refs/original/` backup, expire the reflog and run
     `git gc --prune=now`. That is safe only because nothing was pushed yet, and the file on disk stays.
3. **Only after a clear yes:**
   ```bash
   gh repo create nanotechs001/ai-browser --private --source=. --remote=origin --push \
     --description "AI Browser: a Claude-driven browser, the Brain and Mission Control"
   gh repo view nanotechs001/ai-browser --json visibility,url   # must say PRIVATE
   ```
   If the visibility isn't `PRIVATE`, the main session tells the user at once.
4. **Nothing else.** No secrets, deploy keys, Pages, webhooks or collaborators. Actions stays as GitHub sets it; the
   workflow only runs by hand.

**Why `gh`, and why ask:** the user picked "Private GitHub repo". Pushing sends the code off the machine, so it happens
only on the user's own yes, given after they have seen what will be pushed.

### 18. Covering the other four sub-projects

This sub-project runs last. Its guard tests (Decision 16) run over the other four's code, and they fail on anything
POSIX-only or Mac-only that slipped in. Beyond that, these are the points where each one meets Windows. The names come
from their specs, in `docs/superpowers/specs/`.

- **everyday-brave** (`2026-10-02-everyday-brave-design.md`):
  - **Folders.** Its `chrome.own_browser_dirs()` already lists `%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data`,
    then Chrome's. In the sweep, it takes those paths from `platforms.user_data_dir`, so that `chrome.py` holds no
    macOS literal (guard 3). Its behaviour doesn't change, and its tests, which monkeypatch `sys.platform` and
    `LOCALAPPDATA`, keep working, because `platforms` reads both at call time (Decision 1).
  - **Its other helpers** (`own_browser_dir()`, `switch_on()`, `browser_name()`, `inspect_address()`) are platform-free.
    The switch is the same `brave://inspect/#remote-debugging` on Windows, and Brave writes `DevToolsActivePort` into
    `User Data`. The first real check is manual, on the laptop.
  - **`<home>/app/link.json`** (mode 0600) is written with `syncdir.write_atomic`. It holds the session token, so it
    is one of the token files whose Windows permissions are documented, not changed (Safety).
  - **Is the app, or a session, alive?** A session checks the app's `pid` in link.json, and the app checks each
    session's pid every 30 s. Both go through the engine's `_alive` (as everyday-brave says), so they move to
    `platforms.pid_alive` with it (Decision 7), never `os.kill(pid, 0)`.
  - **Tab groups** (`grouping.py`, `app/groups.py`, `app/bravelink.py`) go through the watcher, so they depend on the
    Windows extension ID (Decision 4). Without it, the watcher can't connect and the AI's tabs fall back to their own
    Brave window.
  - **Its setup warning** says "this Mac" or "this PC" through the `{{THIS_COMPUTER}}` placeholder (Decision 11), and
    its setup test renders both (Decision 16). Its terminal steps and AI Home's browser card already say "this
    computer", so guard 4 passes without a change there.
  - **Its guard** refuses every candidate folder, and an `AIB_CHROME_DIR` only when it is one of them (Decision 5);
    this spec adds the Windows-safe comparison. `doctor --setup` reports the everyday browser's folder
    (`own_browser_dir()`) with its `switch_on()`, which never connects.
  - **Its tests on Windows.** The unit tests (`test_grouping.py`, `test_bravelink.py`, the routes, the folders) and the
    throwaway-Chrome tests in `test_chrome.py` run on `windows-latest`. `test_watcher_groups.py` and the AI Home tests
    use the pipe fixtures, so they are skipped there with the reason (Decision 16).
- **voice-input** (`2026-10-02-voice-input-design.md`):
  - **Windows wheels.** Its extra, `voice = ["faster-whisper>=1.2,<2"]`, must resolve in `uv.lock` with Windows
    wheels for everything it pulls in: `ctranslate2`, `onnxruntime`, `av`, `tokenizers`, `numpy` and the rest. Guard 6
    (Decision 16) checks the lock. If it fails, the sweep stops and the main session tells the user that voice can't
    be installed on Windows yet; the README's Windows section then says so instead of step 8's `uv sync --extra
    voice`. Nothing is built from source.
  - **Lazy import.** `hearing/engine.py` checks `importlib.util.find_spec("faster_whisper")` and imports it only in
    `load()`, so the base install and the import simulation pass without the extra.
  - **The model folder.** It is `<home>/models/faster-whisper-base.en/`, fetched file by file with `urllib`, not
    through the Hugging Face cache. So Windows needs no symbolic links. The swap of the `.part` folder goes through
    `platforms.rmtree` and `platforms.replace` (Decision 12).
  - **Audio** arrives as 16 kHz Int16 PCM in base64 chunks and stays in memory; there is no decoder and no temp file.
  - **The microphone message** on Windows comes from `HearingService(platform=sys.platform)`. The README adds the same
    setting. The voice spec shows its macOS lines (the first-use card's "macOS may also ask", Dictation) only when
    `platform` is `mac`, and gives Windows its own line; guard 4's allowlist names those snippets.
  - **CI.** The workflow's `voice` input installs the extra on the runner and imports `faster_whisper`, which proves the
    Windows wheels install. The voice tests use their fake engine either way, and no run downloads the model.
  - **The install itself** (`uv sync --extra voice`) stays the user's choice, asked by the main session, as that spec
    says.
  - **Its tests on Windows.** `test_hearing.py`, `test_brain_talk.py` and the server tests run on `windows-latest`
    with the fake engine. `test_talk.py` uses the `stack` fixture, so it is skipped there with the reason.
- **mission-visuals** (`2026-10-02-mission-visuals-design.md`):
  - It is pure extension code: `blob.js` keeps one WebGL1 context, `brainshape.js` is new, and the chibi workers are
    SVG. There is no OS code.
  - On Windows, WebGL runs on ANGLE over Direct3D 11. Without WebGL (Remote Desktop, a blocklisted GPU), its dotted
    silhouette fallback shows.
  - Windows "Animation effects: off" arrives as `prefers-reduced-motion: reduce`, which it follows live.
  - It uses no web fonts; the font lists already include `Segoe UI`.
  - Its performance pass on the Windows laptop needs the repo, so it joins the manual Windows check (Testing).
  - New images are covered by `.gitattributes`.
- **safe-browsing** (`2026-10-02-safe-browsing-design.md`):
  - No launch flag is added or removed for Windows. The Windows `Popen` uses the same `chrome_args()`, and a test pins
    that.
  - **Bringing the tab forward.** Its `bring_to_front(tab)` (`Target.activateTarget`) selects the tab inside the
    browser. Windows' focus rules may only flash the window's taskbar button instead of raising the window. So the
    hand-off text's line "The tab is now in front." (`CheckGate.handoff`) gains, on Windows, "(if its window didn't
    come up, look for it in the taskbar)", the words the safe-browsing spec already names. `handoff` takes
    `system=None` for the test.
  - **Notifications.** Its watcher notification (`askCheck`) shows in Windows' notification centre, where Do not
    disturb can hide it. AI Home's **needs you** stays the signal that always shows.
  - **The shell seatbelt** (`shellguard`) reads bash syntax. That is right on Windows too: the shell runs in the Linux
    sandbox, never in cmd.exe or PowerShell.
  - **Its tests on Windows.** The ones that launch a throwaway Chrome (`chrome_engine`, `test_checks_browser.py`,
    `test_isolation.py`, `test_qa_browser.py`) run on `windows-latest`. Its AI Home, panel, Mission Control, watcher
    and app-mode tests use the pipe fixtures, so they are skipped there with the reason (Decision 16).
  - Any new Python it adds passes the same guards.

### 19. CI: one workflow, run by hand

**New file: `.github/workflows/tests.yml`.** Each action is pinned to the full commit SHA of its latest release, with
that release's tag in a comment. The implementer reads both when writing the file, with
`gh release view --repo <owner>/<action> --json tagName` and `gh api repos/<owner>/<action>/commits/<tag> --jq .sha`,
and puts them in place of `<sha>` and `vN` below:

```yaml
name: tests
on:
  workflow_dispatch:
    inputs:
      os:
        description: Which systems to test on
        type: choice
        options: [windows, macos, both]
        default: windows
      voice:
        description: Also install the voice extra (no model download)
        type: boolean
        default: false
permissions:
  contents: read
jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: ${{ fromJSON(inputs.os == 'both' && '["windows-latest","macos-latest"]' || inputs.os == 'macos' && '["macos-latest"]' || '["windows-latest"]') }}
    runs-on: ${{ matrix.os }}
    timeout-minutes: 40
    steps:
      - uses: actions/checkout@<sha>        # vN
      - uses: astral-sh/setup-uv@<sha>      # vN
      - run: uv sync --locked ${{ inputs.voice && '--extra voice' || '' }}
      - if: inputs.voice
        run: uv run --no-sync python -c "import faster_whisper"
      - run: uv run --no-sync pytest -q --junitxml=pytest.xml
      - if: always()
        uses: actions/upload-artifact@<sha>  # vN
        with: { name: pytest-${{ matrix.os }}, path: pytest.xml, retention-days: 7 }
```

`--no-sync` makes the test steps use exactly what the sync step installed, the voice extra included.

**What it does and doesn't do:**
- **Manual only.** It runs when the user clicks **Run workflow**, and never on a push, a pull request or a schedule.
- **Minutes.** It uses the user's GitHub Actions minutes only when they start it. For private repos, Windows and macOS
  minutes cost more than Linux minutes, macOS the most (see GitHub's Actions billing page). That is why the default is
  Windows only: the Mac runs the suite locally anyway.
- **No secrets.**
  - No Claude Code and no API keys: agents are the fake claude.
  - No logins and no real sites.
  - The Docker tests skip themselves, because the runners have no Linux-container sandbox image.
- **No `PYTHONUTF8`,** so Windows' own default encoding is what gets tested.
- **The `voice` box** works only once `uv.lock` has the voice extra (the user's choice, voice-input spec). Without it,
  the sync step fails, because the lock has no such extra.
- **Results.** The test report is kept for 7 days as an artifact of the private repo.

### 20. Build order

The order follows the import chain, so each step leaves the Mac suite green:

1. `platforms.py` and its tests.
2. `workfs` constants, then `winfs.py`.
3. `appbrowser` and `run.py` imports, and the lock.
4. Extension IDs.
5. Browser paths.
6. `pid_alive`.
7. `_bind`.
8. `syncdir.py` and UTF-8 everywhere.
9. `claudecli.py` and process ending.
10. Wording and reveal, with the test lines that follow them (the conftest's `_no_finder_windows`,
    `test_mission.py:322`).
11. Retries.
12. The Claude desktop folder.
13. The Dockerfile line.
14. `.python-version`.
15. The sweep over the other four sub-projects (Decision 18), so their code is ready before the guards check it.
16. The test changes and the guard tests.
17. `doctor --setup`.
18. The README.
19. The CI workflow.
20. Last, the repo steps in Decision 17, through the main session.

## Messages / interfaces

**New modules:**
- `platforms.py`:
  - `WINDOWS`, `O_BINARY`;
  - `user_data_dir(browser, system=None, env=None)`, `browser_candidates(browser, system=None, env=None)` and
    `claude_desktop_dir(system=None, env=None)`;
  - `file_manager(system=None)`, `this_computer(system=None)`, `shortcut(mac, other, system=None)`,
    `reveal_command(path, system=None)` and `reveal(path) -> bool`;
  - `pid_alive(pid) -> bool` and `lock_file(path) -> IO | None` (its `close()` unlocks first on Windows);
  - `replace(src, dst)`, `unlink(path, missing_ok=False)` and `rmtree(path)`;
  - `class KillOnCloseJob` with `.add(pid)` and `.close()`.
- `winfs.py`: `windows_name_problem(name) -> str | None` and `open_in(root, folders, name, writing) -> int`.
- `syncdir.py`: `write_atomic(path, data, mode=0o644)` and `sync_folder(folder, files, keep)`.
- `claudecli.py`: `ClaudeNotUsable(OSError)`, `claude_argv(claude=None, system=None, env=None) -> list[str]` and
  `track(process)`.

**Changed:**
- `appbrowser.extension_path(folder, system=None) -> str` (new) and `appbrowser.extension_id_for(folder,
  system=None)`;
- `AppBrowser.process: _Process | subprocess.Popen`;
- `chrome.brave_binary()` (new);
- the `claude` parameters accept `str | Sequence[str] | None` everywhere;
- `app/server.reveal_in_finder` is renamed `reveal_folder`, and `app/server.setup_page(extension, watcher, key,
  system=None) -> str` (new) builds the setup page;
- `app/run.py`'s `READY`, `SETUP` and `BRAVE` become `ready_text(system=None)`, `setup_text(folder, system=None)` and
  `brave_text(folder, system=None)`;
- safe-browsing's `CheckGate.handoff(..., system=None)` (Decision 18).

**Environment:**
- `AIB_CHROME_BINARY` (new): the full path of the Chrome to use for AI Browser.
- `AIB_CLAUDE` (new): the full path of `claude` or `claude.exe`.
- `AIB_CHROME_DIR`: unchanged, and still overrides the browser folder.
- `PYTHONUTF8=1`: added to the agents' MCP env and to `.mcp.json.example` as a backstop.

**HTTP:**
- `POST /setup/reveal` answers 204 when a folder window opened, 501 when not.
- `GET /setup/status` adds `"mismatch": "chrome-extension://…"` when the extension connected under an unexpected ID.
- The WebSocket messages don't change.

**Command line:**
- `ai-browser doctor --setup` checks, without Docker and without connecting to any browser:
  - Python;
  - Claude Code, resolved by `claude_argv`, and not a `.cmd`;
  - Chrome;
  - Brave: whether it is installed (`brave_binary()`);
  - the everyday browser's folder: `own_browser_dir()` (so `AIB_CHROME_DIR` first), named with `browser_name()`,
    whether it exists, and whether its switch is on. That last check is everyday-brave's `switch_on()`: the port file
    exists and its port answers a plain TCP check. It opens no DevTools connection, so Brave never asks Allow;
  - one free port in each range.

  It exits 1 when Python, Claude Code or Chrome fails. Brave and Docker are informational.

**Files:**
- `.python-version`;
- `.github/workflows/tests.yml`;
- `tests/test_portable.py`, `tests/test_platforms.py` and `tests/test_claudecli.py`;
- the README's Windows section.

**Pytest markers:** `posix_only` and `windows_only`.

## Safety

The project's rules hold on Windows exactly as on the Mac. In this sub-project:

- **No bypassing CAPTCHAs or bot checks.** Nothing here changes how pages are driven.
- **No spoofing or disguise.** The Windows launch uses the same `chrome_args()` as the Mac, and a test pins that. There
  are no `navigator.webdriver` patches, no UA, screen, timezone or GPU changes, no human-like timing or mouse paths, no
  stealth plugins, and no proxies or profile rotation. CI visits no real site.
- **A bot check is handed to the user.** That is unchanged, and owned by safe-browsing. On Windows the hand-off message
  also says where to look (the taskbar).
- **The agent never types passwords.**
  - On Windows the user signs in to Google, GitHub (`gh auth login`) and Claude Code themselves.
  - The README never asks for a password or token in a file or an environment variable.
  - CI has no secrets.
- **The user's own words are instructions; page or message text never is.** Unchanged. Refusing `claude.cmd` keeps
  `PANEL_PROMPT` (and everyday-brave's `BRAVE_PROMPT`), which state this rule, whole. cmd.exe would cut them at the
  first line.
- **Text is set with `textContent`.** The setup page's new result text and the mismatch line are set that way. The
  platform words come from server constants, escaped with `html.escape`.
- **Nothing leaves the machine unless the user knowingly chooses:**
  - the push to GitHub happens only after the user's yes in chat, to a private repo, after the checks and with the
    flights image flagged;
  - CI runs only when the user clicks **Run workflow**. It uploads only the test report, within the private repo, and
    the tests use temporary folders, never the user's data;
  - voice audio stays in memory on Windows too.
- **Downloads need the user's explicit OK:**
  - on the Mac, this sub-project downloads nothing. It adds no dependency: no ruff, psutil or filelock, only the
    standard library (`ctypes`, `msvcrt`, `winreg`);
  - every Windows download (Git, uv, Python, Claude Code, Chrome, Brave, Docker, the voice packages, the voice
    model) is the user's own action, from the README or the app's Download button;
  - CI downloads only on GitHub's runners, when the user starts it.
- **The work folder stays a wall.** On Windows, host reads and writes never follow symbolic links, junctions or WSL
  links. Each folder on the path is held open so it can't be swapped. The final path is checked, and nothing is
  truncated before the checks.
- **The user's real browser profiles are never launched.** The guard now knows Chrome's and Brave's Windows folders.
- **Ports are exclusive on Windows,** so no other local program can take a port that carries the app's token.
- **Token files on Windows.** `chmod 0600` only toggles read-only there. Files under `%USERPROFILE%` keep Windows'
  per-user permissions (the user, SYSTEM and Administrators). This covers the extension's `config.json`, each agent's
  `mcp.json` and everyday-brave's `link.json`. This is documented, not changed.
- **Leftover processes.** A job object ends Claude Code and its MCP children with the app, so no agent keeps running
  unseen.

## Testing

**On the Mac, in the normal suite:**
- **`tests/test_platforms.py`:**
  - `user_data_dir`, `browser_candidates` and `claude_desktop_dir` for `darwin`, `win32` and `linux`, with a fake
    `env` (`LOCALAPPDATA`, `ProgramFiles`, `APPDATA`);
  - `reveal_command` for each system: the Windows string is `explorer /select,"C:\Users\a b\x"` for a path with a
    space;
  - `reveal` returns False when the command can't start (a patched `Popen` raises `OSError`);
  - `pid_alive`: True for this process, False for a child that has exited and been waited for, False for 0 and -1;
  - `lock_file`: a second lock on the same file gives None, and after the first is closed, it works again;
  - `this_computer` and `file_manager` for each system;
  - `replace` retries: a patched `os.replace` that fails twice with `PermissionError` succeeds on the third try when
    `platforms.WINDOWS` is patched to True, and fails at once when it is False.
- **`tests/test_claudecli.py`:**
  - a list argument is kept as is;
  - `AIB_CLAUDE` wins over PATH;
  - with `system="win32"`, a `claude.cmd` or `CLAUDE.BAT` result raises `ClaudeNotUsable` with the install hint, and
    `%USERPROFILE%\.local\bin\claude.exe` is preferred when it exists;
  - `ClaudeBridge.send` yields that message as an error event;
  - `ask_claude` returns it as `OneShot.error`.
- **Extension IDs:**
  - the Windows vectors (Decision 4), computed on the Mac through `ntpath`;
  - the POSIX path is unchanged;
  - the existing headless test (`test_appbrowser.py:116`) still proves the POSIX ID against real Chrome;
  - one string everywhere: for a folder reached through a symbolic link, the setup page, `setup_text` and the reveal
    all show `extension_path(folder)`, the string `extension_id_for` hashes (a guard on the Mac; the Windows case,
    which fails today, is in the CI list below).
- **The Windows launch** (`platforms.WINDOWS` patched to True, a recorder in place of `subprocess.Popen` that keeps
  its arguments and raises `OSError`):
  - the error is "AI Browser could not start: …";
  - the recorded command line equals `chrome_args(binary, profile, False, False, urls)`, so no flag is added or
    removed;
  - with `pipe_install=True`, the pipe message is raised and nothing is started.
- **Finding Chrome:** `AIB_CHROME_BINARY` wins over the usual places.
- **The mismatch report:**
  - a socket with the right token from an unexpected `chrome-extension://` origin is closed with 4403;
  - `origin_mismatch` is set, and `/setup/status` returns it;
  - a wrong token sets nothing.
- **The setup page and the terminal steps:**
  - `setup_page(..., system="win32")` says "File Explorer" and the address-bar step, and has no `⌘`; with
    `system="darwin"` it says "Finder" and `⌘⇧G`;
  - `ready_text`, `setup_text` and `brave_text` with `system="win32"` say `Ctrl+Shift+Y` and "File Explorer", and
    have no `⌘`;
  - `/setup/reveal` answers 501 when the reveal returns False.
- **Wording in Python texts:** guard 4 fails today on `engine.py:315` and the other "this Mac" strings, and passes
  once they use `this_computer()`.
- **The hand-off on Windows:** `CheckGate.handoff(..., system="win32")` has the taskbar line, and with `"darwin"` it
  doesn't.
- **`_bind`:**
  - a second `_bind` on a port whose first socket is listening returns None;
  - with `platforms.WINDOWS` patched to True and a stand-in `socket.SO_EXCLUSIVEADDRUSE` value, a fake socket records
    that option and no `SO_REUSEADDR`.
- **`syncdir`:**
  - an unchanged file keeps its inode and mtime;
  - a stale file is removed;
  - a written file holds exactly the bytes given, so `b"\n"` stays one byte;
  - `prepare_extension` no longer removes the folder.
- **The work folder:** `windows_name_problem` refuses `CON`, `nul.txt`, `a:b`, `x?`, `end.` and `end ` (trailing
  space), and accepts `report.html` and `Ünïcode.txt`.
- **The engine:** `_close_orphans` skips a record whose `pid_alive` raises `OSError`, and closes nothing for it.
- **The command line:**
  - `doctor --setup` with `AIB_CLAUDE`, `AIB_CHROME_BINARY` and `AIB_CHROME_DIR` pointing at temp files reports each
    line. The temp folder's `DevToolsActivePort` names the port of a local test socket: it sees a TCP connection and
    no bytes, so no DevTools request was made;
  - run as a subprocess with `PYTHONIOENCODING=ascii`, it still prints `✓`, read back as UTF-8.
- **Bridge ending:** the test starts the fake claude, then patches `platforms.WINDOWS` to True and calls
  `_end_process`. It closes stdin and waits; the fake claude exits on EOF, and `terminate` is never called. Today
  `terminate` comes at once.
- **`tests/test_portable.py`:** the six guards (Decision 16).
- **The workflow file:** loaded with PyYAML (whose `on:` key loads as `True`):
  - the only trigger is `workflow_dispatch`;
  - `permissions` is `{contents: read}`;
  - the systems are `windows-latest` and `macos-latest`;
  - there is a `uv sync --locked` step and a `pytest` step;
  - the text doesn't contain `secrets.`.

**On Windows, in the manual CI run (in addition to everything above that isn't `posix_only`):**
- **`windows_only` work-folder tests:**
  - a junction inside the work folder pointing outside is refused for reads and writes, and the outside file is
    untouched (same size and mtime);
  - a symbolic link file (the runner has admin rights) is refused;
  - a write to a new file in a fresh sub-folder works;
  - a read of a 10-byte file gives exactly 10 bytes.
- **`windows_only` lock:** a second `lock_file` from another process gives None.
- **`windows_only` port:** a second socket that sets `SO_REUSEADDR` can't bind a port `_bind` holds. Today it can.
- **`windows_only` extension path:** for an `AIB_HOME` reached through a junction, `extension_path` keeps the junction
  path, and the setup page and `setup_text` show that same string. Today they show the resolved path.
- **`windows_only` job,** with a fresh `KillOnCloseJob` in place of `claudecli`'s:
  - a fake claude starts a sleeping grandchild (a new script entry, `{"spawn": seconds}`, which logs
    `{"child": pid}`);
  - the bridge ends the fake claude, and the grandchild is still running, because ending a process on Windows
    doesn't end its children;
  - after the job's `close()`, the grandchild is gone within 5 s.
- **The throwaway-Chrome tests** (`test_chrome.py`, `test_cli.py`) run against `windows-latest`'s Chrome through
  `subprocess.Popen`.
- **The import simulation** is then real: the whole suite imports on Windows.

**On the user's Windows laptop (manual, after the repo exists):**
1. `uv run ai-browser doctor --setup` is all ✓, with Brave noted.
2. **`uv run ai-browser app`:**
   - File Explorer opens with the `extension` folder selected;
   - after Load unpacked, the setup page says **All set**, which confirms the Windows extension ID;
   - **Ctrl+Shift+Y** opens the chat.
3. **The watcher:**
   - loaded in Brave, it connects;
   - the Brain page shows it;
   - no mismatch line is printed.
4. **Everyday Brave:** with the switch ticked, an agent's tabs open in a tab group in Brave, after the user clicks
   **Allow**.
5. **An agent task** completes. After Ctrl-C, Task Manager shows no `claude.exe`, and no `python` running
   `ai_browser.cli mcp`.
6. **Optional, with Docker:** `uv run ai-browser doctor` passes, and `read_file` refuses a link the sandbox shell made
   with `ln -s /work/.. /work/x/up`.
7. **Skills:** if the Claude desktop app is installed, AI Home's skills list shows its claude.ai skills (Decision 13).
8. **The other sub-projects' laptop steps:**
   - mission-visuals' performance pass, in AI Browser (Google Chrome), where Mission Control runs;
   - voice-input on Windows, once the user has chosen to install the extra and download the model.

## Out of scope

- **Installing the extension over the DevTools pipe on Windows** (Chrome's `--remote-debugging-io-pipes` handle switch).
  It can be tried once a Windows CI run is available. Until then, the pipe-based UI tests run on the Mac only.
- **Windows on ARM.** Not tested; the voice extra's wheels may be missing there.
- **Tighter Windows file permissions** (`icacls`, pywin32) for the token files.
- **A Microsoft Store install of the Claude desktop app,** whose data folder Windows redirects. Its claude.ai skills
  don't show until a follow-up adds that folder.
- **An installer, a packaged app, code signing or auto-update** on Windows.
- **Running inside WSL2.** It works with the POSIX code but needs Linux Chrome and Brave inside WSL. Not documented
  beyond one line.
- **Linux desktop polish** beyond the paths in `platforms.py`.
- **A public repo,** CI on push or pull request, scheduled CI, and release builds.
- **Launching the user's Brave or Chrome** from the app, on any OS.
