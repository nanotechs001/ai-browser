# Browser Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One read-only module, `browsers.py`, that says which browsers are installed, whether each one runs with
its remote-debugging switch on, its profiles by name and colour, and which profile holds a copy of the Brain's
watcher. It reads files only, never opens a DevTools session, never writes and never returns an email.

**Architecture:**
- **`platforms.py` gets the facts** (additions only):
  - the table of known browsers (`BrowserFacts`, `KNOWN_BROWSERS`);
  - each browser's data folder (`browser_data_dir`), the app folders, the LaunchServices file and the lock file's
    name;
  - a Windows-safe reader (`open_shared`) and two registry readers that only read.
  - Today's `user_data_dir` and `browser_candidates` become views of the table, with the same results.
- **`browsers.py` (new) gets the logic:** `installed()`, `os_default()`, `profiles()`, `watcher_places()`,
  `devtools_port()`, `listening()`, `running()`, `state()`, `detect()` and `public()`.
  - It is pure: no module state, no cache, no threads, no writes.
  - Every file goes through one capped reader, `_read`, and no public function raises.
- **Callers:** nothing calls `browsers.py` in this wave. Wave B (app-window) and wave C (browser-profile-choice)
  wire it in.

**Tech Stack:**
- Python 3.12 standard library only: `plistlib`, `json`, `ntpath`, `socket` and `unicodedata`, with `ctypes`,
  `msvcrt` and `winreg` inside the Windows branches;
- pytest with:
  - hand-written sample files in `tests/samples/browsers/`;
  - a fake computer under `tmp_path` (the `fake` fixture);
  - a fake `winreg` module for the registry readers.

**Spec:** `docs/superpowers/specs/2026-10-03-browser-detection-design.md`

**Build order and branch:**
1. The cdp-relay branch (one shared connection) is built first and merged into `main`.
2. Wave A runs three branches in parallel, each made from `main` after the relay merge: brain-delegation,
   watcher-safety and this one. Create the branch `browser-detection` from `main` once the relay has merged.
3. Then wave B (app-window), wave C (browser-profile-choice) and wave D (side-chat), each on the merged result of
   everything before it.

The specs number the waves differently. The spec's wave 1 (brain-delegation, watcher-safety) and its track 2B (this
plan) are now wave A, and its track 2A (the relay) lands before wave A. The spec's waves 3, 4 and 5 are this build's
waves B, C and D. Where this plan quotes the spec, "wave 4" means wave C.

Find every edit by the text it quotes, never by a line number: the relay merged first, and the other wave-A branches
may merge before this one. The spec's line numbers are at HEAD `946d5f0`.

**What this plan uses from earlier waves.** Read the merged code before Task 1.
- **From the relay (merged first): nothing by name.**
  - The relay touches none of this plan's code or test files. Its spec's "Files" section says "Not touched: …
    `browsers.py` and `platforms.py` (2B)". It edits the README's switch section, never "Development".
  - It keeps `tests/conftest.py`'s autouse fixture `_never_the_users_browsers` and its helper `symlink_or_skip`.
  - Its link states (`off`, `ready`, `asking`, `connected`, `refused`, `lost`) stay the relay's. Wave C turns the
    links that are `connected` into the browser ids it passes to `public(found, connected=…)`. This plan fixes only
    that parameter's shape: an iterable of browser ids.
- **From brain-delegation and watcher-safety (wave A, in parallel): nothing.**
  - This track adds no page message, so it adds no row to watcher-safety's `MESSAGE_RULES` table.
  - It doesn't use brain-delegation's agent numbers.
  - Neither of them touches this plan's code or test files. Both edit other README sections, never "Development".
- **From today's code** (the relay leaves it as it is):
  - `platforms._system`, `_env`, `_windows_folder`, `_kernel32`, `pid_alive`, `WINDOWS`, `O_BINARY`,
    `user_data_dir` and `browser_candidates`;
  - `tests/conftest.symlink_or_skip`;
  - for the README's hand check only: `ai_browser.appbrowser.extension_id_for` and `ai_browser.config.home`.
- **For the waves after this one:**
  - wave B (app-window) moves `extension_id_for` into `ai_browser.extension_id`. Its plan then changes the import in
    the README command that Task 11 adds;
  - wave B also moves the parts of this plan's `fake` fixture that keep detection off the real files into
    `tests/conftest.py` (the app-window spec, Decision 16). This plan keeps them in `tests/test_browsers.py`. `fake`
    sets `app_folders`, `launch_services_file` and both registry readers itself, so `tests/test_browsers.py` stays
    green under wave B's conftest;
  - the same conftest patches reach `tests/test_platforms.py`, where Tasks 1 and 3 test the real `app_folders`,
    `launch_services_file` and registry readers. Those tests call them through `UNPATCHED`, taken when the file is
    imported, before any fixture runs, so they stay green too. Checked by adding wave B's conftest lines to a replay
    of this plan.

**Checked while writing this plan.** Python 3.12.12 on the Mac, in a scratch copy of the repo. Nothing read the
user's browsers, and the hand check was not run.
1. **Each task's tests:** they fail on the code before the task and pass after it. The build-time files
   (`tests/test_browsers.py`, `tests/test_platforms.py`, `tests/test_portable.py` and `tests/test_chrome.py`) stay
   green.
2. **Deliberate mistakes:** 28 were put into `browsers.py` one at a time, and a test caught each one. Among them:
   - an email let through as a name, or a profile listed twice;
   - the lock's host split at the first dash, or a Windows browser counted twice;
   - a stopped browser's port checked, or a byte sent by the switch check;
   - a file read past the cap, `Path.is_file()` in place of `os.path.isfile()`, or a cookie file opened.
3. **`Path.is_file()` and `Path.exists()` raise `PermissionError`** for a path inside a folder that can't be read.
   Python 3.12 ignores only `ENOENT`, `ENOTDIR`, `EBADF` and `ELOOP` there. The spec names those two methods. This
   plan uses `os.path.isfile`, `os.path.isdir`, `os.path.exists` and `os.path.lexists`: the same `stat` call, without
   the raise (spec Decision 10: "None of them raises").
4. **Two more inputs that would raise:**
   - `os.path.realpath` raises `ValueError` for a path that holds a NUL, so a hostile `path` in Preferences is
     caught;
   - `os.kill` raises `OverflowError` for a pid over 2**31, and `pid_alive` doesn't catch it. So the lock's pid must
     have 1 to 9 digits before `pid_alive` is asked.
5. **`plistlib`** raises `ExpatError` for a cut XML plist and `AttributeError` for a broken `<date>`. That is the
   spec's reason for `except Exception`.
6. **Re-checked in review.** The plan was replayed task by task on a scratch export of HEAD `c9bbcf0`, with each
   task's Step 2 and Step 4 commands. Every task failed first with the error and count it names, and then passed. Not
   run in that replay: `tests/test_chrome.py`, the whole suite and the bench.

**How this plan reads three lines of the spec:**
- **"the text inside the first pair of quotes"** (Decision 3) is read as the command's leading quotes, as in every
  command Windows writes. A quote later in an unquoted command (`…\chrome.exe --flag="x"`) never becomes the
  program.
- **The name:** the `@` check runs before the 64-character cut, so a long name can't hide part of an email past the
  cut.
- **The colour:** `profile_highlight_color` is used, else `default_avatar_fill_color` when the first is missing or
  not a valid colour.

## Global Constraints

Copied from the spec and from the safety rules of this build. Every task's requirements include these.

**The browser's own signs stay:**
- Never auto-click, answer, suppress or hide the browser's "Allow remote debugging?" prompt or its automation bar.
- From the spec: "detection opens no DevTools session, so it can't cause the question or the bar; it never clicks,
  answers, suppresses or hides either one; it never touches the switch."

**No spoofing, no bot-check bypass:** "It launches nothing and changes no browser setting." "Nothing here drives a
page."

**No passwords:**
- "It never opens `Login Data`, `Cookies`, `Web Data`, `History`, the Keychain or DPAPI."
- It reads only:
  - `Info.plist` and the LaunchServices plist;
  - `Local State`, and `Secure Preferences` and `Preferences` in each profile;
  - `DevToolsActivePort`;
  - `SingletonLock` (its link target only) and `lockfile` (whether it exists);
  - the registry keys in Decisions 3 and 4.

**Emails stay put:**
- "Account fields are never read into a result. A name with `@` is replaced by the folder name. `public()` carries
  no path."
- `user_name`, `gaia_name`, `gaia_given_name`, `gaia_id`, `avatar_icon` and every account field are never copied
  into a result.

**Page text is data:**
- "A name is the user's text, read from a browser file: it is cleaned and capped here; wave 4 shows it with
  `textContent` only; if wave 4 ever puts it in the Brain's state summary, it goes there as quoted data, never as part
  of the instructions."
- Wave 4 of the spec is this build's wave C.

**The rest of the build's rules, as they apply here:**
- **Hand-over and take-back are clicks only:** untouched. This module knows nothing about tabs.
- **The Brain only proposes:** "Detection reports, and the user chooses in wave 4. A first guess is only shown.
  Detection never connects to any browser, so it can't connect to one the user didn't pick."
- **Downloads need the user's OK:** this module downloads nothing and adds no dependency. It uses the standard
  library only.

**Read-only and quiet:**
- "It never writes, locks, renames or creates a file in a browser's folder, and never opens the Windows lockfile. On
  Windows it reads with delete shared, so the browser's own saves go through."
- "The only network use is a TCP connect to `127.0.0.1` that sends no bytes."

**Pure:**
- "no module state, no cache, no threads, no writes; every function takes its paths or `system` and `env` as
  arguments, read at call time";
- "No public function raises, whatever the files hold."

**Imports:**
- `browsers.py` imports only the standard library and `platforms`: "no `cdp`, `websockets`, `chrome`,
  `appbrowser`, `http`, `urllib` or `subprocess`";
- `winreg` and `msvcrt` are imported only inside the Windows branches of `platforms.py`.

**Guards that must stay green** (`tests/test_portable.py`):
- `test_no_macos_paths_outside_platforms`: `browsers.py` spells no `Application Support` and no `/Applications/`,
  even in a docstring or a comment, and has no `os.kill(…, 0)`;
- `test_text_io_names_its_encoding`: every read is binary, in the tests too;
- `test_every_module_imports_on_a_windows_like_python`;
- `test_repo_hygiene`: the samples hold no path of this computer. They use the neutral name Alex and `example.com`.

**Files** (spec Decision 13). This track changes only:
- `src/ai_browser/browsers.py` (new);
- `src/ai_browser/platforms.py` (additions; the old helpers keep their results);
- `tests/test_browsers.py` (new) and `tests/samples/browsers/` (new);
- `tests/test_platforms.py` (tests added at the end);
- one paragraph in the README's "Development" section, which no other wave edits.

The README paragraph is this plan's addition to the spec's list: the house format's last task updates the README.
Decision 13 kept the README out because the relay was then built in parallel and edits it. Under the new order the
relay has already merged. Brain-delegation and watcher-safety edit other README sections, so a paragraph inside
"Development" can't conflict with them.

Apart from that README paragraph, it never touches a file on the relay's list. It never touches `chrome.py`, `cli.py`,
`bridge.py`, `tests/conftest.py`, `tests/test_chrome.py` or an earlier spec either.

**House rules:**
- Run tests one file or test at a time: `uv run pytest <path> -q -p no:randomly`. The whole suite runs only in the
  last task.
- Never connect to the user's own Brave or Chrome, and never read their browser files. The by-hand check is the
  user's, after the merge.
- Never touch a running `ai-browser app`.
- Text files name `encoding="utf-8"`, and binary files open with `b`.
- No new text says "this Mac" or "⌘".

## Review Focus

These are the five failures most likely to hit a user that the spec implies but none of its tests cover. Each one
has a test in the task that owns the code.
1. **A Mac whose name has dashes.** macOS names computers like `Alexs-MacBook.local`, so the lock reads
   `Alexs-MacBook.local-23735`. Split at the first dash, every running browser would read as "can't tell". The split
   must be at the last dash, and the browser reads as running. Test: Task 9, `test_a_host_name_with_dashes`.
2. **One Windows browser found by several sources.** Chrome can be installed per machine and per user, listed in
   App Paths and in StartMenuInternet, in other letter case. It must show as one card, with the program found first,
   never as two. Test: Task 5, `test_a_windows_browser_found_twice_is_listed_once`.
3. **A profile name that holds an email among other words, or only invisible characters.** For example
   `Alex (alex@example.com)` or `"‎⁦"`. It shows as the folder's name: no part of an email, and never an
   empty label. Test: Task 7, `test_profile_names_are_cleaned`.
4. **A `Local State` that lists a profile twice, or whose `last_used` names a profile that is dropped.** Each profile
   appears once, and no other profile gets the "last used" mark. Test: Task 7, `test_each_profile_is_listed_once`.
5. **`connected` naming a browser agents can't use, or one that isn't installed.** Wave C passes the relay's ids
   here. Edge keeps its null state, an unknown id adds nothing, and nothing raises. Test: Task 10,
   `test_public_has_no_paths_or_emails` (its last assertion).

## File map

**New:**
- `src/ai_browser/browsers.py`:
  - the dataclasses `Installed`, `Profile`, `WatcherPlace` and `Found`;
  - `MAX_FILE`, `STATES` and the reader `_read`;
  - `by_id`, `data_dir`, `all_data_dirs`, `for_data_dir`, `installed`, `os_default`, `plain_folder`, `profiles`,
    `watcher_places`, `devtools_port`, `listening`, `running`, `state`, `detect` and `public`.
- `tests/test_browsers.py`: the `fake` fixture, the spec's tests 1 to 32, and the Review Focus tests.
- `tests/samples/browsers/`: `brave-info.plist`, `chrome-info.plist`, `launchservices.plist`,
  `brave-local-state.json`, `chrome-local-state.json`, `secure-preferences-watcher.json` and
  `preferences-watcher-disabled.json`.

**Changed:**
- `src/ai_browser/platforms.py`:
  - added: `BrowserFacts`, `KNOWN_BROWSERS`, `browser_data_dir`, `app_folders`, `launch_services_file`,
    `lock_name`, `open_shared`, `windows_browser_commands` and `windows_https_progid`;
  - built from the table: `_MAC_DATA`, `_WINDOWS_DATA`, `_LINUX_DATA`, `_MAC_APPS` and `_WINDOWS_APPS`.
- `tests/test_platforms.py`: the spec's tests 33 to 38.
- `README.md`: one paragraph in "Development".

**The ledger** is `.superpowers/sdd/2026-10-03-browser-detection/progress.md`, which git ignores. Note in it each
task's result and any finding.

---

### Task 1: The table of known browsers and their folders (`platforms.py`)

**Files:**
- Modify: `src/ai_browser/platforms.py`:
  - the imports;
  - the seven lines from `_MAC_DATA = {"chrome": …` to `_WINDOWS_APPS = {…}`;
  - new functions after `browser_candidates`.
- Test: `tests/test_platforms.py` (append)

**Interfaces:**
- Consumes (today's `platforms.py`): `_system(system)`, `_env(env)`, `_windows_folder(env, name, *fallback)`, and
  `user_data_dir` and `browser_candidates`, whose signatures and results don't change.
- Produces:
  - `@dataclass(frozen=True) class BrowserFacts` with the fields `id: str`, `name: str`, `agents: bool`,
    `window: bool`, `inspect: str`, `mac_app: str`, `mac_bundle_id: str`, `mac_data: tuple[str, ...]`,
    `win_exe: tuple[str, ...] | None`, `win_data: tuple[str, ...] | None`, `win_progid: str | None = None` and
    `linux_data: tuple[str, ...] | None = None`;
  - `KNOWN_BROWSERS: tuple[BrowserFacts, ...]`, in display order: `brave`, `brave-beta`, `brave-nightly`, `chrome`,
    `chrome-beta`, `chrome-dev`, `chrome-canary`, `chromium`, `edge`, `arc`, `vivaldi`;
  - `browser_data_dir(facts, system=None, env=None) -> Path | None`;
  - `app_folders(system=None, env=None) -> list[Path]`;
  - `launch_services_file() -> Path`;
  - `lock_name(system=None) -> str`: `"lockfile"` on `win32`, else `"SingletonLock"`;
  - `_MAC_DATA`, `_WINDOWS_DATA`, `_LINUX_DATA`, `_MAC_APPS` and `_WINDOWS_APPS`, built from the `brave` and
    `chrome` rows. `user_data_dir("chrome-beta")` still raises `ValueError`.
- Produces in `tests/test_platforms.py`: `UNPATCHED`, a copy of the module's names taken when the test file is
  imported. Tests of `app_folders`, `launch_services_file` and the registry readers (Task 3) call them through it, so a
  conftest fixture that replaces them for other tests (wave B's) can't change what these tests check.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_platforms.py`. It already imports `os`, `sys`, `Path`, `pytest` and `platforms`, and defines
`WINDOWS_ENV`.

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_platforms.py -q -p no:randomly`

Expected: the three new tests FAIL: `AttributeError: module 'ai_browser.platforms' has no attribute
'KNOWN_BROWSERS'`, `KeyError: 'app_folders'` (not in `UNPATCHED` yet) and `AttributeError: … 'lock_name'`. The other
tests pass.

- [ ] **Step 3: Write the table**

In `src/ai_browser/platforms.py`:

1. After `from collections.abc import Mapping`, add:

```python
from dataclasses import dataclass
```

2. Replace these seven lines (today's two-browser tables):

```python
_MAC_DATA = {"chrome": ("Google", "Chrome"), "brave": ("BraveSoftware", "Brave-Browser")}
_WINDOWS_DATA = {"chrome": ("Google", "Chrome", "User Data"), "brave": ("BraveSoftware", "Brave-Browser", "User Data")}
_LINUX_DATA = {"chrome": ("google-chrome",), "brave": ("BraveSoftware", "Brave-Browser")}
_MAC_APPS = {"chrome": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             "brave": "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"}
_WINDOWS_APPS = {"chrome": ("Google", "Chrome", "Application", "chrome.exe"),
                 "brave": ("BraveSoftware", "Brave-Browser", "Application", "brave.exe")}
```

with the table, and the old tables built from it. Keep two blank lines before `@dataclass` and before
`def _system`.

```python
@dataclass(frozen=True)
class BrowserFacts:
    """One known browser: its names, where its app and its data folder are on each OS, and what AI Browser may do
    with it. `agents`: offered under "Where agents browse" (its remote-debugging switch works as measured in Brave
    and Chrome). `window`: it may draw the app window. `inspect`: the scheme of <scheme>://inspect/#remote-debugging.
    Paths are tuples of parts: `mac_data` under ~/Library/Application Support, `win_exe` under each Windows app
    folder, `win_data` under %LOCALAPPDATA%, `linux_data` under ~/.config. None: the browser has none there."""

    id: str
    name: str
    agents: bool
    window: bool
    inspect: str
    mac_app: str
    mac_bundle_id: str
    mac_data: tuple[str, ...]
    win_exe: tuple[str, ...] | None
    win_data: tuple[str, ...] | None
    win_progid: str | None = None
    linux_data: tuple[str, ...] | None = None


KNOWN_BROWSERS: tuple[BrowserFacts, ...] = (  # display order: Brave, Chrome, Chromium, then the ones agents can't use
    BrowserFacts("brave", "Brave", True, True, "brave", "Brave Browser.app", "com.brave.Browser",
                 ("BraveSoftware", "Brave-Browser"), ("BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                 ("BraveSoftware", "Brave-Browser", "User Data"), win_progid="BraveHTML",
                 linux_data=("BraveSoftware", "Brave-Browser")),
    BrowserFacts("brave-beta", "Brave Beta", True, False, "brave", "Brave Browser Beta.app", "com.brave.Browser.beta",
                 ("BraveSoftware", "Brave-Browser-Beta"),
                 ("BraveSoftware", "Brave-Browser-Beta", "Application", "brave.exe"),
                 ("BraveSoftware", "Brave-Browser-Beta", "User Data")),
    BrowserFacts("brave-nightly", "Brave Nightly", True, False, "brave", "Brave Browser Nightly.app",
                 "com.brave.Browser.nightly", ("BraveSoftware", "Brave-Browser-Nightly"),
                 ("BraveSoftware", "Brave-Browser-Nightly", "Application", "brave.exe"),
                 ("BraveSoftware", "Brave-Browser-Nightly", "User Data")),
    BrowserFacts("chrome", "Chrome", True, True, "chrome", "Google Chrome.app", "com.google.Chrome",
                 ("Google", "Chrome"), ("Google", "Chrome", "Application", "chrome.exe"),
                 ("Google", "Chrome", "User Data"), win_progid="ChromeHTML", linux_data=("google-chrome",)),
    BrowserFacts("chrome-beta", "Chrome Beta", True, False, "chrome", "Google Chrome Beta.app",
                 "com.google.Chrome.beta", ("Google", "Chrome Beta"),
                 ("Google", "Chrome Beta", "Application", "chrome.exe"), ("Google", "Chrome Beta", "User Data")),
    BrowserFacts("chrome-dev", "Chrome Dev", True, False, "chrome", "Google Chrome Dev.app", "com.google.Chrome.dev",
                 ("Google", "Chrome Dev"), ("Google", "Chrome Dev", "Application", "chrome.exe"),
                 ("Google", "Chrome Dev", "User Data")),
    BrowserFacts("chrome-canary", "Chrome Canary", True, False, "chrome", "Google Chrome Canary.app",
                 "com.google.Chrome.canary", ("Google", "Chrome Canary"),
                 ("Google", "Chrome SxS", "Application", "chrome.exe"), ("Google", "Chrome SxS", "User Data")),
    BrowserFacts("chromium", "Chromium", True, False, "chrome", "Chromium.app", "org.chromium.Chromium",
                 ("Chromium",), ("Chromium", "Application", "chrome.exe"), ("Chromium", "User Data")),
    BrowserFacts("edge", "Edge", False, True, "edge", "Microsoft Edge.app", "com.microsoft.edgemac",
                 ("Microsoft Edge",), ("Microsoft", "Edge", "Application", "msedge.exe"),
                 ("Microsoft", "Edge", "User Data"), win_progid="MSEdgeHTM"),
    BrowserFacts("arc", "Arc", False, False, "chrome", "Arc.app", "company.thebrowser.Browser", ("Arc", "User Data"),
                 None, None),  # on Windows an MSIX package: no program path to look for
    BrowserFacts("vivaldi", "Vivaldi", False, False, "chrome", "Vivaldi.app", "com.vivaldi.Vivaldi", ("Vivaldi",),
                 ("Vivaldi", "Application", "vivaldi.exe"), ("Vivaldi", "User Data")),
)

# The two browsers the older helpers (user_data_dir, browser_candidates) know: views of their rows, as before.
_ROWS = {row.id: row for row in KNOWN_BROWSERS}
_MAC_DATA = {name: _ROWS[name].mac_data for name in ("chrome", "brave")}
_WINDOWS_DATA = {name: _ROWS[name].win_data for name in ("chrome", "brave")}
_LINUX_DATA = {name: _ROWS[name].linux_data for name in ("chrome", "brave")}
_MAC_APPS = {name: f"/Applications/{_ROWS[name].mac_app}/Contents/MacOS/{_ROWS[name].mac_app.removesuffix('.app')}"
             for name in ("chrome", "brave")}
_WINDOWS_APPS = {name: _ROWS[name].win_exe for name in ("chrome", "brave")}
```

3. After `browser_candidates` (the function whose docstring is "The usual places the browser's program is
   installed, in the order to try them."), before `def claude_desktop_dir`, add:

```python
def browser_data_dir(facts: BrowserFacts, system: str | None = None, env: Mapping | None = None) -> Path | None:
    """A known browser's folder of profiles on `system`, installed or not; None when it keeps none there. For brave
    and chrome it is user_data_dir()'s folder."""
    system, env = _system(system), _env(env)
    if system == "darwin":
        return Path.home().joinpath("Library", "Application Support", *facts.mac_data)
    if system == "win32":
        if facts.win_data is None:
            return None
        return _windows_folder(env, "LOCALAPPDATA", "AppData", "Local").joinpath(*facts.win_data)
    if facts.linux_data is None:
        return None
    return Path.home().joinpath(".config", *facts.linux_data)


def app_folders(system: str | None = None, env: Mapping | None = None) -> list[Path]:
    """Where apps are installed, in the order to look: /Applications then ~/Applications on macOS; on Windows
    %ProgramFiles%, %ProgramFiles(x86)% and %LOCALAPPDATA%, the ones that are set; none elsewhere."""
    system, env = _system(system), _env(env)
    if system == "darwin":
        return [Path("/Applications"), Path.home() / "Applications"]
    if system == "win32":
        return [Path(env[name]) for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA") if env.get(name)]
    return []


def launch_services_file() -> Path:
    """macOS's record of the default app for each URL scheme (its https entry names the default browser)."""
    return Path.home().joinpath("Library", "Preferences", "com.apple.LaunchServices",
                                "com.apple.launchservices.secure.plist")


def lock_name(system: str | None = None) -> str:
    """The file a running Chromium browser holds in its data folder."""
    return "lockfile" if _system(system) == "win32" else "SingletonLock"
```

`user_data_dir`, `browser_candidates` and `_browser` stay as they are: they read the derived tables, so their results
and their `ValueError` for any other name are unchanged. So `chrome.own_browser_dirs()` is unchanged too.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_platforms.py tests/test_chrome.py -q -p no:randomly`

Expected: PASS. The existing `test_browser_folders_for_each_system`, `test_the_usual_install_places` and
`tests/test_chrome.py` pass unchanged. The Chrome tests start throwaway headless Chromes, and skip without Google
Chrome.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/platforms.py tests/test_platforms.py
git commit -m "feat(platforms): one table of known browsers, their data folders and app folders"
```

### Task 2: A reader that never gets in the browser's way (`platforms.open_shared`)

**Files:**
- Modify: `src/ai_browser/platforms.py`:
  - the `typing` import;
  - `_kernel32()`;
  - a new block before `def pid_alive`.
- Test: `tests/test_platforms.py` (append)

**Interfaces:**
- Consumes: today's `_kernel32()` (cached, Windows only), `WINDOWS` and `O_BINARY`.
- Produces:
  - `open_shared(path) -> BinaryIO`:
    - POSIX: `open(path, "rb")`;
    - Windows: `CreateFileW` with read, write and delete shared, wrapped as a binary file;
    - raises `OSError` when the file can't be opened, like `open`;
  - the constants `GENERIC_READ`, `FILE_SHARE_READ`, `FILE_SHARE_WRITE`, `FILE_SHARE_DELETE`, `OPEN_EXISTING`,
    `FILE_ATTRIBUTE_NORMAL` and `INVALID_HANDLE_VALUE`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_platforms.py`:

```python
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
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_platforms.py::test_open_shared_lets_the_browser_replace_the_file -q -p no:randomly`

Expected: FAIL with `AttributeError: module 'ai_browser.platforms' has no attribute 'open_shared'`.

- [ ] **Step 3: Write `open_shared`**

In `src/ai_browser/platforms.py`:

1. Replace `from typing import IO` with:

```python
from typing import IO, BinaryIO
```

2. In `_kernel32()`, right before its last line (`return kernel32`), add:

```python
    kernel32.CreateFileW.argtypes = (ctypes.c_wchar_p, dword, dword, ctypes.c_void_p, dword, dword, handle)
    kernel32.CreateFileW.restype = handle
```

3. Before `def pid_alive(pid: int) -> bool:`, add:

```python
GENERIC_READ = 0x80000000
FILE_SHARE_READ, FILE_SHARE_WRITE, FILE_SHARE_DELETE = 0x1, 0x2, 0x4
OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL = 3, 0x80
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


def open_shared(path) -> BinaryIO:
    """Open a file for reading only (binary), never in the way of the program that owns it. On Windows a plain open
    doesn't share delete access, so a browser saving its Local State (a new file, then ReplaceFile, which first
    renames the old one away) would fail while we read; this open shares read, write and delete access."""
    if not WINDOWS:
        return open(path, "rb")
    import msvcrt  # Windows only

    kernel32 = _kernel32()
    handle = kernel32.CreateFileW(str(path), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                  None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None)
    if not handle or handle == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | O_BINARY)
    except BaseException:
        kernel32.CloseHandle(handle)
        raise
    try:
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)  # closes the handle with it
        raise
```

The handle is closed before an error goes up: by `CloseHandle` when `open_osfhandle` fails, and by `os.close` (which
closes the handle with it) when `os.fdopen` fails. The file is binary, so `test_text_io_names_its_encoding` stays
green.

- [ ] **Step 4: Run it to see it pass**

Run: `uv run pytest tests/test_platforms.py tests/test_portable.py -q -p no:randomly`

Expected: PASS. On the Mac the test checks the POSIX open. Windows is the case that matters, and the Windows CI runs
it there (Task 11): its second half shows that a plain `open` blocks the rename.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/platforms.py tests/test_platforms.py
git commit -m "feat(platforms): open_shared reads a file while its owner may still replace it"
```

### Task 3: The registry readers, read only (`windows_browser_commands`, `windows_https_progid`)

**Files:**
- Modify: `src/ai_browser/platforms.py` (a new block before `def pid_alive`, after Task 2's `open_shared`)
- Test: `tests/test_platforms.py` (append)

**Interfaces:**
- Consumes: `WINDOWS`. `winreg` is imported inside each function, after the `WINDOWS` check. The tests call the
  readers through Task 1's `UNPATCHED`.
- Produces:
  - `windows_browser_commands() -> list[str]`. Its command strings come, in this order, from:
    - `App Paths\<exe>` for `brave.exe`, `chrome.exe`, `msedge.exe` and `vivaldi.exe`, HKCU before HKLM;
    - `Clients\StartMenuInternet\*\shell\open\command` in HKCU, HKLM and HKLM's `WOW6432Node`.

    It gives `[]` elsewhere.
  - `windows_https_progid() -> str | None`: the first non-empty value of `UserChoiceLatest\ProgId`,
    `UserChoiceLatest` and `UserChoice`, under HKCU's `https` association. It gives None elsewhere.
  - Both open keys with `KEY_READ` only. A key's `OSError` is caught on its own, and a value that isn't a string is
    skipped.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_platforms.py`:

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_platforms.py -q -p no:randomly`

Expected: the two new tests FAIL with `KeyError: 'windows_browser_commands'`: Task 1's `UNPATCHED` doesn't hold it
yet.

- [ ] **Step 3: Write the readers**

In `src/ai_browser/platforms.py`, before `def pid_alive(pid: int) -> bool:` (so after Task 2's `open_shared`), add:

```python
_APP_PATHS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
_START_MENU_INTERNET = r"SOFTWARE\Clients\StartMenuInternet"
_START_MENU_INTERNET_32 = r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet"
_HTTPS_CHOICE = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https"
_REGISTERED_PROGRAMS = ("brave.exe", "chrome.exe", "msedge.exe", "vivaldi.exe")


def windows_browser_commands() -> list[str]:
    """Where Windows' registry says browsers are installed, as command strings: App Paths for each known program
    (current user first), then Windows' own list of registered browsers (StartMenuInternet) in HKCU, HKLM and HKLM's
    32-bit view. Read only: keys are opened with KEY_READ and nothing is ever created, set or deleted. [] elsewhere."""
    if not WINDOWS:
        return []
    import winreg  # Windows only

    user, machine = winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE
    found = [_registry_text(winreg, root, rf"{_APP_PATHS}\{program}", "")
             for program in _REGISTERED_PROGRAMS for root in (user, machine)]
    for root, key in ((user, _START_MENU_INTERNET), (machine, _START_MENU_INTERNET),
                      (machine, _START_MENU_INTERNET_32)):
        found += [_registry_text(winreg, root, rf"{key}\{name}\shell\open\command", "")
                  for name in _registry_subkeys(winreg, root, key)]
    return [command for command in found if command]


def windows_https_progid() -> str | None:
    """The ProgId of the user's default browser for https links (Windows 11 25H2 writes UserChoiceLatest, older
    Windows UserChoice), or None. Read only; None elsewhere."""
    if not WINDOWS:
        return None
    import winreg  # Windows only

    for key in (rf"{_HTTPS_CHOICE}\UserChoiceLatest\ProgId", rf"{_HTTPS_CHOICE}\UserChoiceLatest",
                rf"{_HTTPS_CHOICE}\UserChoice"):
        value = _registry_text(winreg, winreg.HKEY_CURRENT_USER, key, "ProgId")
        if value:
            return value
    return None


def _registry_text(winreg, root, key: str, name: str) -> str | None:
    """A string value, stripped, or None: a missing key, an unreadable one or a value of another type."""
    try:
        with winreg.OpenKey(root, key, 0, winreg.KEY_READ) as handle:
            value, _ = winreg.QueryValueEx(handle, name)
    except OSError:
        return None
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _registry_subkeys(winreg, root, key: str) -> list[str]:
    """The names of a key's subkeys (at most 256), or [] when the key can't be opened."""
    names = []
    try:
        with winreg.OpenKey(root, key, 0, winreg.KEY_READ) as handle:
            for index in range(256):
                try:
                    names.append(winreg.EnumKey(handle, index))
                except OSError:  # no more subkeys
                    break
    except OSError:
        return []
    return names
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_platforms.py tests/test_portable.py -q -p no:randomly`

Expected: PASS. `test_every_module_imports_on_a_windows_like_python` stays green, because `winreg` is imported only
inside the Windows branch.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/platforms.py tests/test_platforms.py
git commit -m "feat(platforms): read-only registry readers for installed browsers and the https default"
```

### Task 4: `browsers.py`: the module, the table lookups and the one safe reader

**Files:**
- Create: `src/ai_browser/browsers.py`
- Create: `tests/test_browsers.py`

**Interfaces:**
- Consumes:
  - Task 1: `platforms.KNOWN_BROWSERS`, `browser_data_dir`, `app_folders` and `launch_services_file`;
  - Task 2: `platforms.open_shared`;
  - Task 3: `platforms.windows_browser_commands` and `windows_https_progid`, which the `fake` fixture patches;
  - `tests/conftest.symlink_or_skip`.
- Produces in `browsers.py`:
  - `MAX_FILE = 16 * 1024 * 1024` and `_system(system) -> str`;
  - `by_id(browser_id) -> BrowserFacts | None`;
  - `data_dir(facts, system=None, env=None) -> Path | None`;
  - `all_data_dirs(system=None, env=None) -> list[Path]`;
  - `for_data_dir(folder, system=None, env=None) -> BrowserFacts | None`;
  - `_path_key(path, system) -> str | None`;
  - `_read(path) -> bytes | None`, which every later task reads through. The tests patch it as a module global.
- Produces in `tests/test_browsers.py`:
  - the imports every later task uses;
  - `SAMPLES` and `AGENTS`;
  - the autouse fixture `fake`. It returns `SimpleNamespace(home, apps, user_apps, local, program_files,
    program_files_x86)`, sets `HOME`, `USERPROFILE`, `LOCALAPPDATA`, `ProgramFiles` and `ProgramFiles(x86)`, replaces
    `platforms.app_folders` and `platforms.launch_services_file` (the fake home's), and turns both registry readers
    off. It sets every one of them itself, so wave B's conftest patches of the same names (the app-window plan) don't
    reach these tests;
  - `recording_reads(monkeypatch) -> list`, which patches `platforms.open_shared` and notes each `read()` size.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_browsers.py`. The module docstring, the imports (later tasks use all of them), the fixture and
the helper come first, then this task's tests:

```python
"""Browser detection (browsers.py), read from sample files in a fake computer under tmp_path. No test reads the
user's real browser files or reaches a real browser: the autouse fixture `fake` points the home folder, the app
folders, the LaunchServices file and the Windows folders at tmp_path, and turns the registry readers off."""

import ast
import contextlib
import dataclasses
import json
import os
import plistlib
import socket
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_browser import browsers, platforms
from conftest import symlink_or_skip

SAMPLES = Path(__file__).parent / "samples" / "browsers"
AGENTS = {"brave", "brave-beta", "brave-nightly", "chrome", "chrome-beta", "chrome-dev", "chrome-canary", "chromium"}


@pytest.fixture(autouse=True)
def fake(tmp_path, monkeypatch):
    """A fake computer: its home, macOS's two app folders and LaunchServices file, Windows' three app folders, and an
    empty registry. It sets each one itself, so a conftest fixture that patches the same names can't change them."""
    home, apps = tmp_path / "home", tmp_path / "Applications"
    local, program_files = tmp_path / "Local", tmp_path / "Program Files"
    program_files_x86 = tmp_path / "Program Files (x86)"
    for folder in (home, apps, local, program_files, program_files_x86):
        folder.mkdir()
    for name, folder in (("HOME", home), ("USERPROFILE", home), ("LOCALAPPDATA", local),
                         ("ProgramFiles", program_files), ("ProgramFiles(x86)", program_files_x86)):
        monkeypatch.setenv(name, str(folder))
    launch_services = home.joinpath("Library", "Preferences", "com.apple.LaunchServices",
                                    "com.apple.launchservices.secure.plist")  # where macOS keeps it in a home

    def app_folders(system=None, env=None):
        system = system or sys.platform
        if system == "darwin":
            return [apps, home / "Applications"]
        if system == "win32":
            return [program_files, program_files_x86, local]
        return []

    monkeypatch.setattr(platforms, "app_folders", app_folders)
    monkeypatch.setattr(platforms, "launch_services_file", lambda: launch_services)
    monkeypatch.setattr(platforms, "windows_browser_commands", lambda: [])
    monkeypatch.setattr(platforms, "windows_https_progid", lambda: None)
    return SimpleNamespace(home=home, apps=apps, user_apps=home / "Applications", local=local,
                           program_files=program_files, program_files_x86=program_files_x86)


def recording_reads(monkeypatch) -> list:
    """platforms.open_shared, patched so that every read() call notes its size argument in the returned list."""
    reads, real = [], platforms.open_shared

    class Handle:
        def __init__(self, path):
            self.handle = real(path)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.handle.close()

        def fileno(self):
            return self.handle.fileno()

        def read(self, size=-1):
            reads.append(size)
            return self.handle.read(size)

    monkeypatch.setattr(platforms, "open_shared", Handle)
    return reads


# The table, and the module's own rules (Task 4)


def test_the_tests_never_read_the_real_browsers(fake, tmp_path):
    assert Path.home() == fake.home
    for system in ("darwin", "win32", "linux"):
        assert all(folder.is_relative_to(tmp_path) for folder in platforms.app_folders(system))
        assert all(folder.is_relative_to(tmp_path) for folder in browsers.all_data_dirs(system))
    assert platforms.launch_services_file().is_relative_to(tmp_path)
    assert platforms.windows_browser_commands() == [] and platforms.windows_https_progid() is None


def test_the_table_lists_each_browser_once():
    ids = [facts.id for facts in platforms.KNOWN_BROWSERS]
    assert ids == ["brave", "brave-beta", "brave-nightly", "chrome", "chrome-beta", "chrome-dev", "chrome-canary",
                   "chromium", "edge", "arc", "vivaldi"]  # each once, Brave first; no Opera, Firefox or Safari
    assert {facts.id for facts in platforms.KNOWN_BROWSERS if facts.agents} == AGENTS
    assert {facts.id for facts in platforms.KNOWN_BROWSERS if facts.window} == {"brave", "chrome", "edge"}
    assert all(facts.mac_data and facts.win_data for facts in platforms.KNOWN_BROWSERS if facts.agents)
    assert browsers.by_id("chrome-canary").name == "Chrome Canary" and browsers.by_id("opera") is None
    inspect = {facts.id: facts.inspect for facts in platforms.KNOWN_BROWSERS}
    assert inspect["brave-nightly"] == "brave" and inspect["edge"] == "edge" and inspect["chromium"] == "chrome"


def test_the_old_folder_helpers_read_the_table():
    env = {"LOCALAPPDATA": "C:\\Users\\Alex\\AppData\\Local", "ProgramFiles": "C:\\Program Files"}
    for name in ("brave", "chrome"):
        for system, given in (("darwin", None), ("win32", env), ("linux", None)):
            assert platforms.user_data_dir(name, system, given) == browsers.data_dir(browsers.by_id(name), system,
                                                                                      given)
    assert platforms.browser_candidates("brave", "darwin") == [
        Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")]
    assert platforms.browser_candidates("chrome", "win32", env) == [
        Path("C:\\Program Files", "Google", "Chrome", "Application", "chrome.exe"),
        Path("C:\\Users\\Alex\\AppData\\Local", "Google", "Chrome", "Application", "chrome.exe")]
    with pytest.raises(ValueError):
        platforms.user_data_dir("chrome-beta")


def test_for_data_dir_names_the_browser(fake, tmp_path):
    brave = browsers.by_id("brave")
    assert browsers.for_data_dir(browsers.data_dir(brave, "darwin"), "darwin") is brave
    env = {"LOCALAPPDATA": str(fake.local)}
    other_case = fake.local / "bravesoftware" / "BRAVE-BROWSER" / "user data"
    assert browsers.for_data_dir(other_case, "win32", env) is brave  # Windows paths ignore case
    linux = browsers.data_dir(brave, "linux")
    assert browsers.for_data_dir(linux, "linux") is brave
    if os.name != "nt":  # Windows' realpath restores the case found on disk
        assert browsers.for_data_dir(linux.parent / "brave-browser", "linux") is None
    assert browsers.for_data_dir(tmp_path / "elsewhere", "darwin") is None
    assert browsers.for_data_dir("bad\0folder", "darwin") is None
    for name in ("edge", "arc", "vivaldi"):  # installed or not, every known folder is listed
        assert browsers.data_dir(browsers.by_id(name), "darwin") in browsers.all_data_dirs("darwin")


def test_the_reader_reads_only_small_regular_files(tmp_path, monkeypatch):
    small = tmp_path / "small"
    small.write_bytes(b"{}")
    assert browsers._read(small) == b"{}"
    assert browsers._read(tmp_path / "missing") is None and browsers._read(tmp_path) is None  # a folder
    if hasattr(os, "mkfifo"):
        os.mkfifo(tmp_path / "pipe")
        assert browsers._read(tmp_path / "pipe") is None  # a plain open would wait for a writer forever
    huge = tmp_path / "huge"
    huge.write_bytes(b"")
    os.truncate(huge, 17 * 1024 * 1024)  # sparse where the file system allows it
    reads = recording_reads(monkeypatch)
    assert browsers._read(huge) is None and reads == []  # too big: never read
    assert browsers._read(small) == b"{}" and reads == [browsers.MAX_FILE + 1]  # one read, capped


def test_a_file_that_grows_while_it_is_read_is_not_used(tmp_path, monkeypatch):
    grown, before = tmp_path / "Local State", tmp_path / "before"
    grown.write_bytes(b"x" * 20)
    before.write_bytes(b"x" * 4)
    real = platforms.open_shared

    class SizeBeforeTheWrite:  # fstat sees the file as it was, read() sees it after the browser's write
        def __init__(self, path):
            self.handle, self.old = real(path), real(before)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.handle.close()
            self.old.close()

        def fileno(self):
            return self.old.fileno()

        def read(self, size=-1):
            return self.handle.read(size)

    monkeypatch.setattr(browsers, "MAX_FILE", 8)
    monkeypatch.setattr(platforms, "open_shared", SizeBeforeTheWrite)
    assert browsers._read(grown) is None


def test_browsers_imports_no_connection_code():
    tree = ast.parse(Path(browsers.__file__).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {part for alias in node.names for part in alias.name.split(".")}
        elif isinstance(node, ast.ImportFrom):
            names |= set((node.module or "").split("."))
            if not node.module:  # from . import chrome
                names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
            names.add("__import__")
    forbidden = {"cdp", "websockets", "chrome", "appbrowser", "http", "urllib", "aiohttp", "subprocess", "importlib",
                 "__import__"}
    assert not names & forbidden, names & forbidden
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_browsers.py -q -p no:randomly`

Expected: ERROR at collection, `ImportError: cannot import name 'browsers' from 'ai_browser'`.

- [ ] **Step 3: Create the module**

Create `src/ai_browser/browsers.py`. The docstring says "the app folders" and "the data folder", never the macOS
spelling: `test_no_macos_paths_outside_platforms` reads docstrings too.

```python
"""Which browsers are installed, whether each one runs with its remote-debugging switch on, its profiles (name and
colour) and which profile holds a copy of the Brain's watcher: found by reading files only.

Pure, like platforms.py: no module state, no cache, no threads, no writes. Every function takes its paths, or
`system` and `env`, read at call time, so the Mac's tests can ask for any OS. The OS facts (the app folders, the data
folder, the LaunchServices file, the registry) come from platforms.py; this module never spells them.

Every public function returns a safe value for a missing, broken, huge or hostile file, and never raises. The only
network use is a TCP connect to 127.0.0.1 that sends no bytes: no DevTools session is opened, so the browser never
asks "Allow remote debugging?" and shows no automation bar because of it. Account fields (emails, account names) are
never read into a result, and nothing here starts a program."""

from __future__ import annotations

import json
import ntpath
import os
import plistlib
import re
import socket
import sys
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from . import platforms

MAX_FILE = 16 * 1024 * 1024  # bytes: a bigger Local State or Preferences file is not read at all


def _system(system: str | None) -> str:
    return system or sys.platform


def by_id(browser_id: str) -> platforms.BrowserFacts | None:
    """The table's row for an id ("brave", "chrome-beta", …), or None."""
    return next((facts for facts in platforms.KNOWN_BROWSERS if facts.id == browser_id), None)


def data_dir(facts: platforms.BrowserFacts, system: str | None = None, env: Mapping | None = None) -> Path | None:
    """The browser's folder of profiles on `system`, installed or not (None when it keeps none there)."""
    return platforms.browser_data_dir(facts, system, env)


def all_data_dirs(system: str | None = None, env: Mapping | None = None) -> list[Path]:
    """Every known browser's folder of profiles on `system`, installed or not, in the table's order."""
    return [folder for facts in platforms.KNOWN_BROWSERS if (folder := data_dir(facts, system, env)) is not None]


def _path_key(path, system: str) -> str | None:
    """A path as compared here: resolved, and on Windows without regard to case; None for a path that can't be (it
    holds a NUL)."""
    try:
        resolved = os.path.realpath(path)
    except (OSError, ValueError):
        return None
    return ntpath.normcase(resolved) if system == "win32" else resolved


def for_data_dir(folder, system: str | None = None, env: Mapping | None = None) -> platforms.BrowserFacts | None:
    """Which known browser owns this data folder, or None."""
    system = _system(system)
    wanted = _path_key(folder, system)
    if wanted is None:
        return None
    for facts in platforms.KNOWN_BROWSERS:
        own = data_dir(facts, system, env)
        if own is not None and _path_key(own, system) == wanted:
            return facts
    return None


def _read(path) -> bytes | None:
    """A file's bytes, or None. Only a regular file is opened, so a pipe or a device can't hang it; the open lets the
    browser replace the file meanwhile (platforms.open_shared); a file over MAX_FILE is never read."""
    try:
        if not os.path.isfile(path):
            return None
        with platforms.open_shared(path) as handle:
            if os.fstat(handle.fileno()).st_size > MAX_FILE:
                return None
            data = handle.read(MAX_FILE + 1)
    except (OSError, ValueError):
        return None
    return data if len(data) <= MAX_FILE else None  # it grew past the limit while we looked
```

The imports are the spec's full list. Tasks 5 to 10 use the ones this task doesn't.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_browsers.py tests/test_portable.py -q -p no:randomly`

Expected: PASS, including `test_no_macos_paths_outside_platforms`, `test_text_io_names_its_encoding` and
`test_every_module_imports_on_a_windows_like_python`. The named-pipe line is skipped where `os.mkfifo` doesn't exist
(Windows).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/browsers.py tests/test_browsers.py
git commit -m "feat(browsers): the detection module, its table lookups and one capped, shared reader"
```

### Task 5: Which browsers are installed (macOS and Windows)

**Files:**
- Modify: `src/ai_browser/browsers.py` (append)
- Create: `tests/samples/browsers/brave-info.plist`, `tests/samples/browsers/chrome-info.plist`
- Test: `tests/test_browsers.py` (append)

**Interfaces:**
- Consumes:
  - Task 4: `_read`, `_system` and `data_dir`;
  - Task 1: `platforms.app_folders` and `KNOWN_BROWSERS` (`mac_app`, `mac_bundle_id` and `win_exe`);
  - Task 3: `platforms.windows_browser_commands`.
- Produces in `browsers.py`:
  - `@dataclass(frozen=True) class Installed(facts, binary: Path, bundle: Path | None, version: str | None,
    data_dir: Path)`, with the properties `id`, `name`, `agents`, `window` and `inspect_address`
    (`"<scheme>://inspect/#remote-debugging"`);
  - `installed(system=None, env=None, folders=None, commands=None) -> list[Installed]`, in table order. It gives `[]`
    on Linux;
  - `_plist(path)`: the parsed plist, or None. Task 6 reads through it.
- Produces in `tests/test_browsers.py`:
  - `sample(name) -> bytes`;
  - `info_plist(bundle_id, program, version="1.0", fmt=plistlib.FMT_XML) -> bytes`;
  - `mac_app(folder, app, info, program) -> Path`, which returns the `.app` folder;
  - `windows_program(root, *parts) -> Path`.

- [ ] **Step 1: Write the samples and the failing tests**

Create `tests/samples/browsers/brave-info.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDisplayName</key>
	<string>Brave Browser</string>
	<key>CFBundleExecutable</key>
	<string>Brave Browser</string>
	<key>CFBundleIdentifier</key>
	<string>com.brave.Browser</string>
	<key>CFBundleShortVersionString</key>
	<string>152.1.94.121</string>
	<key>LSMinimumSystemVersion</key>
	<string>12.0</string>
</dict>
</plist>
```

Create `tests/samples/browsers/chrome-info.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDisplayName</key>
	<string>Google Chrome</string>
	<key>CFBundleExecutable</key>
	<string>Google Chrome</string>
	<key>CFBundleIdentifier</key>
	<string>com.google.Chrome</string>
	<key>CFBundleShortVersionString</key>
	<string>154.0.8037.93</string>
	<key>LSMinimumSystemVersion</key>
	<string>12.0</string>
</dict>
</plist>
```

Append to `tests/test_browsers.py`:

```python
# Installed apps on macOS (Task 5)


def sample(name: str) -> bytes:
    return (SAMPLES / name).read_bytes()


def info_plist(bundle_id: str, program: str, version: str = "1.0", fmt=plistlib.FMT_XML) -> bytes:
    return plistlib.dumps({"CFBundleIdentifier": bundle_id, "CFBundleExecutable": program,
                           "CFBundleShortVersionString": version}, fmt=fmt)


def mac_app(folder: Path, app: str, info: bytes | None, program: str | None) -> Path:
    """An app bundle in `folder`: Contents/Info.plist (unless `info` is None) and Contents/MacOS/<program>."""
    bundle = folder / app
    (bundle / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
    if info is not None:
        (bundle / "Contents" / "Info.plist").write_bytes(info)
    if program:
        (bundle / "Contents" / "MacOS" / program).write_bytes(b"#!/bin/sh\n")
    return bundle


def test_an_empty_fake_computer_has_no_browsers():
    assert browsers.installed() == [] and browsers.installed(system="darwin") == []
    assert browsers.installed(system="win32") == [] and browsers.installed(system="linux") == []


def test_mac_installed_means_the_app_with_its_bundle_id(fake):
    brave = mac_app(fake.apps, "Brave Browser.app", sample("brave-info.plist"), "Brave Browser")
    chrome = mac_app(fake.apps, "Google Chrome.app", sample("chrome-info.plist"), "Google Chrome")
    support = fake.home / "Library" / "Application Support"
    for leftover in ("Arc/User Data", "Chromium", "Microsoft Edge", "Vivaldi", "com.operasoftware.Opera"):
        (support / leftover).mkdir(parents=True)  # data folders of apps that are gone prove nothing
    found = browsers.installed(system="darwin")
    assert [item.id for item in found] == ["brave", "chrome"]
    assert (found[0].binary, found[0].bundle) == (brave / "Contents" / "MacOS" / "Brave Browser", brave)
    assert (found[1].binary, found[1].bundle) == (chrome / "Contents" / "MacOS" / "Google Chrome", chrome)
    assert (found[0].version, found[1].version) == ("152.1.94.121", "154.0.8037.93")
    assert found[0].data_dir == support / "BraveSoftware" / "Brave-Browser"
    assert found[1].data_dir == support / "Google" / "Chrome"
    assert (found[0].name, found[0].agents, found[0].window, found[0].inspect_address) == (
        "Brave", True, True, "brave://inspect/#remote-debugging")


def test_mac_apps_in_the_users_applications_folder(fake):
    canary = mac_app(fake.user_apps, "Google Chrome Canary.app",
                     info_plist("com.google.Chrome.canary", "Google Chrome Canary"), "Google Chrome Canary")
    found = browsers.installed(system="darwin")
    assert [(item.id, item.bundle) for item in found] == [("chrome-canary", canary)]


BROKEN_DATE = (b'<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict>'
               b"<key>CFBundleIdentifier</key><string>com.brave.Browser</string>"
               b"<key>CFBundleExecutable</key><string>Brave Browser</string>"
               b"<key>Built</key><date>not a date</date></dict></plist>")


@pytest.mark.parametrize("info, program, counted", [
    pytest.param(lambda: info_plist("com.example.NotBrave", "Brave Browser"), "Brave Browser", False,
                 id="another bundle id"),
    pytest.param(lambda: None, "Brave Browser", False, id="no Info.plist"),
    pytest.param(lambda: b"\x00\xffgarbage", "Brave Browser", False, id="garbage"),
    pytest.param(lambda: sample("brave-info.plist")[:200], "Brave Browser", False, id="cut XML (ExpatError)"),
    pytest.param(lambda: BROKEN_DATE, "Brave Browser", False, id="broken date (AttributeError)"),
    pytest.param(lambda: info_plist("com.brave.Browser", "../../x"), "Brave Browser", False,
                 id="its program is outside the app"),
    pytest.param(lambda: sample("brave-info.plist"), None, False, id="no program"),
    pytest.param(lambda: info_plist("com.brave.Browser", "Brave Browser", fmt=plistlib.FMT_BINARY), "Brave Browser",
                 True, id="binary plist"),
    pytest.param(lambda: info_plist("com.brave.browser", "Brave Browser"), "Brave Browser", True,
                 id="bundle id in lower case"),
])
def test_a_mac_app_that_isnt_the_browser_is_skipped(fake, info, program, counted):
    bundle = mac_app(fake.apps, "Brave Browser.app", info(), program)
    (bundle / "x").write_bytes(b"#!/bin/sh\n")  # what "../../x" would name
    assert [item.id for item in browsers.installed(system="darwin")] == (["brave"] if counted else [])


# Installed programs on Windows (Task 5, Windows)


def windows_program(root: Path, *parts: str) -> Path:
    program = root.joinpath(*parts)
    program.parent.mkdir(parents=True, exist_ok=True)
    program.write_bytes(b"MZ")
    return program


def test_windows_installed_from_the_app_folders(fake):
    brave = windows_program(fake.local, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
    chrome = windows_program(fake.program_files, "Google", "Chrome", "Application", "chrome.exe")
    edge = windows_program(fake.program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe")
    found = browsers.installed(system="win32")
    assert [(item.id, item.binary) for item in found] == [("brave", brave), ("chrome", chrome), ("edge", edge)]
    assert [item.agents for item in found] == [True, True, False]
    assert all(item.bundle is None and item.version is None for item in found)
    assert [item.data_dir for item in found] == [fake.local / "BraveSoftware" / "Brave-Browser" / "User Data",
                                                 fake.local / "Google" / "Chrome" / "User Data",
                                                 fake.local / "Microsoft" / "Edge" / "User Data"]


def test_windows_installed_from_the_registry(tmp_path):
    beta = windows_program(tmp_path / "Elsewhere", "Google", "Chrome Beta", "Application", "chrome.exe")
    local = tmp_path / "Other Local"
    chromium = windows_program(local, "Chromium", "Application", "CHROME.EXE")
    beta_command = f'"{beta.as_posix()}" --single-argument %1'
    commands = [beta_command,
                "%localappdata%/Chromium/Application/CHROME.EXE -- %1",  # unquoted, other letter case
                f'"{(tmp_path / "Gone" / "Google" / "Chrome" / "Application" / "chrome.exe").as_posix()}" %1',
                "not a path",
                beta_command]
    found = browsers.installed(system="win32", env={"LOCALAPPDATA": str(local)}, folders=[], commands=commands)
    assert [(item.id, item.binary) for item in found] == [("chrome-beta", beta), ("chromium", chromium)]


def test_canary_is_never_taken_for_chrome(tmp_path):
    canary = windows_program(tmp_path / "Apps", "Google", "Chrome SxS", "Application", "chrome.exe")
    found = browsers.installed(system="win32", folders=[], commands=[f'"{canary.as_posix()}"'])
    assert [item.id for item in found] == ["chrome-canary"]


def test_a_windows_browser_found_twice_is_listed_once(fake):
    machine = windows_program(fake.program_files, "Google", "Chrome", "Application", "chrome.exe")
    user = windows_program(fake.local, "Google", "Chrome", "Application", "chrome.exe")
    commands = [f'"{user}" --single-argument %1', str(user).upper()]
    found = browsers.installed(system="win32", commands=commands)
    assert [(item.id, item.binary) for item in found] == [("chrome", machine)]  # where it was found first


def test_a_windows_app_folder_is_a_path_not_a_command(tmp_path):
    local = tmp_path / "alex.exeter" / "AppData" / "Local %TEMP%"  # a user's folder may hold ".exe" or "%"
    brave = windows_program(local, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
    env = {"LOCALAPPDATA": str(local), "TEMP": str(tmp_path / "Temp")}
    found = browsers.installed(system="win32", env=env, folders=[local], commands=[])
    assert [(item.id, item.binary) for item in found] == [("brave", brave)]  # never cut at "alex.exe", never expanded
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_browsers.py -q -p no:randomly`

Expected: the 17 new tests FAIL with `AttributeError: module 'ai_browser.browsers' has no attribute 'installed'`.
Task 4's tests pass.

- [ ] **Step 3: Write `installed()`**

Append to `src/ai_browser/browsers.py`:

```python
@dataclass(frozen=True)
class Installed:
    """A known browser whose app is on this computer: its program, its .app on macOS (None elsewhere), its version
    from the app's Info.plist (None on Windows) and its data folder."""

    facts: platforms.BrowserFacts
    binary: Path
    bundle: Path | None
    version: str | None
    data_dir: Path

    @property
    def id(self) -> str:
        return self.facts.id

    @property
    def name(self) -> str:
        return self.facts.name

    @property
    def agents(self) -> bool:
        return self.facts.agents

    @property
    def window(self) -> bool:
        return self.facts.window

    @property
    def inspect_address(self) -> str:
        return f"{self.facts.inspect}://inspect/#remote-debugging"


def _plist(path):
    """A plist file (XML or binary) as Python data, or None."""
    data = _read(path)
    if data is None:
        return None
    try:
        return plistlib.loads(data)
    except Exception:  # a cut XML plist raises ExpatError, a broken <date> AttributeError: not only ValueError
        return None


def _plain_file_name(name) -> bool:
    return isinstance(name, str) and name not in ("", ".", "..") and "/" not in name and "\0" not in name


def installed(system: str | None = None, env: Mapping | None = None, folders=None, commands=None) -> list[Installed]:
    """The known browsers whose app is on this computer, in the table's order. macOS: the .app in the app folders,
    with the row's bundle id and its program. Windows: the row's program under the app folders, or a program the
    registry names (`commands`), that is a file. Elsewhere: []."""
    system = _system(system)
    env = os.environ if env is None else env
    if system not in ("darwin", "win32"):
        return []
    if folders is None:
        folders = platforms.app_folders(system, env)
    if system == "darwin":
        return _mac_installed(folders, env)
    if commands is None:
        commands = platforms.windows_browser_commands()
    return _windows_installed(folders, commands, env)


def _mac_installed(folders, env: Mapping) -> list[Installed]:
    found = []
    for facts in platforms.KNOWN_BROWSERS:
        for folder in folders:
            bundle = Path(folder) / facts.mac_app
            info = _plist(bundle / "Contents" / "Info.plist")
            if not isinstance(info, dict):
                continue
            ident, program = info.get("CFBundleIdentifier"), info.get("CFBundleExecutable")
            if not isinstance(ident, str) or ident.lower() != facts.mac_bundle_id.lower():
                continue
            if not _plain_file_name(program) or not os.path.isfile(bundle / "Contents" / "MacOS" / program):
                continue
            version = info.get("CFBundleShortVersionString")
            version = version if isinstance(version, str) and len(version) <= 32 else None
            found.append(Installed(facts, bundle / "Contents" / "MacOS" / program, bundle, version,
                                   data_dir(facts, "darwin", env)))
            break  # the first app folder that has it wins
    return found


def _program(command: str) -> str | None:
    """The program in a command line: the text inside its leading quotes, else everything up to and including the
    first ".exe" in any letter case."""
    text = command.strip()
    if text.startswith('"'):
        end = text.find('"', 1)
        if end < 0:
            return None
        return text[1:end].strip() or None
    match = re.search(r"\.exe", text, re.IGNORECASE)
    return text[:match.end()] if match else None


def _expand(text: str, env: Mapping) -> str:
    """%NAME% from env, the name looked up without regard to case, as Windows does; an unknown one stays."""
    values = {str(key).lower(): str(value) for key, value in env.items()}
    return re.sub(r"%([^%]+)%", lambda match: values.get(match.group(1).lower(), match.group(0)), text)


def _windows_row(program: str) -> platforms.BrowserFacts | None:
    """The row whose program path is the tail of `program`, part by part without regard to case, with either
    separator; the longest tail wins."""
    parts = [part.lower() for part in re.split(r"[\\/]+", program) if part]
    best = None
    for facts in platforms.KNOWN_BROWSERS:
        tail = [part.lower() for part in facts.win_exe or ()]
        if tail and parts[-len(tail):] == tail and (best is None or len(tail) > len(best.win_exe)):
            best = facts
    return best


def _windows_installed(folders, commands, env: Mapping) -> list[Installed]:
    # The app folders give paths, used as they are; only the registry's command lines are cut down to their program
    # and have %NAME% expanded, so a user folder whose name holds ".exe" or "%" is still found.
    programs = [str(Path(folder).joinpath(*facts.win_exe))
                for folder in folders for facts in platforms.KNOWN_BROWSERS if facts.win_exe]
    for command in commands:
        program = _program(command) if isinstance(command, str) else None
        if program is not None:
            programs.append(_expand(program, env))
    binaries: dict[str, Path] = {}
    for program in programs:
        facts = _windows_row(program)
        if facts is None or facts.id in binaries or not os.path.isfile(program):
            continue
        binaries[facts.id] = Path(program)  # a browser found twice is counted once, where it was found first
    return [Installed(facts, binaries[facts.id], None, None, data_dir(facts, "win32", env))
            for facts in platforms.KNOWN_BROWSERS if facts.id in binaries]
```

- `os.path.isfile` is used, not `Path.is_file()`, because it never raises ("Checked while writing this plan", fact
  3).
- A row with `win_exe` None (Arc) is never looked for on Windows.
- An app folder's path never goes through `_program` or `_expand`. Those two are for command lines. Cutting a path at
  its first `.exe` would turn `C:\Users\alex.exeter\…\brave.exe` into `C:\Users\alex.exe`, and Brave under
  `%LOCALAPPDATA%` would be missed (`test_a_windows_app_folder_is_a_path_not_a_command`).

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_browsers.py tests/test_portable.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/browsers.py tests/test_browsers.py tests/samples/browsers/brave-info.plist tests/samples/browsers/chrome-info.plist
git commit -m "feat(browsers): installed() finds the apps (macOS) and programs (Windows), not leftover data folders"
```

### Task 6: The system's default browser, a first guess only (`os_default`)

**Files:**
- Modify: `src/ai_browser/browsers.py` (append)
- Create: `tests/samples/browsers/launchservices.plist`
- Test: `tests/test_browsers.py` (append)

**Interfaces:**
- Consumes:
  - Task 5: `_plist`;
  - Task 1: `platforms.launch_services_file()`;
  - Task 3: `platforms.windows_https_progid()`;
  - the rows' `mac_bundle_id` and `win_progid`.
- Produces: `os_default(system=None, env=None) -> str | None`, a browser id.
  - It reads only the first `https` entry.
  - It never picks or connects to anything: wave B uses it for "Auto", and wave C for its first guess.

- [ ] **Step 1: Write the sample and the failing tests**

Create `tests/samples/browsers/launchservices.plist`. The `mailto` entry comes first and names Chrome, so a reader
that takes the first entry fails the test:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>LSHandlers</key>
	<array>
		<dict>
			<key>LSHandlerPreferredVersions</key>
			<dict>
				<key>LSHandlerRoleAll</key>
				<string>-</string>
			</dict>
			<key>LSHandlerRoleAll</key>
			<string>com.google.chrome</string>
			<key>LSHandlerURLScheme</key>
			<string>mailto</string>
		</dict>
		<dict>
			<key>LSHandlerPreferredVersions</key>
			<dict>
				<key>LSHandlerRoleAll</key>
				<string>-</string>
			</dict>
			<key>LSHandlerRoleAll</key>
			<string>com.brave.browser</string>
			<key>LSHandlerURLScheme</key>
			<string>https</string>
		</dict>
		<dict>
			<key>LSHandlerContentType</key>
			<string>public.html</string>
			<key>LSHandlerPreferredVersions</key>
			<dict>
				<key>LSHandlerRoleAll</key>
				<string>-</string>
			</dict>
			<key>LSHandlerRoleAll</key>
			<string>com.brave.browser</string>
		</dict>
	</array>
</dict>
</plist>
```

Append to `tests/test_browsers.py`:

```python
# The default browser (Task 6)


def test_an_empty_fake_computer_has_no_default_browser():
    assert [browsers.os_default(system) for system in (None, "darwin", "win32", "linux")] == [None] * 4


def test_os_default_on_the_mac():
    record = platforms.launch_services_file()
    record.parent.mkdir(parents=True)
    record.write_bytes(sample("launchservices.plist"))
    assert browsers.os_default("darwin") == "brave"
    handlers = plistlib.loads(sample("launchservices.plist"))
    record.write_bytes(plistlib.dumps(handlers, fmt=plistlib.FMT_BINARY))  # as macOS writes it
    assert browsers.os_default("darwin") == "brave"
    mail_only = {"LSHandlers": [entry for entry in handlers["LSHandlers"]
                                if entry.get("LSHandlerURLScheme") == "mailto"]}
    record.write_bytes(plistlib.dumps(mail_only))
    assert browsers.os_default("darwin") is None  # the mail handler (Chrome here) is never taken for the browser
    record.write_bytes(b"\x00garbage")
    assert browsers.os_default("darwin") is None
    record.write_bytes(plistlib.dumps({"LSHandlers": [{"LSHandlerURLScheme": "https",
                                                       "LSHandlerRoleAll": "org.mozilla.firefox"}]}))
    assert browsers.os_default("darwin") is None


@pytest.mark.parametrize("progid, expected", [
    ("ChromeHTML", "chrome"), ("BraveHTML", "brave"), ("MSEdgeHTM", "edge"), ("ChromeHTML.ABC123", "chrome"),
    ("bravehtml", "brave"), ("ChromeBHTML", None), ("FirefoxURL-308046B0AF4A39CB", None), (None, None)])
def test_os_default_on_windows(monkeypatch, progid, expected):
    monkeypatch.setattr(platforms, "windows_https_progid", lambda: progid)
    assert browsers.os_default("win32") == expected
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_browsers.py -q -p no:randomly`

Expected: the 10 new tests FAIL with `AttributeError: module 'ai_browser.browsers' has no attribute 'os_default'`.

- [ ] **Step 3: Write `os_default()`**

Append to `src/ai_browser/browsers.py`:

```python
def os_default(system: str | None = None, env: Mapping | None = None) -> str | None:
    """The id of the system's default browser for https links, or None. Only a first guess, for the user to confirm:
    macOS reads LaunchServices' https entry, Windows the https ProgId."""
    system = _system(system)
    if system == "darwin":
        data = _plist(platforms.launch_services_file())
        handlers = data.get("LSHandlers") if isinstance(data, dict) else None
        for entry in handlers if isinstance(handlers, list) else ():
            if isinstance(entry, dict) and entry.get("LSHandlerURLScheme") == "https":
                bundle = entry.get("LSHandlerRoleAll")
                if not isinstance(bundle, str):
                    return None
                return next((facts.id for facts in platforms.KNOWN_BROWSERS
                             if facts.mac_bundle_id.lower() == bundle.lower()), None)
        return None
    if system == "win32":
        progid = platforms.windows_https_progid()
        if not isinstance(progid, str):
            return None
        base = progid.split(".", 1)[0].lower()  # "ChromeHTML.ABC123" is still Chrome's
        return next((facts.id for facts in platforms.KNOWN_BROWSERS
                     if facts.win_progid and facts.win_progid.lower() == base), None)
    return None
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_browsers.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/browsers.py tests/test_browsers.py tests/samples/browsers/launchservices.plist
git commit -m "feat(browsers): os_default() reads the system's https browser as a first guess"
```

### Task 7: Profiles: name and colour only, never an email

**Files:**
- Modify: `src/ai_browser/browsers.py` (append)
- Create: `tests/samples/browsers/brave-local-state.json`, `tests/samples/browsers/chrome-local-state.json`
- Test: `tests/test_browsers.py` (append)

**Interfaces:**
- Consumes: Task 4's `_read`.
- Produces in `browsers.py`:
  - `@dataclass(frozen=True) class Profile(folder: str, name: str, color: str | None, last_used: bool)`, with exactly
    these four fields;
  - `plain_folder(name) -> bool`. It is public, because wave C's `plain_profile` applies the same rule;
  - `profiles(data_dir) -> list[Profile]`;
  - `_json(path)`: the parsed JSON, or None. Task 8 reads through it.
- Produces in `tests/test_browsers.py`:
  - `BRAVE_FOLDERS`;
  - `data_folder(path, local_state, folders=()) -> Path`;
  - `local_state(drop=(), **changes) -> bytes`;
  - `one_profile(entry) -> bytes`;
  - `BAD_FOLDERS`.

- [ ] **Step 1: Write the samples and the failing tests**

Create `tests/samples/browsers/brave-local-state.json`. It is hand-written with the key names measured in throwaway
Brave 152 and Chrome 154, and copies no value from the user's files. `Default`'s account fields are decoys:

```json
{
  "browser": {"enabled_labs_experiments": []},
  "profile": {
    "info_cache": {
      "Default": {
        "avatar_icon": "chrome://theme/IDR_PROFILE_AVATAR_26",
        "default_avatar_fill_color": -12627531,
        "gaia_given_name": "Alex",
        "gaia_id": "123456789012345678901",
        "gaia_name": "Alex Example",
        "is_ephemeral": false,
        "is_using_default_name": false,
        "name": "Personal",
        "profile_highlight_color": -12627531,
        "user_name": "alex@example.com"
      },
      "Profile 1": {
        "avatar_icon": "chrome://theme/IDR_PROFILE_AVATAR_13",
        "default_avatar_fill_color": -14983648,
        "gaia_name": "",
        "is_ephemeral": false,
        "is_using_default_name": false,
        "name": "Work",
        "user_name": ""
      },
      "Profile 2": {
        "avatar_icon": "chrome://theme/IDR_PROFILE_AVATAR_4",
        "is_ephemeral": false,
        "is_using_default_name": false,
        "name": "alex@example.com",
        "user_name": ""
      },
      "Profile 3": {
        "avatar_icon": "chrome://theme/IDR_PROFILE_AVATAR_0",
        "is_ephemeral": true,
        "name": "Throwaway",
        "user_name": ""
      },
      "Profile 4": {
        "avatar_icon": "chrome://theme/IDR_PROFILE_AVATAR_1",
        "is_ephemeral": false,
        "name": "Deleted",
        "user_name": ""
      },
      "System Profile": {"is_ephemeral": false, "name": "System Profile"},
      "Guest Profile": {"is_ephemeral": false, "name": "Guest"}
    },
    "last_active_profiles": ["Profile 1"],
    "last_used": "Profile 1",
    "metrics": {"next_bucket_index": 5},
    "profile_counts_reported": "13370000000000000",
    "profiles_order": ["Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4"]
  }
}
```

Create `tests/samples/browsers/chrome-local-state.json`:

```json
{
  "browser": {"enabled_labs_experiments": []},
  "profile": {
    "info_cache": {
      "Default": {
        "avatar_icon": "chrome://theme/IDR_PROFILE_AVATAR_26",
        "is_ephemeral": false,
        "is_using_default_name": true,
        "name": "Your Chrome",
        "user_name": ""
      }
    },
    "last_active_profiles": ["Default"],
    "last_used": "Default",
    "metrics": {"next_bucket_index": 1},
    "profiles_order": ["Default"]
  }
}
```

Append to `tests/test_browsers.py`:

```python
# Profiles (Task 7)

BRAVE_FOLDERS = ("Default", "Profile 1", "Profile 2", "Profile 3", "System Profile", "Guest Profile")


def data_folder(path: Path, local_state: bytes | None, folders=()) -> Path:
    """A browser's data folder: its Local State (unless None) and these profile folders."""
    path.mkdir(parents=True, exist_ok=True)
    if local_state is not None:
        (path / "Local State").write_bytes(local_state)
    for folder in folders:
        (path / folder).mkdir(exist_ok=True)
    return path


def local_state(drop=(), **changes) -> bytes:
    """The Brave sample's Local State with keys under "profile" changed, or dropped."""
    data = json.loads(sample("brave-local-state.json"))
    data["profile"].update(changes)
    for key in drop:
        data["profile"].pop(key)
    return json.dumps(data).encode("utf-8")


def one_profile(entry) -> bytes:
    return json.dumps({"profile": {"info_cache": {"Default": entry}}}).encode("utf-8")


def test_profiles_read_name_colour_and_order(tmp_path):
    data = data_folder(tmp_path / "Brave", sample("brave-local-state.json"), BRAVE_FOLDERS)
    expected = [browsers.Profile("Default", "Personal", "#3f51b5", False),
                browsers.Profile("Profile 1", "Work", "#1b5e20", True),
                browsers.Profile("Profile 2", "Profile 2", None, False)]
    assert browsers.profiles(data) == expected  # no System, Guest, ephemeral or folderless profile
    (data / "Local State").write_bytes(local_state(profiles_order=["Profile 4", "Profile 3", "Profile 2",
                                                                   "Profile 1", "Default"]))
    assert browsers.profiles(data) == expected[::-1]
    (data / "Local State").write_bytes(local_state(drop=("profiles_order",)))
    assert browsers.profiles(data) == expected  # Default first, then the rest sorted
    (data / "Profile 5").mkdir()
    assert [profile.folder for profile in browsers.profiles(data)] == ["Default", "Profile 1", "Profile 2"]


def test_profiles_never_return_an_email(tmp_path):
    data = data_folder(tmp_path / "Brave", sample("brave-local-state.json"), BRAVE_FOLDERS)
    shown = repr(browsers.profiles(data))
    for secret in ("alex@example.com", "Alex Example", "Alex", "123456789012345678901", "@"):
        assert secret not in shown
    assert browsers.profiles(data)[2] == browsers.Profile("Profile 2", "Profile 2", None, False)
    assert [field.name for field in dataclasses.fields(browsers.Profile)] == ["folder", "name", "color", "last_used"]


@pytest.mark.parametrize("name, shown", [
    ("\u202eevil\x07", "evil"), ("x" * 200, "x" * 64), ("   ", "Default"), (" Work ", "Work"),
    ("Alex (alex@example.com)", "Default"),  # an email among other words never comes out either
    ("\u200e\u2066\u202e\x1b", "Default"),  # only invisible characters: blank
    (42, "Default")])
def test_profile_names_are_cleaned(tmp_path, name, shown):
    data = data_folder(tmp_path / "Brave", one_profile({"name": name}), ["Default"])
    assert [profile.name for profile in browsers.profiles(data)] == [shown]


@pytest.mark.parametrize("value, color", [
    (-16777216, "#000000"), (-1, "#ffffff"), (4282339765, "#3f51b5"), (-12627531, "#3f51b5"), (True, None),
    ("#fff", None), (2**40, None), (None, None)])
def test_colours(tmp_path, value, color):
    data = data_folder(tmp_path / "Brave", one_profile({"name": "Personal", "profile_highlight_color": value}),
                       ["Default"])
    assert [profile.color for profile in browsers.profiles(data)] == [color]


BAD_FOLDERS = ["../Default", "/etc", "a/b", "a\\b", "C:x", "", ".", "..", "nul\x00here", "x" * 65]


def test_a_profile_folder_name_cannot_leave_the_data_folder(tmp_path):
    assert not any(browsers.plain_folder(name) for name in BAD_FOLDERS) and not browsers.plain_folder(None)
    assert browsers.plain_folder("Default") and browsers.plain_folder("Profile 12")
    cache = {name: {"name": "Sneaky"} for name in [*BAD_FOLDERS, "Profile 1"]}
    data = data_folder(tmp_path / "Brave", json.dumps({"profile": {"info_cache": cache}}).encode("utf-8"),
                       ["Profile 1"])
    (tmp_path / "Default").mkdir()  # beside the data folder: "../Default" names it
    if os.name != "nt":
        (data / "C:x").mkdir()  # on Windows "C:x" is a path on drive C:, not a folder name
    assert [profile.folder for profile in browsers.profiles(data)] == ["Profile 1"]


def test_each_profile_is_listed_once(tmp_path):
    state = {"profile": {"info_cache": {"Default": {"name": "Personal"}, "Profile 1": {"name": "Work"},
                                        "Profile 3": {"name": "Gone", "is_ephemeral": True}},
                         "profiles_order": ["Profile 1", "Default", "Profile 1", "Default"], "last_used": "Profile 3"}}
    data = data_folder(tmp_path / "Brave", json.dumps(state).encode("utf-8"), ["Default", "Profile 1", "Profile 3"])
    assert browsers.profiles(data) == [browsers.Profile("Profile 1", "Work", None, False),
                                       browsers.Profile("Default", "Personal", None, False)]


@pytest.mark.parametrize("contents, shown", [
    pytest.param(lambda: None, [], id="missing file"),
    pytest.param(lambda: b"", [], id="empty file"),
    pytest.param(lambda: sample("brave-local-state.json")[:300], [], id="cut JSON"),
    pytest.param(lambda: b"[]", [], id="a list"),
    pytest.param(lambda: b'{"profile": "Default"}', [], id="profile is a string"),
    pytest.param(lambda: b'{"profile": {"info_cache": ["Default"]}}', [], id="info_cache is a list"),
    pytest.param(lambda: b'{"profile": {"info_cache": {"Default": 7, "Profile 1": {"name": "Work"}}}}',
                 ["Profile 1:Work"], id="an entry is a number"),
    pytest.param(lambda: b'{"profile": {"info_cache": {"Default": {"name": 7}}}}', ["Default:Default"],
                 id="name is a number"),
    pytest.param(lambda: b'{"profile": {"info_cache": {"Default": {"name": "A"}}, "profiles_order": [1, null]}}',
                 ["Default:A"], id="order holds numbers"),
    pytest.param(lambda: b'{"profile": {"info_cache": {"Default": {"name": "A"}}, "profiles_order": ["\xff\xfe"]}}',
                 ["Default:A"], id="invalid UTF-8"),
    pytest.param(lambda: b'{"profile": {"profiles_order": ' + b"[" * 10000 + b"]" * 10000 + b"}}", [],
                 id="10,000 nested lists"),
])
def test_profiles_fail_safely(tmp_path, contents, shown):
    data = data_folder(tmp_path / "Brave", contents(), ["Default", "Profile 1"])
    assert [f"{profile.folder}:{profile.name}" for profile in browsers.profiles(data)] == shown


def test_profiles_fail_safely_on_odd_files(tmp_path, monkeypatch):
    data = data_folder(tmp_path / "Brave", None, ["Default"])
    (data / "Local State").mkdir()  # a folder called Local State
    assert browsers.profiles(data) == []
    (data / "Local State").rmdir()
    if hasattr(os, "mkfifo"):
        os.mkfifo(data / "Local State")  # a plain read would wait forever
        assert browsers.profiles(data) == []
        (data / "Local State").unlink()
    (data / "Local State").write_bytes(b"")
    os.truncate(data / "Local State", 17 * 1024 * 1024)
    reads = recording_reads(monkeypatch)
    assert browsers.profiles(data) == [] and reads == []  # 17 MB: not read at all
    if os.name != "nt" and os.geteuid() != 0:  # root reads any folder
        locked = data_folder(tmp_path / "Locked", sample("brave-local-state.json"), ["Default"])
        locked.chmod(0)  # Path.is_file() would raise PermissionError here
        try:
            assert browsers.profiles(locked) == []
        finally:
            locked.chmod(0o700)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_browsers.py -q -p no:randomly`

Expected: the 31 new tests FAIL with `AttributeError: module 'ai_browser.browsers' has no attribute 'Profile'` (and
`… 'profiles'`, `… 'plain_folder'`).

- [ ] **Step 3: Write `profiles()`**

Append to `src/ai_browser/browsers.py`:

```python
@dataclass(frozen=True)
class Profile:
    """A profile of a browser: its folder in the data folder, the name and colour the user gave it, and whether the
    browser used it last. Nothing from the account: no email, no account name."""

    folder: str
    name: str
    color: str | None
    last_used: bool


_NOT_PROFILES = ("System Profile", "Guest Profile")
_BIDI_CONTROLS = frozenset("\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
_NAME_LIMIT = 64


def plain_folder(name) -> bool:
    """Whether a profile folder name is a plain name inside the data folder: not empty, not . or .., at most 64
    characters, and no /, \\, : or control character."""
    return (isinstance(name, str) and 0 < len(name) <= _NAME_LIMIT and name not in (".", "..")
            and not any(char in "/\\:" or unicodedata.category(char) == "Cc" for char in name))


def _profile_name(name, folder: str) -> str:
    """The name the user gave a profile, cleaned: no control or bidi characters, trimmed, at most 64 characters.
    A blank name, or one holding "@" (it may be an email), shows as the folder's name."""
    if not isinstance(name, str):
        return folder
    text = "".join(char for char in name
                   if unicodedata.category(char) != "Cc" and char not in _BIDI_CONTROLS).strip()
    if not text or "@" in text:
        return folder
    return text[:_NAME_LIMIT]


def _color(value) -> str | None:
    """A signed 32-bit ARGB integer as "#rrggbb", or None."""
    if isinstance(value, bool) or not isinstance(value, int) or not -2**31 <= value <= 2**32 - 1:
        return None
    return f"#{value & 0xFFFFFF:06x}"


def _json(path):
    """A JSON file as Python data, or None."""
    data = _read(path)
    if data is None:
        return None
    try:
        return json.loads(data.decode("utf-8", errors="replace"))
    except (ValueError, RecursionError):
        return None


def profiles(data_dir) -> list[Profile]:
    """The browser's profiles from its Local State, in its own order: never System, Guest or ephemeral ones, never
    a folder that isn't plain or isn't there. Only `name` and the colour are copied from each entry."""
    state = _json(Path(data_dir) / "Local State")
    profile = state.get("profile") if isinstance(state, dict) else None
    cache = profile.get("info_cache") if isinstance(profile, dict) else None
    if not isinstance(cache, dict):
        return []
    order = profile.get("profiles_order")
    order = [folder for folder in order if isinstance(folder, str)] if isinstance(order, list) else []
    rest = sorted((folder for folder in cache if folder not in order), key=lambda folder: (folder != "Default", folder))
    last_used = profile.get("last_used")
    found, seen = [], set()
    for folder in [*order, *rest]:
        entry = cache.get(folder)
        if folder in seen or not isinstance(entry, dict):
            continue
        seen.add(folder)
        if (folder in _NOT_PROFILES or entry.get("is_ephemeral") is True or not plain_folder(folder)
                or not os.path.isdir(os.path.join(data_dir, folder))):
            continue
        color = _color(entry.get("profile_highlight_color")) or _color(entry.get("default_avatar_fill_color"))
        found.append(Profile(folder, _profile_name(entry.get("name"), folder), color, folder == last_used))
    return found
```

Only `name`, `profile_highlight_color` and `default_avatar_fill_color` are read from an entry, plus
`is_ephemeral` to drop it. No account field is ever looked at.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_browsers.py -q -p no:randomly`

Expected: PASS. The named pipe and locked-folder lines are skipped on Windows, and the locked folder as root.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/browsers.py tests/test_browsers.py tests/samples/browsers/brave-local-state.json tests/samples/browsers/chrome-local-state.json
git commit -m "feat(browsers): profiles() lists each profile by name and colour, never an account field"
```

### Task 8: Which profile holds a copy of the watcher (`watcher_places`)

**Files:**
- Modify: `src/ai_browser/browsers.py` (append)
- Create: `tests/samples/browsers/secure-preferences-watcher.json`,
  `tests/samples/browsers/preferences-watcher-disabled.json`
- Test: `tests/test_browsers.py` (append)

**Interfaces:**
- Consumes: Task 7's `profiles` and `_json`.
- Produces in `browsers.py`:
  - `@dataclass(frozen=True) class WatcherPlace(profile: str, extension_id: str)`;
  - `watcher_places(data_dir, watchers: Mapping[str, str | Path], system=None) -> list[WatcherPlace]`, in profile
    order;
  - `watchers` maps each watcher id to its folder. Today that is one entry: `<home>/app/watcher` and its id.
- Produces in `tests/test_browsers.py`:
  - `WATCHER_ID`, `OTHER_ID` and `SAMPLE_ID`;
  - `preferences(profile, file_name, watcher_folder, extension_id=WATCHER_ID, sample_name=…, **changes)`;
  - `brave_data(tmp_path) -> Path`.

- [ ] **Step 1: Write the samples and the failing tests**

Create `tests/samples/browsers/secure-preferences-watcher.json`. Its watcher entry has `location: 4` (Load
unpacked) and `disable_reasons: []`, plus one unrelated extension:

```json
{
  "extensions": {
    "settings": {
      "aaaabbbbccccddddeeeeffffgggghhhh": {
        "active_permissions": {"api": ["storage", "tabGroups", "tabs"], "manifest_permissions": []},
        "creation_flags": 38,
        "disable_reasons": [],
        "from_webstore": false,
        "location": 4,
        "path": "/Users/Alex/.ai-browser/app/watcher",
        "service_worker_registration_info": {"version": "0.1.0"},
        "was_installed_by_default": false
      },
      "nmmhkkegccagdldgiimedpiccmgmieda": {
        "disable_reasons": [],
        "location": 10,
        "path": "nmmhkkegccagdldgiimedpiccmgmieda/1.0.0.6_0",
        "was_installed_by_default": true
      }
    }
  },
  "protection": {"macs": {"extensions": {"settings": {"aaaabbbbccccddddeeeeffffgggghhhh": "00000000"}}}}
}
```

Create `tests/samples/browsers/preferences-watcher-disabled.json`, the same entry disabled:

```json
{
  "extensions": {
    "settings": {
      "aaaabbbbccccddddeeeeffffgggghhhh": {
        "active_permissions": {"api": ["storage", "tabGroups", "tabs"], "manifest_permissions": []},
        "creation_flags": 38,
        "disable_reasons": [1],
        "from_webstore": false,
        "location": 4,
        "path": "/Users/Alex/.ai-browser/app/watcher",
        "service_worker_registration_info": {"version": "0.1.0"},
        "was_installed_by_default": false
      }
    }
  },
  "profile": {"name": "Alex"}
}
```

Append to `tests/test_browsers.py`:

```python
# Watcher copies (Task 8)

WATCHER_ID, OTHER_ID = "mnopmnopmnopmnopmnopmnopmnopmnop", "ijklijklijklijklijklijklijklijkl"
SAMPLE_ID = "aaaabbbbccccddddeeeeffffgggghhhh"  # the watcher's entry in the samples


def preferences(profile: Path, file_name: str, watcher_folder, extension_id: str = WATCHER_ID,
                sample_name: str = "secure-preferences-watcher.json", **changes) -> None:
    """A profile's Secure Preferences or Preferences: the sample's watcher entry, under `extension_id`, loaded from
    `watcher_folder`, with `changes` made to the entry. json.dumps writes a Windows path with its escapes."""
    data = json.loads(sample(sample_name))
    settings = data["extensions"]["settings"]
    entry = settings.pop(SAMPLE_ID)
    entry["path"] = str(watcher_folder)
    entry.update(changes)
    settings[extension_id] = entry
    profile.mkdir(parents=True, exist_ok=True)
    (profile / file_name).write_bytes(json.dumps(data).encode("utf-8"))


def brave_data(tmp_path) -> Path:
    return data_folder(tmp_path / "Brave", sample("brave-local-state.json"), BRAVE_FOLDERS)


def test_watcher_places(tmp_path):
    data, watcher = brave_data(tmp_path), tmp_path / "watcher"
    watcher.mkdir()
    watchers = {WATCHER_ID: watcher}
    profile_1 = [browsers.WatcherPlace("Profile 1", WATCHER_ID)]
    preferences(data / "Profile 1", "Secure Preferences", watcher)
    assert browsers.watcher_places(data, watchers) == profile_1
    preferences(data / "Default", "Preferences", watcher)  # only in Preferences: counts too
    assert browsers.watcher_places(data, watchers) == [browsers.WatcherPlace("Default", WATCHER_ID), *profile_1]
    for disabled in ({"disable_reasons": [1]}, {"disable_reasons": 1}, {"state": 0}):
        preferences(data / "Default", "Preferences", watcher, **disabled)
        assert browsers.watcher_places(data, watchers) == profile_1, disabled
    preferences(data / "Default", "Preferences", tmp_path / "another-folder")
    assert browsers.watcher_places(data, watchers) == profile_1
    preferences(data / "Default", "Preferences", watcher, extension_id=OTHER_ID)  # not one of the watchers
    assert browsers.watcher_places(data, watchers) == profile_1
    preferences(data / "Profile 1", "Preferences", watcher)  # enabled here, but Secure Preferences says disabled
    preferences(data / "Profile 1", "Secure Preferences", watcher, sample_name="preferences-watcher-disabled.json")
    assert browsers.watcher_places(data, watchers) == []


def test_the_same_watcher_in_two_profiles_is_listed_twice(tmp_path):
    data, watcher = brave_data(tmp_path), tmp_path / "watcher"
    for profile in ("Default", "Profile 1"):
        preferences(data / profile, "Secure Preferences", watcher)
    assert browsers.watcher_places(data, {WATCHER_ID: watcher}) == [browsers.WatcherPlace("Default", WATCHER_ID),
                                                                    browsers.WatcherPlace("Profile 1", WATCHER_ID)]


def test_watcher_paths_ignore_case_only_on_windows(tmp_path):
    data = brave_data(tmp_path)
    default = [browsers.WatcherPlace("Default", WATCHER_ID)]

    def places(folder, system):
        return browsers.watcher_places(data, {WATCHER_ID: folder}, system=system)

    preferences(data / "Default", "Secure Preferences", "c:\\users\\alex\\.ai-browser\\app\\watcher")
    assert places("C:\\Users\\Alex\\.ai-browser\\app\\watcher", "win32") == default
    assert places("C:\\Users\\Alex\\.ai-browser\\app\\watcher\\", "win32") == default  # a trailing separator
    assert places("C:\\Users\\Alex\\.ai-browser\\app\\watcher2", "win32") == []
    if os.name != "nt":  # Windows' realpath restores the case found on disk
        watcher = tmp_path / "home" / ".ai-browser" / "app" / "watcher"
        watcher.mkdir(parents=True)
        preferences(data / "Default", "Secure Preferences", watcher.parent / "WATCHER")
        assert places(watcher, "darwin") == []  # the id hashes the exact path: other case is another copy
        preferences(data / "Default", "Secure Preferences", f"{watcher}/")
        assert places(watcher, "darwin") == default


@pytest.mark.parametrize("contents", [
    pytest.param(lambda folder: b"{broken", id="broken file"),
    pytest.param(lambda folder: {"extensions": []}, id="extensions is a list"),
    pytest.param(lambda folder: {"extensions": {"settings": "x"}}, id="settings is a string"),
    pytest.param(lambda folder: {"extensions": {"settings": {WATCHER_ID: {"path": 7}}}}, id="path is a number"),
    pytest.param(lambda folder: {"extensions": {"settings": {WATCHER_ID: {"path": str(folder),
                                                                          "disable_reasons": "none"}}}},
                 id="disable_reasons is a string"),
    pytest.param(lambda folder: {"extensions": {"settings": {WATCHER_ID: {"path": f"{folder}\0x"}}}},
                 id="path holds a NUL"),
    pytest.param(lambda folder: {"extensions": {"settings": {WATCHER_ID: ["path", str(folder)]}}},
                 id="the entry is a list"),
])
def test_watcher_places_fail_safely(tmp_path, contents):
    data, watcher = brave_data(tmp_path), tmp_path / "watcher"
    watcher.mkdir()
    written = contents(watcher)
    (data / "Default" / "Secure Preferences").write_bytes(
        written if isinstance(written, bytes) else json.dumps(written).encode("utf-8"))
    assert browsers.watcher_places(data, {WATCHER_ID: watcher}) == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_browsers.py -q -p no:randomly`

Expected: the 10 new tests FAIL with `AttributeError: module 'ai_browser.browsers' has no attribute
'watcher_places'` (and `… 'WatcherPlace'`).

- [ ] **Step 3: Write `watcher_places()`**

Append to `src/ai_browser/browsers.py`:

```python
@dataclass(frozen=True)
class WatcherPlace:
    """A profile folder that holds an enabled copy of a watcher, and that copy's extension id."""

    profile: str
    extension_id: str


def _extension_settings(path) -> dict:
    data = _json(path)
    extensions = data.get("extensions") if isinstance(data, dict) else None
    settings = extensions.get("settings") if isinstance(extensions, dict) else None
    return settings if isinstance(settings, dict) else {}


def _watcher_key(path, system: str) -> str | None:
    """A watcher folder as compared with the path a browser recorded: on Windows the absolute path without regard
    to case and with no link resolved (as Chrome records it), elsewhere the real path, exactly."""
    try:
        if system == "win32":
            return ntpath.normcase(ntpath.abspath(str(path)))
        return os.path.realpath(path)
    except (OSError, ValueError):
        return None


def _enabled(entry) -> bool:
    reasons = entry.get("disable_reasons", 0)
    if not (reasons == [] or (type(reasons) is int and reasons == 0)):
        return False
    state = entry.get("state")
    return not (type(state) is int and state == 0)  # an older Chromium's "disabled"


def watcher_places(data_dir, watchers: Mapping[str, str | Path], system: str | None = None) -> list[WatcherPlace]:
    """Which profiles hold an enabled copy of which watcher: `watchers` maps each watcher's extension id to the
    folder it was loaded from. Read from each profile's Secure Preferences, then Preferences (the first wins)."""
    system = _system(system)
    if not isinstance(watchers, Mapping):
        return []
    wanted = {extension_id: _watcher_key(folder, system) for extension_id, folder in watchers.items()
              if isinstance(extension_id, str)}
    places = []
    for profile in profiles(data_dir):
        secure = _extension_settings(Path(data_dir) / profile.folder / "Secure Preferences")
        plain = _extension_settings(Path(data_dir) / profile.folder / "Preferences")
        for extension_id, key in wanted.items():
            entry = secure[extension_id] if extension_id in secure else plain.get(extension_id)
            if (key is not None and isinstance(entry, dict) and isinstance(entry.get("path"), str)
                    and _watcher_key(entry["path"], system) == key and _enabled(entry)):
                places.append(WatcherPlace(profile.folder, extension_id))
    return places
```

`location` is not checked: `--load-extension` gives 8, and Load unpacked gives 4. Today's
`appbrowser.extension_installed` stays as it is: it serves AI Browser's own extension until wave B retires it.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_browsers.py -q -p no:randomly`

Expected: PASS. The macOS case lines of `test_watcher_paths_ignore_case_only_on_windows` are skipped on Windows,
where `realpath` restores the case found on disk.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/browsers.py tests/test_browsers.py tests/samples/browsers/secure-preferences-watcher.json tests/samples/browsers/preferences-watcher-disabled.json
git commit -m "feat(browsers): watcher_places() finds enabled watcher copies per profile"
```

### Task 9: Running, the switch, and the state

**Files:**
- Modify: `src/ai_browser/browsers.py` (append)
- Test: `tests/test_browsers.py` (append)

**Interfaces:**
- Consumes:
  - Task 4: `_read`;
  - Task 1: `platforms.lock_name`;
  - today's `platforms.pid_alive`.
- Produces in `browsers.py`:
  - `STATES = ("not_running", "switch_off", "switch_on")`;
  - `devtools_port(data_dir) -> int | None`;
  - `listening(port, timeout=0.5) -> bool`;
  - `running(data_dir, system=None) -> bool | None`;
  - `state(data_dir, system=None) -> str`.

  `state()` calls `running` and `listening` as module globals, and the tests patch them.
- Produces in `tests/test_browsers.py`: `open_port() -> tuple[socket.socket, int]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_browsers.py`:

```python
# Running, the switch and the state (Task 9)


def test_running_reads_the_lock_on_mac_and_linux(tmp_path):
    lock = tmp_path / "SingletonLock"
    assert browsers.running(tmp_path, "darwin") is False  # no lock: not running
    symlink_or_skip(f"{socket.gethostname()}-{os.getpid()}", lock)
    assert browsers.running(tmp_path, "darwin") is True
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=30)
    for target, expected in ((f"{socket.gethostname()}-{child.pid}", False),  # exited and waited for
                             (f"elsewhere.local-{os.getpid()}", None), ("garbage", None),
                             (f"{socket.gethostname()}-99999999999", None)):  # too big for os.kill: no OverflowError
        lock.unlink()
        os.symlink(target, lock)
        assert browsers.running(tmp_path, "darwin") is expected, target
    lock.unlink()
    lock.write_bytes(b"not a link")
    assert browsers.running(tmp_path, "darwin") is None


def test_a_host_name_with_dashes(tmp_path, monkeypatch):
    monkeypatch.setattr(browsers.socket, "gethostname", lambda: "Alexs-Mac-Book.local")
    lock = tmp_path / "SingletonLock"
    symlink_or_skip(f"Alexs-Mac-Book.local-{os.getpid()}", lock)
    assert browsers.running(tmp_path, "darwin") is True  # split at the last dash
    lock.unlink()
    os.symlink("Alexs-Mac-Book.local-", lock)
    assert browsers.running(tmp_path, "darwin") is None


def test_running_on_windows_only_looks_for_the_lockfile(tmp_path, monkeypatch):
    import builtins

    lock = tmp_path / "lockfile"
    assert browsers.running(tmp_path, "win32") is False
    lock.write_bytes(b"")
    if os.name != "nt":
        lock.chmod(0)

    def refusing(real):
        def opener(file, *args, **kwargs):
            if isinstance(file, (str, os.PathLike)) and Path(file).name == "lockfile":
                pytest.fail(f"the lockfile was opened: {file}")
            return real(file, *args, **kwargs)
        return opener

    monkeypatch.setattr(builtins, "open", refusing(builtins.open))
    monkeypatch.setattr(platforms, "open_shared", refusing(platforms.open_shared))
    try:
        assert browsers.running(tmp_path, "win32") is True
    finally:
        lock.chmod(0o600)


def test_the_switch_check_sends_nothing(tmp_path):
    server = socket.create_server(("127.0.0.1", 0))
    port, received = server.getsockname()[1], []

    def serve():
        connection, _ = server.accept()
        with connection:
            connection.settimeout(5)
            received.append(connection.recv(1024))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        (tmp_path / "DevToolsActivePort").write_bytes(f"{port}\n/devtools/browser/x\n".encode("utf-8"))
        assert browsers.devtools_port(tmp_path) == port
        assert browsers.listening(port) is True
        thread.join(timeout=10)
    finally:
        server.close()
    assert received == [b""]  # connected and closed: no HTTP request, no websocket


def open_port() -> tuple[socket.socket, int]:
    server = socket.create_server(("127.0.0.1", 0))
    return server, server.getsockname()[1]


@pytest.mark.parametrize("alive, answers, expected", [
    (False, True, "not_running"), (True, True, "switch_on"), (True, False, "switch_off"), (None, True, "switch_on"),
    (None, False, "not_running")])
def test_state_combines_the_lock_and_the_switch(tmp_path, monkeypatch, alive, answers, expected):
    monkeypatch.setattr(browsers, "running", lambda data_dir, system=None: alive)
    server, port = open_port()
    try:
        if not answers:
            server.close()
        (tmp_path / "DevToolsActivePort").write_bytes(f"{port}\n/devtools/browser/x\n".encode("utf-8"))
        assert browsers.state(tmp_path) == expected
    finally:
        server.close()


@pytest.mark.parametrize("contents", [None, b"abc\n/x\n", b"0\n/x\n", b"70000\n/x\n", "\u00b2\n/x\n".encode("utf-8"),
                                      b""], ids=["no port file", "abc", "0", "70000", "superscript two", "empty"])
def test_a_running_browser_without_a_usable_port_has_its_switch_off(tmp_path, monkeypatch, contents):
    monkeypatch.setattr(browsers, "running", lambda data_dir, system=None: True)
    if contents is not None:
        (tmp_path / "DevToolsActivePort").write_bytes(contents)
    assert browsers.devtools_port(tmp_path) is None
    assert browsers.state(tmp_path) == "switch_off"


def test_the_port_file_may_end_its_lines_with_crlf(tmp_path):
    (tmp_path / "DevToolsActivePort").write_bytes(b"9222\r\n/devtools/browser/x\r\n")
    assert browsers.devtools_port(tmp_path) == 9222


def test_a_missing_data_folder_is_not_running(tmp_path):
    assert browsers.state(tmp_path / "missing") == "not_running" and browsers.state(None) == "not_running"


def test_a_stale_port_of_a_stopped_browser_is_never_checked(tmp_path, monkeypatch):
    (tmp_path / "DevToolsActivePort").write_bytes(b"9222\n/devtools/browser/old\n")
    monkeypatch.setattr(browsers, "running", lambda data_dir, system=None: False)
    monkeypatch.setattr(browsers, "listening", lambda port, timeout=0.5: pytest.fail("a stopped browser's port"))
    assert browsers.state(tmp_path) == "not_running"
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_browsers.py -q -p no:randomly`

Expected: the 18 new tests FAIL with `AttributeError: module 'ai_browser.browsers' has no attribute 'running'` (and
`… 'devtools_port'`, `… 'listening'`, `… 'state'`). `monkeypatch.setattr` raises the same error for a name that
doesn't exist yet. pytest may also warn that the server thread of `test_the_switch_check_sends_nothing` ended with an
error: nothing connected to it.

- [ ] **Step 3: Write the state**

Append to `src/ai_browser/browsers.py`:

```python
STATES = ("not_running", "switch_off", "switch_on")


def devtools_port(data_dir) -> int | None:
    """The port in the data folder's DevToolsActivePort (its first line: 1 to 5 ASCII digits, 1 to 65535), or None.
    The file stays behind after the browser exits, so the port alone says nothing about the browser running."""
    data = _read(Path(data_dir) / "DevToolsActivePort")
    lines = data.decode("utf-8", errors="replace").splitlines() if data is not None else []
    first = lines[0].strip() if lines else ""
    if not re.fullmatch(r"[0-9]{1,5}", first):
        return None
    port = int(first)
    return port if 1 <= port <= 65535 else None


def listening(port, timeout: float = 0.5) -> bool:
    """Whether something accepts a TCP connection on 127.0.0.1:port. It connects and closes at once, sending no
    bytes: no HTTP request and no websocket, so no DevTools session and no "Allow remote debugging?" question."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def running(data_dir, system: str | None = None) -> bool | None:
    """Whether the browser of this data folder runs, from its own lock: True, False, or None when it can't tell.
    macOS and Linux: SingletonLock is a link to "<host>-<pid>" (read, never followed). Windows: the lockfile exists
    while the browser runs; it is never opened, since the browser holds it without sharing delete access."""
    system = _system(system)
    lock = os.path.join(data_dir, platforms.lock_name(system))
    if system == "win32":
        return os.path.exists(lock)
    if not os.path.lexists(lock):
        return False
    try:
        target = os.readlink(lock)
        host_name = socket.gethostname()
    except (OSError, ValueError):
        return None  # a regular file, or a link that can't be read
    host, dash, pid = target.rpartition("-")  # the host name may hold dashes itself
    if not dash or not re.fullmatch(r"[1-9][0-9]{0,8}", pid) or host != host_name:
        return None
    return platforms.pid_alive(int(pid))


def state(data_dir, system: str | None = None) -> str:
    """One of STATES. The lock tells "not running" from "switch off"; only DevToolsActivePort and the silent TCP
    check say the switch is on. A browser that isn't running gets no TCP check, so a stale port is never touched."""
    if data_dir is None or not os.path.isdir(data_dir):
        return "not_running"
    alive = running(data_dir, system)
    if alive is False:
        return "not_running"
    port = devtools_port(data_dir)
    if port is not None and listening(port):
        return "switch_on"
    return "switch_off" if alive else "not_running"  # can't tell: today's rule, the port alone
```

- These two helpers are copied from `chrome._port_of` and `chrome._listening`, not imported: `browsers.py` imports
  nothing from `chrome.py`. Wave C points `chrome.py` at these two, which also ends the `²` crash of
  `chrome.switch_on` (spec Decision 7).
- `running()` never lists processes, reads another process's memory or signals one: `pid_alive` sends signal 0 on
  POSIX, which delivers nothing.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_browsers.py tests/test_portable.py -q -p no:randomly`

Expected: PASS. The lock tests skip where symbolic links can't be made (Windows without Developer Mode).
`test_no_macos_paths_outside_platforms` stays green: there is no `os.kill(…, 0)` here.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/browsers.py tests/test_browsers.py
git commit -m "feat(browsers): running, switch on or off, from the browser's lock and a TCP check that sends nothing"
```

### Task 10: All together: `detect()`, `public()` and the read-only guards

**Files:**
- Modify: `src/ai_browser/browsers.py` (append)
- Test: `tests/test_browsers.py` (append)

**Interfaces:**
- Consumes: `installed` (Task 5), `os_default` (Task 6), `profiles` (Task 7), `watcher_places` (Task 8) and `state`
  (Task 9).
- Produces:
  - `@dataclass(frozen=True) class Found(browser: Installed, state: str | None, profiles: tuple[Profile, ...],
    watchers: tuple[WatcherPlace, ...], default: bool)`;
  - `detect(watchers=None, system=None, env=None) -> list[Found]`: the rows that agents can't use get no state, no
    profiles and no watchers, and nothing in their data folder is read;
  - `public(found, connected=()) -> list[dict]`, the only shape meant for pages:
    - per browser, the keys `id`, `name`, `agents`, `default`, `state` and `profiles`;
    - per profile, the keys `folder`, `name`, `color`, `last_used`, `watcher` and `shared_watcher`;
    - `state` is one of `STATES`, `"connected"` or null;
    - wave C sends exactly this to its pages.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_browsers.py`:

```python
# All together (Task 10)


def fake_mac(fake, port: int) -> SimpleNamespace:
    """Brave (running, its switch on, the watcher in Profile 1), Chrome (not running) and Edge on the fake Mac."""
    mac_app(fake.apps, "Brave Browser.app", sample("brave-info.plist"), "Brave Browser")
    mac_app(fake.apps, "Google Chrome.app", sample("chrome-info.plist"), "Google Chrome")
    mac_app(fake.apps, "Microsoft Edge.app", info_plist("com.microsoft.edgemac", "Microsoft Edge"), "Microsoft Edge")
    brave = data_folder(browsers.data_dir(browsers.by_id("brave"), "darwin"), sample("brave-local-state.json"),
                        BRAVE_FOLDERS)
    symlink_or_skip(f"{socket.gethostname()}-{os.getpid()}", brave / "SingletonLock")
    (brave / "DevToolsActivePort").write_bytes(f"{port}\n/devtools/browser/x\n".encode("utf-8"))
    watcher = fake.home / ".ai-browser" / "app" / "watcher"
    watcher.mkdir(parents=True)
    preferences(brave / "Profile 1", "Secure Preferences", watcher)
    chrome = data_folder(browsers.data_dir(browsers.by_id("chrome"), "darwin"), sample("chrome-local-state.json"),
                         ["Default"])
    edge = data_folder(browsers.data_dir(browsers.by_id("edge"), "darwin"), sample("brave-local-state.json"),
                       ["Default"])
    record = platforms.launch_services_file()
    record.parent.mkdir(parents=True)
    record.write_bytes(sample("launchservices.plist"))
    for profile in [*(brave / name for name in BRAVE_FOLDERS), chrome / "Default", edge / "Default"]:
        for decoy in ("Cookies", "Login Data", "History", "Web Data"):
            (profile / decoy).write_bytes(b"SQLite format 3\x00decoy")
    return SimpleNamespace(brave=brave, chrome=chrome, edge=edge, watchers={WATCHER_ID: watcher})


def shown_profile(folder, name, color, last_used, watcher=False, shared_watcher=False) -> dict:
    return {"folder": folder, "name": name, "color": color, "last_used": last_used, "watcher": watcher,
            "shared_watcher": shared_watcher}


EXPECTED = [
    {"id": "brave", "name": "Brave", "agents": True, "default": True, "state": "switch_on",
     "profiles": [shown_profile("Default", "Personal", "#3f51b5", False),
                  shown_profile("Profile 1", "Work", "#1b5e20", True, watcher=True),
                  shown_profile("Profile 2", "Profile 2", None, False)]},
    {"id": "chrome", "name": "Chrome", "agents": True, "default": False, "state": "not_running",
     "profiles": [shown_profile("Default", "Your Chrome", None, True)]},
    {"id": "edge", "name": "Edge", "agents": False, "default": False, "state": None, "profiles": []},
]


def test_detect_lists_installed_browsers_with_their_state_profiles_and_watchers(fake, monkeypatch):
    server, port = open_port()
    try:
        mac = fake_mac(fake, port)
        seen, real_read = [], browsers._read
        monkeypatch.setattr(browsers, "_read", lambda path: seen.append(Path(path)) or real_read(path))
        found = browsers.detect(mac.watchers, system="darwin")
    finally:
        server.close()
    assert browsers.public(found, connected=()) == EXPECTED
    assert seen and not any(path.is_relative_to(mac.edge) for path in seen)  # agents can't use Edge: not read
    assert browsers.detect(mac.watchers, system="linux") == []


def test_public_has_no_paths_or_emails(fake, tmp_path):
    server, port = open_port()
    try:
        found = browsers.detect(fake_mac(fake, port).watchers, system="darwin")
    finally:
        server.close()
    text = json.dumps(browsers.public(found))
    for secret in (str(tmp_path), tmp_path.as_posix(), "@", "Library", "Alex", "123456789012345678901", WATCHER_ID,
                   "152.1"):
        assert secret not in text
    shown = browsers.public(found, connected=("brave",))
    assert [browser["state"] for browser in shown] == ["connected", "not_running", None]
    assert all(set(browser) == {"id", "name", "agents", "default", "state", "profiles"} for browser in shown)
    assert all(set(profile) == {"folder", "name", "color", "last_used", "watcher", "shared_watcher"}
               for browser in shown for profile in browser["profiles"])
    assert [browser["state"] for browser in browsers.public(found, connected=("edge", "firefox"))] == [
        "switch_on", "not_running", None]  # Edge has no state to replace, and an unknown id adds nothing


def found_for(browser_id: str, folders, places) -> "browsers.Found":
    """A Found with these profile folders, and the watcher enabled in `places`."""
    browser = browsers.Installed(browsers.by_id(browser_id), Path("program"), None, None, Path("data"))
    return browsers.Found(browser, "not_running", tuple(browsers.Profile(f, f, None, False) for f in folders),
                          tuple(browsers.WatcherPlace(f, WATCHER_ID) for f in places), False)


def test_the_same_watcher_in_two_profiles_is_reported():
    def marks(*found):
        return [[(profile["folder"], profile["watcher"], profile["shared_watcher"]) for profile in browser["profiles"]]
                for browser in browsers.public(list(found))]

    assert marks(found_for("brave", ["Default", "Profile 1"], ["Default", "Profile 1"])) == [
        [("Default", True, True), ("Profile 1", True, True)]]
    assert marks(found_for("brave", ["Default"], ["Default"]), found_for("chrome", ["Default"], ["Default"])) == [
        [("Default", True, True)], [("Default", True, True)]]  # Chrome gives the same folder the same id
    assert marks(found_for("brave", ["Default", "Profile 1"], ["Profile 1"]), found_for("chrome", ["Default"], [])) == [
        [("Default", False, False), ("Profile 1", True, False)], [("Default", False, False)]]


READ_NAMES = {"Info.plist", "Local State", "Secure Preferences", "Preferences", "DevToolsActivePort",
              "com.apple.launchservices.secure.plist"}
_OPENED: list | None = None
_HOOKED: list = []


def _note_open(event, args):
    if _OPENED is not None and event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        _OPENED.append(os.fsdecode(args[0]))


@contextlib.contextmanager
def recording_opens():
    """Every file opened in the block, by any code (an audit hook: it can't be removed, so it records only while
    the block runs)."""
    global _OPENED
    if not _HOOKED:
        sys.addaudithook(_note_open)
        _HOOKED.append(_note_open)
    _OPENED = opened = []
    try:
        yield opened
    finally:
        _OPENED = None


def snapshot(root: Path) -> dict:
    """Every file, folder and link under root: its mtime, and its bytes or link target. Links are not followed."""
    tree = {}
    for folder, folders, files in os.walk(root):
        for name in [*folders, *files]:
            path = Path(folder, name)
            content = os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None
            tree[path.relative_to(root).as_posix()] = (path.lstat().st_mtime_ns, content)
    return tree


def test_detection_reads_only_its_files_and_writes_nothing(fake, tmp_path, monkeypatch):
    server, port = open_port()
    try:
        mac = fake_mac(fake, port)
        shared, real = [], platforms.open_shared
        monkeypatch.setattr(platforms, "open_shared", lambda path: shared.append(os.fspath(path)) or real(path))
        before = snapshot(tmp_path)
        with recording_opens() as opened:
            browsers.detect(mac.watchers, system="darwin")
        after = snapshot(tmp_path)
    finally:
        server.close()
    inside = {Path(path).name for path in [*opened, *shared] if Path(path).is_relative_to(tmp_path)}
    assert "Local State" in {Path(path).name for path in opened}  # the audit hook sees every open
    assert inside <= READ_NAMES, inside - READ_NAMES  # never Cookies, Login Data, History or Web Data
    assert after == before  # nothing written, touched or created


@pytest.mark.parametrize("name", [
    "brave-local-state.json", "chrome-local-state.json", "secure-preferences-watcher.json",
    "preferences-watcher-disabled.json", "brave-info.plist", "chrome-info.plist", "launchservices.plist",
    "launchservices.plist (binary)"])
def test_every_read_survives_a_truncated_file(fake, name):
    data = sample(name.removesuffix(" (binary)"))
    if name.endswith("(binary)"):
        data = plistlib.dumps(plistlib.loads(data), fmt=plistlib.FMT_BINARY)
    mac_app(fake.apps, "Brave Browser.app", sample("brave-info.plist"), "Brave Browser")
    brave = data_folder(browsers.data_dir(browsers.by_id("brave"), "darwin"), sample("brave-local-state.json"),
                        BRAVE_FOLDERS)
    record = platforms.launch_services_file()
    record.parent.mkdir(parents=True)
    record.write_bytes(sample("launchservices.plist"))
    watchers = {SAMPLE_ID: "/Users/Alex/.ai-browser/app/watcher"}
    for size in sorted({0, *range(1, len(data), 37)}):
        piece = data[:size]
        if name.endswith("local-state.json"):
            (brave / "Local State").write_bytes(piece)
            browsers.profiles(brave)
        elif "preferences" in name:
            (brave / "Default" / "Secure Preferences").write_bytes(piece)
            browsers.watcher_places(brave, watchers)
        elif "info" in name:
            mac_app(fake.apps, "Brave Browser.app", piece, "Brave Browser")
            browsers.installed(system="darwin")
        else:
            record.write_bytes(piece)
            browsers.os_default("darwin")
        browsers.public(browsers.detect(watchers, system="darwin"))  # and the whole detection, with that piece
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_browsers.py -q -p no:randomly`

Expected: the 12 new tests FAIL with `AttributeError: module 'ai_browser.browsers' has no attribute 'detect'` (and
`… 'public'`, `… 'Found'`). `test_every_read_survives_a_truncated_file` (8 cases) is the spec's guard (test 32) over
the readers of Tasks 5 to 8. It also runs `detect()` and `public()` on each piece, so it fails here first, and a later
change to any reader must keep it green. Brave in it has no lock, so `detect()` makes no TCP check.

- [ ] **Step 3: Write `detect()` and `public()`**

Append to `src/ai_browser/browsers.py`:

```python
@dataclass(frozen=True)
class Found:
    """One installed browser with what detection knows of it. A browser agents can't use has no state, no profiles
    and no watchers: nothing in its data folder is read."""

    browser: Installed
    state: str | None
    profiles: tuple[Profile, ...]
    watchers: tuple[WatcherPlace, ...]
    default: bool


def detect(watchers: Mapping[str, str | Path] | None = None, system: str | None = None,
           env: Mapping | None = None) -> list[Found]:
    """Every installed browser, in the table's order, with its state, profiles and watcher copies (for the ones
    agents can use) and whether it is the system's default. Reads files only; never connects."""
    system = _system(system)
    default = os_default(system, env)
    found = []
    for browser in installed(system, env):
        if not browser.agents:
            found.append(Found(browser, None, (), (), browser.id == default))
            continue
        found.append(Found(browser, state(browser.data_dir, system), tuple(profiles(browser.data_dir)),
                           tuple(watcher_places(browser.data_dir, watchers or {}, system)), browser.id == default))
    return found


def public(found, connected=()) -> list[dict]:
    """What pages may see of detect()'s result: no paths, versions, watcher ids or account fields. `connected` holds
    the ids of browsers the app's own link is connected to; one with a known state shows "connected"."""
    connected = {browser_id for browser_id in connected if isinstance(browser_id, str)}
    copies: dict[str, int] = {}  # extension id -> how many profiles, in any browser, hold an enabled copy
    for item in found:
        for place in item.watchers:
            copies[place.extension_id] = copies.get(place.extension_id, 0) + 1
    shown = []
    for item in found:
        ids = {}
        for place in item.watchers:
            ids.setdefault(place.profile, set()).add(place.extension_id)
        state_shown = "connected" if item.state is not None and item.browser.id in connected else item.state
        shown.append({
            "id": item.browser.id, "name": item.browser.name, "agents": item.browser.agents,
            "default": item.default, "state": state_shown,
            "profiles": [{"folder": profile.folder, "name": profile.name, "color": profile.color,
                          "last_used": profile.last_used, "watcher": bool(ids.get(profile.folder)),
                          "shared_watcher": any(copies[extension_id] > 1
                                                for extension_id in ids.get(profile.folder, ()))}
                         for profile in item.profiles]})
    return shown
```

- `public()` leaves out paths (they hold the user's account name), versions, watcher ids and every account field.
- `detect()` costs:
  - for each browser agents can use, one `state()` (two small files and at most one 0.5 s TCP check), `Local State`,
    and two preference files per profile;
  - wave C calls it when a page opens or after a click, never on a timer;
  - the async app calls it through `asyncio.to_thread`.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_browsers.py tests/test_platforms.py tests/test_portable.py -q -p no:randomly`

Expected: PASS. The fake-Mac tests skip where symbolic links can't be made.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/browsers.py tests/test_browsers.py
git commit -m "feat(browsers): detect() and public(), the read-only shape pages will get"
```

### Task 11: The README; the whole suite and the bench

**Files:**
- Modify: `README.md`: the "Development" section, before the line that starts ``Layout: `src/ai_browser/` (engine)``
- Test: `tests/test_browsers.py` (append)

**Interfaces:**
- Consumes:
  - everything above;
  - for the README command: today's `ai_browser.appbrowser.extension_id_for` and `ai_browser.config.home`.
- Produces:
  - the README says what detection reads and how to see its result;
  - the command imports `extension_id_for` from `ai_browser.appbrowser`. Wave B's plan moves that function to
    `ai_browser.extension_id` and changes this line with it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_browsers.py`:

```python
# The README (Task 11)


def test_the_readme_says_what_detection_reads():
    from ai_browser.config import project_root

    text = (project_root() / "README.md").read_text(encoding="utf-8")
    development = " ".join(text.split("## Development", 1)[1].split())
    assert "**Browser detection** (`src/ai_browser/browsers.py`)" in development
    assert 'so it never makes your browser ask "Allow remote debugging?"' in development
    assert "It never opens cookies, saved passwords or history, and never reads your account's email." in development
    assert "browsers.public(browsers.detect({extension_id_for(w): w})" in development
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_browsers.py::test_the_readme_says_what_detection_reads -q -p no:randomly`

Expected: FAIL on the first `assert`: the "Development" section doesn't mention browser detection yet.

- [ ] **Step 3: Write the README paragraph**

In `README.md`'s "Development" section, insert this right before the line that starts
``Layout: `src/ai_browser/` (engine)``, after the "**Tests on Windows (GitHub):**" paragraph:

````markdown
**Browser detection** (`src/ai_browser/browsers.py`): finds which browsers are installed (Brave and Chrome with their
other channels, and Chromium; Edge, Arc and Vivaldi are listed as not supported yet), whether each one runs with its
remote-debugging switch on, its profiles by name and colour, and which profile holds the Brain's watcher. It only
reads files, and for each running browser opens a TCP connection to 127.0.0.1 that sends nothing, so it never makes
your browser ask "Allow remote debugging?". It never opens cookies, saved passwords or history, and never reads your
account's email. Nothing in the app uses it yet. To see what it finds on your computer (it only reads, and opens no
DevTools session):

```bash
uv run python -c "import json; from ai_browser import browsers; from ai_browser.appbrowser import extension_id_for; from ai_browser.config import home; w = home() / 'app' / 'watcher'; print(json.dumps(browsers.public(browsers.detect({extension_id_for(w): w})), indent=1))"
```
````

Nothing else in the README changes: this wave adds no command, page or setting.

- [ ] **Step 4: Run the docs test, the build-time files, then the whole suite and the bench**

Run: `uv run pytest tests/test_browsers.py::test_the_readme_says_what_detection_reads -q -p no:randomly`

Expected: PASS.

Run: `uv run pytest tests/test_browsers.py tests/test_platforms.py tests/test_portable.py tests/test_chrome.py -q -p no:randomly`

Expected: PASS. These are the spec's files to run while building. The existing `tests/test_platforms.py` and
`tests/test_chrome.py` tests pass unchanged.

Run: `uv run pytest -q -p no:randomly`

Expected:
- PASS. Docker tests skip when Docker or the image is missing, and the Chrome tests need Google Chrome.
- Write the tail of the output to the ledger.
- If anything fails, fix it test-first in the task that owns the code, then run the whole suite again.

Run: `uv run ai-browser bench`

Expected:
- every row PASS. This plan adds no code to the paths the bench times;
- write the table to the ledger.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_browsers.py
git commit -m "docs: what browser detection reads, and how to see what it finds"
```

Then:
1. **The final review.** A fresh reviewer checks the branch against the Global Constraints and the Review Focus. One
   fix pass follows, test-first. Minor findings go to the ledger.
2. **The Windows CI, by the user.** On GitHub, the user clicks **Run workflow** on **tests** with `both`. This runs
   `open_shared`'s Windows half, the real registry readers and the Windows paths. The main session asks the user. No
   agent pushes or starts it.
3. **The hand check, by the user, after wave A merges** (the spec's "By hand").
   - **Who:** the user, or the main session with the user's OK. Never a build agent: it reads the user's real browser
     files.
   - **What it does:** it makes at most one TCP check per running browser, which sends nothing, and opens no DevTools
     session, so no question can follow.
   - **The command** is the README's.
   - **On this Mac, expect:**
     - Brave and Chrome only, with Brave `default` true;
     - Brave's two profiles (`Default` and `Profile 1`) by name and colour, with no email anywhere;
     - `watcher` true on the profile where the user loaded the watcher;
     - Brave `switch_on` while its switch is ticked, `switch_off` after unticking it, and `not_running` after
       quitting it;
     - no "Allow remote debugging?" question and no automation bar at any point.
   - **On the Windows laptop,** the same command. Expect:
     - Chrome, and Edge with `agents` false;
     - Brave, if it is installed;
     - Brave's state follows opening and quitting it. This checks the `lockfile` rule;
     - `default` true on the browser chosen in Windows' Settings → Default apps. This checks the `UserChoiceLatest`
       read on Windows 11;
     - every Windows path in the spec's Decision 2 that is installed there, found.
