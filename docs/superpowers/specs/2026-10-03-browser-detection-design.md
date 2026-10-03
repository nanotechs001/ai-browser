# Finding the installed browsers and their profiles

Date: 2026-10-03.

## Status

Status: the user approved the design in chat and answered its four questions; this spec was written and reviewed by agents without a user review round.

**Part of** "The app as an app" (`docs/superpowers/specs/2026-10-03-app-as-an-app-overview.md`). This spec covers the
detection part of the brief's section 4, "Browser and profile choice".

**Wave 2, track 2B.** It runs in parallel with the relay (2A, `app/cdprelay.py`). The two tracks share no file
(Decision 13).

**The user's answers that bear on it:**
- "Default in Settings, switch any time";
- the Brave profile for agents is "the one the user is signed in on", picked in Settings, with the watcher loaded in
  that profile.

**Builds on:**
- the windows-and-repo spec, Decision 1: `platforms.py` holds the OS facts, and every macOS-only path lives there;
- the everyday-brave spec, Decision 13: `own_browser_dirs()`, `switch_on()` and the TCP-only check;
- the investigation's `browsers` findings (`2026-10-03-app-as-an-app-investigation.json`), measured in throwaway
  Chrome 154 and throwaway Brave 152, never in the user's own browsers.

**Used by:**
- wave 3: the app window's browser (Chrome, Brave, or Edge on Windows);
- wave 4: Settings → "Where agents browse", the AI Home chip, the saved choice and the per-profile watchers.

**Line numbers** are at HEAD `946d5f0`.

## Goal and success criteria

**Goal:** one module, `browsers.py`, that answers four questions by reading files only:
- which browsers are installed;
- for each one, whether it runs and whether its remote-debugging switch is on;
- which profiles it has, by name and colour;
- which profile holds a copy of the Brain's watcher.

It never opens a DevTools session, never writes, and never returns an email.

Success means:
1. **Installed apps, not data folders.** On this Mac, `installed()` lists Brave and Chrome only. Arc, Chromium,
   Microsoft Edge, Vivaldi and Opera have leftover data folders here but no app, so they are absent (investigation
   finding 10).
2. **Profiles.** `profiles()` lists each real profile from `Local State` with its folder, name and colour, in the
   browser's own order. System, Guest and ephemeral profiles never appear. No field holds an email.
3. **State.** `state()` gives `not_running`, `switch_off` or `switch_on`. It reads the browser's lock and
   `DevToolsActivePort`, then makes a TCP check that sends no bytes. No "Allow remote debugging?" question and no
   automation bar can follow from it.
4. **Watchers.** `watcher_places()` says which profile folder holds which watcher id, and counts only enabled copies.
5. **Every read fails safely.** Each public function returns a safe value for a missing, broken, huge or hostile file.
   None of them raises.
6. **Read-only and quiet.** Detection writes nothing, launches nothing, and never holds a browser file in a way that
   blocks the browser's own saves.
7. **Windows from the Mac.** Every Windows path is tested on the Mac with `system="win32"`. The registry readers run
   against a fake `winreg` on the Mac, and against the real registry in the Windows CI job (run by hand).
8. **No collisions.** The track adds `browsers.py`, its test file and its sample files, and adds to `platforms.py`
   and `tests/test_platforms.py` (Decision 13). It edits no file the relay track touches. The existing functions give
   the same results as before, and the existing tests stay green unchanged.

## What the user sees

**In this wave, nothing changes.** There is no page, no message and no new command. The module has no caller outside
its tests (Decision 13).

**Wave 4 builds the visible parts on it:**
- a card for each installed browser, with its state (switch on, switch off, not running, or connected);
- greyed cards, marked "not supported yet", for detected browsers that agents can't use yet;
- under the chosen browser, its profiles: a colour dot and a name, "✓ watcher" or "needs the watcher";
- a first guess at the browser, from the system's default browser.

**The hand check prints the same data** (Testing, "By hand"). On this Mac it should look like this; the names are
examples:

```json
[{"id": "brave", "name": "Brave", "agents": true, "default": true, "state": "switch_on",
  "profiles": [{"folder": "Default", "name": "Personal", "color": "#3f51b5", "last_used": false,
                "watcher": true, "shared_watcher": false},
               {"folder": "Profile 1", "name": "Work", "color": "#1b5e20", "last_used": true,
                "watcher": false, "shared_watcher": false}]},
 {"id": "chrome", "name": "Chrome", "agents": true, "default": false, "state": "not_running",
  "profiles": [{"folder": "Default", "name": "Your Chrome", "color": null, "last_used": true,
                "watcher": false, "shared_watcher": false}]}]
```

## Decisions (with reasons)

### 1. Two files: the facts in `platforms.py`, the reading in `browsers.py`

- **`platforms.py` gets the facts:**
  - the table of known browsers (Decision 2);
  - each browser's data folder, `browser_data_dir()` (the macOS one is under `Application Support`);
  - the folders where apps are installed;
  - the LaunchServices file;
  - the registry readers;
  - the lock file's name;
  - one Windows-safe way to open a file for reading (Decision 11).
- **`browsers.py` gets the logic:**
  - parsing `Info.plist`, `Local State`, `Secure Preferences`, `Preferences` and `DevToolsActivePort`;
  - the lock and TCP checks;
  - putting it all together in `detect()`.
- **What "pure" means here:**
  - no module state, no cache, no threads, no writes;
  - every function takes its paths or `system` and `env` as arguments, read at call time, as in `platforms.py`;
  - its only network use is the TCP check to `127.0.0.1` (Decision 7);
  - the same files in give the same result out.
- **Why:**
  - the guard `test_no_macos_paths_outside_platforms` (`tests/test_portable.py:261-266`) refuses `Application Support`
    and `/Applications/` in any other module, even in a docstring or a comment. So `browsers.py` must not spell them,
    and its docstrings say "the app folders" and "the data folder" instead. It spells only the parts inside an app
    bundle (`Contents/Info.plist`, `Contents/MacOS`), under a folder that `platforms.app_folders()` gave;
  - the platforms module docstring (`platforms.py:1-9`) already says every macOS-only path lives there;
  - the parsing is plain Python over sample files, so the Mac's suite tests every OS's case.

### 2. The table of browsers

- **`platforms.KNOWN_BROWSERS`** is a tuple of `BrowserFacts` rows, in display order: the Brave family first, then the
  Chrome family, then Chromium, then the browsers that agents can't use yet.
- **Two flags per row:**
  - `agents`: offered under "Where agents browse". True for the Brave family, the Chrome family and Chromium. The
    switch was measured in Brave 152 and Chrome 154. The other channels and Chromium build the same Chromium code,
    which was not measured.
  - `window`: may draw the app window (wave 3). True for `brave`, `chrome` and `edge` only. The brief offers Edge
    for the window on Windows only ("Auto, Chrome, Brave, or Edge on Windows"), so wave 3 drops a macOS Edge. The
    flag says only that the browser can do it.
- **Listed but not offered to agents:** Edge, Arc and Vivaldi. Their support for the switch is unverified (investigation
  risk 7). Wave 4 shows them greyed.
- **Not listed:** Opera, because its profile layout differs; Firefox and Safari.

**macOS** (app in the app folders; data under `~/Library/Application Support`):

| id | name | app | bundle id | data folder |
|---|---|---|---|---|
| `brave` | Brave | `Brave Browser.app` | `com.brave.Browser` | `BraveSoftware/Brave-Browser` |
| `brave-beta` | Brave Beta | `Brave Browser Beta.app` | `com.brave.Browser.beta` | `BraveSoftware/Brave-Browser-Beta` |
| `brave-nightly` | Brave Nightly | `Brave Browser Nightly.app` | `com.brave.Browser.nightly` | `BraveSoftware/Brave-Browser-Nightly` |
| `chrome` | Chrome | `Google Chrome.app` | `com.google.Chrome` | `Google/Chrome` |
| `chrome-beta` | Chrome Beta | `Google Chrome Beta.app` | `com.google.Chrome.beta` | `Google/Chrome Beta` |
| `chrome-dev` | Chrome Dev | `Google Chrome Dev.app` | `com.google.Chrome.dev` | `Google/Chrome Dev` |
| `chrome-canary` | Chrome Canary | `Google Chrome Canary.app` | `com.google.Chrome.canary` | `Google/Chrome Canary` |
| `chromium` | Chromium | `Chromium.app` | `org.chromium.Chromium` | `Chromium` |
| `edge` | Edge | `Microsoft Edge.app` | `com.microsoft.edgemac` | `Microsoft Edge` |
| `arc` | Arc | `Arc.app` | `company.thebrowser.Browser` | `Arc/User Data` |
| `vivaldi` | Vivaldi | `Vivaldi.app` | `com.vivaldi.Vivaldi` | `Vivaldi` |

**Windows** (program under each app folder; data under `%LOCALAPPDATA%`):

| id | program | data folder | https ProgId |
|---|---|---|---|
| `brave` | `BraveSoftware\Brave-Browser\Application\brave.exe` | `BraveSoftware\Brave-Browser\User Data` | `BraveHTML` |
| `brave-beta` | `BraveSoftware\Brave-Browser-Beta\Application\brave.exe` | `BraveSoftware\Brave-Browser-Beta\User Data` | |
| `brave-nightly` | `BraveSoftware\Brave-Browser-Nightly\Application\brave.exe` | `BraveSoftware\Brave-Browser-Nightly\User Data` | |
| `chrome` | `Google\Chrome\Application\chrome.exe` | `Google\Chrome\User Data` | `ChromeHTML` |
| `chrome-beta` | `Google\Chrome Beta\Application\chrome.exe` | `Google\Chrome Beta\User Data` | |
| `chrome-dev` | `Google\Chrome Dev\Application\chrome.exe` | `Google\Chrome Dev\User Data` | |
| `chrome-canary` | `Google\Chrome SxS\Application\chrome.exe` | `Google\Chrome SxS\User Data` | |
| `chromium` | `Chromium\Application\chrome.exe` | `Chromium\User Data` | |
| `edge` | `Microsoft\Edge\Application\msedge.exe` | `Microsoft\Edge\User Data` | `MSEdgeHTM` |
| `arc` | none (an MSIX package) | none | |
| `vivaldi` | `Vivaldi\Application\vivaldi.exe` | `Vivaldi\User Data` | |

- **Linux:** only `brave` and `chrome` keep a data folder, today's (`platforms.py:30`). Linux detection is out of
  scope.
- **The inspect address** is `<scheme>://inspect/#remote-debugging`. The scheme is `brave` for the Brave rows, `edge`
  for Edge, and `chrome` for the rest. Pages show it only for rows with `agents` true, whose switch was measured.
- **What was measured, and what wasn't:**
  - measured on this Mac: `Brave Browser.app` (`com.brave.Browser`, 152.1.94.121) and `Google Chrome.app`
    (`com.google.Chrome`, 154.0.8037.93), and the leftover data folders of Arc (`Arc/User Data`), Chromium, Microsoft
    Edge and Vivaldi (investigation finding 10);
  - the Windows paths of stable Brave and Chrome are today's (`platforms.py:29`, `:33-34`);
  - the rest is the vendors' usual layout, from the investigation's design section 8. The laptop check (Testing, "By
    hand") confirms the Windows rows that are installed there. The other macOS channels stay unverified until one is
    installed. A wrong row only means that browser isn't found; nothing else reads it.
- **Only the stable ProgIds are listed.** The investigation names `BraveHTML`, `ChromeHTML` and `MSEdgeHTM`. Another
  channel as the system default gives no first guess, which is harmless (Decision 4).
- **The old helpers become views of the table.** `_MAC_DATA`, `_WINDOWS_DATA`, `_LINUX_DATA`, `_MAC_APPS` and
  `_WINDOWS_APPS` (`platforms.py:28-34`) are built from the `brave` and `chrome` rows. A `_MAC_APPS` entry is
  `/Applications/<app>/Contents/MacOS/<app without ".app">`, which gives today's two paths. `user_data_dir()` and
  `browser_candidates()` (`:57-75`) keep their signatures, results and `ValueError` for any other name, such as
  `"chrome-beta"`. So `chrome.own_browser_dirs()` (`chrome.py:24-26`) is unchanged.
- **Why one table:** today the code knows only Brave and Chrome, in two places (`platforms.py:28-34`,
  `chrome.py:83-84`). A table lets wave 4 name the browser (`browser_name`, `inspect_address`) from the row instead of
  looking for "bravesoftware" in a path (`chrome.py:69-76`).

### 3. Installed means the app is there

- **macOS:** a row is installed when all of these hold:
  - `<app folder>/<app>` exists, where the app folders are `/Applications`, then `~/Applications`;
  - its `Contents/Info.plist` reads with `plistlib`, XML or binary;
  - its `CFBundleIdentifier` equals the row's bundle id, ignoring case. LaunchServices writes `com.brave.browser` in
    lower case (investigation finding 9);
  - its `CFBundleExecutable` is a plain file name (no `/`, not `.` or `..`), and `Contents/MacOS/<that name>` is a
    file.

  The first match wins. `version` is `CFBundleShortVersionString` when it is a string of at most 32 characters, else
  None.
- **Windows:** the candidate programs come from three sources, in this order:
  1. the row's program path under each of `%ProgramFiles%`, `%ProgramFiles(x86)%` and `%LOCALAPPDATA%`, as today's
     `browser_candidates` does (`platforms.py:72-74`);
  2. `platforms.windows_browser_commands()`. It reads, current user first:
     - `SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\<exe>` for `brave.exe`, `chrome.exe`, `msedge.exe` and
       `vivaldi.exe` (as `chrome._registry_path` does, `chrome.py:117-130`);
     - `SOFTWARE\Clients\StartMenuInternet\*\shell\open\command`, in HKCU, HKLM and HKLM's `WOW6432Node`. This is
       Windows' own list of registered browsers.
  3. Nothing else.

  Then, for each candidate:
  - a command string is cut down to its program: the text inside the first pair of quotes, or else everything up to
    and including the first `.exe`, in any letter case;
  - `%NAME%` is expanded from `env`, with the name looked up without regard to case, as Windows does. An unknown
    name stays as written, so that path isn't a file;
  - the path must be a file;
  - it is matched to the row whose program path is its tail, compared part by part without regard to case, with either
    separator. Whole parts are compared, so `Google\Chrome SxS\...` is Canary and never Chrome. If two rows ever
    match, the longer tail wins;
  - a row found twice is counted once.
- **Not used:**
  - **the data folder.** Leftover folders exist on this Mac, so a folder proves nothing (finding 10). Today
    `app/run.py:99` decides on `own_browser_dir().is_dir()`; wave 4 replaces that;
  - **Spotlight (`mdfind`).** It returned nothing, even for Chrome, on this Mac (finding 10);
  - **PATH on macOS.** Browsers there aren't on PATH;
  - **renamed or moved apps,** and Windows installs outside the three folders that the registry doesn't list. They are
    not found (Out of scope).
- **Linux:** `installed()` returns `[]`. Callers keep today's `own_browser_dirs()` there.
- **Why both a bundle id and a program file:** an app with the right name but another bundle id is not that browser.
  A half-deleted app has no program, and wave 3 must be able to start what it finds.

### 4. The system's default browser, for a first guess only

- **`os_default(system=None, env=None) -> str | None`** gives the id of the system's default browser, or None.
  - **macOS:** it reads `~/Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist`. It
    takes the first `LSHandlers` entry whose `LSHandlerURLScheme` is `https`, and that entry's `LSHandlerRoleAll`.
    That is a bundle id, matched to a row ignoring case. On this Mac it is `com.brave.browser` (finding 9).
  - **Windows:** it takes `platforms.windows_https_progid()`. Under
    `HKCU\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https` it reads, and the first that gives a
    non-empty string wins:
    1. the key `UserChoiceLatest\ProgId`, value `ProgId`. Windows 11 25H2 writes the choice there and no longer
       updates `UserChoice` (reported in microsoft/PowerToys issue #39996 and by other projects; not measured
       here);
    2. the key `UserChoiceLatest`, value `ProgId`;
    3. the key `UserChoice`, value `ProgId`, which older Windows uses.

    A suffix after a `.` is dropped, and the rest is matched to a row's ProgId without regard to case.
  - **Elsewhere,** and on any failure: None.
- **What it is for:**
  - wave 4's first guess at the agents' browser;
  - wave 3's "Auto". The brief keeps the window apart from the browser that opens links from other apps (question
    1), and that browser is the system's default.
- **What it never does:** pick a browser by itself, or connect to one. A first guess is only shown; the user saves the
  choice.
- **Only the `https` entry is read.** Other handlers in the same file are ignored and never returned.

### 5. Profiles from `Local State`: name and colour only

- **`profiles(data_dir) -> list[Profile]`** reads `<data_dir>/Local State`. It uses three keys under `profile`, all
  measured in Chrome 154 and Brave 152 (finding 6):
  - `info_cache`: one entry per profile folder;
  - `profiles_order`: the browser's own order;
  - `last_used`: the folder used last.
- **The order:** first the folders in `profiles_order`, then any other `info_cache` folders, `Default` first and the
  rest sorted.
- **Dropped:**
  - `System Profile` and `Guest Profile`;
  - any entry whose `is_ephemeral` is true;
  - any folder name that is not a plain name (`plain_folder()`): empty, `.` or `..`, longer than 64 characters, or
    holding `/`, `\`, `:` or a control character (Unicode category `Cc`);
  - any folder that isn't a directory under `data_dir`. `Local State` can lag: a deleted profile may still be listed,
    and a new one may appear only after the browser saves the file, often at exit (finding 6).
- **Copied from each entry, and only these keys:**
  - `name`;
  - `profile_highlight_color`, else `default_avatar_fill_color`;
  - nothing else.
- **Never read into any result:** `user_name`, `gaia_name`, `gaia_given_name`, `gaia_id`, `avatar_icon` and every
  account field. `user_name` and `gaia_name` can hold the signed-in email (finding 6).
- **The colour:** a signed 32-bit ARGB integer becomes `#rrggbb` (`value & 0xFFFFFF`). For example, `-12627531` gives
  `#3f51b5`. It is None when the value is missing, a bool, not an int, or outside `-2**31 .. 2**32-1`.
- **The name:**
  - a `name` that isn't a string counts as blank;
  - control characters (category `Cc`) and bidi controls (U+200E, U+200F, U+202A to U+202E, U+2066 to U+2069) are
    removed;
  - spaces at the ends are trimmed;
  - it is cut to 64 characters;
  - a blank name, or a name that holds `@`, becomes the folder name ("Profile 2"). So an email used as a profile name
    never comes out either.
- **`Profile`** has exactly four fields: `folder`, `name`, `color` and `last_used` (a bool).
- **No "signed in" flag.** The investigation proposed one. Dropped:
  - a browser account isn't what the user meant by "signed in": that was the sites agents need;
  - Brave has no Google account;
  - it would mean reading account fields.
- **The name shown can differ from the browser's menu.** Chrome may show the account's first name for a profile that
  keeps its default name ("Your Chrome"). We show `name` and the colour, and don't read the account's name.

### 6. Is it running? The browser's own lock

- **`running(data_dir, system=None) -> bool | None`.** True means it runs, False means it doesn't, and None means it
  can't tell.
- **macOS and Linux:** `<data_dir>/SingletonLock` is a symbolic link whose target is `<host>-<pid>`, for example
  `Alexs-MacBook.local-23735` (finding 8 measured this shape; the name here is neutral).
  - It reads the link's target with `os.readlink` and never follows it.
  - It splits at the last `-`.
  - When the host equals `socket.gethostname()`, the answer is `platforms.pid_alive(pid)` (`platforms.py:175-187`).
    Chromium writes the target from the same `gethostname()` call.
  - No link gives False. A regular file, an unreadable link, a target with no number, or another host gives None.
  - After a crash, a stale lock whose pid now belongs to another program reads as running. The card then says
    "switch off" instead of "not running" until the browser starts again and rewrites the lock.
- **Windows:** True when `<data_dir>/lockfile` exists, False when it doesn't.
  - It is only checked for existence, with `Path.exists()`. It is never opened for reading or writing. On Windows
    `exists()` asks only for the file's attributes, and a handle that asks only for attributes takes no part in
    sharing checks, so it can't make the browser's own open fail.
  - Chromium creates it with `GENERIC_WRITE`, share mode `FILE_SHARE_READ`, `CREATE_ALWAYS` and
    `FILE_FLAG_DELETE_ON_CLOSE` (`chrome/browser/process_singleton_win.cc`, Chromium main, read 2026-10-03). Our open
    would not share delete access. If it landed while the browser starts, the browser's own `CreateFile` could fail,
    and the browser would think another copy of itself holds the profile. Not opening it can't cause that.
  - Delete-on-close removes it when the browser exits, even after a crash, because Windows closes the handle. A power
    cut can leave one behind: then the card says "switch off" instead of "not running".
  - The investigation proposed "the lockfile can't be opened". That is replaced by this existence check, for the
    reason above. It is a laptop check.
- **Why the lock is needed at all:** `DevToolsActivePort` and `SingletonLock` both stay behind after the browser exits
  (measured, finding 8). The port file alone can't tell "not running" from "switch off". A stale port can even answer,
  if another program now holds it.
- **What it never does:** list processes, read another process's memory or command line, or signal a process.
  `pid_alive` sends signal 0 on POSIX, which delivers nothing. On Windows it is never needed here.

### 7. Is the switch on? `DevToolsActivePort` plus a silent TCP check

- **`devtools_port(data_dir) -> int | None`.** The first line of `<data_dir>/DevToolsActivePort`, stripped, must be
  one to five ASCII digits (`re.fullmatch(r"[0-9]{1,5}", …)`), from 1 to 65535. Anything else gives None. The
  second line, the browser's path, isn't needed here.
  - This is stricter than `chrome._port_of` (`chrome.py:29-37`). Its `isdigit()` also takes other Unicode digits,
    and `int("²")` then raises `ValueError`: `chrome.switch_on` raises on a port file whose first line is `²`
    (checked at HEAD with a scratch folder). This track doesn't touch `chrome.py` (Decision 13).
- **`listening(port, timeout=0.5) -> bool`:**
  - `socket.create_connection(("127.0.0.1", port), timeout)`, then it closes at once;
  - it sends no bytes, so no HTTP request and no websocket upgrade;
  - any `OSError` gives False, and so does a port outside 1 to 65535, without trying;
  - this is the same rule as `chrome._listening` (`chrome.py:40-45`), with the timeout as an argument.
- **Why it can't ask Allow:** the question belongs to a DevTools session, and the browser asks only when a websocket
  upgrade request arrives (the brief cites `devtools_http_handler.cc:858-870`). A TCP connection that sends no bytes
  makes no request, so that code never runs (investigation `relay` finding: "switch_on and find_ws_url only read
  DevToolsActivePort and open a raw TCP socket…"). The app already makes this check every 2 s (`bravelink.py:20`,
  `:80-88`) and `doctor --setup` makes it once (`cli.py:175`), with no question.
- **The two helpers are copied, not imported from `chrome.py`.** `browsers.py` imports nothing from `chrome.py`. Wave 4
  makes `chrome.py` use `browsers.py` (the saved choice, the browser's name), and a cycle would break that. Wave 4 then
  points `chrome._port_of` and `_listening` at these two, which also ends the `²` crash above.

### 8. The state, and who adds "connected"

- **`state(data_dir, system=None) -> str`** is one of `STATES = ("not_running", "switch_off", "switch_on")`:

  | `running()` | port answers | state |
  |---|---|---|
  | False | not checked | `not_running` |
  | True | yes | `switch_on` |
  | True | no, or no port file | `switch_off` |
  | None | yes | `switch_on` |
  | None | no | `not_running` |

  A missing `data_dir` gives `not_running`.
- **The switch is judged only by `DevToolsActivePort` and the TCP check.** The lock only tells "not running" apart from
  "switch off".
- **When it can't tell (None),** it falls back to today's rule, the port alone (`chrome.switch_on`, `chrome.py:48-52`).
  It never claims `switch_off` without knowing the browser runs. "Switch off" shows steps to tick a box, which are
  wrong for a browser that isn't open.
- **No TCP check for a browser that isn't running.** So a stale port held by another program is never touched.
- **"connected" is not detected here.** It means the app's own link to that browser is up, which is wave 2A's and wave
  4's state (today `BraveLink.state`, `bravelink.py:30`). `public()` takes the ids that are connected and shows them as
  `connected` (Decision 12).
- **No `not_installed` state.** `detect()` lists only installed browsers, and `state()` is asked about a data folder.

### 9. Which profile holds a watcher copy

- **`watcher_places(data_dir, watchers, system=None) -> list[WatcherPlace]`:**
  - `watchers` maps each watcher id to the folder it was loaded from. Today that is one entry: `<home>/app/watcher`
    (`brain/watcher.py:35`) and its id, `extension_id_for(folder)` (`appbrowser.py:79-85`, used at `app/run.py:206`).
    Wave 4 adds one copy per profile;
  - for each profile from `profiles(data_dir)`, it reads `<profile>/Secure Preferences`, then `<profile>/Preferences`,
    and looks at `extensions.settings.<id>` for each watcher id. An entry in `Secure Preferences` wins over one in
    `Preferences`. In the throwaway Brave the entry was in `Secure Preferences`, and `Preferences` had none (finding 5);
  - an entry counts only when all of these hold:
    - its `path` is a string naming the same folder. On `system == "win32"` both strings go through
      `ntpath.normcase(ntpath.abspath(…))`, the comparison `extension_installed` makes (`appbrowser.py:90-94`), with
      no link resolved, as Chrome resolves none (`extension_path`, `appbrowser.py:68-76`). Elsewhere it is
      `os.path.realpath` of both, compared exactly;
    - it is enabled: `disable_reasons` is missing, `0` or an empty list. A non-zero number, a non-empty list or any
      other type means disabled. An old-style `state` of `0` means disabled too.
  - `location` is not checked. The probe's `--load-extension` gave 8, and Load unpacked gives 4.
- **`WatcherPlace`** has two fields, `profile` (the folder name) and `extension_id`. The list is in profile order.
- **The same id in two profiles is reported, not guessed.** Loading one folder in two profiles gives one id (the id
  comes from the path), and at run time the two can't be told apart (investigation risk 2). The same holds across
  browsers: Chrome gives a folder the same id as Brave (measured, brief section 5). Both places are listed, and
  `public()` marks them `shared_watcher`. Wave 4 then asks for a copy per profile.
- **Why not today's `extension_installed`** (`appbrowser.py:88-105`):
  - it looks only in `Default`;
  - it counts a disabled copy;
  - it lives in `appbrowser.py`, which wave 3 rewrites.

  It stays as it is for AI Browser's own extension until wave 3 retires it.
- **The runtime side is wave 4's.** Matching a profile folder to its live `browserContextId` needs the watcher's
  service-worker target, so it needs a connection (finding 5). This module never connects.

### 10. Every read fails safely

- **One reader,** `browsers._read(path) -> bytes | None`:
  - only a regular file is read (`Path.is_file()`). A folder, a pipe or a device gives None, so a pipe can't hang it;
  - the file is opened through `platforms.open_shared` (Decision 11), with `MAX_FILE = 16 * 1024 * 1024`. When
    `os.fstat` gives a size over `MAX_FILE`, it gives None without reading. Otherwise it reads up to `MAX_FILE + 1`
    bytes in one `read()`, and more than `MAX_FILE` (a file that grew) gives None too;
  - any `OSError` gives None.
- **JSON** is decoded as UTF-8 with `errors="replace"`, then parsed with `json.loads`. `ValueError` and
  `RecursionError` give None.
- **Plists** use `plistlib.loads`, and any `Exception` it raises gives None. A narrower list would miss some: a cut
  XML plist raises `xml.parsers.expat.ExpatError`, and a broken `<date>` raises `AttributeError`, neither of them a
  `ValueError` (checked with Python 3.12 at HEAD).
- **Every level is type-checked** before use: a dict where a dict is expected, a str where a str is expected. A bad
  entry is skipped and the others are kept.
- **What each failure gives:**

  | read | failure | result |
  |---|---|---|
  | `Info.plist` | missing, broken, wrong id, bad executable name | that app isn't counted |
  | registry key | any `OSError` | that source gives nothing |
  | LaunchServices plist, ProgId | anything | `os_default()` is None |
  | `Local State` | missing, too big, broken, wrong types | `[]` |
  | one `info_cache` entry | wrong type, bad folder name | that entry is skipped |
  | `Secure Preferences`, `Preferences` | anything | no watcher found in that file |
  | `SingletonLock` | missing | False |
  | `SingletonLock` | not a link, bad target, other host | None |
  | `DevToolsActivePort` | missing, broken | no port, so not listening |
  | TCP check | refused, timed out, any `OSError` | not listening |

- **No public function raises,** whatever the files hold. The tests feed every sample cut short at many points
  (Testing).
- **Why:** `Local State` and `Secure Preferences` are Chromium internals, not an API (brief, "The risks"). A browser
  update may rename a key. Then we show less, never wrong data, and never crash Settings.

### 11. Reading never gets in the browser's way

- **`platforms.open_shared(path) -> BinaryIO`** opens a file for reading only:
  - **POSIX:** `open(path, "rb")`;
  - **Windows:** `CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, None,
    OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None)`, wrapped with `msvcrt.open_osfhandle(handle, os.O_RDONLY | O_BINARY)`
    and `os.fdopen(fd, "rb")`. It goes through `_kernel32()`, with the `CreateFileW` prototype added
    (`platforms.py:159-172`). An invalid handle raises `ctypes.WinError(ctypes.get_last_error())`, an `OSError`. If
    the wrapping fails, the handle is closed before the error goes up.
  - Like every reader there, it returns a binary file, so `test_text_io_names_its_encoding` stays green.
- **Why:**
  - Chromium saves `Local State` and `Preferences` by writing a temporary file, then calling Win32 `ReplaceFile` with a
    backup name (`base/files/file_util_win.cc`, `ReplaceFile`, Chromium main, read 2026-10-03). `ReplaceFile` first
    renames the old file to the backup name;
  - a plain Python `open` on Windows doesn't share delete access, and the Win32 documentation says delete access
    covers rename. So a save that lands while we read would fail. Chromium's fallback `MoveFile` then fails too,
    because the old name still exists, and the browser loses that save;
  - with delete shared, the old file can be renamed away while we hold it, and the save goes through;
  - the read is also a single `read()`, and the handle closes before parsing, so any overlap lasts milliseconds.
- **Never:** a write, a lock, a rename, a `touch` or a temporary file in a browser's folder.

### 12. One call for the pages: `detect()` and `public()`

- **`detect(watchers=None, system=None, env=None) -> list[Found]`:**
  - `installed()`, in table order;
  - then, for each row with `agents` true: `state()`, `profiles()` and `watcher_places()`;
  - rows with `agents` false get no state, no profiles and no watchers. Nothing in their data folder is read: the
    greyed card needs only the name. On macOS, `installed()` has read only their app's `Info.plist`, to find them;
  - `default` is true for the row `os_default()` names.
- **`public(found, connected=()) -> list[dict]`** is the only shape meant for pages, so wave 4's message is fixed here:
  - per browser: `id`, `name`, `agents`, `default`, `state` (one of `STATES` or `"connected"`, or null when `agents`
    is false) and `profiles`;
  - per profile: `folder`, `name`, `color`, `last_used`, `watcher` and `shared_watcher`. `watcher` is true when the
    profile holds an enabled copy of any watcher id. `shared_watcher` is true when one of those ids is also enabled
    in another profile anywhere in `found`, of the same browser or of another one;
  - `connected` holds browser ids. A listed id with a known state shows `"connected"`.
- **Left out of `public()` on purpose:**
  - paths: they hold the user's account name;
  - versions;
  - watcher ids;
  - anything from an account field.
- **Cost:**
  - `state()` reads two small files and makes at most one TCP check, which can wait up to 0.5 s. It is fine to poll
    every 2 s, as `BraveLink._look` does today;
  - `detect()` also reads `Local State` and two preference files per profile, which can be a few MB. Wave 4 calls it
    when a page opens or after a click, never on a timer. Not measured;
  - all functions are synchronous. The async app calls them through `asyncio.to_thread`.

### 13. No callers yet, and no file the relay touches

- **This track changes:**
  - `src/ai_browser/browsers.py` (new);
  - `src/ai_browser/platforms.py` (additions only);
  - `tests/test_browsers.py` (new);
  - `tests/test_platforms.py` (new tests added);
  - `tests/samples/browsers/` (new sample files).
- **It doesn't touch** any file in the relay's list (the cdp-relay spec, "Files"), among them `app/cdprelay.py`,
  `cdp.py`, `engine.py`, `agentlink.py`, `browser.py`, `app/bravelink.py`, `app/tabs.py`, `app/server.py`,
  `app/run.py`, `app/agents.py`, `tests/conftest.py`, `tests/test_chrome.py` and the everyday-brave spec. It doesn't
  touch `chrome.py`, `cli.py` or `bridge.py` either. The relay, in turn, touches neither `browsers.py` nor
  `platforms.py`.
- **Nothing calls `browsers.py` in this wave.** Wave 4 wires it in, and wave 3 may use it to find the window's
  browser. Shipping it alone keeps the parallel tracks apart, and lets the planner merge it without a hand check of
  Brave.

### 14. What this changes in earlier specs

These notes live here. This track edits no earlier spec file: the relay (2A) edits the everyday-brave spec in the same
wave, and wave 4 corrects its profile claim.

- **everyday-brave, Out of scope** (`2026-10-02-everyday-brave-design.md:972`, "Chromium browsers other than Brave and
  Chrome"): detection now knows the Brave and Chrome channels and Chromium, and wave 4 offers them. Edge, Arc and
  Vivaldi are detected and shown as "not supported yet".
- **everyday-brave, Out of scope** (`:969`, choosing a profile): this spec supplies the profile list. Wave 4 supplies
  the choice. The wrong claim at `:806-807` ("Brave's default profile") is wave 4's to correct, where tabs are placed.
- **windows-and-repo, Decision 1:** the two-row tables in `platforms.py` become views of one table. Results are
  unchanged.
- **From the investigation's design, changed here:**
  - `state()` has no `not_installed` (Decision 8);
  - `Profile` has no `signed_in` (Decision 5);
  - the Windows running check looks for the lockfile and never opens it (Decision 6);
  - a profile folder must exist on disk and have a plain name (Decision 5).

## Messages / interfaces

**New module `src/ai_browser/browsers.py`:**
- `STATES = ("not_running", "switch_off", "switch_on")` and `MAX_FILE = 16 * 1024 * 1024`.
- `@dataclass(frozen=True) class Installed`:
  - `facts: platforms.BrowserFacts`, `binary: Path`, `bundle: Path | None` (the `.app` on macOS), `version: str | None`
    and `data_dir: Path`;
  - properties `id`, `name`, `agents`, `window` and `inspect_address`.
- `@dataclass(frozen=True) class Profile`: `folder: str`, `name: str`, `color: str | None` and `last_used: bool`.
- `@dataclass(frozen=True) class WatcherPlace`: `profile: str` and `extension_id: str`.
- `@dataclass(frozen=True) class Found`: `browser: Installed`, `state: str | None`, `profiles: tuple[Profile, ...]`,
  `watchers: tuple[WatcherPlace, ...]` and `default: bool`.
- Functions:
  - `by_id(browser_id) -> BrowserFacts | None`;
  - `data_dir(facts, system=None, env=None) -> Path | None`: `platforms.browser_data_dir()`, so the macOS folder is
    spelled only in `platforms.py`;
  - `all_data_dirs(system=None, env=None) -> list[Path]`: every row's data folder on this system, installed or not.
    Wave 3's window and wave 4's `launch()` guard can refuse them all;
  - `for_data_dir(folder, system=None, env=None) -> BrowserFacts | None`: which known browser owns a data folder.
    Both paths go through `os.path.realpath`, and on `system == "win32"` through `ntpath.normcase` too. That is
    `chrome._same_folder`'s rule (`chrome.py:133-138`), except that the case rule follows `system` instead of the real
    OS, so the Mac can test it. Wave 4's `browser_name` and `inspect_address` use it;
  - `installed(system=None, env=None, folders=None, commands=None) -> list[Installed]`. `folders` defaults to
    `platforms.app_folders(system, env)`, and `commands` to `platforms.windows_browser_commands()` on `win32`;
  - `os_default(system=None, env=None) -> str | None`;
  - `plain_folder(name) -> bool`: Decision 5's plain-name rule for a profile folder. It is public so that wave 4's
    `plain_profile` (the browser-profile-choice spec) applies the same rule to a name from the environment or a file;
  - `profiles(data_dir) -> list[Profile]`;
  - `watcher_places(data_dir, watchers: Mapping[str, str | Path], system=None) -> list[WatcherPlace]`;
  - `devtools_port(data_dir) -> int | None` and `listening(port, timeout=0.5) -> bool`;
  - `running(data_dir, system=None) -> bool | None`;
  - `state(data_dir, system=None) -> str`;
  - `detect(watchers=None, system=None, env=None) -> list[Found]`;
  - `public(found, connected=()) -> list[dict]`.
- It imports only the standard library (`collections.abc`, `dataclasses`, `json`, `ntpath`, `os`, `pathlib`,
  `plistlib`, `re`, `socket`, `sys`, `unicodedata`) and `platforms`. It imports nothing that can open a DevTools session or start a
  program: no `cdp`, `websockets`, `chrome`, `appbrowser`, `http`, `urllib` or `subprocess`.

**Added to `src/ai_browser/platforms.py`:**
- `@dataclass(frozen=True) class BrowserFacts`, with these fields:
  - `id: str`, `name: str`, `agents: bool`, `window: bool` and `inspect: str` (the scheme);
  - `mac_app: str`, `mac_bundle_id: str` and `mac_data: tuple[str, ...]`;
  - `win_exe: tuple[str, ...] | None` and `win_data: tuple[str, ...] | None` (None for Arc), and
    `win_progid: str | None`;
  - `linux_data: tuple[str, ...] | None` (set for `brave` and `chrome` only).
- `KNOWN_BROWSERS: tuple[BrowserFacts, ...]` (Decision 2).
- `browser_data_dir(facts, system=None, env=None) -> Path | None`: `~/Library/Application Support/<mac_data>` on
  `darwin`, `%LOCALAPPDATA%\<win_data>` on `win32` (with today's fallback when the variable is missing,
  `platforms.py:51-54`), `~/.config/<linux_data>` elsewhere, and None when the row has no folder there.
  `user_data_dir()` returns the same path for `brave` and `chrome`.
- `app_folders(system=None, env=None) -> list[Path]`:
  - macOS: `/Applications`, then `~/Applications`;
  - Windows: `%ProgramFiles%`, `%ProgramFiles(x86)%` and `%LOCALAPPDATA%`, the ones that are set;
  - elsewhere: `[]`.
- `launch_services_file() -> Path`: the LaunchServices plist (macOS).
- `lock_name(system=None) -> str`: `"lockfile"` on `win32`, else `"SingletonLock"`.
- `windows_browser_commands() -> list[str]` and `windows_https_progid() -> str | None`, the registry readers of
  Decisions 3 and 4. They use the real OS, branch on `WINDOWS` and import `winreg` inside the function. Elsewhere they
  give `[]` and None.
  - They only open keys with `KEY_READ` and read values: `OpenKey`, `EnumKey`, `QueryValueEx`. They never create,
    set or delete a key or value.
  - Each key's `OSError` is caught on its own, and a value that isn't a string is skipped.
- `open_shared(path) -> BinaryIO` (Decision 11).
- `_MAC_DATA`, `_WINDOWS_DATA`, `_LINUX_DATA`, `_MAC_APPS` and `_WINDOWS_APPS` are derived from the table.
  `user_data_dir` and `browser_candidates` don't change.

**No messages, HTTP routes, settings or environment variables** in this wave. `settings.json`, `AIB_CHROME_PROFILE`,
the `browsers` page message and the Settings page are wave 4's. `public()` fixes the fields wave 4 sends.

**Sample files, `tests/samples/browsers/`:** hand-written, trimmed to the keys this module reads, plus decoys. The key
names follow what the investigation measured in throwaway Chrome 154 and Brave 152 (findings 5 and 6). No value is
copied from the user's own browser files. They use the neutral name Alex and `example.com`, and hold no path of this
computer (`test_repo_hygiene`, `tests/test_portable.py:229-238`):
- `brave-local-state.json`:
  - `Default` "Personal" with `profile_highlight_color: -12627531`;
  - `Profile 1` "Work" with `default_avatar_fill_color: -14983648`;
  - `Profile 2` named `alex@example.com`;
  - `Profile 3` with `is_ephemeral: true`;
  - `Profile 4`, listed but with no folder;
  - `System Profile` and `Guest Profile`;
  - `user_name: "alex@example.com"`, `gaia_name: "Alex Example"`, `gaia_given_name: "Alex"` and `gaia_id` on Default;
  - `profiles_order: ["Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4"]` and
    `last_used: "Profile 1"`.
- `chrome-local-state.json`: one `Default` "Your Chrome" with `is_using_default_name: true` and no colour.
- `secure-preferences-watcher.json`: one entry under `extensions.settings` with `location: 4` and
  `disable_reasons: []`, plus one unrelated extension. The test loads it, puts the entry under the watcher's id with
  the watcher's folder as `path`, and writes it with `json.dumps`, so a Windows path is escaped correctly.
- `preferences-watcher-disabled.json`: the same entry with `disable_reasons: [1]`.
- `brave-info.plist` and `chrome-info.plist` (XML): `CFBundleIdentifier`, `CFBundleExecutable` and
  `CFBundleShortVersionString`.
- `launchservices.plist` (XML): `LSHandlers` with a `mailto` entry first, then `https` → `com.brave.browser`.

**How later waves use it** (guidance, not this wave's work):
- **Wave 3:** finds the window's browser with `installed()`, keeps the rows with `window` true (Edge on Windows
  only), and uses `os_default()` for "Auto". `all_data_dirs()` keeps the window's own profile away from every real
  one.
- **Wave 4:**
  - Settings and the chip come from `detect()` and `public(found, connected=…)`;
  - `own_browser_dir()` uses the saved choice in place of "first switch on" (`chrome.py:55-63`);
  - `browser_name` and `inspect_address` come from `for_data_dir()`;
  - the first-run profile is the one holding the watcher, else the `last_used` one. The user still picks it in
    Settings (their answer to question 2).
- **The test fixture:** wave 3 moves the parts of this spec's test fixture that keep detection off the real files
  into `tests/conftest.py`'s autouse fixture (`:53-60`), because it is the first wave whose app code calls
  `installed()` and `os_default()` (the app-window spec, Decision 16). Those read only app bundles' `Info.plist`, the
  LaunchServices file and the registry, never a profile, and wave 3's `pick()` also takes both as arguments so its
  tests can pass them. Wave 4, whose app calls `detect()`, keeps that fixture (the browser-profile-choice spec,
  Testing).

## Safety

The rules of this project hold. In this module:

- **The "Allow remote debugging?" question and the automation bar:**
  - detection opens no DevTools session, so it can't cause the question or the bar;
  - it never clicks, answers, suppresses or hides either one;
  - it never touches the switch.
- **No spoofing or disguise.** It launches nothing and changes no browser setting.
- **No bot-check bypass.** Nothing here drives a page.
- **Passwords:** it types nothing. It reads only these files and keys:
  - `Info.plist` and the LaunchServices plist;
  - `Local State`, and `Secure Preferences` and `Preferences` in each profile;
  - `DevToolsActivePort`;
  - `SingletonLock` (its link target only) and `lockfile` (whether it exists);
  - the registry keys in Decisions 3 and 4.

  It never opens `Login Data`, `Cookies`, `Web Data`, `History`, the Keychain or DPAPI. Test 30 enforces the file
  list, and test 38 that the registry is only read.
- **Emails stay put.** Account fields are never read into a result. A name with `@` is replaced by the folder name.
  `public()` carries no path. Tests check it with the sample's email and name.
- **Profile names are data, not instructions.** A name is the user's text, read from a browser file:
  - it is cleaned and capped here;
  - wave 4 shows it with `textContent` only;
  - if wave 4 ever puts it in the Brain's state summary, it goes there as quoted data, never as part of the
    instructions.
- **Nothing leaves the machine.** The only network use is a TCP connect to `127.0.0.1` that sends no bytes. Results
  stay in the app's process until wave 4 sends `public()` to its own pages. Nothing goes to Claude from this module.
- **No downloads, and no new dependency.** It uses only `plistlib`, `winreg`, `ctypes` and `msvcrt`, all in the
  standard library.
- **Read-only.** It never writes, locks, renames or creates a file in a browser's folder, and never opens the Windows
  lockfile. On Windows it reads with delete shared, so the browser's own saves go through (Decision 11).
- **No choice by itself.** Detection reports, and the user chooses in wave 4. A first guess is only shown. Detection
  never connects to any browser, so it can't connect to one the user didn't pick.
- **Hand-over and take-back** are untouched: this module knows nothing about tabs.

## Testing

All tests below are new, so each fails before (`ImportError`, or the missing `platforms` names) and passes after. No
test reads the user's real files or reaches a real browser:
- an autouse fixture in `tests/test_browsers.py` points `HOME`, `USERPROFILE`, `LOCALAPPDATA`, `ProgramFiles` and
  `ProgramFiles(x86)` at `tmp_path`;
- it replaces `platforms.app_folders` with one that gives temporary folders: `<tmp>/Applications` and
  `<fake home>/Applications` for `darwin`, the three Windows roots above for `win32`, and `[]` elsewhere;
- it makes `platforms.windows_browser_commands` return `[]` and `platforms.windows_https_progid` return None.

The first test proves this fixture works. Tests that need a symbolic link use `symlink_or_skip` from
`tests/conftest.py`.

### `tests/test_browsers.py` (the Mac and Windows CI)

**The table:**
1. `test_the_tests_never_read_the_real_browsers`: with the fixture and empty temporary folders, `installed()` and
   `installed(system="darwin")` are `[]`, `os_default()` is None, `Path.home()` is under `tmp_path`, and
   `platforms.app_folders("darwin")` holds no folder outside `tmp_path`.
2. `test_the_table_lists_each_browser_once`:
   - the ids are unique, and `brave` comes first;
   - `agents` is true exactly for the eight ids in Decision 2;
   - `window` is true exactly for `brave`, `chrome` and `edge`;
   - there is no `opera`;
   - every `agents` row has `mac_data` and `win_data`.
3. `test_the_old_folder_helpers_read_the_table`: for `darwin`, `win32` (fake `env`) and `linux`,
   `platforms.user_data_dir("brave"/"chrome")` equals `browsers.data_dir(by_id(...))`. `browser_candidates` gives
   today's lists, and `user_data_dir("chrome-beta")` still raises `ValueError`.
4. `test_for_data_dir_names_the_browser`:
   - a fake Brave data folder gives the `brave` row;
   - with `system="win32"` and a fake `env`, the same path in other letter case gives `brave`;
   - on a POSIX host, with `system="linux"`, that other-case path gives None. (Windows' `realpath` restores the case
     found on disk, so this part is skipped there.)
   - an unknown folder gives None;
   - `all_data_dirs("darwin")` includes the Edge, Arc and Vivaldi folders.

**Installed apps:**

5. `test_mac_installed_means_the_app_with_its_bundle_id`:
   - temporary app folders hold `Brave Browser.app` and `Google Chrome.app`, each with its sample `Info.plist` and its
     program file;
   - the fake home has leftover data folders for Arc, Chromium, Microsoft Edge, Vivaldi and `com.operasoftware.Opera`;
   - the result is `brave` then `chrome`, with the right `binary`, `version` and `data_dir`.
6. `test_mac_apps_in_the_users_applications_folder`: `~/Applications/Google Chrome Canary.app` gives `chrome-canary`.
7. `test_a_mac_app_that_isnt_the_browser_is_skipped` (parametrized):
   - skipped: a wrong `CFBundleIdentifier`, a missing `Info.plist`, garbage bytes, an XML plist cut in the middle
     (`ExpatError`), a broken `<date>` value (`AttributeError`), `CFBundleExecutable` set to `../../x`, and a
     missing program;
   - counted: a binary plist, and the bundle id in lower case.
8. `test_windows_installed_from_the_app_folders`: with `system="win32"` and the roots in `tmp_path`, `brave.exe` under
   `LOCALAPPDATA`, `chrome.exe` under `ProgramFiles` and `msedge.exe` under `ProgramFiles(x86)` give `brave`, `chrome`
   and `edge`. Edge has `agents` false. Each `data_dir` is under `LOCALAPPDATA`.
9. `test_windows_installed_from_the_registry`, with `system="win32"` and `commands=[…]`. The paths are written with
   `/`, so the files exist on the Mac, and the parser takes both separators. The `commands` are:
   - a quoted `…/Google/Chrome Beta/Application/chrome.exe --single-argument %1`;
   - an unquoted `%localappdata%/Chromium/Application/CHROME.EXE -- %1` (other letter case);
   - a quoted path that doesn't exist;
   - `not a path`;
   - the Chrome Beta command again.

   The result is `chrome-beta` and `chromium`, once each.
10. `test_canary_is_never_taken_for_chrome`: `…/Google/Chrome SxS/Application/chrome.exe` gives `chrome-canary` only.

**The default browser:**

11. `test_os_default_on_the_mac` (`system="darwin"`):
    - the sample LaunchServices plist at `platforms.launch_services_file()` under the fake home gives `brave`. The
      same data written as a binary plist, as macOS writes it, gives `brave` too;
    - with no `https` entry: None; with garbage: None; with an unknown bundle id: None;
    - the `mailto` handler is never returned.
12. `test_os_default_on_windows` (parametrized, `windows_https_progid` patched):
    - `ChromeHTML` gives `chrome`, `BraveHTML` gives `brave`, `MSEdgeHTM` gives `edge`, `ChromeHTML.ABC123`
      gives `chrome`, and `bravehtml` gives `brave`;
    - `ChromeBHTML` (Chrome Beta's) gives None, never `chrome`;
    - `FirefoxURL-308046B0AF4A39CB` gives None, and None gives None.

**Profiles:**

13. `test_profiles_read_name_colour_and_order`:
    - the data folder holds the folders `Default`, `Profile 1`, `Profile 2`, `Profile 3`, `System Profile` and
      `Guest Profile`, and no `Profile 4`;
    - the Brave sample gives `[Profile("Default", "Personal", "#3f51b5", False), Profile("Profile 1", "Work",
      "#1b5e20", True), Profile("Profile 2", "Profile 2", None, False)]`. System, Guest, the ephemeral profile and
      the folderless `Profile 4` are absent;
    - with `profiles_order` reversed, the order follows it;
    - without `profiles_order`, `Default` comes first and the rest are sorted;
    - a folder `Profile 5` that `info_cache` doesn't list is not shown.
14. `test_profiles_never_return_an_email`:
    - `alex@example.com`, `Alex Example` and the `gaia_id` appear nowhere in `repr(profiles(...))` or in
      `json.dumps(public(detect(...)))`;
    - the profile named `alex@example.com` shows as `Profile 2`;
    - `dataclasses.fields(Profile)` are exactly `folder`, `name`, `color` and `last_used`.
15. `test_profile_names_are_cleaned`:
    - `"\u202eevil\x07"` becomes `"evil"`;
    - 200 characters are cut to 64;
    - `"   "` becomes the folder name.
16. `test_colours` (parametrized):
    - `-16777216` gives `#000000`, `-1` gives `#ffffff`, and `4282339765` gives `#3f51b5`;
    - `True`, `"#fff"`, `2**40` and None give None.
17. `test_a_profile_folder_name_cannot_leave_the_data_folder`:
    - `plain_folder()` is False for `../Default`, `/etc`, `a/b`, `a\\b`, `C:x`, `""`, `.`, `..`, a name holding
      `\x00` and a name of 65 characters, and True for `Default` and `Profile 12`;
    - as `info_cache` keys, the same names are skipped, even when the path they name exists (a `Default` folder
      beside the data folder, `/etc`, a folder `C:x`).
18. `test_profiles_fail_safely` (parametrized). None raises, and each gives `[]` or keeps only the good entries:
    - a missing file, an empty file, truncated JSON, or a JSON list;
    - `profile` as a string, `info_cache` as a list, or an entry as a number;
    - `name` as a number, which shows the folder name;
    - `profiles_order` holding numbers, invalid UTF-8, or 10,000 nested lists;
    - a folder named `Local State`, and on POSIX a named pipe called `Local State` (a plain read would wait
      forever);
    - a 17 MB sparse file, which returns `[]` without reading it (a recording `read` sees no call).

**Watchers:**

19. `test_watcher_places`:
    - `Profile 1`'s `Secure Preferences` holds the watcher, enabled: it gives `[WatcherPlace("Profile 1", ID)]`;
    - an entry only in `Default`'s `Preferences` counts;
    - `disable_reasons: [1]`, `disable_reasons: 1` or `state: 0` doesn't count;
    - a `path` naming another folder doesn't count;
    - an id that isn't in `watchers` is ignored;
    - `Secure Preferences` saying disabled wins over `Preferences` saying enabled.
20. `test_the_same_watcher_in_two_profiles_is_reported`:
    - the watcher enabled in Brave's `Default` and `Profile 1`: both places are listed, and `public()` marks both
      `shared_watcher`;
    - the watcher enabled in Brave's `Default` and Chrome's `Default`: `public()` marks both `shared_watcher`;
    - the watcher enabled in one profile only: `shared_watcher` is false everywhere.
21. `test_watcher_paths_ignore_case_only_on_windows`:
    - with `system="win32"`, `C:\Users\Alex\.ai-browser\app\watcher` matches `c:\users\alex\.ai-browser\app\watcher`,
      and `C:\Users\Alex\.ai-browser\app\watcher2` doesn't;
    - on a POSIX host, with `system="darwin"`, the watcher's folder with its last part in other letter case doesn't
      match. The comparison is exact there, as the extension id hashes the exact path (`appbrowser.py:79-85`).
      Windows' `realpath` restores the case found on disk, so this part is skipped there.
22. `test_watcher_places_fail_safely` (parametrized): a broken file, `extensions` as a list, `settings` as a string,
    `path` as a number, or `disable_reasons` as a string gives no place and doesn't raise.

**Running, the switch and the state:**

23. `test_running_reads_the_lock_on_mac_and_linux` (with `symlink_or_skip`, `system="darwin"`):
    - `<gethostname()>-<os.getpid()>` gives True;
    - the pid of a child that has exited and been waited for gives False;
    - no link gives False;
    - `elsewhere.local-<os.getpid()>` gives None, `garbage` gives None, and a regular file gives None.
24. `test_running_on_windows_only_looks_for_the_lockfile` (`system="win32"`):
    - a present `lockfile` gives True, and a missing one gives False;
    - `platforms.open_shared` and `builtins.open` are patched to fail the test if they get that path. On POSIX the
      file is also `chmod 000`.
25. `test_the_switch_check_sends_nothing`:
    - a listening socket runs in a thread, and `DevToolsActivePort` names its port;
    - `listening(port)` is True;
    - the accepted connection reads `b""` before it closes.
26. `test_state_combines_the_lock_and_the_switch`, parametrized with `running` patched and a real or closed port:
    - the five rows of Decision 8's table;
    - running, with no port file;
    - running, with a broken port file (`abc`, `0`, `70000`, `²`, an empty file): `switch_off`, and nothing raises;
    - a missing data folder.
27. `test_a_stale_port_of_a_stopped_browser_is_never_checked`: with `running` False, `listening` is patched to fail the
    test, and `state()` gives `not_running`.

**All together:**

28. `test_detect_lists_installed_browsers_with_their_state_profiles_and_watchers`, with `system="darwin"` and
    `symlink_or_skip`:
    - a fake Mac with Brave and Chrome installed, each with its sample `Info.plist` and program file;
    - Brave's data folder: a `SingletonLock` link to `<gethostname()>-<os.getpid()>`, a `DevToolsActivePort` naming a
      socket that listens in a thread, the Brave sample `Local State` with the profile folders of test 13, and the
      watcher enabled in `Profile 1`'s `Secure Preferences`. `watchers` maps the watcher's id to its folder;
    - Chrome's data folder: the Chrome sample `Local State`, a `Default` folder and no lock;
    - the sample LaunchServices plist names Brave;
    - plus Edge, installed, with its own data folder and a `Local State`;
    - `public(detect(...), connected=())` equals an expected list exactly: Brave `default` true and `switch_on`,
      with `Profile 1` `watcher` true; Chrome `default` false and `not_running`; Edge with `agents` false, state null
      and no profiles;
    - nothing under Edge's data folder went through `browsers._read` (a recording reader).
29. `test_public_has_no_paths_or_emails`:
    - the JSON holds no `str(tmp_path)`, no `@` and no `Library`;
    - the keys are exactly those in Decision 12;
    - `connected=("brave",)` turns Brave's state into `connected`.
30. `test_detection_reads_only_its_files_and_writes_nothing`, on the fake Mac of test 28:
    - every profile folder also holds decoy `Cookies`, `Login Data`, `History` and `Web Data`;
    - every file under `tmp_path` opened during `detect()` is recorded, through a wrapper on `platforms.open_shared`
      and an `open` audit hook (`sys.addaudithook`, recording only while the test's flag is set). So an open that
      skips the reader is caught too. Their names are a subset of `Info.plist`, `Local State`,
      `Secure Preferences`, `Preferences`, `DevToolsActivePort` and the LaunchServices plist, and none is a decoy;
    - a snapshot of the whole tree (path, bytes, `st_mtime_ns`) is equal before and after `detect()`, with no new
      files.
31. `test_browsers_imports_no_connection_code`: an AST walk of `browsers.py` finds no import of `cdp`, `websockets`,
    `chrome`, `appbrowser`, `http`, `urllib`, `aiohttp` or `subprocess`, counting `import x`, `from x import y` and
    relative ones such as `from . import chrome` and `from .chrome import y`.
32. `test_every_read_survives_a_truncated_file`: for each sample file, and the binary copy of the LaunchServices
    plist, its prefixes (every 37 bytes, and empty) go through the matching function, and none raises.

### `tests/test_platforms.py` (added)

33. `test_browser_folders_for_every_known_browser`, through `platforms.browser_data_dir`:
    - `chrome-canary` on `win32` gives `<LOCALAPPDATA>/Google/Chrome SxS/User Data`;
    - `brave-nightly` on `darwin` gives `~/Library/Application Support/BraveSoftware/Brave-Browser-Nightly`;
    - `arc` on `win32` gives None;
    - `brave` on `linux` gives today's folder, and `edge` on `linux` gives None.
34. `test_app_folders`:
    - `darwin` gives `[/Applications, ~/Applications]`;
    - `win32` gives the three roots in order, without the ones not set;
    - `linux` gives `[]`.
35. `test_lock_names`: `win32` gives `lockfile`, and `darwin` and `linux` give `SingletonLock`.
36. `test_open_shared_lets_the_browser_replace_the_file`: this does what `ReplaceFile` with a backup does (Decision
    11). While `open_shared(path)` is held open:
    - `os.rename(path, backup)` succeeds;
    - then `os.rename(new, path)` succeeds;
    - the held handle still reads the old bytes.

    It runs everywhere. Windows is the case that matters. There, a second part holds a plain `open(path, "rb")`
    instead, and the first rename raises `PermissionError`: that shows the test can fail, and why `open_shared`
    exists.
37. `test_the_registry_readers_never_raise`:
    - on Windows they return a `list[str]` and a `str | None` from the real registry, reading only;
    - elsewhere, and with `platforms.WINDOWS` patched to False on Windows, `[]` and None. The Mac has no `winreg`,
      so this also shows it is imported only inside the Windows branch.
38. `test_the_registry_readers_with_a_fake_winreg` (runs on the Mac too): a fake `winreg` module in `sys.modules`,
    with `platforms.WINDOWS` patched to True:
    - `App Paths\chrome.exe` in HKCU and HKLM, and `StartMenuInternet\Brave\shell\open\command` in HKLM and in
      HKLM's `WOW6432Node`, all come back from `windows_browser_commands()`;
    - a key whose `OpenKey` raises `OSError`, and a value that is a number, are skipped, and the others still come
      back;
    - `windows_https_progid()` gives `UserChoiceLatest\ProgId`'s value when it is there, else `UserChoice`'s, and
      None when neither key exists;
    - the fake has `CreateKey`, `SetValueEx`, `DeleteKey` and `DeleteValue` that fail the test if called, and every
      `OpenKey` asks for read access only.

### Guards that must stay green

- `test_no_macos_paths_outside_platforms` (`tests/test_portable.py:261-266`): `browsers.py` spells no
  `Application Support` and no `/Applications/`, even in docstrings, and has no `os.kill(…, 0)`: it asks
  `platforms.pid_alive`.
- `test_text_io_names_its_encoding` (`:157-161`): every read is binary and decoded by name.
- `test_every_module_imports_on_a_windows_like_python` (`:105-111`): nothing POSIX-only (`fcntl`, `pwd`, `grp`) is
  imported at the top. `winreg` and `msvcrt` are imported inside the Windows branches only, since the Mac's normal
  import of the module would fail otherwise.
- `test_repo_hygiene` (`:229-238`): the samples hold no path of this computer.
- The existing `tests/test_platforms.py` and `tests/test_chrome.py` tests pass unchanged.

Run only these files while building: `uv run pytest tests/test_browsers.py tests/test_platforms.py
tests/test_portable.py tests/test_chrome.py -q`.

### By hand, after wave 2

**Who does it:** the user, or the main session with the user's OK. Never a build agent. It reads the user's real
browser files and makes one TCP check: no DevTools session, so no question.

- **On this Mac:**

  ```
  uv run python -c "import json; from ai_browser import browsers; from ai_browser.appbrowser import extension_id_for; from ai_browser.config import home; w = home() / 'app' / 'watcher'; print(json.dumps(browsers.public(browsers.detect({extension_id_for(w): w})), indent=1))"
  ```

  It only reads files: `appbrowser` is imported for the id's hash, and nothing connects. (From wave 3 on,
  `extension_id_for` lives in `ai_browser.extension_id`; the command then imports it from there.) Expect:
  - Brave and Chrome only, with Brave `default` true;
  - Brave's two profiles (`Default`, `Profile 1`) by name and colour, with no email anywhere;
  - "✓ watcher" (`watcher` true) on the profile where the user loaded the watcher;
  - Brave `switch_on` while its switch is ticked, `switch_off` after unticking, and `not_running` after quitting it;
  - no "Allow remote debugging?" question and no automation bar at any point.
- **On the Windows laptop,** the same command. Expect:
  - Chrome, and Edge with `agents` false;
  - Brave if it is installed;
  - Brave's state follows opening and quitting it. This checks the `lockfile` rule;
  - `default` true on the browser chosen in Windows' Settings → Default apps. This checks the `UserChoiceLatest`
    read on Windows 11;
  - every Windows path in Decision 2 that is installed there, found.

## Out of scope

- **Any UI:** the Settings page, the AI Home chip, cards and copy. These are wave 4's.
- **The saved choice:** `settings.json`, `AIB_CHROME_PROFILE`, the change to `own_browser_dir()`, and engines and
  sessions using the choice (wave 4).
- **Placing tabs in a profile:** the watcher's `open_tab`, per-profile watcher copies, and mapping a profile folder to
  its live `browserContextId` (wave 4, through the app's one connection).
- **`doctor --setup` lines** for the new browsers. Wave 4 may add them.
- **Linux detection,** beyond today's two data folders.
- **Firefox, Safari and Opera;** Edge, Arc and Vivaldi for agents (listed, not offered); Edge's Beta, Dev and Canary.
- **Renamed or moved apps,** and Windows installs that neither the three app folders nor the registry show.
- **Account details:** the account's name, picture or email. We never read them.
- **Watching files for changes** (FSEvents, inotify, ReadDirectoryChangesW). Callers ask again when they need to.
- **Launching a browser,** or opening a window for a profile. Detection never starts anything.
