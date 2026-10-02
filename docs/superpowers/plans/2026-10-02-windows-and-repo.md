# Windows Support and the Private Repo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ai-browser runs natively on the user's Windows laptop (Windows 10 22H2 or 11, x64) with the same safety
promises as on the Mac, the Mac is unchanged, the code of all five sub-projects passes portability guards, a manual
GitHub Actions workflow can run the suite on `windows-latest`, and the main session has everything it needs to ask the
user about a private `nanotechs001/ai-browser` repo.

**Architecture:**
- **One module holds the OS facts:** `platforms.py`.
  - Pure functions (folders, install places, names, wording, the reveal command) take `system` and `env`, read at
    call time, so the Mac's suite tests every OS.
  - The few calls that use the real OS (pid check, lock, retrying replace/unlink/rmtree, the kill-on-close job)
    branch on `platforms.WINDOWS`.
- **Three more new modules:**
  - `winfs.py`: link-proof opens in the work folder through Win32;
  - `syncdir.py`: binary atomic writes and in-place folder sync;
  - `claudecli.py`: the native `claude.exe`, never an npm `.cmd`; its own process group; the job.
- **Guards:** `tests/test_portable.py` keeps it this way over every sub-project's code: encodings named, imports
  that work without POSIX modules, no macOS paths, no Mac words where Windows shows them, repo hygiene, voice wheels.

**Tech Stack:**
- Python 3.12, standard library only (`ctypes`, `msvcrt`, `winreg`, `ntpath`);
- the Starlette/uvicorn app server and the MV3 extension pages;
- pytest with two new markers, the fake claude (`tests/fake_claude.py`, now an argv prefix) and throwaway headless
  Chrome;
- GitHub Actions (`workflow_dispatch` only).

**Spec:** `docs/superpowers/specs/2026-10-02-windows-and-repo-design.md`

## Global Constraints

Copied from the spec. Every task's requirements include these.

- "The project runs natively on the user's Windows laptop (Windows 10 22H2 or Windows 11, x64), from a private GitHub
  repo, with the same safety promises as on the Mac. The Mac keeps working exactly as it does now."
- "**Line numbers** (`file.py:12`) are from the baseline commit `1974d2d`. The four sub-projects built before this one
  move some of them, so the plan finds each place again by its name."
- Pure functions: "Each takes `system: str | None = None` and `env: Mapping | None = None`. `None` means `sys.platform`
  (`"darwin"`, `"win32"` or `"linux"`) and `os.environ`, read at call time."
- OS calls: "These branch on `WINDOWS = os.name == "nt"`, read at call time, never on `sys.platform`. A test may patch
  `WINDOWS` only where no Win32 API is called (a retry loop, a socket option, a wait), so Windows APIs never run on
  the Mac by accident. Their Win32 calls go through `ctypes.WinDLL("kernel32", use_last_error=True)` and read errors
  with `ctypes.get_last_error()`, because a bare `GetLastError()` through ctypes can read a stale value".
- "**Every text read or write names its encoding:** `read_text`, `write_text`, `open()` and `os.fdopen()` pass
  `encoding="utf-8"`."
- "**The same flags on every OS.** Windows uses `chrome_args()` (`:77-85`) unchanged; this sub-project adds and removes
  no flag. A test pins that."
- "on the Mac, this sub-project downloads nothing. It adds no dependency: no ruff, psutil or filelock, only the
  standard library (`ctypes`, `msvcrt`, `winreg`)".
- "**`requires-python` stays `>=3.12`**, so the lock doesn't need re-resolving now, and nothing is downloaded on the
  Mac."
- "Comments and docstrings may keep "this Mac"."
- "**The app never starts the user's Brave.**"
- Safety, from the spec's Safety section:
  - "**No bypassing CAPTCHAs or bot checks.** Nothing here changes how pages are driven."
  - "**No spoofing or disguise.** The Windows launch uses the same `chrome_args()` as the Mac, and a test pins that."
  - "**A bot check is handed to the user.**"
  - "**The agent never types passwords.**" "The README never asks for a password or token in a file or an environment
    variable." "CI has no secrets."
  - "**The user's own words are instructions; page or message text never is.**"
  - "**Text is set with `textContent`.** The setup page's new result text and the mismatch line are set that way. The
    platform words come from server constants, escaped with `html.escape`."
  - "**Nothing leaves the machine unless the user knowingly chooses**".
  - "**Downloads need the user's explicit OK**".
- CI: "**Manual only.** It runs when the user clicks **Run workflow**, and never on a push, a pull request or a
  schedule." "**No `PYTHONUTF8`,** so Windows' own default encoding is what gets tested."
- The repo: "Nothing is pushed until step 2's yes." Creating it is the main session's work, after this plan (see
  **After Task 25**).

## Review Focus

1. **A Windows home folder with spaces, accents or `&`** (`C:\Users\José & Ana`): the extension ID is still Chrome's
   (UTF-16LE of that exact path), the setup page shows the path whole and escaped, and the reveal quotes it. Tests:
   Task 8 (`test_windows_extension_ids_follow_chromium`, the `José & Ana` row), Task 16
   (`test_the_setup_page_is_worded_for_each_computer`) and Task 2 (`test_reveal_commands`).
2. **`AIB_HOME` typed with forward slashes, a trailing separator or a lower-case drive** (`c:/dev/aib-home/`): the
   same ID and the same shown path as the plain backslash form. Test: Task 8 (`test_windows_extension_ids_follow_chromium`).
3. **A workflow or `SKILL.md` saved from Notepad** (UTF-8 with a BOM, CRLF line ends): it loads like one written on the
   Mac, instead of losing its front matter. Test: Task 13 (`test_files_saved_by_notepad_load_like_the_macs`).
4. **A port inside a range Hyper-V or WSL reserved** (bind fails with WinError 10013, a `PermissionError`): it counts as
   taken and the next port is tried. Test: Task 11 (`test_a_reserved_port_is_skipped_like_a_taken_one`).
5. **AI Browser ended from Task Manager, or crashed:** the lock file left behind never blocks the next
   `ai-browser app`. Test: Task 5 (`test_a_lock_held_by_a_crashed_app_is_free_again`).

## Before you start

- **Waves 1 and 2 are merged.** Safe-browsing, mission-visuals, everyday-brave and voice-input are on `main`. Make a
  branch: `git switch main && git switch -c windows-and-repo`.
- **Commit each task, never push.** Pushing is the main session's step, after the user's yes.
- **Find places by name.** The old code this plan quotes, to replace, is from the baseline. Waves 1 and 2 may have
  moved it or changed the lines around it. Find the function or constant by its name, and keep their changes.
- **Names from the other specs:**
  - safe-browsing: `checks.Check`, `checks.CheckGate.handoff`, `render.render_check` (the hand-off text);
  - everyday-brave: `chrome.own_browser_dirs()`, `own_browser_dir()`, `browser_name()`, `inspect_address()`,
    `switch_on()`, `<home>/app/link.json`, `doctor --own`, and the setup page's `#switch` section;
  - voice-input: `hearing/model.py`'s model swap, `HearingService(platform=...)`.
- **Test commands:**
  - run one test with `uv run pytest tests/test_x.py::test_y -q -p no:randomly`;
  - never run the whole suite before Task 25;
  - when a task touches many test files, also run `uv run pytest --collect-only -q -p no:randomly`, which only
    imports them.
- **Test fixtures already there:**
  - `fake_claude`: `(runner, log, script)`. Until Task 14, `runner` is a script path, so tests pass
    `claude=str(runner)`. From Task 14 on, `runner` is a list (`[python, fake_claude.py]`) and tests pass
    `claude=runner`.
  - `test_home.stack` and `home`, `test_watcher.watcher`, and `test_mission`'s `open_mission` and `open_with`.
- **Windows-only tests:**
  - `@pytest.mark.windows_only` tests are skipped on the Mac, with their reason. They run in the manual CI run
    (Task 24).
  - Write them exactly as given: they can't be checked here.
- **Hands off the user's browsers:**
  - never connect to the user's Brave or Chrome;
  - every test uses a throwaway Chrome or a fake;
  - `doctor --setup`'s test uses a local socket that stands in for a browser.

## File map

- **New:**
  - `src/ai_browser/platforms.py`: OS facts (folders, install places, wording, the reveal command), and the calls that
    differ by OS (`pid_alive`, `lock_file`, `replace`, `unlink`, `rmtree`, `KillOnCloseJob`);
  - `src/ai_browser/winfs.py`: `windows_name_problem`, `open_in` (the work folder through Win32);
  - `src/ai_browser/syncdir.py`: `write_atomic`, `sync_folder`;
  - `src/ai_browser/claudecli.py`: `ClaudeNotUsable`, `claude_argv`, `spawn_options`, `track`;
  - `.python-version`, `.github/workflows/tests.yml`;
  - tests: `tests/test_platforms.py`, `tests/test_claudecli.py`, `tests/test_syncdir.py`, `tests/test_portable.py`.
- **Modified, Python:**
  - `workfs.py` (imports, the Windows open);
  - `appbrowser.py` (imports, Windows launch, `extension_path`, IDs, in-place copy);
  - `app/run.py` (lock, texts, reveal, `extension_path`);
  - `app/server.py` (`setup_page`, `reveal_folder`, 501, `origin_mismatch`, the Claude folder);
  - `app/bridge.py` (`claude_argv`, clean exit, `write_atomic`, `PYTHONUTF8`);
  - `app/agents.py`, `brain/service.py`, `brain/skillwriter.py` (the `claude` type);
  - `brain/oneshot.py`, `brain/tools.py` (`claude_argv`, `track`, `write_atomic`);
  - `brain/store.py`, `brain/watcher.py`, `brain/workflows.py` (`write_atomic`, retries, BOM);
  - `chrome.py` (binaries, folders, the guard);
  - `live.py` (`_bind`);
  - `engine.py` (`pid_alive`, orphans, the Claude folder, wording);
  - `browser.py`, `qa/report.py` (wording);
  - `skills.py` (BOM);
  - `sandbox.py` (encoding);
  - `cli.py` (`doctor --setup`, UTF-8 console);
  - from the other specs: `render.py` and `checks.py` (safe-browsing), `hearing/model.py` (voice-input), and
    everyday-brave's `link.json` in `app/run.py` (`write_link`);
  - and every text read or write in `src/` names its encoding.
- **Modified, pages:**
  - `app/setup.html`;
  - `app/extension/voice.js`, `mission.html`, `mission.js`, `worker.js`.
- **Modified, other:** `docker/Dockerfile`, `.mcp.json.example`, `pyproject.toml` (markers), `README.md`.
- **Modified, tests:**
  - `tests/conftest.py` (markers hook, helpers, the fake claude as a list, the reveal patch);
  - `tests/fake_claude.py` (UTF-8, `spawn`);
  - `test_appbrowser.py`, `test_app_run.py`, `test_app_server.py`, `test_workfs.py`, `test_chrome.py`,
    `test_engine.py`, `test_oneshot.py`, `test_bridge.py`, `test_mission.py`, `test_qa_report.py`, `test_workflows.py`,
    `test_brain_store.py`, `test_cli.py`, `test_tools.py`, `test_skillwriter.py`, `test_ai_home_phase2.py`;
  - from the other specs: `test_render.py` and `test_checks_browser.py` (safe-browsing's hand-off literals);
  - every test file: `claude=runner`, and named encodings.

---

### Task 1: Platform markers and test helpers

**Files:**
- Modify: `pyproject.toml` (`[tool.pytest.ini_options] markers`)
- Modify: `tests/conftest.py`
- Create: `tests/test_portable.py`
- Modify: `tests/test_appbrowser.py`, `tests/test_app_run.py`, `tests/test_workfs.py`, `tests/test_chrome.py`,
  `tests/test_app_server.py`, `tests/test_brain_store.py`, `tests/test_bridge.py`, `tests/test_skillwriter.py`,
  `tests/test_tools.py`, `tests/test_workflows.py`, `tests/test_ai_home_phase2.py` (`USERPROFILE` beside `HOME`)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - markers `posix_only` and `windows_only`;
  - in `tests/conftest.py`:
    - `POSIX_ONLY: str` and `WINDOWS_ONLY: str` (the skip reasons);
    - `PIPE_FIXTURES = {"stack", "watcher", "app_browser", "app_engine"}`;
    - `platform_skip(item, windows: bool) -> str | None`;
    - `symlink_or_skip(target, link) -> None`;
    - `file_mode(path) -> int | None` (None on Windows);
  - `tests/test_portable.py` with `ROOT` and `SRC`. Later tasks append to it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_portable.py`:

```python
"""Guards that keep ai-browser portable. They run on every OS and cover every sub-project's code."""

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "ai_browser"


def test_platform_markers_skip_with_their_reason():
    import tomllib

    from conftest import PIPE_FIXTURES, POSIX_ONLY, WINDOWS_ONLY, platform_skip

    def item(*markers, fixtures=()):
        return SimpleNamespace(keywords={name: True for name in markers}, fixturenames=list(fixtures))

    assert PIPE_FIXTURES == {"stack", "watcher", "app_browser", "app_engine"}
    assert platform_skip(item("posix_only"), windows=True) == POSIX_ONLY
    assert platform_skip(item("posix_only"), windows=False) is None
    for fixture in sorted(PIPE_FIXTURES):  # they launch AI Browser over the DevTools pipe
        assert platform_skip(item(fixtures=["tmp_path", fixture]), windows=True) == POSIX_ONLY
        assert platform_skip(item(fixtures=[fixture]), windows=False) is None
    assert platform_skip(item("windows_only"), windows=False) == WINDOWS_ONLY
    assert platform_skip(item("windows_only"), windows=True) is None
    assert platform_skip(item(fixtures=["fake_claude", "tmp_path"]), windows=True) is None
    with (ROOT / "pyproject.toml").open("rb") as handle:
        markers = tomllib.load(handle)["tool"]["pytest"]["ini_options"]["markers"]
    assert f"posix_only: {POSIX_ONLY}" in markers and f"windows_only: {WINDOWS_ONLY}" in markers


def test_the_test_helpers_work_on_this_system(tmp_path):
    from conftest import file_mode, symlink_or_skip

    target = tmp_path / "target.txt"
    target.write_bytes(b"x")
    target.chmod(0o600)
    assert file_mode(target) == (None if os.name == "nt" else 0o600)
    symlink_or_skip(target, tmp_path / "link.txt")  # skips, with the reason, where links can't be made
    assert (tmp_path / "link.txt").is_symlink()
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_portable.py -q -p no:randomly`
Expected: FAIL with `ImportError: cannot import name 'PIPE_FIXTURES' from 'conftest'`.

- [ ] **Step 3: Implement**

`pyproject.toml`, replace the `markers` line under `[tool.pytest.ini_options]`:

```toml
markers = [
  "docker: needs Docker and the sandbox image",
  "posix_only: needs macOS or Linux (file descriptors 3 and 4, or the DevTools pipe)",
  "windows_only: Windows behaviour (junctions, msvcrt, Win32 APIs)",
]
```

`tests/conftest.py`:
- Add `import os` and `from pathlib import Path` to the imports at the top.
- Add this block after `_docker_unavailable`:

```python
POSIX_ONLY = "needs macOS or Linux (file descriptors 3 and 4, or the DevTools pipe)"
WINDOWS_ONLY = "Windows behaviour (junctions, msvcrt, Win32 APIs)"
PIPE_FIXTURES = {"stack", "watcher", "app_browser", "app_engine"}  # they launch AI Browser over the DevTools pipe


def platform_skip(item, windows: bool) -> str | None:
    """Why this test can't run on this OS, or None. On Windows: a posix_only test, or one that uses a fixture that
    installs the extension over the DevTools pipe (item.fixturenames holds every fixture it needs, however deep)."""
    if windows and ("posix_only" in item.keywords or set(getattr(item, "fixturenames", ())) & PIPE_FIXTURES):
        return POSIX_ONLY
    if not windows and "windows_only" in item.keywords:
        return WINDOWS_ONLY
    return None


def symlink_or_skip(target, link) -> None:
    """os.symlink, or a skip with the reason where this system can't make links (Windows without Developer Mode)."""
    try:
        os.symlink(target, link, target_is_directory=Path(target).is_dir())
    except OSError as exc:
        pytest.skip(f"this system can't make symbolic links: {exc}")


def file_mode(path) -> int | None:
    """A file's permission bits, or None on Windows: there chmod only toggles read-only, and the token files keep
    Windows' per-user folder permissions instead (the spec's Safety section)."""
    return None if os.name == "nt" else Path(path).stat().st_mode & 0o777
```

- Replace `pytest_collection_modifyitems` with:

```python
def pytest_collection_modifyitems(config, items):
    windows = os.name == "nt"
    for item in items:
        reason = platform_skip(item, windows)
        if reason:
            item.add_marker(pytest.mark.skip(reason=reason))
    docker_items = [item for item in items if "docker" in item.keywords]
    if not docker_items:
        return
    reason = _docker_unavailable()
    if reason:
        for item in docker_items:
            item.add_marker(pytest.mark.skip(reason=reason))
```

Mark the tests that launch AI Browser over the pipe themselves. Add `@pytest.mark.posix_only` on the line above
their `@CHROME`:
- `tests/test_appbrowser.py`:
  - `test_launch_installs_the_panel_and_the_engine_can_connect`;
  - `test_launch_works_whatever_descriptors_the_caller_has_open`;
  - `test_the_extension_id_is_the_one_chrome_gives`.
- `tests/test_app_run.py`, every test that calls `run_app(..., headless=True)` or `launch_app_browser(...,
  headless=True)` without `pipe_install=False`:
  - `test_run_app_opens_the_browser_and_ends_when_it_closes`;
  - `test_run_app_refuses_a_profile_already_in_use`;
  - `test_a_second_run_changes_nothing_for_the_running_one`;
  - `test_run_app_ends_when_the_last_window_closes`;
  - `test_first_start_also_sets_up_the_watcher`;
  - `test_the_brain_survives_a_restart`;
  - `test_scheduled_workflows_tick_while_the_app_runs`.
- `test_first_start_opens_the_setup_steps` and `test_a_stale_install_record_still_gets_the_setup_steps` pass
  `pipe_install=False`, so they stay unmarked.
- If waves 1 and 2 added tests to these two files that launch over the pipe without one of the `PIPE_FIXTURES`, mark
  those too.

In `tests/test_appbrowser.py`, `test_a_chrome_that_cannot_run_is_reported_plainly`, change the launch line so it
runs on every OS:

```python
        appbrowser.launch_app_browser(tmp_path / "profile", tmp_path / "extension", headless=True, pipe_install=False)
```

`tests/test_workfs.py`:
- add `from conftest import symlink_or_skip` under the existing imports;
- replace every `os.symlink(` with `symlink_or_skip(`. There are five, at the baseline's lines 42, 72, 82, 92 and 141,
  and the arguments keep their order;
- above `def test_a_fifo_is_refused_without_hanging` add:

```python
@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="Windows has no FIFOs (NTFS can't hold one)")
```

`tests/test_chrome.py`:
- in `test_chrome_mode_uploads_a_copy_the_sandbox_cannot_swap`, replace `logo.symlink_to(secret)` with
  `symlink_or_skip(secret, logo)`;
- add `from conftest import symlink_or_skip` under the imports.

Permission bits. Add `from conftest import file_mode` under each file's imports, then replace these lines (the old
line first, then the new one):

- `tests/test_app_server.py`, in `test_prepare_watcher_updates_its_folder_in_place`:

```python
    assert (folder / "config.json").stat().st_mode & 0o777 == 0o600
    assert file_mode(folder / "config.json") in (0o600, None)
```

- `tests/test_brain_store.py`:

```python
        assert (tmp_path / "brain" / name).stat().st_mode & 0o777 == 0o600
        assert file_mode(tmp_path / "brain" / name) in (0o600, None)
```

- `tests/test_bridge.py`:

```python
    assert argv[argv.index("--mcp-config") + 1] == str(config) and config.stat().st_mode & 0o777 == 0o600
    assert argv[argv.index("--mcp-config") + 1] == str(config) and file_mode(config) in (0o600, None)
```

- `tests/test_skillwriter.py`:

```python
    assert path.stat().st_mode & 0o777 == 0o644 and [entry.name for entry in path.parent.iterdir()] == ["SKILL.md"]
    assert file_mode(path) in (0o644, None) and [entry.name for entry in path.parent.iterdir()] == ["SKILL.md"]
```

- `tests/test_tools.py`, two places:

```python
    assert (tmp_path / "home" / "tools.json").stat().st_mode & 0o777 == 0o600
    assert file_mode(tmp_path / "home" / "tools.json") in (0o600, None)
```

```python
    assert set(servers) == {"ai-browser", "figma"} and config_file.stat().st_mode & 0o777 == 0o600
    assert set(servers) == {"ai-browser", "figma"} and file_mode(config_file) in (0o600, None)
```

- `tests/test_workflows.py`:

```python
    assert saved.slug == "footer-fix" and path.stat().st_mode & 0o777 == 0o600
    assert saved.slug == "footer-fix" and file_mode(path) in (0o600, None)
```

Then `grep -rn "st_mode & 0o777" tests` must print nothing. If waves 1 and 2 added more, replace each with
`file_mode(<that path>) in (<that mode>, None)`, as above.

The home folder. `Path.home()` reads `USERPROFILE` on Windows, not `HOME`, so a test that only sets `HOME` reads the
runner's real home there. Next to every `monkeypatch.setenv("HOME", <value>)` in `tests`, add
`monkeypatch.setenv("USERPROFILE", <the same value>)`. At the baseline that is one place,
`tests/test_skillwriter.py`'s `test_save_and_update_over_the_socket`:

```python
    monkeypatch.setenv("HOME", str(user_home))  # the skills catalog reads ~/.claude/skills
    monkeypatch.setenv("USERPROFILE", str(user_home))  # Path.home() on Windows
```

Everyday-brave added another, in `tests/test_chrome.py`'s `test_own_browser_folders_brave_first`
(`monkeypatch.setenv("HOME", str(tmp_path))`): add `monkeypatch.setenv("USERPROFILE", str(tmp_path))` under it.
`tests/test_ai_home_phase2.py`'s uses the `stack` fixture, so it never runs on Windows; add the line there too, for
the same reading. Then `grep -rn 'setenv("HOME"' tests` and `grep -rn 'setenv("USERPROFILE"' tests` list the same
tests.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_portable.py tests/test_workfs.py tests/test_brain_store.py tests/test_tools.py tests/test_skillwriter.py tests/test_bridge.py tests/test_chrome.py -q -p no:randomly`
Expected: PASS (on the Mac, the symlink tests still run; the Chrome tests skip only if Chrome is missing).

Run: `uv run pytest tests/test_appbrowser.py tests/test_app_run.py -m posix_only --collect-only -q -p no:randomly`
Expected: the last line reads `10/<all> tests collected (<the rest> deselected)`: 10 selected, plus any wave 1 or 2
tests you marked.

Run: `uv run pytest tests/test_appbrowser.py::test_a_chrome_that_cannot_run_is_reported_plainly tests/test_app_server.py::test_prepare_watcher_updates_its_folder_in_place tests/test_workflows.py::test_workflow_files_round_trip_and_bad_ones_are_reported -q -p no:randomly`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/conftest.py tests/test_portable.py tests/test_appbrowser.py tests/test_app_run.py \
  tests/test_workfs.py tests/test_chrome.py tests/test_app_server.py tests/test_brain_store.py tests/test_bridge.py \
  tests/test_skillwriter.py tests/test_tools.py tests/test_workflows.py tests/test_ai_home_phase2.py
git commit -m "Windows: posix_only and windows_only markers, and test helpers that skip with a reason"
```

---

### Task 2: `platforms.py`, the OS facts

**Files:**
- Create: `src/ai_browser/platforms.py`
- Create: `tests/test_platforms.py`

**Interfaces:**
- Consumes: nothing.
- Produces, in `ai_browser.platforms`:
  - `WINDOWS: bool` (`os.name == "nt"`) and `O_BINARY: int` (`getattr(os, "O_BINARY", 0)`);
  - `user_data_dir(browser: str, system: str | None = None, env: Mapping | None = None) -> Path`, where `browser` is
    `"chrome"` or `"brave"`, and anything else is a `ValueError`;
  - `browser_candidates(browser: str, system=None, env=None) -> list[Path]`;
  - `claude_desktop_dir(system=None, env=None) -> Path`;
  - `file_manager(system=None) -> str`, `this_computer(system=None) -> str` and `shortcut(mac: str, other: str,
    system=None) -> str`;
  - `reveal_command(path: str, system=None) -> list[str] | str | None`;
  - `reveal(path: str) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_platforms.py`:

```python
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
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_platforms.py -q -p no:randomly`
Expected: FAIL with `ImportError: cannot import name 'platforms' from 'ai_browser'`.

- [ ] **Step 3: Implement**

Create `src/ai_browser/platforms.py`:

```python
"""What differs between macOS, Windows and Linux: folders, names, wording, and the few OS calls that differ.

Two kinds of function live here:
- pure ones take `system` (sys.platform's values: "darwin", "win32", "linux") and `env` (os.environ by default), both
  read at call time, so the Mac's tests can ask for any OS;
- the ones that use the real OS branch on WINDOWS (os.name == "nt", read at call time, never sys.platform). Their
  Win32 calls go through ctypes.WinDLL("kernel32", use_last_error=True) and read errors with ctypes.get_last_error().

Every macOS-only path of the project is written here and nowhere else (tests/test_portable.py checks it)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

WINDOWS = os.name == "nt"
O_BINARY = getattr(os, "O_BINARY", 0)  # without it, os.open on Windows turns every "\n" written into "\r\n"

_MAC_DATA = {"chrome": ("Google", "Chrome"), "brave": ("BraveSoftware", "Brave-Browser")}
_WINDOWS_DATA = {"chrome": ("Google", "Chrome", "User Data"), "brave": ("BraveSoftware", "Brave-Browser", "User Data")}
_LINUX_DATA = {"chrome": ("google-chrome",), "brave": ("BraveSoftware", "Brave-Browser")}
_MAC_APPS = {"chrome": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             "brave": "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"}
_WINDOWS_APPS = {"chrome": ("Google", "Chrome", "Application", "chrome.exe"),
                 "brave": ("BraveSoftware", "Brave-Browser", "Application", "brave.exe")}


def _system(system: str | None) -> str:
    return system or sys.platform


def _env(env: Mapping | None) -> Mapping:
    return os.environ if env is None else env


def _browser(browser: str) -> str:
    if browser not in _MAC_DATA:
        raise ValueError(f"unknown browser {browser!r}: chrome or brave")
    return browser


def _windows_folder(env: Mapping, name: str, *fallback: str) -> Path:
    """%LOCALAPPDATA% or %APPDATA%, or where Windows keeps it when the variable is missing."""
    value = env.get(name)
    return Path(value) if value else Path.home().joinpath(*fallback)


def user_data_dir(browser: str, system: str | None = None, env: Mapping | None = None) -> Path:
    """The browser's folder of profiles: where it writes DevToolsActivePort (on Windows, its "User Data")."""
    browser, system, env = _browser(browser), _system(system), _env(env)
    if system == "darwin":
        return Path.home().joinpath("Library", "Application Support", *_MAC_DATA[browser])
    if system == "win32":
        return _windows_folder(env, "LOCALAPPDATA", "AppData", "Local").joinpath(*_WINDOWS_DATA[browser])
    return Path.home().joinpath(".config", *_LINUX_DATA[browser])


def browser_candidates(browser: str, system: str | None = None, env: Mapping | None = None) -> list[Path]:
    """The usual places the browser's program is installed, in the order to try them."""
    browser, system, env = _browser(browser), _system(system), _env(env)
    if system == "darwin":
        return [Path(_MAC_APPS[browser])]
    if system == "win32":
        roots = [env.get(name) for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        return [Path(root, *_WINDOWS_APPS[browser]) for root in roots if root]
    return []


def claude_desktop_dir(system: str | None = None, env: Mapping | None = None) -> Path:
    """Where the Claude desktop app keeps its data, the skills synced from claude.ai among them."""
    system, env = _system(system), _env(env)
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude"
    if system == "win32":
        return _windows_folder(env, "APPDATA", "AppData", "Roaming") / "Claude"
    return Path.home() / ".config" / "Claude"


def file_manager(system: str | None = None) -> str:
    return {"darwin": "Finder", "win32": "File Explorer"}.get(_system(system), "your file manager")


def this_computer(system: str | None = None) -> str:
    return {"darwin": "this Mac", "win32": "this PC"}.get(_system(system), "this computer")


def shortcut(mac: str, other: str, system: str | None = None) -> str:
    """Wording that differs by keyboard: `mac` on macOS (⌘⇧Y), `other` elsewhere (Ctrl+Shift+Y)."""
    return mac if _system(system) == "darwin" else other


def reveal_command(path: str, system: str | None = None) -> list[str] | str | None:
    """The command that shows a folder in the file manager, selected; None when there is none."""
    system = _system(system)
    if system == "darwin":
        return ["open", "-R", str(path)]
    if system == "win32":
        # A string: explorer.exe parses its own command line, and a list would break on a space in the user name.
        # A Windows path can't contain ".
        return f'explorer /select,"{path}"'
    if shutil.which("xdg-open") is None:
        return None
    return ["xdg-open", os.path.dirname(str(path)) or "."]


def reveal(path: str) -> bool:
    """Show a folder in the file manager, selected; True when the command started."""
    command = reveal_command(path)
    if command is None:
        return False
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True
```

- [ ] **Step 4: Run it to see it pass**

Run: `uv run pytest tests/test_platforms.py -q -p no:randomly`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/platforms.py tests/test_platforms.py
git commit -m "Windows: platforms.py holds the OS facts (folders, install places, wording, reveal)"
```

---

### Task 3: Replace, unlink and rmtree wait out a short hold on Windows

**Files:**
- Modify: `src/ai_browser/platforms.py`
- Test: `tests/test_platforms.py`

**Interfaces:**
- Consumes: `platforms.WINDOWS`.
- Produces:
  - `RETRY_WAITS = (0.05, 0.1, 0.2, 0.4)`;
  - `replace(src, dst) -> None`, `unlink(path, missing_ok: bool = False) -> None` and `rmtree(path) -> None`. On
    Windows they retry a `PermissionError` (5 tries in all), then raise it. Elsewhere they are plain `os.replace`,
    `Path.unlink` and `shutil.rmtree`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_platforms.py`:

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_platforms.py -q -p no:randomly -k "replace or unlink"`
Expected: FAIL with `AttributeError: module 'ai_browser.platforms' has no attribute 'time'`.

- [ ] **Step 3: Implement**

In `src/ai_browser/platforms.py`, add `import time` to the imports, then append:

```python
RETRY_WAITS = (0.05, 0.1, 0.2, 0.4)  # seconds between tries: Defender, Brave or an editor holds a file that long


def _retrying(action):
    """Run `action`; on Windows a PermissionError (a file another process holds open) is tried again, 5 times in
    all, then raised as before."""
    for wait in (*RETRY_WAITS, None):
        try:
            return action()
        except PermissionError:
            if not WINDOWS or wait is None:
                raise
            time.sleep(wait)


def replace(src, dst) -> None:
    _retrying(lambda: os.replace(src, dst))


def unlink(path, missing_ok: bool = False) -> None:
    _retrying(lambda: Path(path).unlink(missing_ok=missing_ok))


def rmtree(path) -> None:
    _retrying(lambda: shutil.rmtree(path))
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_platforms.py -q -p no:randomly`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/platforms.py tests/test_platforms.py
git commit -m "Windows: replace, unlink and rmtree retry a briefly held file"
```

---

### Task 4: Is that process still alive? `pid_alive`, and orphans that can't be judged

**Files:**
- Modify: `src/ai_browser/platforms.py`
- Modify: `src/ai_browser/engine.py` (`_alive`, `_close_orphans`)
- Test: `tests/test_platforms.py`, `tests/test_engine.py`, `tests/test_oneshot.py`

**Interfaces:**
- Consumes: `platforms.WINDOWS`.
- Produces:
  - `platforms.pid_alive(pid: int) -> bool`:
    - a pid of 0 or less is False;
    - POSIX uses `os.kill(pid, 0)`;
    - Windows uses `OpenProcess` and `GetExitCodeProcess`, and raises `OSError` when it can't tell;
  - `platforms._kernel32()`, the cached kernel32 with its prototypes (Windows only; Task 15 adds the job functions);
  - `engine._alive(pid)` stays, as a call to `platforms.pid_alive` made at call time. Everyday-brave's link.json and
    session checks call it;
  - `Engine._close_orphans` skips a record whose pid check raises `OSError`, and closes nothing for it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_platforms.py`:

```python
def test_pid_alive():
    import subprocess

    assert platforms.pid_alive(os.getpid())
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=30)
    assert not platforms.pid_alive(child.pid)  # exited and waited for
    assert not platforms.pid_alive(0) and not platforms.pid_alive(-1)
```

Append to `tests/test_engine.py`:

```python
async def test_a_session_record_that_cant_be_judged_is_left_alone(tmp_path, monkeypatch):
    import sys

    from ai_browser import platforms
    from ai_browser.sandbox import SandboxInfo

    engine = Engine(home=tmp_path, catalog=Catalog([], set()))
    engine.info = SandboxInfo("aib-chrome", "chrome", "", tmp_path / "work", False, False, chrome=True)
    dead = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True,
                          encoding="utf-8").stdout.strip()
    record = engine._sessions_dir() / "old-task.json"
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"pid": int(dead), "targets": ["T-orphan"]}), encoding="utf-8")
    sent = []

    class Recorder:
        async def send(self, method, params=None):
            sent.append(method)

    def cannot_tell(pid):
        raise OSError("OpenProcess failed")

    engine.cdp = Recorder()
    monkeypatch.setattr(platforms, "pid_alive", cannot_tell)
    await engine._close_orphans()
    assert sent == [] and record.exists()  # its tabs are not closed
```

In `tests/test_oneshot.py`, in the test that cancels a call and then expects its process gone (the one ending with
`os.kill(pid, 0)`), replace:

```python
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
```

with:

```python
    from ai_browser import platforms

    assert not platforms.pid_alive(pid)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_platforms.py::test_pid_alive tests/test_engine.py::test_a_session_record_that_cant_be_judged_is_left_alone -q -p no:randomly`
Expected: FAIL:
- `test_pid_alive`: `AttributeError: module 'ai_browser.platforms' has no attribute 'pid_alive'`;
- the engine test: `assert sent == []` fails, because `_alive` still calls `os.kill` and the orphan's tab gets
  closed.

- [ ] **Step 3: Implement**

`src/ai_browser/platforms.py`:
- add `import ctypes` and `import functools` to the imports;
- append:

```python
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
ERROR_ACCESS_DENIED = 5


@functools.cache
def _kernel32():
    """kernel32 with the prototypes used here (Windows only: ctypes.WinDLL exists nowhere else)."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle, dword, boolean = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int
    kernel32.OpenProcess.argtypes, kernel32.OpenProcess.restype = (dword, boolean, dword), handle
    kernel32.GetExitCodeProcess.argtypes = (handle, ctypes.POINTER(dword))
    kernel32.GetExitCodeProcess.restype = boolean
    kernel32.CloseHandle.argtypes, kernel32.CloseHandle.restype = (handle,), boolean
    return kernel32


def pid_alive(pid: int) -> bool:
    """Whether a process still runs. Never a signal: on Windows, os.kill(pid, 0) sends Ctrl-C to a console group."""
    if pid <= 0:
        return False
    if WINDOWS:
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # it runs, as another user
        return True
    return True


def _windows_pid_alive(pid: int) -> bool:
    kernel32 = _kernel32()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ctypes.get_last_error() == ERROR_ACCESS_DENIED  # it exists, but isn't ours to look at
    try:
        code = ctypes.c_uint32()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)
```

`src/ai_browser/engine.py`:
- add `from . import platforms` to the imports;
- replace the whole `_alive` function with:

```python
def _alive(pid: int) -> bool:
    """Whether a process still runs: platforms.pid_alive, looked up at call time (safe on Windows too)."""
    return platforms.pid_alive(pid)
```

- in `_close_orphans`, replace:

```python
            if _alive(int(data.get("pid", 0))):
                continue
```

with:

```python
            try:
                alive = _alive(int(data.get("pid", 0)))
            except (OSError, TypeError, ValueError):  # a record it can't judge is left alone: its tabs stay open
                continue
            if alive:
                continue
```

Then run `grep -rn "os\.kill(" src/ai_browser`. Only `appbrowser.py`'s `os.kill(self.pid, number)` (SIGTERM or
SIGKILL) and `platforms.py` may remain. Replace any other `os.kill(<pid>, 0)`, for example in everyday-brave's
`agentlink.py` or `app/server.py`, with `platforms.pid_alive(<pid>)`, and import `platforms` there (`from . import
platforms`, or `from .. import platforms` under `app/`).

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_platforms.py tests/test_engine.py::test_a_session_record_that_cant_be_judged_is_left_alone tests/test_oneshot.py -q -p no:randomly`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/platforms.py src/ai_browser/engine.py tests/test_platforms.py tests/test_engine.py \
  tests/test_oneshot.py
git commit -m "Windows: pid_alive without signals; a session record that can't be judged is left alone"
```

(Also `git add` any file where you replaced an `os.kill(<pid>, 0)`.)

---

### Task 5: The single-instance lock

**Files:**
- Modify: `src/ai_browser/platforms.py`
- Modify: `src/ai_browser/app/run.py` (`import fcntl`, `_lock`)
- Test: `tests/test_platforms.py`

**Interfaces:**
- Consumes: `platforms.WINDOWS`.
- Produces: `platforms.lock_file(path) -> IO | None`. It is an exclusive lock, held until the returned object's
  `close()`, and None when another holder has it.
  - POSIX: `fcntl.flock(LOCK_EX | LOCK_NB)`.
  - Windows: `msvcrt.locking(LK_NBLCK)` on byte 0, and the returned `close()` unlocks first.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_platforms.py`:

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_platforms.py -q -p no:randomly -k lock`
Expected: FAIL with `AttributeError: module 'ai_browser.platforms' has no attribute 'lock_file'`.

- [ ] **Step 3: Implement**

`src/ai_browser/platforms.py`:
- add `import contextlib` to the imports, and `IO` from `typing` (`from typing import IO`);
- append:

```python
class _WindowsLock:
    """The lock file's handle on Windows. close() unlocks the byte before closing: Windows may release the lock of a
    closed file late, and the next start must not find it taken."""

    def __init__(self, handle):
        self._handle = handle

    @property
    def closed(self) -> bool:
        return self._handle.closed

    def close(self) -> None:
        import msvcrt  # Windows only

        if self._handle.closed:
            return
        with contextlib.suppress(OSError):
            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        self._handle.close()


def lock_file(path) -> IO | _WindowsLock | None:
    """An exclusive lock on `path`, held until the returned object's close(); None when another holder has it. If
    the holder dies, the OS releases the lock either way."""
    handle = open(path, "a+b")
    if WINDOWS:
        import msvcrt  # Windows only

        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            return None
        return _WindowsLock(handle)
    import fcntl  # POSIX only

    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle
```

`src/ai_browser/app/run.py`:
- delete `import fcntl`;
- add `from .. import platforms` to the imports;
- replace the body of `_lock`:

```python
def _lock(home: Path):
    """An exclusive lock on <home>/app/lock held for the whole run, or None if another run holds it."""
    folder = home / "app"
    folder.mkdir(parents=True, exist_ok=True)
    return platforms.lock_file(folder / "lock")
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_platforms.py -q -p no:randomly`
Expected: PASS.

Run: `uv run pytest tests/test_app_run.py::test_a_second_run_changes_nothing_for_the_running_one -q -p no:randomly`
Expected: PASS (the lock still refuses a second run).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/platforms.py src/ai_browser/app/run.py tests/test_platforms.py
git commit -m "Windows: the single-instance lock through platforms.lock_file (msvcrt on Windows)"
```

---

### Task 6: The work folder on Windows (`winfs.py`)

**Files:**
- Create: `src/ai_browser/winfs.py`
- Modify: `src/ai_browser/workfs.py` (`_FOLDER`, `WorkDir._open`)
- Test: `tests/test_workfs.py`

**Interfaces:**
- Consumes: `platforms.WINDOWS`, `platforms.O_BINARY`, `workfs.PathError`.
- Produces:
  - `winfs.windows_name_problem(name: str) -> str | None`: why Windows can't hold the name, or None;
  - `winfs.open_in(root, folders: list[str], name: str, writing: bool, shown: str = "") -> int`, a binary file
    descriptor:
    - it never follows a symbolic link, junction or WSL link below `root`;
    - a link gives `PathError("<shown>: is a symbolic link (or inside one); use the file it points to")`;
    - a name Windows can't hold gives `PathError("<shown>: not a valid file name on Windows")`;
    - a folder gives `IsADirectoryError`, and a missing part gives `FileNotFoundError`;
  - `WorkDir._open` uses it when `platforms.WINDOWS` is true. The POSIX path is unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_workfs.py`:

```python
@pytest.mark.parametrize("name", ["CON", "con", "nul.txt", "NUL .txt", "COM1", "lpt3.log", "COM¹", "CONIN$", "a:b",
                                  "x?", 'say"hi"', "a<b", "pipe|", "star*", "back\\slash", "tab\tname", "end.", "end "])
def test_names_windows_cant_hold(name):
    from ai_browser.winfs import windows_name_problem

    assert windows_name_problem(name)


@pytest.mark.parametrize("name", ["report.html", "Ünïcode.txt", "COM10", "console.log", "con-notes.md", ".shell",
                                  "a b.txt", "日本語.md"])
def test_ordinary_names_pass(name):
    from ai_browser.winfs import windows_name_problem

    assert windows_name_problem(name) is None


def test_a_deep_folder_reads_and_writes(work):
    deep = "/".join(f"folder-{number:02d}-name" for number in range(24)) + "/page.html"
    assert len(str(work.host_task / deep)) > 300  # past Windows' old 260-character limit
    assert work.write_text(deep, "<p>deep</p>") == f"/work/t1/{deep}"
    assert work.read_text(deep, 100) == "<p>deep</p>"


@pytest.mark.windows_only
def test_a_junction_to_outside_is_refused_on_windows(work, tmp_path):
    import _winapi

    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_bytes(b"TOP SECRET")
    before = secret.stat()
    _winapi.CreateJunction(str(outside), str(work.host_task / "out"))  # needs no admin rights
    with pytest.raises(PathError, match="symbolic link"):
        work.read_text("out/secret.txt", 100)
    with pytest.raises(PathError, match="symbolic link"):
        work.write_text("out/secret.txt", "replaced")
    with pytest.raises(PathError, match="symbolic link"):
        work.write_text("out/new.txt", "x")
    after = secret.stat()
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    assert not (outside / "new.txt").exists()


@pytest.mark.windows_only
def test_a_symbolic_link_file_is_refused_on_windows(work, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"TOP SECRET")
    symlink_or_skip(secret, work.host_task / "notes.txt")  # the CI runner is an admin, so it can make one
    with pytest.raises(PathError, match="symbolic link"):
        work.read_text("notes.txt", 100)
    with pytest.raises(PathError, match="symbolic link"):
        work.write_text("notes.txt", "x")
    assert secret.read_bytes() == b"TOP SECRET"


@pytest.mark.windows_only
def test_windows_writes_new_folders_and_reads_exact_bytes(work):
    assert work.write_bytes("fresh/sub/ten.bin", b"0123456789") == "/work/t1/fresh/sub/ten.bin"
    assert (work.host_task / "fresh" / "sub" / "ten.bin").read_bytes() == b"0123456789"
    assert work.read_text("fresh/sub/ten.bin", 100) == "0123456789"
    work.write_bytes("fresh/sub/ten.bin", b"1")  # a write truncates, after the checks
    assert (work.host_task / "fresh" / "sub" / "ten.bin").read_bytes() == b"1"
    with pytest.raises(IsADirectoryError):
        work.read_text("fresh", 100)
    with pytest.raises(PathError, match="not a valid file name on Windows"):
        work.write_text("CON", "x")
    with pytest.raises(PathError, match="not a valid file name on Windows"):
        work.write_text("notes:hidden", "x")  # also an alternate data stream
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_workfs.py -q -p no:randomly`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai_browser.winfs'`. `test_a_deep_folder_reads_and_writes`
already passes on the Mac; it pins the Windows path for CI. The three `windows_only` tests are skipped.

- [ ] **Step 3: Implement**

Create `src/ai_browser/winfs.py`:

```python
r"""The work folder on Windows: open a file below the work root without following any link, junction or WSL link.

POSIX opens each folder relative to the one before it (dir_fd); Windows can't. So every folder on the way is opened
by its full path (with the \\?\ prefix, so deep folders work) and held, without FILE_SHARE_DELETE, until the file is
open: none of them can be renamed or swapped meanwhile. Each folder below the root is checked for a reparse point
(symbolic links, junctions, and the links a Linux container makes through Docker Desktop's file share all are one),
and the file's final path must lie inside the work root's. Imports on any OS; Win32 is touched only in functions."""

from __future__ import annotations

import ctypes
import errno
import functools
import ntpath
import os

from . import platforms
from .workfs import PathError

_BAD = frozenset('<>:"/\\|?*') | frozenset(chr(code) for code in range(32))
_DEVICES = frozenset({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
                      *(f"COM{n}" for n in "123456789¹²³"), *(f"LPT{n}" for n in "123456789¹²³")})
LINK = "{}: is a symbolic link (or inside one); use the file it points to"

GENERIC_READ, GENERIC_WRITE, FILE_READ_ATTRIBUTES = 0x80000000, 0x40000000, 0x80
FILE_SHARE_READ, FILE_SHARE_WRITE = 0x1, 0x2  # never FILE_SHARE_DELETE: a held folder can't be renamed or swapped
OPEN_EXISTING, OPEN_ALWAYS = 3, 4
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000  # lets a folder open, so it can be told apart from a file
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000  # a link is opened as itself, never followed
FILE_ATTRIBUTE_DIRECTORY, FILE_ATTRIBUTE_REPARSE_POINT = 0x10, 0x400
ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND, ERROR_ACCESS_DENIED, ERROR_ALREADY_EXISTS = 2, 3, 5, 183
_INVALID = ctypes.c_void_p(-1).value


def windows_name_problem(name: str) -> str | None:
    """Why Windows can't hold this file or folder name, or None. The device names are the ones Python 3.13's
    ntpath.isreserved knows, in any case, with or without an extension (nul.txt too)."""
    if not name:
        return "an empty name"
    bad = sorted({char for char in name if char in _BAD})
    if bad:  # ":" also rules out alternate data streams
        return "it contains " + " ".join(repr(char) for char in bad)
    if name[-1] in ". ":
        return "it ends with a dot or a space"
    if name.partition(".")[0].rstrip(" ").upper() in _DEVICES:
        return "it is a device name (CON, NUL, COM1…)"
    return None


class _FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


class _Info(ctypes.Structure):  # BY_HANDLE_FILE_INFORMATION
    _fields_ = [("attributes", ctypes.c_uint32), ("created", _FileTime), ("accessed", _FileTime),
                ("written", _FileTime), ("volume", ctypes.c_uint32), ("size_high", ctypes.c_uint32),
                ("size_low", ctypes.c_uint32), ("links", ctypes.c_uint32), ("index_high", ctypes.c_uint32),
                ("index_low", ctypes.c_uint32)]


@functools.cache
def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle, dword, boolean, text = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p
    kernel32.CreateFileW.argtypes = (text, dword, dword, ctypes.c_void_p, dword, dword, handle)
    kernel32.CreateFileW.restype = handle
    kernel32.CreateDirectoryW.argtypes, kernel32.CreateDirectoryW.restype = (text, ctypes.c_void_p), boolean
    kernel32.GetFileInformationByHandle.argtypes = (handle, ctypes.POINTER(_Info))
    kernel32.GetFileInformationByHandle.restype = boolean
    kernel32.GetFinalPathNameByHandleW.argtypes = (handle, text, dword, dword)
    kernel32.GetFinalPathNameByHandleW.restype = dword
    kernel32.SetEndOfFile.argtypes, kernel32.SetEndOfFile.restype = (handle,), boolean
    kernel32.CloseHandle.argtypes, kernel32.CloseHandle.restype = (handle,), boolean
    return kernel32


def _long(path: str) -> str:
    r"""A full path in the \\?\ form, so folders deeper than 260 characters work."""
    if path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + path


def _error(code: int, shown: str) -> OSError:
    if code in (ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND):
        return FileNotFoundError(errno.ENOENT, "no such file", shown)
    if code == ERROR_ACCESS_DENIED:
        return PermissionError(errno.EACCES, "access denied", shown)
    error = ctypes.WinError(code)
    error.filename = shown
    return error


def _open(path: str, access: int, disposition: int, flags: int, shown: str) -> int:
    handle = _kernel32().CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None, disposition, flags, None)
    if handle in (None, _INVALID):
        raise _error(ctypes.get_last_error(), shown)
    return handle


def _attributes(handle: int, shown: str) -> int:
    info = _Info()
    if not _kernel32().GetFileInformationByHandle(handle, ctypes.byref(info)):
        raise _error(ctypes.get_last_error(), shown)
    return info.attributes


def _final_path(handle: int, shown: str) -> str:
    size = 512
    while True:
        buffer = ctypes.create_unicode_buffer(size)
        length = _kernel32().GetFinalPathNameByHandleW(handle, buffer, size, 0)
        if not length:
            raise _error(ctypes.get_last_error(), shown)
        if length < size:
            return buffer.value
        size = length + 1


def _close(handle: int) -> None:
    _kernel32().CloseHandle(handle)


def _hold_folder(path: str, follow: bool, shown: str) -> int:
    """Open and hold a folder. GENERIC_READ, not only attributes: an open that reads nothing takes no part in the
    sharing checks, and the missing FILE_SHARE_DELETE is what stops a rename while it is held."""
    flags = FILE_FLAG_BACKUP_SEMANTICS | (0 if follow else FILE_FLAG_OPEN_REPARSE_POINT)
    handle = _open(path, GENERIC_READ, OPEN_EXISTING, flags, shown)
    if follow:  # the work root: the app made it, and the sandbox can't replace its own mount point
        return handle
    try:
        attributes = _attributes(handle, shown)
        if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            raise PathError(LINK.format(shown))
        if not attributes & FILE_ATTRIBUTE_DIRECTORY:  # like POSIX's ENOTDIR
            raise FileNotFoundError(errno.ENOENT, "no such file", shown)
    except BaseException:
        _close(handle)
        raise
    return handle


def _what_is(path: str, shown: str) -> str:
    """"link", "folder" or "file", read with attribute access only (for a name Windows wouldn't open for writing)."""
    handle = _open(path, FILE_READ_ATTRIBUTES, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS,
                   shown)
    try:
        attributes = _attributes(handle, shown)
    finally:
        _close(handle)
    if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
        return "link"
    return "folder" if attributes & FILE_ATTRIBUTE_DIRECTORY else "file"


def _inside(final: str, root: str) -> bool:
    final, root = ntpath.normcase(final), ntpath.normcase(root).rstrip("\\")
    return final.startswith(root + "\\")


def open_in(root, folders, name: str, writing: bool, shown: str = "") -> int:
    """A binary file descriptor for root/folders.../name, opened without following any link below the root. Writes
    create missing folders, and truncate only after every check."""
    shown = shown or "/".join([*folders, name])
    for part in (*folders, name):
        if windows_name_problem(part):
            raise PathError(f"{shown}: not a valid file name on Windows")
    held: list[int] = []
    try:
        path = _long(os.path.abspath(root))
        held.append(_hold_folder(path, True, shown))
        root_final = _final_path(held[0], shown)
        for folder in folders:
            path = f"{path}\\{folder}"
            if writing and not _kernel32().CreateDirectoryW(path, None):
                code = ctypes.get_last_error()
                if code != ERROR_ALREADY_EXISTS:
                    raise _error(code, shown)
            held.append(_hold_folder(path, False, shown))
        return _open_file(f"{path}\\{name}", writing, root_final, shown)
    finally:
        for handle in held:
            _close(handle)


def _open_file(path: str, writing: bool, root_final: str, shown: str) -> int:
    import msvcrt  # Windows only

    access = GENERIC_READ | (GENERIC_WRITE if writing else 0)
    flags = FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS
    try:
        handle = _open(path, access, OPEN_ALWAYS if writing else OPEN_EXISTING, flags, shown)
    except PermissionError:
        kind = _what_is(path, shown)
        if kind == "link":
            raise PathError(LINK.format(shown)) from None
        if kind == "folder":
            raise IsADirectoryError(errno.EISDIR, "is a folder", shown) from None
        raise
    try:
        attributes = _attributes(handle, shown)
        if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            raise PathError(LINK.format(shown))
        if attributes & FILE_ATTRIBUTE_DIRECTORY:
            raise IsADirectoryError(errno.EISDIR, "is a folder", shown)
        if not _inside(_final_path(handle, shown), root_final):  # belt and braces
            raise PathError(f"{shown}: points outside /work")
        if writing and not _kernel32().SetEndOfFile(handle):  # at 0: the file was just opened
            raise _error(ctypes.get_last_error(), shown)
        return msvcrt.open_osfhandle(handle, (os.O_WRONLY if writing else os.O_RDONLY) | platforms.O_BINARY)
    except BaseException:
        _close(handle)
        raise
```

`src/ai_browser/workfs.py`:
- add `from . import platforms` to the imports;
- replace `_FOLDER = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW` with:

```python
_FOLDER = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)  # Windows Python has neither
```

- in `WorkDir._open`, right after `writing = bool(flags & os.O_WRONLY)`, add:

```python
        if platforms.WINDOWS:  # no dir_fd there: winfs holds each folder open instead (and NTFS has no FIFOs)
            from . import winfs

            return os.fdopen(winfs.open_in(self.host_root, folders, name, writing, path), "wb" if writing else "rb")
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_workfs.py -q -p no:randomly`
Expected: PASS, with 3 skipped and the reason "Windows behaviour (junctions, msvcrt, Win32 APIs)".

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/winfs.py src/ai_browser/workfs.py tests/test_workfs.py
git commit -m "Windows: the work folder never follows links, junctions or WSL links, and refuses names Windows can't hold"
```

---

### Task 7: Launching AI Browser on Windows, and the import simulation

**Files:**
- Modify: `src/ai_browser/appbrowser.py` (imports, `ALREADY_OPEN`, `_Pipe.call`, `AppBrowser.process`,
  `launch_app_browser` split into `_spawn_posix` and `_spawn_windows`)
- Test: `tests/test_appbrowser.py`, `tests/test_portable.py`

**Interfaces:**
- Consumes: `platforms.WINDOWS`, `platforms.shortcut`, `platforms.unlink`.
- Produces:
  - `appbrowser.PIPE_ON_WINDOWS: str`, the refusal;
  - `ALREADY_OPEN` takes two fields, `(profile, quit hint)`;
  - `AppBrowser.process: _Process | subprocess.Popen`;
  - on Windows, `launch_app_browser` starts `subprocess.Popen(chrome_args(...), stdout=DEVNULL, stderr=DEVNULL)` and
    refuses `pipe=True` before starting anything;
  - every `ai_browser` module imports on a Python without `fcntl`, `termios`, `resource`, `pwd`, `grp` or the POSIX
    `os` names.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_appbrowser.py`:

```python
def test_the_windows_launch_uses_popen_with_the_same_flags(tmp_path, monkeypatch):
    import subprocess

    import ai_browser.appbrowser as appbrowser
    from ai_browser import platforms

    calls = []

    def recorder(args, **options):
        calls.append((args, options))
        raise OSError("no such program")

    monkeypatch.setattr(platforms, "WINDOWS", True)  # only the launch path changes: Popen is a recorder
    monkeypatch.setattr(appbrowser, "chrome_binary", lambda: "C:/chrome/chrome.exe")
    monkeypatch.setattr(appbrowser.subprocess, "Popen", recorder)
    urls = ["https://example.com/"]
    with pytest.raises(appbrowser.AppBrowserError, match="AI Browser could not start: no such program"):
        appbrowser.launch_app_browser(tmp_path / "profile", tmp_path / "extension", urls=urls)
    [(args, options)] = calls
    assert args == appbrowser.chrome_args("C:/chrome/chrome.exe", tmp_path / "profile", False, False, urls)
    assert options == {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


def test_the_pipe_install_is_refused_on_windows(tmp_path, monkeypatch):
    import ai_browser.appbrowser as appbrowser
    from ai_browser import platforms

    calls = []
    monkeypatch.setattr(platforms, "WINDOWS", True)
    monkeypatch.setattr(appbrowser, "chrome_binary", lambda: "C:/chrome/chrome.exe")
    monkeypatch.setattr(appbrowser.subprocess, "Popen", lambda *args, **options: calls.append(args))
    with pytest.raises(appbrowser.AppBrowserError, match="needs macOS or Linux; on Windows, load it once with Load "
                                                         "unpacked"):
        appbrowser.launch_app_browser(tmp_path / "profile", tmp_path / "extension", pipe_install=True)
    assert calls == [] and not (tmp_path / "profile").exists()  # nothing was started


def test_already_open_says_how_to_quit_on_each_computer(monkeypatch):
    import sys

    from ai_browser.appbrowser import ALREADY_OPEN, _quit_hint

    monkeypatch.setattr(sys, "platform", "darwin")
    assert "(⌘Q in its window)" in ALREADY_OPEN.format("/p", _quit_hint())
    monkeypatch.setattr(sys, "platform", "win32")
    assert "(close its window)" in ALREADY_OPEN.format("C:\\p", _quit_hint())
```

Append to `tests/test_portable.py`:

```python
LIST_MODULES = r'''
import importlib, pkgutil, sys
import ai_browser
for module in pkgutil.walk_packages(ai_browser.__path__, "ai_browser."):
    importlib.import_module(module.name)
print("\n".join(sorted(name for name in sys.modules if not name.startswith("ai_browser") and name != "__main__")))
'''

LIKE_WINDOWS = r'''
import importlib, importlib.abc, os, pkgutil, sys

BLOCKED = ("fcntl", "termios", "resource", "pwd", "grp")
for name in sys.stdin.read().split():  # the libraries ai_browser brings in, loaded first, the way this OS loads them
    if name.split(".")[0] not in BLOCKED:
        try:
            importlib.import_module(name)
        except Exception:
            pass


class WindowsHasNone(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return None


for name in BLOCKED:
    sys.modules.pop(name, None)
sys.meta_path.insert(0, WindowsHasNone())
for attr in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "posix_spawn", "POSIX_SPAWN_OPEN", "POSIX_SPAWN_DUP2",
             "WNOHANG"):
    if hasattr(os, attr):
        delattr(os, attr)
import ai_browser

failed = {}


def note(name):
    failed.setdefault(name, f"{sys.exc_info()[0].__name__}: {sys.exc_info()[1]}")


for module in pkgutil.walk_packages(ai_browser.__path__, "ai_browser.", onerror=note):
    if module.name in sys.modules or module.name in failed:
        continue
    try:
        importlib.import_module(module.name)
    except Exception as exc:
        failed[module.name] = f"{type(exc).__name__}: {exc}"
print("\n".join(f"{name}: {why}" for name, why in sorted(failed.items())))
'''


def test_every_module_imports_on_a_windows_like_python():
    """The investigation's simulation, kept: no POSIX-only module or os name may be needed at import time."""
    names = subprocess.run([sys.executable, "-c", LIST_MODULES], capture_output=True, encoding="utf-8", check=True,
                           timeout=180).stdout
    result = subprocess.run([sys.executable, "-c", LIKE_WINDOWS], input=names, capture_output=True,
                            encoding="utf-8", timeout=180)
    assert result.returncode == 0 and not result.stdout.strip(), result.stdout + result.stderr[-2000:]
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_appbrowser.py -k "windows or already_open" tests/test_portable.py::test_every_module_imports_on_a_windows_like_python -q -p no:randomly`
Expected: FAIL:
- the Windows launch: the message is posix_spawn's `[Errno 2]`, not "no such program", and `calls` is empty;
- the pipe refusal: no refusal;
- `_quit_hint`: `ImportError`;
- the simulation lists `No module named 'fcntl'` for `ai_browser.appbrowser`, and for the modules that import it
  (`app.run`, `engine`, `server`). Task 5 removed `app.run`'s own `fcntl`, and Task 6 `workfs`'s POSIX flags.

- [ ] **Step 3: Implement**

In `src/ai_browser/appbrowser.py`:
- delete `import fcntl` and `import select`;
- add `from . import platforms` to the imports.

Replace `ALREADY_OPEN` and add the refusal under it:

```python
ALREADY_OPEN = "AI Browser is already open (profile {}), maybe from an earlier run: quit it ({}), then start again"
PIPE_ON_WINDOWS = ("installing the extension over the DevTools pipe needs macOS or Linux; on Windows, load it once "
                   "with Load unpacked")


def _quit_hint() -> str:
    return platforms.shortcut("⌘Q in its window", "close its window")
```

In `_Pipe.call`, add `import select  # POSIX only, like the pipe itself` as the method's first line.

In `@dataclass class AppBrowser`, change `process: _Process` to `process: _Process | subprocess.Popen`.

Replace `launch_app_browser` (from its `def` to its `return`) with the three functions below. `_open_tabs` after
it stays.

```python
def _spawn_posix(binary: str, args: list[str], pipe: bool) -> tuple[_Process, _Pipe | None]:
    """posix_spawn. With the pipe, Chrome reads commands on fd 3 and writes answers on fd 4."""
    import fcntl  # POSIX only

    actions = [(os.POSIX_SPAWN_OPEN, 1, os.devnull, os.O_WRONLY, 0), (os.POSIX_SPAWN_OPEN, 2, os.devnull, os.O_WRONLY, 0)]
    ours: list[int] = []  # our ends of the pipe
    theirs: list[int] = []  # Chrome's ends, closed here once it has started
    if pipe:
        to_read, to_write = os.pipe()  # Chrome reads commands on fd 3...
        from_read, from_write = os.pipe()  # ...and writes answers on fd 4
        # Chrome's ends go above 9 first, so moving one onto 3 or 4 in the child can never overwrite the other.
        theirs = [fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 10) for fd in (to_read, from_write)]
        for fd in (to_read, from_write):
            os.close(fd)
        actions = [(os.POSIX_SPAWN_DUP2, theirs[0], 3), (os.POSIX_SPAWN_DUP2, theirs[1], 4), *actions]
        ours = [to_write, from_read]
    try:
        process = _Process(os.posix_spawn(binary, args, os.environ, file_actions=actions,
                                          setsigdef=(signal.SIGPIPE, signal.SIGXFSZ)))
    except OSError as exc:
        for fd in ours:
            os.close(fd)
        raise AppBrowserError(f"AI Browser could not start: {exc}") from None
    finally:
        for fd in theirs:
            os.close(fd)
    return process, (_Pipe(*ours) if pipe else None)


def _spawn_windows(args: list[str]) -> subprocess.Popen:
    """Windows has no posix_spawn, and the headed launch needs no extra descriptors: a plain Popen, the same flags."""
    try:
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        raise AppBrowserError(f"AI Browser could not start: {exc}") from None


def launch_app_browser(profile: Path, extension_dir: Path, headless: bool = False, pipe_install: bool | None = None,
                       urls=()) -> AppBrowser:
    """Start AI Browser on its own profile, opening `urls`; refuses a profile already in use. Headed, it is a normal
    Chrome and the extension is whatever the user installed; headless (or pipe_install=True) installs it for the run
    (macOS and Linux only: Windows loads it once with Load unpacked)."""
    binary = chrome_binary()
    if binary is None:
        raise AppBrowserError("Google Chrome is not installed: install it from google.com/chrome, then try again")
    profile = Path(profile)
    pipe = headless if pipe_install is None else pipe_install
    if pipe and platforms.WINDOWS:
        raise AppBrowserError(PIPE_ON_WINDOWS)
    with contextlib.suppress(ChromeError):
        find_ws_url(profile)
        raise AppBrowserError(ALREADY_OPEN.format(profile, _quit_hint()))
    profile.mkdir(parents=True, exist_ok=True)
    platforms.unlink(profile / "DevToolsActivePort", missing_ok=True)  # a stale one from a crash would mislead the wait
    installed = pipe or extension_installed(profile, extension_dir)
    urls = list(urls)
    first, later = (urls[:1], urls[1:]) if headless else (urls, [])  # headless Chrome takes one start page only
    args = chrome_args(binary, profile, headless, pipe, first)
    if platforms.WINDOWS:
        process, channel = _spawn_windows(args), None
    else:
        process, channel = _spawn_posix(binary, args, pipe)
    try:
        extension_id = (channel.call("Extensions.loadUnpacked", {"path": str(extension_dir)})["id"] if channel
                        else extension_id_for(extension_dir))
        ws_url = find_ws_url(profile, START_TIMEOUT)
    except (AppBrowserError, ChromeError, OSError, KeyError) as exc:
        if channel is not None:
            channel.close()
        exited_at_once = process.poll() is not None
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.terminate()
            process.wait(timeout=10)
        if exited_at_once:  # another Chrome holds this profile and took over the launch
            raise AppBrowserError(ALREADY_OPEN.format(profile, _quit_hint())) from None
        raise AppBrowserError(f"AI Browser could not start: {exc}") from None
    if channel is not None:
        channel.drain()
    if later:
        _open_tabs(ws_url, later)
    return AppBrowser(process, ws_url, extension_id, profile, installed, channel)
```

If the simulation lists other modules (code from waves 1 and 2), fix each the same way: move the POSIX-only import into
the function that needs it, and read an `os` name that Windows lacks with `getattr(os, NAME, 0)` or inside a
POSIX-only branch.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_appbrowser.py tests/test_portable.py -q -p no:randomly`
Expected: PASS. That includes the existing pipe launches on the Mac, which still use `posix_spawn`.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/appbrowser.py tests/test_appbrowser.py tests/test_portable.py
git commit -m "Windows: AI Browser starts with Popen and the same flags; every module imports without POSIX modules"
```

---

### Task 8: Extension IDs on Windows, and one path string everywhere

**Files:**
- Modify: `src/ai_browser/appbrowser.py` (`extension_path`, `extension_id_for`, `extension_installed`)
- Modify: `src/ai_browser/app/server.py` (`_extension_folder`, `_watcher_folder`)
- Modify: `src/ai_browser/app/run.py` (the watcher folder, the reveal, the printed folder)
- Test: `tests/test_appbrowser.py`, `tests/test_app_server.py`, `tests/test_app_run.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `appbrowser.extension_path(folder: Path | str, system: str | None = None) -> str`: `ntpath.abspath` on Windows,
    with the drive letter upper-cased as Chromium's `MaybeNormalizePath` does; `os.path.realpath` elsewhere. It is
    the string that is hashed, shown, revealed and printed, so `c:/dev/aib-home/` and `C:\dev\aib-home` give one
    string;
  - `appbrowser.extension_id_for(folder: Path | str, system: str | None = None) -> str`: on Windows, SHA-256 of the
    UTF-16LE path with an upper-case drive letter;
  - `appbrowser.extension_installed(profile: Path, extension_dir: Path | str, system: str | None = None) -> bool`:
    compares with `ntpath.normcase` on Windows.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_appbrowser.py`:

```python
EXT = "C:\\Users\\me\\.ai-browser\\app\\extension"
WATCH = "C:\\Users\\me\\.ai-browser\\app\\watcher"
JOSE = "C:\\Users\\José & Ana\\.ai-browser\\app\\extension"
DEV = "C:\\dev\\aib-home\\app\\extension"


@pytest.mark.parametrize("folder, shown, expected", [
    (EXT, EXT, "jjdpkibincdinfnjejbcmmghdbgfjpph"),
    ("c:\\Users\\me\\.ai-browser\\app\\extension", EXT, "jjdpkibincdinfnjejbcmmghdbgfjpph"),  # a lower-case drive
    (WATCH, WATCH, "ncapijkcfmdajdlhdhbgnnmkgejiggeg"),
    ("C:/Users/me/.ai-browser/app/extension", EXT, "jjdpkibincdinfnjejbcmmghdbgfjpph"),  # forward slashes
    ("C:\\Users\\me\\.ai-browser\\app\\extension\\", EXT, "jjdpkibincdinfnjejbcmmghdbgfjpph"),  # a trailing separator
    ("c:/dev/aib-home/app/extension/", DEV, "nhhpnkhncgedihejcoolkhbhmnklfgik"),  # all three at once
    (DEV, DEV, "nhhpnkhncgedihejcoolkhbhmnklfgik"),
    (JOSE, JOSE, "lfcipbofoccnodmlbinbgmflefkkgomp"),  # UTF-16LE of the exact path, not UTF-8
])
def test_windows_extension_ids_follow_chromium(folder, shown, expected):
    from ai_browser.appbrowser import extension_id_for, extension_path

    assert extension_id_for(folder, system="win32") == expected
    assert extension_path(folder, system="win32") == shown  # one string: hashed, shown, pasted


def test_the_old_utf8_hash_was_wrong_on_windows():
    from ai_browser.appbrowser import extension_id_for

    assert extension_id_for(EXT, system="win32") != "mkeihmjkgdgccikkejdhgpoikkjpilll"  # the old UTF-8 code's ID


def test_the_posix_id_is_unchanged(tmp_path):
    import hashlib
    import os

    from ai_browser.appbrowser import extension_id_for, extension_path

    folder = tmp_path / "ext"
    folder.mkdir()
    digest = hashlib.sha256(os.path.realpath(folder).encode("utf-8")).hexdigest()[:32]
    assert extension_id_for(folder, system="darwin") == "".join(chr(ord("a") + int(c, 16)) for c in digest)
    assert extension_path(folder, system="darwin") == os.path.realpath(folder)


def test_the_install_check_ignores_case_on_windows(tmp_path):
    from ai_browser.appbrowser import extension_id_for, extension_installed

    folder = "C:\\Users\\Me\\.ai-browser\\app\\extension"
    recorded = "c:\\users\\ME\\.AI-BROWSER\\app\\extension"  # the same folder, as Chrome may record it
    for system, installed in (("win32", True), ("darwin", False)):  # elsewhere, paths keep their case
        prefs = tmp_path / system / "Default" / "Secure Preferences"
        prefs.parent.mkdir(parents=True)
        key = extension_id_for(folder, system=system)  # the right key for that system: only the path differs
        prefs.write_text(json.dumps({"extensions": {"settings": {key: {"path": recorded}}}}), encoding="utf-8")
        assert extension_installed(tmp_path / system, folder, system=system) is installed
```

Append to `tests/test_app_server.py`:

```python
async def test_the_setup_page_shows_the_path_the_id_is_hashed_from(fake_claude, tmp_path):
    import html

    from conftest import symlink_or_skip

    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.appbrowser import extension_id_for, extension_path

    real = tmp_path / "real"
    real.mkdir()
    symlink_or_skip(real, tmp_path / "link")
    home = tmp_path / "link" / "home"  # a home reached through a link
    server = AppServer(home, AgentManager(home))
    revealed = []
    server.reveal = lambda path: revealed.append(path) or True  # True: a folder window opened (Task 16 reads it)
    url = await server.start()
    try:
        async with httpx.AsyncClient() as client:
            page = (await client.get(url + "/setup")).text
            key = page.split('data-key="', 1)[1].split('"', 1)[0]
            await client.post(url + "/setup/reveal", headers={"X-AIB-Setup": key})
        shown = extension_path(home / "app" / "extension")
        assert html.escape(shown) in page and revealed == [shown]
        assert extension_id_for(home / "app" / "extension") == extension_id_for(shown)
        if os.name != "nt":  # on POSIX, the real path (Chrome resolves the link too)
            assert shown == os.path.realpath(home / "app" / "extension")
    finally:
        await server.stop()


@pytest.mark.windows_only
async def test_a_home_through_a_junction_keeps_the_path_chrome_sees(tmp_path):
    import _winapi
    import html

    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.appbrowser import extension_path

    real = tmp_path / "real-home"
    real.mkdir()
    link = tmp_path / "home-link"
    _winapi.CreateJunction(str(real), str(link))
    folder = link / "app" / "extension"
    folder.mkdir(parents=True)
    assert extension_path(folder) == str(folder)  # not the resolved path
    server = AppServer(link, AgentManager(link))
    assert server._extension_folder() == str(folder)
    url = await server.start()
    try:
        async with httpx.AsyncClient() as client:
            page = (await client.get(url + "/setup")).text
        assert html.escape(str(folder)) in page  # the page shows the junction's path too
    finally:
        await server.stop()
```

Append to `tests/test_app_run.py`. It is the spec's "one string everywhere" check for the printed steps and the
reveal: a guard on the Mac, where `extension_path` is the real path and the baseline already printed that (so it
passes there before and after this task); on Windows it uses a junction, and fails until this task:

```python
@CHROME
async def test_the_setup_steps_show_the_path_the_id_is_hashed_from(fake_claude, tmp_path, monkeypatch):
    import os

    from conftest import symlink_or_skip

    from ai_browser.app import run
    from ai_browser.appbrowser import extension_id_for, extension_path

    runner, _, _ = fake_claude
    real = tmp_path / "real"
    real.mkdir()
    if os.name == "nt":  # a junction needs no rights; Chrome doesn't resolve it
        import _winapi

        _winapi.CreateJunction(str(real), str(tmp_path / "link"))
    else:
        symlink_or_skip(real, tmp_path / "link")
    home = tmp_path / "link" / "home"
    folder = home / "app" / "extension"
    lines, shown = [], []
    stop = asyncio.Event()

    async def ready(url, app):
        stop.set()

    monkeypatch.setattr(run, "reveal", shown.append)
    code = await asyncio.wait_for(run.run_app(home, headless=True, pipe_install=False, claude=str(runner),
                                              ready=ready, stop=stop, out=lines.append), 60)
    expected = extension_path(folder)
    assert code == 0 and shown == [expected] and expected in "\n".join(lines)
    assert extension_id_for(expected) == extension_id_for(folder)
    if os.name == "nt":
        assert expected == str(folder)  # the junction's path, as Chrome sees it, not the resolved one
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_appbrowser.py tests/test_app_server.py tests/test_app_run.py -k "extension_id or old_utf8 or posix_id or ignores_case or path_the_id" -q -p no:randomly`
Expected: FAIL:
- `ImportError: cannot import name 'extension_path' from 'ai_browser.appbrowser'` (the ID, POSIX, server and
  `run_app` tests);
- `TypeError`: `extension_id_for` and `extension_installed` take no `system` yet.

- [ ] **Step 3: Implement**

`src/ai_browser/appbrowser.py`:
- add `import ntpath` and `import sys` to the imports;
- replace `extension_id_for` and `extension_installed` with:

```python
def extension_path(folder: Path | str, system: str | None = None) -> str:
    """The folder's path as Chrome sees it: the string that is hashed into the ID, and the one the user sees, pastes
    and gets revealed. Windows: the absolute path as written (Chrome resolves neither junctions nor OneDrive's
    redirection), with the drive letter upper-cased as Chromium's MaybeNormalizePath does. Elsewhere: the real
    path."""
    if (system or sys.platform) == "win32":
        path = ntpath.abspath(str(folder))
        return path[0].upper() + path[1:] if path[1:2] == ":" else path
    return os.path.realpath(folder)


def extension_id_for(folder: Path | str, system: str | None = None) -> str:
    """The ID Chrome gives an unpacked extension: SHA-256 of its folder's path, 0-f mapped to a-p. Windows hashes the
    path as UTF-16LE (Chromium's id_util.cc, GenerateIdForPath); extension_path already upper-cased its drive."""
    path = extension_path(folder, system)
    data = path.encode("utf-16-le" if (system or sys.platform) == "win32" else "utf-8")
    digest = hashlib.sha256(data).hexdigest()[:32]
    return "".join(chr(ord("a") + int(char, 16)) for char in digest)


def extension_installed(profile: Path, extension_dir: Path | str, system: str | None = None) -> bool:
    """Whether the user loaded our extension into this profile: Chrome records it in its Preferences files."""
    windows = (system or sys.platform) == "win32"

    def same(path) -> str:  # Windows paths ignore case
        shown = extension_path(path, system)
        return ntpath.normcase(shown) if windows else shown

    wanted, key = same(extension_dir), extension_id_for(extension_dir, system)
    for name in ("Secure Preferences", "Preferences"):
        try:
            data = json.loads((Path(profile) / "Default" / name).read_text(encoding="utf-8"))
            path = data["extensions"]["settings"][key]["path"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if isinstance(path, str) and same(path) == wanted:
            return True
    return False
```

`src/ai_browser/app/server.py`:
- add `from ..appbrowser import extension_path` to the imports;
- replace the two folder methods:

```python
    def _extension_folder(self) -> str:
        return extension_path(self.home / "app" / "extension")

    def _watcher_folder(self) -> str:
        return extension_path(self.watcher_folder or self.home / "app" / "watcher")
```

`src/ai_browser/app/run.py`:
- import `extension_path` from `..appbrowser`, alongside `extension_id_for`;
- `server.watcher_folder = os.path.realpath(watcher)` becomes `server.watcher_folder = extension_path(watcher)`;
- `reveal(os.path.realpath(folder))` becomes `reveal(extension_path(folder))`;
- `SETUP.format(folder=os.path.realpath(folder))` becomes `SETUP.format(folder=extension_path(folder))`.

`run.py`'s `extension_id_for(watcher)` already hashes `extension_path(watcher)`. Everyday-brave's tab groups go
through that same watcher origin, so they are fixed with it.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_appbrowser.py -k "extension_id or old_utf8 or posix_id or install" -q -p no:randomly`
Expected: PASS.

Run: `uv run pytest tests/test_app_server.py -q -p no:randomly`
Expected: PASS (the junction test is skipped on the Mac).

Run: `uv run pytest tests/test_app_run.py::test_first_start_opens_the_setup_steps tests/test_app_run.py::test_the_setup_steps_show_the_path_the_id_is_hashed_from -q -p no:randomly`
Expected: PASS: the reveal and the printed folder are still the resolved path on the Mac.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/appbrowser.py src/ai_browser/app/server.py src/ai_browser/app/run.py \
  tests/test_appbrowser.py tests/test_app_server.py tests/test_app_run.py
git commit -m "Windows: Chrome's extension ID (UTF-16LE path), and one path string to hash, show and reveal"
```

---

### Task 9: A mismatched extension origin is reported, never allowed

**Files:**
- Modify: `src/ai_browser/app/server.py` (`AppServer.__init__`, `_socket`, `_setup_status`, new `_mismatch`)
- Modify: `src/ai_browser/app/run.py` (`server.out = out`)
- Modify: `src/ai_browser/app/setup.html` (the mismatch line)
- Test: `tests/test_app_server.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `AppServer.origin_mismatch: str | None`;
  - `AppServer.out: Callable[[str], None]` (default `print`; `run_app` sets its `out`);
  - `/setup/status` gains `"mismatch": "chrome-extension://…"`, present only after a mismatch;
  - the socket is still closed with 4403;
  - a mismatch counts only once the app has allowed at least one origin. Before that (AI Browser still starting in
    its thread, the extension already holding this run's token), a refusal is just a refusal.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app_server.py`:

```python
async def test_a_wrong_extension_id_is_reported_not_allowed(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer

    runner, _, _ = fake_claude
    server = AppServer(tmp_path / "home", AgentManager(tmp_path / "home", claude=str(runner)))
    url = await server.start()
    lines = []
    server.out = lines.append
    try:
        # AI Browser is still starting: the app hasn't allowed its computed IDs yet, and the extension (which already
        # has this run's token) may connect first. Refused as always, but that is no mismatch.
        async with connect(socket_url(server, url), origin="chrome-extension://early") as ws:
            with pytest.raises(ConnectionClosed):
                await ws.recv()
        assert server.origin_mismatch is None and lines == []
        server.allow_origin(ORIGIN)
        server.allow_origin(WATCHER, watcher=True)
        async with httpx.AsyncClient() as client:
            assert "mismatch" not in (await client.get(url + "/setup/status")).json()
            async with connect(socket_url(server, url, "wrong"), origin="chrome-extension://other") as ws:
                with pytest.raises(ConnectionClosed):
                    await ws.recv()
            assert server.origin_mismatch is None and lines == []  # a wrong token sets nothing
            for _ in range(2):  # the right token from an origin the app didn't compute: said once
                async with connect(socket_url(server, url), origin="chrome-extension://unexpected") as ws:
                    with pytest.raises(ConnectionClosed) as closed:
                        await ws.recv()
                    assert closed.value.rcvd.code == 4403  # still refused, never allowed on its own
            assert server.origin_mismatch == "chrome-extension://unexpected"
            assert lines == ["An AI Browser extension connected as chrome-extension://unexpected, but the app "
                             "expected chrome-extension://good (AI Browser) or chrome-extension://watcher (the "
                             "watcher): please report this"]
            status = (await client.get(url + "/setup/status")).json()
            assert status["mismatch"] == "chrome-extension://unexpected"
    finally:
        await server.stop()


def test_the_setup_page_shows_the_mismatch_as_text():
    from ai_browser.app.server import SETUP_PAGE

    page = SETUP_PAGE.read_text(encoding="utf-8")
    assert 'id="mismatch"' in page and "mismatch.textContent" in page and "innerHTML" not in page
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_server.py -k "wrong_extension_id or mismatch_as_text" -q -p no:randomly`
Expected: FAIL: `AppServer` has no `origin_mismatch`, and the page has no `id="mismatch"`.

- [ ] **Step 3: Implement**

`src/ai_browser/app/server.py`:
- add `from collections.abc import Callable` to the imports, unless it is already there;
- in `AppServer.__init__`, after `self.extension_seen = False`, add:

```python
        self.origin_mismatch: str | None = None  # an extension with our token, from an origin we didn't compute
        self.out: Callable[[str], None] = print  # where the app's one-line notes go (run_app passes its own)
```

- in `_socket`, replace the refusal:

```python
        if not hmac.compare_digest(token.encode(), self.token.encode()) or origin not in self._origins:
            await ws.close(code=REFUSED)
            return
```

with:

```python
        token_ok = hmac.compare_digest(token.encode(), self.token.encode())
        if not token_ok or origin not in self._origins:
            # Only once the app has allowed its computed IDs: during start-up the extension can connect before
            # allow_origin runs (AI Browser is launched in a thread), and that is no mismatch.
            if token_ok and self._origins and isinstance(origin, str) and origin.startswith("chrome-extension://"):
                self._mismatch(origin)
            await ws.close(code=REFUSED)
            return
```

- add this method after `allow_origin`:

```python
    def _mismatch(self, origin: str) -> None:
        """Only an extension holding our config.json has the token: from an origin we didn't compute, it means an
        extension ID is computed wrong on this computer. The socket is still refused; this says so, once."""
        if origin == self.origin_mismatch:
            return
        self.origin_mismatch = origin
        app = ", ".join(sorted(self._origins - self._watcher_origins)) or "?"
        watcher = ", ".join(sorted(self._watcher_origins)) or "?"
        self.out(f"An AI Browser extension connected as {origin}, but the app expected {app} (AI Browser) or "
                 f"{watcher} (the watcher): please report this")
```

- in `_setup_status`, build the answer with the key only when there is a mismatch:

```python
    async def _setup_status(self, request: Request) -> JSONResponse:
        seen = self.brain is not None and self.brain.store.watcher_seen
        answer = {"installed": self.extension_seen, "watcher": seen}
        if self.origin_mismatch:
            answer["mismatch"] = self.origin_mismatch
        return JSONResponse(answer)
```

If everyday-brave added keys to this answer, keep them in `answer`.

`src/ai_browser/app/run.py`, in `_run`, right after `server = AppServer(...)`, add `server.out = out`.

`src/ai_browser/app/setup.html`:
- under `<p id="status">Waiting for the extension…</p>`, add:

```html
  <p id="mismatch" class="alt" hidden></p>
```

- in the script, after `const status = document.getElementById("status");`, add
  `const mismatch = document.getElementById("mismatch");`;
- in `check()`, after the `if (answer.watcher) { … }` block, add:

```js
      if (answer.mismatch) {
        mismatch.textContent = "An AI Browser extension connected as " + answer.mismatch +
          ", which this app didn't expect, so it was refused: please report this.";
        mismatch.hidden = false;
      }
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_app_server.py -q -p no:randomly`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py src/ai_browser/app/run.py src/ai_browser/app/setup.html tests/test_app_server.py
git commit -m "Windows: an extension with our token from an unexpected origin is refused and reported"
```

---

### Task 10: Finding Chrome, Brave and the browser folders

**Files:**
- Modify: `src/ai_browser/chrome.py` (`MAC_CHROME`, `chrome_binary`, new `brave_binary`, `_installed`,
  `_registry_path`, everyday-brave's `own_browser_dirs` and `default_chrome_dir`, the guard in `launch`)
- Test: `tests/test_chrome.py`

**Interfaces:**
- Consumes: `platforms.browser_candidates`, `platforms.user_data_dir`, `platforms.WINDOWS`.
- Produces:
  - `chrome.chrome_binary() -> str | None`, found in this order: `AIB_CHROME_BINARY` (as given), the usual places,
    the registry's `App Paths` (Windows), then PATH;
  - `chrome.brave_binary() -> str | None`, the same order without an override. `doctor --setup` uses it, and the app
    never starts Brave;
  - `chrome.own_browser_dirs()` keeps its name, order (Brave first) and behaviour, and takes its paths from
    `platforms.user_data_dir`;
  - `chrome._same_folder(a, b) -> bool`: compares resolved paths, ignoring case on Windows. The guard in `launch()`
    uses it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_chrome.py`:

```python
def test_aib_chrome_binary_wins_over_the_usual_places(tmp_path, monkeypatch):
    custom = tmp_path / "chrome.exe"
    custom.write_bytes(b"")
    monkeypatch.setenv("AIB_CHROME_BINARY", str(custom))
    assert chrome_binary() == str(custom)


def test_browsers_are_found_in_the_usual_places_then_on_path(tmp_path, monkeypatch):
    from ai_browser import chrome, platforms

    brave = tmp_path / "Brave Browser"
    brave.write_bytes(b"")
    monkeypatch.delenv("AIB_CHROME_BINARY", raising=False)
    monkeypatch.setattr(platforms, "browser_candidates",
                        lambda browser, system=None, env=None: [tmp_path / "missing", brave] if browser == "brave" else [])
    monkeypatch.setattr(chrome, "_registry_path", lambda program: None)
    assert chrome.brave_binary() == str(brave)
    monkeypatch.setattr(chrome.shutil, "which", lambda name: f"/bin/{name}")
    assert chrome.chrome_binary() == "/bin/" + ("chrome" if os.name == "nt" else "google-chrome")


def test_the_everyday_folders_come_from_platforms(monkeypatch):
    import sys

    from ai_browser import chrome, platforms

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\me\\AppData\\Local")
    assert chrome.own_browser_dirs() == [platforms.user_data_dir("brave"), platforms.user_data_dir("chrome")]
    assert all(folder.name.endswith("User Data") for folder in chrome.own_browser_dirs())


def test_the_guard_ignores_case_on_windows(tmp_path, monkeypatch):
    from ai_browser import chrome, platforms

    real = tmp_path / "BraveSoftware" / "Brave-Browser" / "User Data"
    monkeypatch.setattr(chrome, "own_browser_dirs", lambda: [real])
    monkeypatch.setenv("AIB_CHROME_BINARY", str(tmp_path / "chrome.exe"))
    monkeypatch.setattr(platforms, "WINDOWS", True)  # only the comparison changes: no Win32 call is made
    assert chrome._same_folder(tmp_path / "bravesoftware" / "brave-browser" / "user data", real)
    with pytest.raises(ChromeError):
        launch(tmp_path / "bravesoftware" / "brave-browser" / "user data")
    assert not (tmp_path / "bravesoftware").exists()  # refused before anything was made
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_chrome.py -k "aib_chrome_binary or usual_places or everyday_folders or ignores_case" -q -p no:randomly`
Expected: FAIL:
- `AIB_CHROME_BINARY` is ignored;
- `brave_binary` and `_registry_path` don't exist (`AttributeError`);
- `_same_folder` doesn't exist.

`test_the_everyday_folders_come_from_platforms` may already pass, because everyday-brave lists the same folders. It
keeps them in step from now on.

- [ ] **Step 3: Implement**

In `src/ai_browser/chrome.py`:
- add `import ntpath` and `from . import platforms` to the imports;
- delete `MAC_CHROME = Path(...)`;
- replace `chrome_binary` with:

```python
_ON_PATH = {"chrome": (("chrome",), ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")),
            "brave": (("brave",), ("brave-browser",))}


def chrome_binary() -> str | None:
    """Google Chrome for AI Browser and the throwaway test browsers: $AIB_CHROME_BINARY as given, else the usual
    places, else Windows' App Paths record, else PATH."""
    configured = os.environ.get("AIB_CHROME_BINARY")
    if configured:
        return configured  # a wrong path shows up as "AI Browser could not start: …"
    return _installed("chrome")


def brave_binary() -> str | None:
    """Whether Brave is installed (doctor --setup says so). The app never starts the user's Brave."""
    return _installed("brave")


def _installed(browser: str) -> str | None:
    for candidate in platforms.browser_candidates(browser):
        if candidate.is_file():
            return str(candidate)
    if platforms.WINDOWS:
        found = _registry_path(f"{browser}.exe")
        if found:
            return found
    windows_names, other_names = _ON_PATH[browser]
    for name in windows_names if platforms.WINDOWS else other_names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _registry_path(program: str) -> str | None:
    """Windows' own record of where a program is installed (App Paths), current user first."""
    import winreg  # Windows only

    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{program}") as key:
                value, _ = winreg.QueryValueEx(key, "")
        except OSError:
            continue
        path = str(value or "").strip().strip('"')
        if path and Path(path).is_file():
            return path
    return None


def _same_folder(a, b) -> bool:
    """Whether two paths name the same folder: resolved, and on Windows without regard to case."""
    left, right = os.path.realpath(a), os.path.realpath(b)
    if platforms.WINDOWS:
        return ntpath.normcase(left) == ntpath.normcase(right)
    return left == right
```

- replace the body of everyday-brave's `own_browser_dirs()` (its `if sys.platform == "darwin": … return [config /
  …]` branches). Keep its docstring, and if it ends by filtering or appending anything, keep that too:

```python
    return [platforms.user_data_dir("brave"), platforms.user_data_dir("chrome")]  # Brave first
```

- keep `import sys` in `chrome.py` even if nothing there uses it any more: everyday-brave's tests
  (`test_own_browser_folders_brave_first`, `test_windows_folders_are_under_local_app_data`) patch
  `chrome.sys.platform`. That is the one `sys` module, so `platforms` sees it at call time;
- if `default_chrome_dir()` still builds a folder itself (`Path.home() / "Library" / …`), make its body
  `return own_browser_dir()`, as everyday-brave's spec says (everyday-brave's plan already made it
  `default_chrome_dir = own_browser_dir`);
- in `launch()`, the guard everyday-brave wrote refuses every candidate folder by comparing resolved paths:
  `if folder.resolve() in {real.resolve() for real in own_browser_dirs()}:` (at the baseline it was
  `if folder.resolve() == real_profile.resolve():`). Make its condition:

```python
    if any(_same_folder(folder, candidate) for candidate in own_browser_dirs()):  # never a real browser folder
```

  The `raise ChromeError(…)` line under it, and everyday-brave's message, stay as they are.

`tests/test_chrome.py`: if `REAL_CHROME = Path.home() / "Library" / …` is still defined there, make it
`REAL_CHROME = platforms.user_data_dir("chrome")`, with `from ai_browser import platforms` at the top.

Then `grep -n "Application Support\|/Applications/" src/ai_browser/chrome.py` must print nothing.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_chrome.py -q -p no:randomly`
Expected: PASS. The throwaway-Chrome tests still find Chrome in its usual place, and everyday-brave's folder tests
(which patch `chrome.sys.platform`, `HOME` and `LOCALAPPDATA`) still pass.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/chrome.py tests/test_chrome.py
git commit -m "Windows: find Chrome and Brave (AIB_CHROME_BINARY, usual places, App Paths, PATH); case-blind guard"
```

---

### Task 11: Ports are exclusive on Windows

**Files:**
- Modify: `src/ai_browser/live.py` (`_bind`)
- Test: `tests/test_platforms.py`

**Interfaces:**
- Consumes: `platforms.WINDOWS`.
- Produces: `live._bind(host, port) -> socket | None`:
  - it sets `SO_EXCLUSIVEADDRUSE` on Windows and `SO_REUSEADDR` elsewhere;
  - any `OSError` on bind, WinError 10013 included, means the port is taken.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_platforms.py`:

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_platforms.py -k "port" -q -p no:randomly`
Expected: FAIL in `test_windows_binds_ports_for_exclusive_use`: the options are `[(SOL_SOCKET, SO_REUSEADDR, 1)]`.
The two other tests already pass on the Mac; they pin the "taken" behaviour.

- [ ] **Step 3: Implement**

`src/ai_browser/live.py`:
- add `from . import platforms` to the imports;
- replace `_bind`:

```python
def _bind(host: str, port: int) -> socket.socket | None:
    """Bind the port ourselves (no probe-then-bind race); None when it is taken, or reserved (Hyper-V's ranges
    answer WinError 10013, which is an OSError too)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if platforms.WINDOWS:
        # On Windows SO_REUSEADDR lets a second socket bind a port already held: any local program could take the
        # app's port and receive connections that carry the token. Exclusive use instead.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError:
        sock.close()
        return None
    return sock
```

Add to `tests/test_platforms.py`:

```python
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
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_platforms.py -q -p no:randomly`
Expected: PASS (the `windows_only` test is skipped on the Mac).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/live.py tests/test_platforms.py
git commit -m "Windows: ports are bound for exclusive use; reserved ports count as taken"
```

---

### Task 12: Atomic binary writes and in-place folders (`syncdir.py`)

**Files:**
- Create: `src/ai_browser/syncdir.py`
- Create: `tests/test_syncdir.py`
- Modify:
  - `src/ai_browser/brain/watcher.py` (`prepare_watcher`, `_write`);
  - `src/ai_browser/appbrowser.py` (`prepare_extension`);
  - `src/ai_browser/brain/store.py` (`_write`), `brain/tools.py` (`_save`), `brain/workflows.py` (`save`);
  - `brain/skillwriter.py` (`save`, `update`);
  - `app/bridge.py` (`_mcp_config`, `PYTHONUTF8`);
  - everyday-brave's `link.json` writer and remover (`app/run.py`: `write_link`, and `_run`'s `finally`);
  - `.mcp.json.example`.
- Test: `tests/test_syncdir.py`, `tests/test_appbrowser.py`, `tests/test_bridge.py`, `tests/test_portable.py`,
  `tests/test_workflows.py`

**Interfaces:**
- Consumes: `platforms.O_BINARY`, `platforms.replace`, `platforms.unlink`.
- Produces:
  - `syncdir.write_atomic(path, data: bytes, mode: int = 0o644) -> None`: a temp file in the same folder, opened
    `O_WRONLY | O_CREAT | O_TRUNC | O_BINARY`, then `chmod` and `platforms.replace`. The temp file is removed if
    anything fails, and the parent folder is made if missing;
  - `syncdir.sync_folder(folder, files: dict[str, bytes], keep: set[str]) -> None`: rewrites only the files whose
    bytes changed, and removes every other file that is in neither `files` nor `keep`;
  - the agents' ai-browser MCP server env has `"PYTHONUTF8": "1"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_syncdir.py`:

```python
"""Atomic writes in binary (so "\n" stays one byte on Windows), and folders updated in place."""

import os

import pytest

from ai_browser.syncdir import sync_folder, write_atomic


def test_write_atomic_writes_exactly_the_bytes_given(tmp_path):
    path = tmp_path / "deep" / "file.bin"
    write_atomic(path, b"a\nb\r\n\x00\xff", 0o600)
    assert path.read_bytes() == b"a\nb\r\n\x00\xff"
    assert [entry.name for entry in path.parent.iterdir()] == ["file.bin"]  # no temp file left behind
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_write_atomic_leaves_nothing_behind_when_it_fails(tmp_path, monkeypatch):
    from ai_browser import platforms

    def held(src, dst):
        raise PermissionError(13, "held by another process")

    monkeypatch.setattr(platforms, "replace", held)
    with pytest.raises(PermissionError):
        write_atomic(tmp_path / "x.json", b"{}")
    assert list(tmp_path.iterdir()) == []


def test_sync_folder_rewrites_only_what_changed(tmp_path):
    folder = tmp_path / "ext"
    sync_folder(folder, {"same.js": b"one", "changed.js": b"old", "stale.js": b"x", "img/icon.png": b"\x89PNG\r\n"},
                set())
    (folder / "config.json").write_bytes(b"{}")
    same, icon = (folder / "same.js").stat(), (folder / "img" / "icon.png").stat()
    sync_folder(folder, {"same.js": b"one", "changed.js": b"new", "img/icon.png": b"\x89PNG\r\n"}, {"config.json"})
    again, icon_again = (folder / "same.js").stat(), (folder / "img" / "icon.png").stat()
    assert (again.st_ino, again.st_mtime_ns) == (same.st_ino, same.st_mtime_ns)  # unchanged: not rewritten
    assert (icon_again.st_ino, icon_again.st_mtime_ns) == (icon.st_ino, icon.st_mtime_ns)
    assert (folder / "changed.js").read_bytes() == b"new"
    assert not (folder / "stale.js").exists() and (folder / "config.json").read_bytes() == b"{}"
    assert (folder / "img" / "icon.png").read_bytes() == b"\x89PNG\r\n"  # one byte per "\n", as given
```

Append to `tests/test_appbrowser.py`:

```python
def test_prepare_extension_updates_the_folder_in_place(tmp_path):
    import os

    from ai_browser.appbrowser import prepare_extension

    folder = prepare_extension(tmp_path, "http://127.0.0.1:8792", "one")
    manifest = (folder / "manifest.json").stat()
    (folder / "stale.js").write_bytes(b"old")
    prepare_extension(tmp_path, "http://127.0.0.1:8793", "two")
    again = (folder / "manifest.json").stat()
    assert (again.st_ino, again.st_mtime_ns) == (manifest.st_ino, manifest.st_mtime_ns)  # never removed and copied
    assert not (folder / "stale.js").exists()
    assert json.loads((folder / "config.json").read_text(encoding="utf-8")) == {"server": "http://127.0.0.1:8793",
                                                                                "token": "two"}
    if os.name != "nt":
        assert (folder / "config.json").stat().st_mode & 0o777 == 0o600
```

Append to `tests/test_bridge.py`:

```python
async def test_the_agents_mcp_server_gets_utf8_as_a_backstop(fake_claude, tmp_path):
    from pathlib import Path

    from ai_browser.app.bridge import ClaudeBridge

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    bridge = ClaudeBridge(tmp_path / "home", claude=str(runner))
    [event async for event in bridge.send("hi")]
    await bridge.close()
    argv = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    config = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text(encoding="utf-8"))
    assert config["mcpServers"]["ai-browser"]["env"]["PYTHONUTF8"] == "1"
```

Append to `tests/test_portable.py`:

```python
def test_the_mcp_example_sets_utf8_for_the_server():
    example = json.loads((ROOT / ".mcp.json.example").read_text(encoding="utf-8"))
    assert example["mcpServers"]["ai-browser"]["env"]["PYTHONUTF8"] == "1"
```

Append to `tests/test_workflows.py`:

```python
def test_workflows_and_skills_keep_arrows_emoji_and_cjk(tmp_path):
    from ai_browser.brain.skillwriter import SkillWriter
    from ai_browser.brain.workflows import WorkflowStore

    store = WorkflowStore(tmp_path)
    saved = store.save({"name": "Morning → report 🚀", "instructions": "Check 日本語 mail\nthen tell me"})
    raw = (tmp_path / "workflows" / f"{saved.slug}.md").read_bytes()
    assert b"\r\n" not in raw and "→".encode("utf-8") in raw
    assert store.get(saved.slug).name == "Morning → report 🚀"
    skills = SkillWriter(tmp_path / "skills")
    text = "---\nname: notes\ndescription: Takes notes → fast 🚀\n---\nWrite 日本語 notes.\n"
    path = skills.save(text)
    assert path.read_bytes() == text.encode("utf-8")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_syncdir.py tests/test_appbrowser.py::test_prepare_extension_updates_the_folder_in_place tests/test_bridge.py::test_the_agents_mcp_server_gets_utf8_as_a_backstop tests/test_portable.py::test_the_mcp_example_sets_utf8_for_the_server tests/test_workflows.py::test_workflows_and_skills_keep_arrows_emoji_and_cjk -q -p no:randomly`
Expected: FAIL:
- `ModuleNotFoundError: No module named 'ai_browser.syncdir'`;
- the manifest's inode changed (the folder was removed and copied);
- `KeyError: 'PYTHONUTF8'`, in the bridge and in the example.

The emoji test already passes on the Mac. On Windows the old text-mode writes would fail it.

- [ ] **Step 3: Implement**

Create `src/ai_browser/syncdir.py`:

```python
"""Files written whole and in binary, the same on every OS.

write_atomic writes a temp file in the same folder (opened with O_BINARY: without it Windows turns every "\n" into
"\r\n", which corrupts icon.png and keeps "rewrite only what changed" from ever matching), then replaces the target
with platforms.replace, which waits out a moment's hold by Defender, Brave or an editor on Windows. sync_folder
updates a folder in place, as Chrome and Brave need for an unpacked extension: a file is rewritten only when its
bytes changed, and a file that is no longer wanted is removed."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from . import platforms


def write_atomic(path, data: bytes, mode: int = 0o644) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | platforms.O_BINARY, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(temp, mode)
        platforms.replace(temp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise


def sync_folder(folder, files: dict[str, bytes], keep: set[str]) -> None:
    """Make `folder` hold `files` (relative POSIX names -> bytes), touching only what changed; the names in `keep`
    (such as config.json, written apart) stay."""
    folder = Path(folder)
    for name, data in files.items():
        path = folder / name
        try:
            if path.read_bytes() == data:
                continue
        except OSError:
            pass
        write_atomic(path, data)
    wanted = set(files) | set(keep)
    for path in list(folder.rglob("*")):
        if path.is_file() and path.relative_to(folder).as_posix() not in wanted:
            platforms.unlink(path, missing_ok=True)
```

`src/ai_browser/brain/watcher.py`:
- add `from ..syncdir import sync_folder, write_atomic` to the imports;
- delete `_write`, and delete `import os` if nothing else uses `os.`;
- in `prepare_watcher`, replace everything from `for name, data in files.items():` (the comparing loop) to the last
  `_write(...)` with:

```python
    sync_folder(folder, files, keep={"config.json"})
    write_atomic(folder / "config.json", json.dumps({"server": server_url, "token": token}).encode("utf-8"), 0o600)
```

- in the same function, `digest.update(name.encode() + b"\0" + data + b"\0")` becomes
  `digest.update(name.encode("utf-8") + b"\0" + data + b"\0")`, and `files["build.js"] = f'...'.encode()` gets
  `.encode("utf-8")`.

`src/ai_browser/appbrowser.py`:
- add `from .syncdir import sync_folder, write_atomic` to the imports;
- delete `import shutil` if nothing else uses `shutil.`;
- replace `prepare_extension`:

```python
def prepare_extension(home: Path, server_url: str, token: str) -> Path:
    """The side panel at home/app/extension (a fixed path keeps its ID), with the server's address and token. The
    folder is updated in place: on Windows a removal fails while anything holds a file open (a Defender scan, an
    AI Browser left from an earlier run)."""
    folder = Path(home) / "app" / "extension"
    files = {path.relative_to(EXTENSION_SOURCE).as_posix(): path.read_bytes()
             for path in sorted(EXTENSION_SOURCE.rglob("*"))
             if path.is_file() and not path.name.startswith(".") and "__pycache__" not in path.parts}
    sync_folder(folder, files, keep={"config.json"})
    write_atomic(folder / "config.json", json.dumps({"server": server_url, "token": token}).encode("utf-8"),
                 0o600)  # holds the token
    return folder
```

`src/ai_browser/brain/store.py`:
- add `from ..syncdir import write_atomic`;
- replace the body of `_write`:

```python
    def _write(self, name: str, data: dict) -> None:
        write_atomic(self.folder / name, json.dumps(data).encode("utf-8"), 0o600)
```

`src/ai_browser/brain/tools.py`:
- add `from ..syncdir import write_atomic`;
- in `_save`, replace the five lines from `temp = self.path.with_name(...)` through `os.replace(temp, self.path)`
  (the temp name, the `with` block and its `json.dump`, the `chmod`, the `replace`) with:

```python
        write_atomic(self.path, json.dumps(data).encode("utf-8"), 0o600)
```

`src/ai_browser/brain/workflows.py`:
- add `from ..syncdir import write_atomic`;
- in `save`, replace the five lines from `temp = path.with_name(...)` through `os.replace(temp, path)` with:

```python
        write_atomic(path, text.encode("utf-8"), 0o600)
```

`src/ai_browser/brain/skillwriter.py`:
- add `from .. import platforms` and `from ..syncdir import write_atomic`;
- in `save`, replace the `with os.fdopen(os.open(path, ... os.O_EXCL, 0o644), "w") as handle:` block with this. It
  keeps `O_EXCL`, so a new skill never overwrites one:

```python
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | platforms.O_BINARY, 0o644)
        with os.fdopen(fd, "wb") as handle:  # bytes: Python's text mode would end each line with \r\n on Windows
            handle.write((text.strip() + "\n").encode("utf-8"))
```

- in `update`, replace the five lines from `temp = path.with_name(...)` through `os.replace(temp, path)` with:

```python
        write_atomic(path, (text.strip() + "\n").encode("utf-8"), 0o644)
```

`src/ai_browser/app/bridge.py`:
- add `from ..syncdir import write_atomic`;
- in `_mcp_config`:
  - add `"PYTHONUTF8": "1"` to the env dict, right after `"AIB_HOME": str(self.home),`. It is a backstop for
    third-party libraries; our own code names its encodings. Keep everyday-brave's `AIB_BROWSER` logic as it is;
  - replace the three lines from `with os.fdopen(os.open(path, ...` to `os.chmod(path, 0o600)` with:

```python
        write_atomic(path, json.dumps(config, indent=1).encode("utf-8"), 0o600)  # its env carries the agent token
```

Everyday-brave's `link.json`, in `src/ai_browser/app/run.py` (`grep -n "link.json\|link_file" src/ai_browser/app/run.py`):
- `write_link(home, url, token)` writes it at start. In its body, replace the five lines from
  `temp = path.with_name(f".link.{os.getpid()}.tmp")` through `os.replace(temp, path)` with:

```python
    write_atomic(path, data, 0o600)  # holds the session token
```

  `data` (the UTF-8 JSON bytes it already builds) and `return path` stay;
- `_run`'s `finally` removes it at exit with `link_file.unlink()`: make that
  `platforms.unlink(link_file, missing_ok=True)` (keep any `contextlib.suppress(OSError)` around it);
- `run.py` already imports `platforms` (Task 5); add `from ..syncdir import write_atomic`.

Everyday-brave's link.json tests (`test_in_brave_mode_the_app_shows_the_switch_and_writes_link_json`) keep covering
it.

`.mcp.json.example`: everyday-brave left `"env": {}` there (its `tests/test_skills.py`
`test_the_website_qa_skill_says_where_qa_crawls` checks that `AIB_CHROME_DIR` is gone; never put it back). Make it:

```json
      "env": {"PYTHONUTF8": "1"}
```

If `"env"` holds other keys by now, add `"PYTHONUTF8": "1"` as its first key and keep the rest.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_syncdir.py tests/test_appbrowser.py tests/test_bridge.py tests/test_portable.py tests/test_workflows.py tests/test_brain_store.py tests/test_tools.py tests/test_skillwriter.py tests/test_app_server.py tests/test_skills.py -q -p no:randomly`
Expected: PASS.

Run: `uv run pytest tests/test_app_run.py -k link_json -q -p no:randomly`
Expected: PASS (everyday-brave's `link.json` test, through `write_atomic` now).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/syncdir.py src/ai_browser/brain/watcher.py src/ai_browser/appbrowser.py \
  src/ai_browser/brain/store.py src/ai_browser/brain/tools.py src/ai_browser/brain/workflows.py \
  src/ai_browser/brain/skillwriter.py src/ai_browser/app/bridge.py src/ai_browser/app/run.py .mcp.json.example \
  tests/test_syncdir.py tests/test_appbrowser.py tests/test_bridge.py tests/test_portable.py tests/test_workflows.py
git commit -m "Windows: atomic binary writes and in-place folders (syncdir); PYTHONUTF8 as a backstop"
```

---

### Task 13: Text keeps its characters: every read and write names its encoding

**Files:**
- Modify:
  - `src/ai_browser/brain/workflows.py` (`_load`), `src/ai_browser/skills.py` (`Catalog._read`, `Catalog.load`);
  - `src/ai_browser/brain/skillwriter.py` (`diff`);
  - `src/ai_browser/sandbox.py` (`_docker`);
  - `tests/fake_claude.py` (UTF-8 streams);
  - every other file the guard lists, in `src/ai_browser` and `tests`, through the one-off script in Step 3.
- Test: `tests/test_portable.py`, `tests/test_workflows.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `test_portable.text_io_calls(source: str) -> list[ast.Call]`: the calls that read or write text without
    `encoding=`. The guard uses it, and so does Step 3's script;
  - the user-editable files (workflows, `SKILL.md`) are read with `encoding="utf-8-sig"`, so a BOM is dropped.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_portable.py`:

```python
def _binary_mode(node) -> bool:
    """A mode counts as binary when it is a literal with b, or an `x if c else y` of such literals."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "b" in node.value
    if isinstance(node, ast.IfExp):
        return _binary_mode(node.body) and _binary_mode(node.orelse)
    return False


def _true(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name and isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in call.keywords)


def text_io_calls(source: str) -> list[ast.Call]:
    """The calls that read or write text without naming the encoding (Windows would use its code page):
    .read_text() with no positional argument, .write_text(x) with one, open() and os.fdopen() in a mode without b,
    and subprocess calls with text=True or universal_newlines=True."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or any(kw.arg == "encoding" for kw in node.keywords):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        owner = func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else ""
        if isinstance(func, ast.Attribute) and name == "read_text" and not node.args:
            found.append(node)  # WorkDir.read_text(path, limit) has two
        elif isinstance(func, ast.Attribute) and name == "write_text" and len(node.args) == 1:
            found.append(node)  # WorkDir.write_text(path, content) has two
        elif (isinstance(func, ast.Name) and name == "open") or (owner == "os" and name == "fdopen"):
            mode = node.args[1] if len(node.args) > 1 else next(
                (kw.value for kw in node.keywords if kw.arg == "mode"), None)
            if mode is None or not _binary_mode(mode):
                found.append(node)
        elif owner == "subprocess" and (_true(node, "text") or _true(node, "universal_newlines")):
            found.append(node)
    return found


def test_text_io_names_its_encoding():
    found = [f"{path.relative_to(ROOT)}:{call.lineno}"
             for top in (SRC, ROOT / "tests") for path in sorted(top.rglob("*.py"))
             for call in text_io_calls(path.read_text(encoding="utf-8"))]
    assert not found, "text read or written without encoding=:\n" + "\n".join(sorted(found))
```

Append to `tests/test_workflows.py`:

```python
def test_files_saved_by_notepad_load_like_the_macs(tmp_path):
    from ai_browser.brain.workflows import WorkflowStore
    from ai_browser.skills import Catalog, SkillSource

    store = WorkflowStore(tmp_path)
    store.folder.mkdir(parents=True)
    (store.folder / "morning.md").write_bytes(  # UTF-8 with a BOM, and CRLF line ends
        "\ufeff---\r\nname: Morning → report 🚀\r\ntrigger: manual\r\n---\r\nCheck 日本語 mail\r\n".encode("utf-8"))
    assert [(w.slug, w.name, w.instructions) for w in store.all()] == [
        ("morning", "Morning → report 🚀", "Check 日本語 mail")]
    assert store.problems() == []
    folder = tmp_path / "skills" / "notes"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_bytes(
        "\ufeff---\r\nname: notes\r\ndescription: Takes notes — fast\r\n---\r\nBody\r\n".encode("utf-8"))
    catalog = Catalog([SkillSource("personal", tmp_path / "skills", "/skills/personal", "*/SKILL.md")], set())
    [skill] = catalog.all()
    assert (skill.name, skill.description) == ("notes", "Takes notes — fast")
    assert catalog.load("notes").rstrip().endswith("Body")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_portable.py::test_text_io_names_its_encoding tests/test_workflows.py::test_files_saved_by_notepad_load_like_the_macs -q -p no:randomly`
Expected: FAIL:
- the guard lists the unnamed reads and writes left after Task 12, about 20 in `src` and about 170 in `tests`, for
  example `src/ai_browser/browser.py:26` and `src/ai_browser/sandbox.py:72`;
- the Notepad workflow isn't loaded (`[]`), because the BOM hides its front matter.

- [ ] **Step 3: Implement**

First the reads whose encoding isn't plain UTF-8, by hand:
- `src/ai_browser/brain/workflows.py`, `_load`: `text = path.read_text()` becomes
  `text = path.read_text(encoding="utf-8-sig")  # a BOM from Notepad is dropped`;
- `src/ai_browser/skills.py`:
  - in `Catalog._read`: `skill_md.read_text(errors="replace")` becomes
    `skill_md.read_text(encoding="utf-8-sig", errors="replace")`;
  - in `Catalog.load`: `(skill.host_dir / "SKILL.md").read_text(errors="replace")` becomes
    `(skill.host_dir / "SKILL.md").read_text(encoding="utf-8-sig", errors="replace")`;
- `src/ai_browser/brain/skillwriter.py`, `diff`: `path.read_text().splitlines(keepends=True)` becomes
  `path.read_text(encoding="utf-8-sig").splitlines(keepends=True)`;
- `src/ai_browser/sandbox.py`, `_docker`: `capture_output=True, text=True, timeout=timeout` becomes
  `capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout`;
- `tests/fake_claude.py`, right after the imports (before the `.env` log is opened):

```python
for stream in (sys.stdin, sys.stdout, sys.stderr):  # UTF-8 on every OS, as Claude Code's own streams are
    stream.reconfigure(encoding="utf-8")
```

Then every remaining one. Save this one-off script outside the repo, in your scratchpad folder, as
`name_encodings.py`. Don't commit it. Run it from the repo root with `uv run python <scratchpad>/name_encodings.py`:

```python
"""One-off: add encoding="utf-8" to every text read or write that tests/test_portable.py's guard lists."""

import sys
from pathlib import Path

sys.path.insert(0, "tests")
from test_portable import text_io_calls  # the guard's own finder

for top in ("src/ai_browser", "tests"):
    for path in sorted(Path(top).rglob("*.py")):
        data = path.read_bytes()
        calls = text_io_calls(data.decode("utf-8"))
        if not calls:
            continue
        starts = [0]  # byte offset of each line: ast's column offsets count UTF-8 bytes
        for line in data.splitlines(keepends=True):
            starts.append(starts[-1] + len(line))
        for call in sorted(calls, key=lambda node: (node.end_lineno, node.end_col_offset), reverse=True):
            close = starts[call.end_lineno - 1] + call.end_col_offset - 1
            assert data[close:close + 1] == b")", (path, call.lineno)
            before = data[:close].rstrip()
            glue = b"" if before.endswith(b"(") else b" " if before.endswith(b",") else b", "
            data = data[:close] + glue + b'encoding="utf-8"' + data[close:]
        path.write_bytes(data)
        print(f"{path}: {len(calls)}")
```

Then check the result:
- `git diff --stat` touches only `.py` files under `src/ai_browser` and `tests`;
- read the diff for `src/ai_browser`. No `encoding=` may land in a `WorkDir.read_text`/`write_text` call: those take
  a sandbox path, and pass their arguments positionally. If one did, undo it;
- `git diff -U0 | grep '^+' | awk 'length > 121'` lists lines the edit made longer than 120 characters. Wrap each
  one at a comma.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_portable.py tests/test_workflows.py::test_files_saved_by_notepad_load_like_the_macs -q -p no:randomly`
Expected: PASS.

Run: `uv run pytest --collect-only -q -p no:randomly`
Expected: every test module imports (no errors).

Run: `uv run pytest tests/test_skills.py tests/test_oneshot.py tests/test_bridge.py tests/test_config.py tests/test_tasklog.py tests/test_brain_store.py tests/test_tools.py tests/test_qa_report.py tests/test_skillwriter.py tests/test_engine.py -q -p no:randomly`
Expected: PASS (the Docker tests skip themselves without Docker).

- [ ] **Step 5: Commit**

```bash
git add -u src/ai_browser tests
git commit -m "Windows: every text read and write names UTF-8; Notepad's BOM is dropped from workflows and skills"
```

---

### Task 14: Finding Claude Code (`claudecli.py`), and the fake claude as an argv list

**Files:**
- Create: `src/ai_browser/claudecli.py`
- Create: `tests/test_claudecli.py`
- Modify:
  - `src/ai_browser/app/bridge.py` (`__init__`, `_command`, `send`);
  - `src/ai_browser/brain/oneshot.py` (`command`, `ask_claude`), `src/ai_browser/brain/tools.py` (`probe`);
  - the `claude` annotations in `app/agents.py`, `brain/service.py`, `brain/skillwriter.py` and `app/run.py`;
  - `tests/conftest.py` (`fake_claude`), and every test that turned the runner into a string.

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `claudecli.ClaudeNotUsable(OSError)`: its message is the whole explanation;
  - `claudecli.claude_argv(claude: str | Sequence[str] | None = None, system: str | None = None, env: Mapping | None
    = None) -> list[str]`, which looks in this order: the argument (a list is kept as it is), `AIB_CLAUDE`, Windows'
    `%USERPROFILE%\.local\bin\claude.exe`, `shutil.which("claude")`, then `~/.local/bin/claude` (`claude.exe` on
    Windows). On Windows a `.cmd` or `.bat` raises `ClaudeNotUsable`;
  - every `claude` parameter (`ClaudeBridge`, `AgentManager`, `BrainService`, `SkillWriter`, `run_app`,
    `ask_claude`, `ToolsConfig.probe`) accepts `str | Sequence[str] | None` and passes it on unchanged. It is
    resolved when a process starts;
  - the errors stay text:
    - `ClaudeBridge.send` yields `{"type": "error", "text": str(exc)}`;
    - `ask_claude` returns `OneShot(error=str(exc))`;
    - `probe` returns False;
  - the `fake_claude` fixture's `runner` is `[sys.executable, ".../tests/fake_claude.py"]`, and tests pass
    `claude=runner`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_claudecli.py`:

```python
"""Finding Claude Code on every OS: the native executable, never an npm .cmd script on Windows."""

import os
import shutil
import sys

import pytest

from ai_browser.claudecli import ClaudeNotUsable, claude_argv

NPM = "C:\\Users\\me\\AppData\\Roaming\\npm\\claude.cmd"


def test_a_list_or_a_string_is_kept_as_it_is():
    assert claude_argv([sys.executable, "fake_claude.py"], env={}) == [sys.executable, "fake_claude.py"]
    assert claude_argv(("claude", "--debug"), env={}) == ["claude", "--debug"]
    assert claude_argv("/opt/claude", env={}) == ["/opt/claude"]


def test_aib_claude_wins_over_path(tmp_path):
    folder = tmp_path / "bin"
    folder.mkdir()
    for name in ("claude", "claude.exe"):
        (folder / name).write_bytes(b"")
        (folder / name).chmod(0o755)
    assert claude_argv(env={"AIB_CLAUDE": "/somewhere/claude", "PATH": str(folder)}) == ["/somewhere/claude"]
    found = shutil.which("claude", path=str(folder))
    assert found and claude_argv(env={"PATH": str(folder)}) == [found]


def test_windows_refuses_the_npm_script():
    for found in (NPM, NPM.replace("claude.cmd", "CLAUDE.BAT")):
        with pytest.raises(ClaudeNotUsable) as refused:
            claude_argv(found, system="win32", env={})
        message = str(refused.value)
        assert message.startswith(f"Claude Code was found at {found}, a script from the npm install.")
        assert "irm https://claude.ai/install.ps1 | iex" in message and "AIB_CLAUDE" in message
    with pytest.raises(ClaudeNotUsable):
        claude_argv(env={"AIB_CLAUDE": NPM}, system="win32")
    assert claude_argv("/opt/claude.cmd", system="darwin", env={}) == ["/opt/claude.cmd"]  # only cmd.exe mangles it


def test_windows_prefers_the_native_install(tmp_path):
    native = tmp_path / ".local" / "bin" / "claude.exe"
    native.parent.mkdir(parents=True)
    native.write_bytes(b"MZ")
    npm = tmp_path / "npm"
    npm.mkdir()
    (npm / "claude.cmd").write_text("@echo off\n", encoding="utf-8")
    assert claude_argv(env={"USERPROFILE": str(tmp_path), "PATH": str(npm)}, system="win32") == [str(native)]


async def test_the_panel_the_brain_and_the_probe_say_why(tmp_path, monkeypatch):
    from ai_browser.app.bridge import ClaudeBridge
    from ai_browser.brain.oneshot import ask_claude
    from ai_browser.brain.tools import ToolsConfig

    monkeypatch.setattr(sys, "platform", "win32")  # claude_argv's default system; nothing is started
    bridge = ClaudeBridge(tmp_path / "home", claude=NPM)
    [event] = [event async for event in bridge.send("hi")]
    assert event["type"] == "error" and event["text"].startswith(f"Claude Code was found at {NPM}")
    answer = await ask_claude("hi", claude=NPM, cwd=tmp_path / "calls")
    assert answer.text == "" and answer.error.startswith(f"Claude Code was found at {NPM}")
    assert await ToolsConfig(tmp_path / "home").probe(NPM) is False


def test_the_fake_claude_is_an_argv_prefix(fake_claude):
    runner, _, _ = fake_claude
    assert runner[0] == sys.executable and runner[1].endswith("fake_claude.py") and os.path.isfile(runner[1])
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_claudecli.py -q -p no:randomly`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai_browser.claudecli'`.

- [ ] **Step 3: Implement**

Create `src/ai_browser/claudecli.py`:

```python
"""Claude Code, found the same way on every OS: the native executable, never the npm install's .cmd script.

On Windows an npm claude.cmd runs through cmd.exe. cmd.exe cuts the multi-line --append-system-prompt at its first
line (the agent's safety rules are in it) and mangles quoting, and stopping it would end only cmd.exe while the real
CLI kept running. So it is refused, with the whole explanation."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

NPM_SCRIPT = ("Claude Code was found at {path}, a script from the npm install. AI Browser needs the native claude.exe: "
              "install it with `irm https://claude.ai/install.ps1 | iex` in PowerShell, or set AIB_CLAUDE to the full "
              "path of claude.exe.")


class ClaudeNotUsable(OSError):
    """Claude Code can't be used as found; the message is the whole explanation."""


def claude_argv(claude: str | Sequence[str] | None = None, system: str | None = None,
                env: Mapping | None = None) -> list[str]:
    """The command that starts Claude Code: the argument (a string, or a list such as [python, fake_claude.py]),
    else $AIB_CLAUDE, else (Windows) %USERPROFILE%\\.local\\bin\\claude.exe, else claude on PATH, else
    ~/.local/bin/claude (claude.exe on Windows)."""
    windows = (system or sys.platform) == "win32"
    env = os.environ if env is None else env
    if isinstance(claude, (list, tuple)):
        argv = [str(part) for part in claude]
    elif claude:
        argv = [str(claude)]
    elif env.get("AIB_CLAUDE"):
        argv = [env["AIB_CLAUDE"]]
    else:
        argv = [_find(windows, env)]
    if windows and argv[0].lower().endswith((".cmd", ".bat")):
        raise ClaudeNotUsable(NPM_SCRIPT.format(path=argv[0]))
    return argv


def _find(windows: bool, env: Mapping) -> str:
    if windows:  # where the native installer puts it, ahead of an npm claude.cmd on PATH
        native = Path(env.get("USERPROFILE") or Path.home()) / ".local" / "bin" / "claude.exe"
        if native.is_file():
            return str(native)
    found = shutil.which("claude", path=env.get("PATH"))
    if found:
        return found
    return str(Path.home() / ".local" / "bin" / ("claude.exe" if windows else "claude"))
```

`src/ai_browser/app/bridge.py`:
- add `from collections.abc import Sequence` (unless it is already there) and
  `from ..claudecli import ClaudeNotUsable, claude_argv`;
- in `ClaudeBridge.__init__`, the parameter becomes `claude: str | Sequence[str] | None = None`, and
  `self.claude = claude or shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")` becomes:

```python
        self.claude = claude  # resolved when a process starts (claude_argv): a list too, such as the tests' fake
```

- in `_command`, make the first line `argv = claude_argv(self.claude)  # ClaudeNotUsable for an npm claude.cmd`,
  and start the command list with `*argv` instead of `self.claude`:

```python
        command = [*argv, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
```

  The rest of the list stays as it is, `PANEL_PROMPT`/`BRAVE_PROMPT` included.
- in `send`, add a branch before the generic one:

```python
                try:
                    await self._start()
                except ClaudeNotUsable as exc:  # its message is the whole explanation
                    yield {"type": "error", "text": str(exc)}
                    return
                except OSError as exc:
```

- delete `import shutil` if `grep -n "shutil\." src/ai_browser/app/bridge.py` finds nothing else.

`src/ai_browser/brain/oneshot.py`:
- add `from collections.abc import Sequence` and `from ..claudecli import ClaudeNotUsable, claude_argv`;
- replace `command`:

```python
def command(claude: str | Sequence[str] | None, model: str) -> list[str]:
    return [*claude_argv(claude), "-p", "--model", model, "--tools", "", "--strict-mcp-config", "--mcp-config",
            NO_SERVERS, "--setting-sources", "local", "--no-session-persistence", "--output-format", "json"]
```

- in `ask_claude`:
  - the parameter becomes `claude: str | Sequence[str] | None = None`;
  - delete the `claude = claude or shutil.which(...)` line;
  - add the `ClaudeNotUsable` branch before the generic one:

```python
    except ClaudeNotUsable as exc:
        return OneShot(error=str(exc))
    except OSError as exc:
```

  - delete `import shutil` if nothing else uses it.

`src/ai_browser/brain/tools.py`:
- add `from collections.abc import Sequence` and `from ..claudecli import claude_argv`;
- in `probe`:
  - the parameter becomes `claude: str | Sequence[str] | None = None`;
  - delete the `claude = claude or shutil.which(...)` line;
  - the subprocess call starts `*claude_argv(claude), "-p", PROBE_PROMPT, ...` instead of `claude, "-p",
    PROBE_PROMPT, ...`. It stays inside the `try`, whose `except OSError: return False` also catches
    `ClaudeNotUsable`;
  - delete `import shutil` if nothing else uses it.

Annotations: the `claude` parameter becomes `str | Sequence[str] | None = None` (with
`from collections.abc import Sequence` in each file) in:
- `AgentManager.__init__` (`app/agents.py`);
- `BrainService.__init__` (`brain/service.py`);
- `SkillWriter.__init__` (`brain/skillwriter.py`);
- `run_app` and `_run` (`app/run.py`).

Their bodies already pass `claude` on as it is.

`tests/conftest.py`, replace the `fake_claude` fixture:

```python
@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """The fake `claude`: (runner, log, script). runner is an argv prefix, [python, fake_claude.py], which every
    `claude` parameter accepts, the same on every OS. Write the reply events to `script` as a JSON list."""
    import sys

    script, log = tmp_path / "fake-claude-script.json", tmp_path / "fake-claude.log"
    script.write_text("[]", encoding="utf-8")
    runner = [sys.executable, str(Path(__file__).with_name("fake_claude.py"))]
    monkeypatch.setenv("FAKE_CLAUDE_SCRIPT", str(script))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    return runner, log, script
```

Every test that turned the runner into a string now passes it as it is: 51 `claude=str(runner)`, `str(runner_bin)`,
`str(stack["runner"])`, `str(watcher.runner)` and `tools.probe(str(runner))` at the baseline, plus any that waves
1-3 added. Run once from the repo root:

```bash
uv run python - <<'EOF'
import re
from pathlib import Path

for path in sorted(Path("tests").glob("*.py")):
    text = path.read_text(encoding="utf-8")
    new = re.sub(r'str\((runner_bin|runner|stack\["runner"\]|watcher\.runner)\)', r"\1", text)
    if new != text:
        path.write_text(new, encoding="utf-8")
        print(path)
EOF
```

Then `grep -rn 'str(runner\|str(stack\["runner"\])\|str(watcher\.runner)' tests` must print nothing.
`claude=str(tmp_path / "nope")` in `test_bridge.py` stays: it is a missing binary on purpose.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_claudecli.py tests/test_bridge.py tests/test_oneshot.py tests/test_agents.py tests/test_tools.py tests/test_skillwriter.py tests/test_brain_service.py -q -p no:randomly`
Expected: PASS.

Run: `uv run pytest --collect-only -q -p no:randomly`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/claudecli.py src/ai_browser/app/bridge.py src/ai_browser/brain/oneshot.py \
  src/ai_browser/brain/tools.py src/ai_browser/app/agents.py src/ai_browser/brain/service.py \
  src/ai_browser/brain/skillwriter.py src/ai_browser/app/run.py tests/test_claudecli.py
git add -u tests
git commit -m "Windows: Claude Code is the native executable (an npm claude.cmd is refused); the fake claude is an argv list"
```

---

### Task 15: Ending Claude Code on Windows: its own group, a clean exit, the kill-on-close job

**Files:**
- Modify: `src/ai_browser/claudecli.py` (`CREATE_NEW_PROCESS_GROUP`, `spawn_options`, `track`, `_job`)
- Modify: `src/ai_browser/platforms.py` (`KillOnCloseJob`, the job prototypes in `_kernel32`)
- Modify: `src/ai_browser/app/bridge.py` (`CLEAN_EXIT`, `_start`, `_end_process`)
- Modify: `src/ai_browser/brain/oneshot.py` and `src/ai_browser/brain/tools.py` (spawn options and `track`)
- Modify: `tests/fake_claude.py` (the `spawn` entry)
- Test: `tests/test_claudecli.py`, `tests/test_bridge.py`

**Interfaces:**
- Consumes: `claudecli.claude_argv`, `platforms.WINDOWS`, `platforms.pid_alive`, `platforms._kernel32`.
- Produces:
  - `claudecli.spawn_options() -> dict`: `{"creationflags": CREATE_NEW_PROCESS_GROUP}` on Windows, `{}` elsewhere;
  - `claudecli.track(process) -> None`: on Windows, adds the process to a module-level `KillOnCloseJob`, made on first
    use. It is a no-op elsewhere, and a failed add is ignored;
  - `platforms.KillOnCloseJob()` with `.add(pid)` and `.close()`. Windows only. Its handle is never closed by the
    app; it closes when the app's process ends;
  - `bridge.CLEAN_EXIT = 3`. On Windows `_end_process` closes stdin and waits up to `CLEAN_EXIT` s before
    `terminate()`. `_end_if_still_running` (Stop) keeps its `terminate()`;
  - the fake claude's script entry `{"spawn": seconds}` starts a sleeping child and logs `{"child": pid}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_claudecli.py`:

```python
def test_claude_code_gets_its_own_process_group_on_windows(monkeypatch):
    from ai_browser import claudecli, platforms

    assert claudecli.spawn_options() == ({"creationflags": 0x00000200} if os.name == "nt" else {})
    monkeypatch.setattr(platforms, "WINDOWS", True)  # only the options change: nothing is started
    assert claudecli.spawn_options() == {"creationflags": 0x00000200}  # CREATE_NEW_PROCESS_GROUP
```

Append to `tests/test_bridge.py`:

```python
async def test_on_windows_claude_code_gets_to_exit_by_itself_first(fake_claude, tmp_path, monkeypatch):
    from ai_browser import platforms
    from ai_browser.app.bridge import ClaudeBridge

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    bridge = ClaudeBridge(tmp_path / "home", claude=runner)
    [event async for event in bridge.send("hi")]
    process, ended = bridge._process, []
    monkeypatch.setattr(process, "terminate", lambda: ended.append("terminate"))
    monkeypatch.setattr(platforms, "WINDOWS", True)  # only the wait changes: no Win32 call is made
    await bridge._end_process()
    assert ended == [] and process.returncode == 0  # it saw stdin close and exited, closing its MCP server itself


@pytest.mark.windows_only
async def test_the_job_ends_what_claude_code_started(fake_claude, tmp_path, monkeypatch):
    from ai_browser import claudecli, platforms
    from ai_browser.app.bridge import ClaudeBridge

    runner, log, script = fake_claude
    script.write_text(json.dumps([{"spawn": 60}, *EVENTS]), encoding="utf-8")
    job = platforms.KillOnCloseJob()  # a fresh one in place of the app's
    monkeypatch.setattr(claudecli, "_job", job)
    bridge = ClaudeBridge(tmp_path / "home", claude=runner)
    [event async for event in bridge.send("hi")]
    child = next(json.loads(line)["child"] for line in log.read_text(encoding="utf-8").splitlines()
                 if line.startswith('{"child"'))
    await bridge.close()  # the fake claude exits; ending a process on Windows doesn't end its children
    assert platforms.pid_alive(child)
    job.close()
    for _ in range(50):
        if not platforms.pid_alive(child):
            break
        await asyncio.sleep(0.1)
    assert not platforms.pid_alive(child)
```

At the top of `tests/test_bridge.py`, add `import pytest` if it isn't imported yet.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_claudecli.py::test_claude_code_gets_its_own_process_group_on_windows tests/test_bridge.py::test_on_windows_claude_code_gets_to_exit_by_itself_first -q -p no:randomly`
Expected: FAIL:
- `AttributeError: module 'ai_browser.claudecli' has no attribute 'spawn_options'`;
- `ended == ["terminate"]`, because today `terminate` comes at once.

- [ ] **Step 3: Implement**

`src/ai_browser/platforms.py`:
- in `_kernel32()`, before `return kernel32`, add:

```python
    kernel32.CreateJobObjectW.argtypes, kernel32.CreateJobObjectW.restype = (ctypes.c_void_p, ctypes.c_wchar_p), handle
    kernel32.SetInformationJobObject.argtypes = (handle, ctypes.c_int, ctypes.c_void_p, dword)
    kernel32.SetInformationJobObject.restype = boolean
    kernel32.AssignProcessToJobObject.argtypes, kernel32.AssignProcessToJobObject.restype = (handle, handle), boolean
```

- append:

```python
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
PROCESS_TERMINATE, PROCESS_SET_QUOTA = 0x0001, 0x0100


class _BasicLimits(ctypes.Structure):  # JOBOBJECT_BASIC_LIMIT_INFORMATION
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32)]


class _IoCounters(ctypes.Structure):  # IO_COUNTERS
    _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount",
                                                     "OtherOperationCount", "ReadTransferCount",
                                                     "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimits(ctypes.Structure):  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class KillOnCloseJob:
    """A Windows job object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: when its handle closes (the app's process
    ending, even by a crash), Windows ends every process in it, and the ones they started. Windows only."""

    def __init__(self):
        kernel32 = _kernel32()
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits),
                                                ctypes.sizeof(limits)):
            error = ctypes.get_last_error()
            kernel32.CloseHandle(handle)
            raise ctypes.WinError(error)
        self._handle = handle

    def add(self, pid: int) -> None:
        """Put a running process in the job; OSError when it can't (for example, it has already exited)."""
        kernel32 = _kernel32()
        process = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not kernel32.AssignProcessToJobObject(self._handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel32.CloseHandle(process)

    def close(self) -> None:
        """End every process in the job now. Tests call it; the app never does, its handle closes with the app."""
        if self._handle:
            _kernel32().CloseHandle(self._handle)
            self._handle = None
```

`src/ai_browser/claudecli.py`:
- add `import subprocess` and `from . import platforms` to the imports;
- append:

```python
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)  # Windows' value
_job = None  # the app's KillOnCloseJob, made on first use on Windows; its handle closes only with the app


def spawn_options() -> dict:
    """Claude Code in a process group of its own on Windows. Windows turns Ctrl-C off for a new group, and its
    children inherit that, so a Ctrl-C in the console ends only the app, which then closes the agents in order."""
    return {"creationflags": CREATE_NEW_PROCESS_GROUP} if platforms.WINDOWS else {}


def track(process) -> None:
    """Put a Claude Code process in the app's kill-on-close job (Windows; a no-op elsewhere), so it and the MCP
    servers it starts end with the app, even after a crash. It is called right after the process starts, in the same
    event-loop step: Claude Code takes hundreds of milliseconds to start its children, so in practice none starts
    first. asyncio can't start a process suspended."""
    global _job
    if not platforms.WINDOWS or not getattr(process, "pid", None):
        return
    try:
        if _job is None:
            _job = platforms.KillOnCloseJob()
        _job.add(process.pid)
    except OSError:  # it has already exited, or no job could be made: the clean exit still ends it
        pass
```

`src/ai_browser/app/bridge.py`:
- add `from .. import platforms` and import `spawn_options` and `track` from `..claudecli`, alongside
  `ClaudeNotUsable` and `claude_argv`;
- add `CLEAN_EXIT = 3  # seconds Claude Code gets on Windows to exit by itself, closing its own MCP server` under
  `STOP_GRACE`;
- in `_start`, pass `**spawn_options()` to `asyncio.create_subprocess_exec(...)`, after `limit=STDOUT_LIMIT`, and add
  `track(self._process)` on the line right after the call;
- replace `_end_process`:

```python
    async def _end_process(self) -> None:
        process, self._process = self._process, None
        if process is None or process.returncode is not None:
            return
        with contextlib.suppress(Exception):
            process.stdin.close()
        if platforms.WINDOWS:
            # terminate() there is TerminateProcess, which never ends a process's children. Claude Code sees its
            # stdin close and exits by itself, closing its ai-browser MCP server on the way out. (On POSIX,
            # terminate() is SIGTERM, which is already graceful.)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(process.wait(), CLEAN_EXIT)
            if process.returncode is not None:
                return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            process.kill()
            await process.wait()
```

`src/ai_browser/brain/oneshot.py`:
- import `spawn_options` and `track` from `..claudecli`;
- in `ask_claude`, pass `**spawn_options()` to `asyncio.create_subprocess_exec(...)`;
- right after the `try`/`except` that starts the process (before `process.communicate`), add `track(process)`.

`src/ai_browser/brain/tools.py`:
- import `spawn_options` and `track` from `..claudecli`;
- in `probe`, pass `**spawn_options()` to `asyncio.create_subprocess_exec(...)`, and add `track(process)` right after
  the `try`/`except OSError: return False`.

`tests/fake_claude.py`:
- add `import subprocess` to the imports;
- in the module docstring, add `{"spawn": s} starts a child that sleeps s seconds and logs {"child": pid}` to the
  sentence listing the script entries;
- in the main loop's `for event in events:`, right after the `ignore_interrupt` check, add:

```python
            if "spawn" in event:  # a child of its own, as Claude Code starts its MCP servers
                child = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({float(event['spawn'])})"])
                log.write(json.dumps({"child": child.pid}) + "\n")
                continue
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_claudecli.py tests/test_bridge.py tests/test_oneshot.py tests/test_tools.py -q -p no:randomly`
Expected: PASS (the job test is skipped on the Mac).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/claudecli.py src/ai_browser/platforms.py src/ai_browser/app/bridge.py \
  src/ai_browser/brain/oneshot.py src/ai_browser/brain/tools.py tests/fake_claude.py tests/test_claudecli.py \
  tests/test_bridge.py
git commit -m "Windows: Claude Code in its own process group, a clean exit first, and a kill-on-close job"
```

---

### Task 16: The setup page in Windows words, and a reveal that says when it couldn't

**Files:**
- Modify: `src/ai_browser/app/server.py` (`reveal_in_finder` becomes `reveal_folder`; `GOTO_MAC`, `GOTO_OTHER`,
  `setup_page`; `_setup`; `_setup_reveal`)
- Modify: `src/ai_browser/app/setup.html` (placeholders, `data-manager`, the result text, `#switch`)
- Modify: `src/ai_browser/app/run.py` (the import of the reveal)
- Modify: `tests/conftest.py` (`_no_finder_windows`)
- Test: `tests/test_app_server.py`

**Interfaces:**
- Consumes: `platforms.reveal`, `platforms.file_manager`, `platforms.shortcut`, `platforms.this_computer`.
- Produces:
  - `server.reveal_folder = platforms.reveal`;
  - `run.reveal = reveal_folder`;
  - `server.setup_page(extension: str, watcher: str, key: str, system: str | None = None) -> str`;
  - `POST /setup/reveal` answers 204 when a folder window opened and 501 when none could;
  - the placeholders `{{FILE_MANAGER}}`, `{{GOTO}}` and `{{THIS_COMPUTER}}`, each filled with `html.escape`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app_server.py`:

```python
def test_the_setup_page_is_worded_for_each_computer():
    from ai_browser.app.server import setup_page

    windows = setup_page("C:\\Users\\José & Ana\\.ai-browser\\app\\extension", "C:\\w", "k", system="win32")
    assert "File Explorer" in windows and 'data-manager="File Explorer"' in windows
    assert "click the address bar at the top of the folder window, paste the path and press Enter" in windows
    assert "⌘" not in windows and "Finder" not in windows and "{{" not in windows
    assert "C:\\Users\\José &amp; Ana\\.ai-browser\\app\\extension" in windows  # whole, accents kept, escaped
    mac = setup_page("/Users/me/.ai-browser/app/extension", "/w", "k", system="darwin")
    assert "Finder" in mac and "press ⌘⇧G, paste the path and press Enter" in mac and "<kbd>" not in mac


async def test_the_reveal_says_when_no_folder_window_opened(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    server.reveal = lambda path: False  # no file manager could start
    try:
        async with httpx.AsyncClient() as client:
            page = (await client.get(url + "/setup")).text
            key = page.split('data-key="', 1)[1].split('"', 1)[0]
            assert (await client.post(url + "/setup/reveal", headers={"X-AIB-Setup": key})).status_code == 501
    finally:
        await server.stop()
```

The reveal now reports whether a window opened, so the two tests that record the reveal must return True. In
`test_the_setup_page_can_show_the_folder_in_finder` and `test_the_setup_page_has_the_brave_steps`, replace
`server.reveal = shown.append` with:

```python
    server.reveal = lambda path: shown.append(path) or True
```

Then `grep -rn "\.reveal = " tests` must list only replacements that return True (Task 8's test already does),
`lambda path: False` in the new 501 test, and the conftest's patches.

Everyday-brave's `test_the_setup_page_has_the_switch_and_its_warning` (in `tests/test_app_server.py`) asserts the
sentence "While this switch is on, any program on this Mac can reach your Brave, not only AI Browser." on `/setup`.
Replace that one assertion with these lines. The page breaks the sentence over two lines, so the words are compared
with whitespace flattened, as that test already does for `/setup`:

```python
        from ai_browser.app.server import setup_page

        def words(system):
            return " ".join(setup_page("/x", "/w", "k", system=system).split())

        sentence = "While this switch is on, any program on {} can reach your Brave, not only AI Browser."
        assert sentence.format("this Mac") in words("darwin")
        assert sentence.format("this PC") in words("win32")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_server.py -k "worded or no_folder_window" -q -p no:randomly`
Expected: FAIL:
- `ImportError: cannot import name 'setup_page'`;
- the reveal answers 204.

- [ ] **Step 3: Implement**

`src/ai_browser/app/server.py`:
- add `from .. import platforms` to the imports;
- replace `reveal_in_finder` (the whole function) with:

```python
reveal_folder = platforms.reveal  # a file manager window with the folder selected; False when none could open
GOTO_MAC = "press ⌘⇧G, paste the path and press Enter"
GOTO_OTHER = "click the address bar at the top of the folder window, paste the path and press Enter"


def setup_page(extension: str, watcher: str, key: str, system: str | None = None) -> str:
    """The one-time setup page, worded for the computer it runs on; every value is escaped."""
    values = {"{{FILE_MANAGER}}": platforms.file_manager(system),
              "{{GOTO}}": platforms.shortcut(GOTO_MAC, GOTO_OTHER, system),
              "{{THIS_COMPUTER}}": platforms.this_computer(system),
              "{{FOLDER}}": extension, "{{WATCHER}}": watcher, "{{KEY}}": key}
    page = SETUP_PAGE.read_text(encoding="utf-8")
    for placeholder, value in values.items():
        page = page.replace(placeholder, html.escape(value))
    return page
```

- in `AppServer.__init__`, `self.reveal = reveal_in_finder` becomes `self.reveal = reveal_folder`;
- `_setup` becomes:

```python
    async def _setup(self, request: Request) -> HTMLResponse:
        return HTMLResponse(setup_page(self._extension_folder(), self._watcher_folder(), self.setup_key))
```

  If waves 1 and 2 made `_setup` fill other placeholders, keep those `.replace(...)` calls: apply them to
  `setup_page(...)`'s result before returning it.

- in `_setup_reveal`, the last two lines become:

```python
        shown = self.reveal(self._watcher_folder() if watcher else self._extension_folder())
        return Response(status_code=204 if shown else 501)  # 501: nothing could show it (no file manager)
```

- delete the `subprocess` and `sys` imports if `grep -n "subprocess\.\|sys\." src/ai_browser/app/server.py` finds
  no other use.

`src/ai_browser/app/run.py`:
- the import `from .server import AppServer, reveal_in_finder` becomes `from .server import AppServer, reveal_folder`;
- `reveal = reveal_in_finder  # ...` becomes:

```python
reveal = reveal_folder  # a file manager window with the extension folder selected (tests replace it)
```

`src/ai_browser/app/setup.html`. In the AI Browser section, replace step 2 (the `<li>Drag the
<strong>extension</strong> folder…` item, through its `</li>`) with:

```html
    <li>Drag the <strong>extension</strong> folder from the {{FILE_MANAGER}} window onto that page.
      <div class="path"><button id="reveal" type="button" data-key="{{KEY}}" data-manager="{{FILE_MANAGER}}">Show the folder in {{FILE_MANAGER}}</button></div>
      <p class="alt">Or click <strong>Load unpacked</strong>, {{GOTO}}, then <strong>Select</strong>. The folder:</p>
      <div class="path"><code id="folder">{{FOLDER}}</code><button id="copy" type="button">Copy</button></div>
    </li>
```

In the Brave section, replace step 2 (the `<li>Drag the <strong>watcher</strong> folder…` item) with:

```html
    <li>Drag the <strong>watcher</strong> folder onto that page.
      <div class="path"><button id="reveal-watcher" type="button" data-key="{{KEY}}" data-manager="{{FILE_MANAGER}}">Show the folder in {{FILE_MANAGER}}</button></div>
      <p class="alt">Or click <strong>Load unpacked</strong>, {{GOTO}}, then <strong>Select</strong>. The folder:</p>
      <div class="path"><code id="watcher-folder">{{WATCHER}}</code></div>
    </li>
```

In the script, the reveal result:

```js
        button.textContent = answer.ok ? "Shown in Finder" : "Couldn't open Finder";
```

becomes:

```js
        const manager = button.dataset.manager;  // the file manager's name, from the server
        button.textContent = answer.ok ? "Shown in " + manager : "Couldn't open " + manager;
```

In everyday-brave's `#switch` section, "any program on this Mac can reach your Brave" becomes "any program on
{{THIS_COMPUTER}} can reach your Brave". Then `grep -n "this Mac\|⌘" src/ai_browser/app/setup.html` must print
nothing.

`tests/conftest.py`, replace the body of `_no_finder_windows`:

```python
@pytest.fixture(autouse=True)
def _no_finder_windows(monkeypatch):
    """No test may open a file manager window on the machine running the suite (tests that check it patch it again)."""
    import ai_browser.app.run as run
    import ai_browser.app.server as server

    monkeypatch.setattr(run, "reveal", lambda path: True)
    monkeypatch.setattr(server, "reveal_folder", lambda path: True)
```

Then `grep -rn "reveal_in_finder" src tests` must print nothing.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_app_server.py -q -p no:randomly`
Expected: PASS.

Run: `uv run pytest tests/test_app_run.py::test_first_start_opens_the_setup_steps -q -p no:randomly`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py src/ai_browser/app/setup.html src/ai_browser/app/run.py tests/conftest.py \
  tests/test_app_server.py
git commit -m "Windows: the setup page names File Explorer and the address bar; /setup/reveal answers 501 when it can't"
```

(Also `git add` the test file holding everyday-brave's setup test, if it isn't `test_app_server.py`.)

---

### Task 17: The terminal steps in Windows words

**Files:**
- Modify: `src/ai_browser/app/run.py` (`READY`, `SETUP`, `BRAVE` become functions; their two uses)
- Test: `tests/test_app_run.py`

**Interfaces:**
- Consumes: `platforms.shortcut`, `platforms.file_manager`, `appbrowser.extension_path`.
- Produces: `run.ready_text(system: str | None = None) -> str`, `run.setup_text(folder: str, system: str | None =
  None) -> str` and `run.brave_text(folder: str, system: str | None = None) -> str`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app_run.py`:

```python
def test_the_terminal_steps_are_worded_for_each_computer():
    from ai_browser.app.run import brave_text, ready_text, setup_text

    folder, watcher = "C:\\Users\\me\\.ai-browser\\app\\extension", "C:\\Users\\me\\.ai-browser\\app\\watcher"
    windows = [ready_text("win32"), setup_text(folder, "win32"), brave_text(watcher, "win32")]
    assert "Ctrl+Shift+Y" in windows[0]
    assert all("⌘" not in text and "Finder" not in text for text in windows)
    assert "File Explorer" in windows[1] and "address bar" in windows[1] and folder in windows[1]
    assert "address bar" in windows[2] and watcher in windows[2] and "brave://extensions" in windows[2]
    mac = [ready_text("darwin"), setup_text("/x/extension", "darwin"), brave_text("/x/watcher", "darwin")]
    assert "⌘⇧Y" in mac[0] and "Finder" in mac[1] and "⌘⇧G" in mac[1] and "/x/extension" in mac[1]
    assert "⌘⇧G" in mac[2] and "/x/watcher" in mac[2]
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_app_run.py::test_the_terminal_steps_are_worded_for_each_computer -q -p no:randomly`
Expected: FAIL with `ImportError: cannot import name 'brave_text'`.

- [ ] **Step 3: Implement**

In `src/ai_browser/app/run.py`, replace the constants `READY`, `SETUP` and `BRAVE` with the three functions below.
If waves 1 and 2 changed any of their words, keep those words. Change only:
- `⌘⇧Y` becomes `{keys}`;
- "Finder" becomes `{manager}`;
- the `⌘⇧G` sentence becomes `{goto}`.

At the baseline they read:

```python
def _goto(folder: str, system: str | None) -> str:
    return platforms.shortcut(f"press ⌘⇧G, paste {folder} and press Enter",
                              f"click the address bar at the top of the folder window, paste {folder} and press Enter",
                              system)


def ready_text(system: str | None = None) -> str:
    keys = platforms.shortcut("⌘⇧Y", "Ctrl+Shift+Y", system)  # the manifest maps both
    return ("AI Browser is open: AI Home is the first tab (every agent, tab and skill). Click the AI Browser icon or "
            f"press {keys} to chat beside any page, or type ai and a space in the address bar.\n"
            "Press Ctrl-C here to close it.")


def setup_text(folder: str, system: str | None = None) -> str:
    manager = platforms.file_manager(system)
    return f"""AI Browser needs its extension, once ({manager} shows its folder):
  1. In the chrome://extensions tab, turn on Developer mode (top right).
  2. Drag the "extension" folder from {manager} onto that page.
     (Or click Load unpacked, {_goto(folder, system)}.)
  3. Pin the AI Browser icon from the puzzle-piece menu.
Already listed there but switched off? Switch it on. If Chrome asks about the new tab page, choose Keep it.
The setup tab says "All set" when it's done. Press Ctrl-C here to close AI Browser."""


def brave_text(folder: str, system: str | None = None) -> str:
    return f"""The Brain watches your messages (Gmail, Slack, Asana…) in Brave, through a small extension. Once:
  1. In Brave, open brave://extensions and turn on Developer mode (top right).
  2. Drag the "watcher" folder onto that page.
     (Or click Load unpacked, {_goto(folder, system)}.)
  3. Click the watcher's icon to open the Brain, and switch on the sites to watch.
It reads new messages in tabs you have open and never sends anything."""
```

In `_run`:
- `out(READY if installed else SETUP.format(folder=extension_path(folder)))` becomes
  `out(ready_text() if installed else setup_text(extension_path(folder)))`;
- `out(BRAVE.format(folder=server.watcher_folder))` becomes `out(brave_text(server.watcher_folder))`.

Then `grep -rn "READY if installed\|SETUP\.format\|BRAVE\.format\|run\.READY\|run\.SETUP\|run\.BRAVE" src tests`
must print nothing. Everyday-brave's `SWITCH` steps and `BRAVE_PROMPT`, and voice-input's `BRAVE` test constant, are
other names and stay.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_app_run.py::test_the_terminal_steps_are_worded_for_each_computer tests/test_app_run.py::test_first_start_opens_the_setup_steps -q -p no:randomly`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/run.py tests/test_app_run.py
git commit -m "Windows: the terminal steps say Ctrl+Shift+Y, File Explorer and the address bar"
```

---

### Task 18: No Mac words where Windows shows them

**Files:**
- Modify:
  - `src/ai_browser/engine.py` (`_status_text`), `src/ai_browser/browser.py` (`url_problem`);
  - `src/ai_browser/qa/report.py` (`summary`);
  - `src/ai_browser/app/extension/voice.js`, `mission.html`, `mission.js`, `worker.js`;
  - any other text the guard lists.
- Test: `tests/test_portable.py`, `tests/test_qa_report.py`, `tests/test_mission.py`

**Interfaces:**
- Consumes: `platforms.this_computer`.
- Produces:
  - `test_portable.MAC_ONLY`: a set of `(path relative to src/ai_browser, snippet)` for text that is shown only on
    macOS, picked by a platform value;
  - the Python texts say `platforms.this_computer()`;
  - the extension pages say "this computer".

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_portable.py`:

```python
MAC_ONLY = {
    ("platforms.py", "this Mac"),  # this_computer() itself
    # Add (path, snippet) here only for text shown when a platform value says macOS, for example voice-input's
    # macOS microphone lines chosen by hearing_status.platform == "mac".
}
PAGE_SUFFIXES = {".html", ".js", ".css", ".json", ".svg", ".txt", ".md"}


def _mac_only(path: Path, text: str) -> bool:
    relative = path.relative_to(SRC).as_posix()
    return any(relative == where and snippet in text for where, snippet in MAC_ONLY)


def _docstrings(tree: ast.AST) -> set[int]:
    return {id(node.body[0].value) for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body
            and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)}


def test_no_mac_words_where_windows_shows_them():
    found = []
    pages = [*(SRC / "app" / "extension").rglob("*"), *(SRC / "app" / "watcher").rglob("*"), SRC / "app" / "setup.html"]
    for path in sorted(pages):
        if path.is_file() and path.suffix in PAGE_SUFFIXES:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for word in ("this Mac", "⌘"):
                    if word in line and not _mac_only(path, line):
                        found.append(f"{path.relative_to(SRC).as_posix()}:{number}: {word}")
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstrings(tree)  # comments aren't in the tree; docstrings may keep "this Mac"
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip \
                    and "this Mac" in node.value and not _mac_only(path, node.value):
                found.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno}: this Mac")
    assert not found, "Mac-only words in text Windows shows:\n" + "\n".join(found)
```

Append to `tests/test_qa_report.py`:

```python
def test_the_summary_names_the_computer(tmp_path, monkeypatch):
    import sys

    work = WorkDir(tmp_path / "work", "t1")
    run = sample_run()
    paths = write_report(work, run)
    monkeypatch.setattr(sys, "platform", "win32")
    assert any(line.startswith("report: ") and "(on this PC: " in line for line in summary(run, paths).splitlines())
```

In `tests/test_mission.py`:
- rename `test_voice_is_off_by_default_and_needs_a_voice_on_this_mac` to
  `test_voice_is_off_by_default_and_needs_a_voice_on_this_computer`;
- its expectation `'No voice on this Mac'` becomes `'No voice on this computer'`;
- the comment `# only a voice that runs on this Mac` becomes `# only a voice that runs on this computer`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_portable.py::test_no_mac_words_where_windows_shows_them tests/test_qa_report.py::test_the_summary_names_the_computer -q -p no:randomly`
Expected: FAIL:
- the guard lists, among others, `engine.py` (the "on this Mac:" work-folder lines), `browser.py` (the local-file
  refusals), `qa/report.py:80`, `app/extension/voice.js` (lines 2 and 130), `mission.html:16`, `mission.js:445` and
  `worker.js:11` (`⌘`);
- the summary says "on this Mac".

- [ ] **Step 3: Implement**

Python. Add `from . import platforms` (`from .. import platforms` in `qa/report.py`), then:
- `engine.py`, `_status_text`: every `(on this Mac: {self.work.host_task}` becomes
  `(on {platforms.this_computer()}: {self.work.host_task}`. Everyday-brave rewrote this function, so do it wherever
  the guard points;
- `browser.py`, `url_problem`: both `"…pages would reach this Mac and Chrome's settings…"` strings become f-strings
  with `{platforms.this_computer()}` in place of `this Mac`. The docstring and the comment at
  `# Chrome reads it from this Mac later` stay;
- `qa/report.py`, `summary`: the report line becomes
  `lines.append(f"report: {paths.html} (on {platforms.this_computer()}: {paths.folder_host}/report.html)")`.

Pages. These files are the same on every OS, so their words become neutral:
- `app/extension/voice.js`:
  - line 2's comment: "voices that run on this Mac (localService)" becomes "voices that run on this computer
    (localService)";
  - `reason: "No voice on this Mac"` becomes `reason: "No voice on this computer"`;
- `app/extension/mission.html`: `title="Updates spoken aloud, with a voice that runs on this Mac only"` becomes
  `title="Updates spoken aloud, with a voice that runs on this computer only"`;
- `app/extension/mission.js`, `setVoice`'s comment: "only a voice that runs on this Mac" becomes "only a voice that
  runs on this computer";
- `app/extension/worker.js`: `// Clicking the toolbar icon (or pressing ⌘⇧Y) opens the chat in the side panel.`
  becomes `// Clicking the toolbar icon (or its shortcut, in manifest.json's "commands") opens the chat in the side panel.`

For each other line the guard lists (waves 1 and 2):
- if the text is shown only when a platform value says macOS (voice-input's `hearing_status.platform === "mac"`
  lines), add `(path, snippet)` to `MAC_ONLY`, with the snippet copied from that line;
- otherwise, say "this computer" in pages, use `platforms.this_computer()` in Python, and write a keyboard shortcut
  both ways or not at all.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_portable.py tests/test_qa_report.py -q -p no:randomly`
Expected: PASS.

Run: `uv run pytest tests/test_mission.py::test_voice_is_off_by_default_and_needs_a_voice_on_this_computer tests/test_chrome.py::test_chrome_mode_refuses_local_files_and_browser_pages -q -p no:randomly`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/engine.py src/ai_browser/browser.py src/ai_browser/qa/report.py \
  src/ai_browser/app/extension/voice.js src/ai_browser/app/extension/mission.html \
  src/ai_browser/app/extension/mission.js src/ai_browser/app/extension/worker.js tests/test_portable.py \
  tests/test_qa_report.py tests/test_mission.py
git commit -m "Windows: \"this computer\" in shared pages, this_computer() in Python texts, and a guard for both"
```

(Also `git add` any other file the guard made you change.)

---

### Task 19: The places that replace or delete files retry on Windows

**Files:**
- Modify:
  - `src/ai_browser/brain/store.py` (`_read`: the `.bad` rename);
  - `src/ai_browser/brain/workflows.py` (`delete`);
  - voice-input's `src/ai_browser/hearing/model.py` (the model swap).
- Test: `tests/test_brain_store.py`, `tests/test_workflows.py`, `tests/test_portable.py`

**Interfaces:**
- Consumes: `platforms.replace`, `platforms.unlink`, `platforms.rmtree`.
- Produces: no new names. These users now wait out a short hold on Windows:
  - the store's `.bad` rename;
  - deleting a workflow;
  - the voice model's swap of its `.part` folder.

(The watcher's stale files, `prepare_extension` and AI Browser's stale `DevToolsActivePort` already go through
`platforms`, since Tasks 7 and 12.)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_brain_store.py`:

```python
def test_a_damaged_file_is_set_aside_even_while_windows_holds_it(tmp_path, monkeypatch):
    from ai_browser import platforms
    from ai_browser.brain.store import BrainStore

    folder = tmp_path / "brain"
    folder.mkdir()
    (folder / "inbox.json").write_text("not json", encoding="utf-8")
    real, held = platforms.os.replace, []

    def busy_once(src, dst):
        if str(dst).endswith(".bad") and not held:  # only the rename that sets the damaged file aside
            held.append(src)
            raise PermissionError(13, "being scanned")
        real(src, dst)

    monkeypatch.setattr(platforms.os, "replace", busy_once)
    monkeypatch.setattr(platforms.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(platforms, "WINDOWS", True)  # only the retry loop changes: no Win32 call is made
    BrainStore(tmp_path)
    assert (folder / "inbox.json.bad").read_text(encoding="utf-8") == "not json"
```

Append to `tests/test_workflows.py`:

```python
def test_deleting_a_workflow_waits_out_a_short_hold(tmp_path, monkeypatch):
    from pathlib import Path

    from ai_browser import platforms
    from ai_browser.brain.workflows import WorkflowStore

    store = WorkflowStore(tmp_path)
    saved = store.save({"name": "Morning report", "instructions": "Check the inbox"})
    real, held = Path.unlink, []

    def busy_once(self, missing_ok=False):
        if not held:
            held.append(self)
            raise PermissionError(13, "open in an editor")
        return real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", busy_once)
    monkeypatch.setattr(platforms.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(platforms, "WINDOWS", True)
    store.delete(saved.slug)
    assert held and store.get(saved.slug) is None
```

Append to `tests/test_portable.py`:

```python
def test_the_voice_model_swap_goes_through_the_retrying_helpers():
    path = SRC / "hearing" / "model.py"
    if not path.exists():
        pytest.skip("voice input isn't in this checkout")
    calls = {ast.unparse(node.func) for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
             if isinstance(node, ast.Call)}
    assert {"platforms.rmtree", "platforms.replace"} <= calls  # Defender may hold a fresh file for a moment
    assert not calls & {"shutil.rmtree", "os.replace", "os.rename"}
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_brain_store.py::test_a_damaged_file_is_set_aside_even_while_windows_holds_it tests/test_workflows.py::test_deleting_a_workflow_waits_out_a_short_hold tests/test_portable.py::test_the_voice_model_swap_goes_through_the_retrying_helpers -q -p no:randomly`
Expected: FAIL:
- no `inbox.json.bad`, because the plain `os.replace` failed once and was swallowed;
- the workflow delete raises `PermissionError`;
- `hearing/model.py` calls `shutil.rmtree` and `os.replace`.

- [ ] **Step 3: Implement**

`src/ai_browser/brain/store.py`:
- add `from .. import platforms`;
- in `_read`, `os.replace(path, path.with_name(name + ".bad"))` becomes
  `platforms.replace(path, path.with_name(name + ".bad"))`. Keep its `contextlib.suppress(OSError)`.

`src/ai_browser/brain/workflows.py`:
- add `from .. import platforms`;
- `delete` becomes:

```python
    def delete(self, slug: str) -> None:
        platforms.unlink(self.path_of(slug), missing_ok=True)  # an editor may hold it a moment on Windows
```

`src/ai_browser/hearing/model.py` (voice-input's `ModelStore`):
- add `import contextlib` (unless it is there) and `from .. import platforms`;
- `remove_partial`'s body, `shutil.rmtree(self.part, ignore_errors=True)`, becomes:

```python
        with contextlib.suppress(OSError):  # missing already, or still held: the next download clears it
            platforms.rmtree(self.part)
```

- in `download`, the swap at the end of the `try`:

```python
            if self.folder.exists():  # only now, with every file checked, does the old folder go
                shutil.rmtree(self.folder)
            os.replace(self.part, self.folder)
```

  becomes:

```python
            if self.folder.exists():  # only now, with every file checked, does the old folder go
                platforms.rmtree(self.folder)
            platforms.replace(self.part, self.folder)  # Defender may hold a fresh file a moment on Windows
```

- if voice-input moved or renamed the folder anywhere else in that file (`os.rename`, `<path>.rename(…)`,
  `<path>.replace(…)`), make it `platforms.replace(<path>, <target>)` too. `shutil.disk_usage` stays.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_brain_store.py tests/test_portable.py tests/test_workflows.py::test_deleting_a_workflow_waits_out_a_short_hold tests/test_workflows.py::test_workflow_files_round_trip_and_bad_ones_are_reported -q -p no:randomly`
Expected: PASS.

Run voice-input's model tests: `uv run pytest tests/test_hearing.py -q -p no:randomly`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/brain/store.py src/ai_browser/brain/workflows.py src/ai_browser/hearing/model.py \
  tests/test_brain_store.py tests/test_workflows.py tests/test_portable.py
git commit -m "Windows: the .bad rename, workflow deletes and the voice model swap wait out a short hold"
```

---

### Task 20: The Claude desktop app's skills folder

**Files:**
- Modify: `src/ai_browser/engine.py` (`Engine.catalog`), `src/ai_browser/app/server.py` (`_skills`)
- Test: `tests/test_platforms.py`

**Interfaces:**
- Consumes: `platforms.claude_desktop_dir()`.
- Produces: the engine and AI Home look for claude.ai's synced skills in `platforms.claude_desktop_dir()`.
  `Catalog.discover` is unchanged and looks under it for `local-agent-mode-sessions/skills-plugin`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_platforms.py`:

```python
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
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_platforms.py::test_the_claude_ai_skills_come_from_the_desktop_apps_folder -q -p no:randomly`
Expected: FAIL: both look only in `~/Library/Application Support/Claude`.

- [ ] **Step 3: Implement**

`src/ai_browser/engine.py`, in the `catalog` property:
`Path.home() / "Library" / "Application Support" / "Claude",` becomes `platforms.claude_desktop_dir(),`.

`src/ai_browser/app/server.py`, in `_skills`:
`Path.home() / "Library" / "Application Support" / "Claude",` becomes `platforms.claude_desktop_dir(),`.

`platforms` is already imported in both files, since Tasks 4 and 16.

- [ ] **Step 4: Run it to see it pass**

Run: `uv run pytest tests/test_platforms.py tests/test_app_server.py::test_skills_for_the_dashboard -q -p no:randomly`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/engine.py src/ai_browser/app/server.py tests/test_platforms.py
git commit -m "Windows: claude.ai's synced skills come from %APPDATA%\\Claude there"
```

---

### Task 21: A ZIP copy still runs in Docker, Python 3.12 is pinned, and the repo is clean

**Files:**
- Modify: `docker/Dockerfile`
- Create: `.python-version`
- Test: `tests/test_portable.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `.python-version` containing `3.12`;
  - the Dockerfile strips `\r` from the two copied scripts;
  - `test_portable.test_repo_hygiene`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_portable.py`:

```python
def test_repo_hygiene():
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git isn't installed")
    inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT, capture_output=True,
                            encoding="utf-8")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        pytest.skip("not a git checkout")
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    tracked = [name for name in listing.decode("utf-8").split("\0") if name]
    personal = [name for name in tracked
                if PurePosixPath(name).name in {".mcp.json", ".DS_Store"} or PurePosixPath(name).name.startswith(".env")
                or name.endswith(".log") or name.split("/")[0] in {".venv", ".superpowers", ".pytest_cache", ".claude"}]
    assert not personal, f"personal or generated files are tracked: {personal}"
    home = str(Path.home()).encode("utf-8")
    leaking = []
    for name in tracked:
        try:
            data = (ROOT / name).read_bytes()
        except OSError:  # deleted, and not committed yet
            continue
        if b"\0" not in data and home in data:
            leaking.append(name)
    assert not leaking, f"tracked files name this computer's home folder ({Path.home()}): {leaking}"
    eol = subprocess.run(["git", "check-attr", "eol", "--", "docker/entrypoint.sh"], cwd=ROOT, capture_output=True,
                         encoding="utf-8", check=True).stdout
    assert eol.strip() == "docker/entrypoint.sh: eol: lf"
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12"
    dockerfile = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert r"RUN sed -i 's/\r$//' /usr/local/bin/aib-entrypoint /usr/local/bin/aib-cdp-proxy" in dockerfile
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_portable.py::test_repo_hygiene -q -p no:randomly`
Expected: FAIL with `FileNotFoundError` for `.python-version`.

- [ ] **Step 3: Implement**

Create `.python-version`:

```
3.12
```

`uv.lock` has no Python 3.15 Windows wheels for `pydantic-core` or `pyyaml`, so a fresh laptop must not pick the
newest Python. `requires-python` stays `>=3.12`.

`docker/Dockerfile`: right after the two `COPY` lines, before `RUN chmod 755 …`, add:

```dockerfile
RUN sed -i 's/\r$//' /usr/local/bin/aib-entrypoint /usr/local/bin/aib-cdp-proxy
```

`.gitattributes` already checks these out with LF. This line covers a copy made without git (a ZIP). The next
`ai-browser build` picks it up; the Mac needs no rebuild now.

If the hygiene test lists tracked files that contain this computer's home folder (for example a plan written with
absolute paths under `docs/`), replace that path with `~` or with a path relative to the repo, and `git add` those
files with this task.

- [ ] **Step 4: Run it to see it pass**

Run: `uv run pytest tests/test_portable.py::test_repo_hygiene -q -p no:randomly`
Expected: PASS.

First check, without running uv: `grep version_info .venv/pyvenv.cfg` must say `3.12.x`. If it doesn't, stop and
report: uv would fetch a Python, and this plan downloads nothing without the user's OK.

Run: `uv run python --version`
Expected: `Python 3.12.x`, with nothing downloaded (the `.venv` is already 3.12).

- [ ] **Step 5: Commit**

```bash
git add .python-version docker/Dockerfile tests/test_portable.py
git commit -m "Windows: pin Python 3.12, strip CR from the sandbox scripts, and a repo hygiene guard"
```

---

### Task 22: The other four sub-projects: the taskbar line, and the last two guards

**Files:**
- Modify: safe-browsing's `src/ai_browser/render.py` (`render_check`, where the hand-off text lives) and
  `src/ai_browser/checks.py` (`CheckGate.handoff`, which calls it)
- Modify: safe-browsing's `tests/test_render.py` (`test_the_hand_off_has_nothing_to_click`) and
  `tests/test_checks_browser.py` (`test_in_the_sandbox_the_hand_off_gives_the_live_view`)
- Modify: any file guard 3 lists
- Test: `tests/test_portable.py`

**Interfaces:**
- Consumes:
  - safe-browsing's `checks.Check(kind, site)`, `render.render_check(check, tab_key, live_url=None)` and the static
    `CheckGate.handoff(check, tab_key, live_url=None)`, which returns `render_check(...)`;
  - `uv.lock`;
  - `packaging.markers` (pytest brings it).
- Produces:
  - `render.TASKBAR`;
  - `render_check(check, tab_key, live_url=None, system: str | None = None)` and
    `CheckGate.handoff(check, tab_key, live_url=None, system: str | None = None)`. On Windows, "The tab is now in
    front." gains " (if its window didn't come up, look for it in the taskbar)". Every caller passes no `system`, so
    the computer it runs on decides;
  - guard 3, `test_no_macos_paths_outside_platforms`;
  - guard 6, `test_voice_extra_has_windows_wheels`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_portable.py`:

```python
def test_the_hand_off_says_where_to_look_on_windows():
    from ai_browser.checks import Check, CheckGate
    from ai_browser.render import render_check

    check = Check("google", "www.google.com")
    windows = CheckGate.handoff(check, "t2", None, system="win32")
    mac = CheckGate.handoff(check, "t2", None, system="darwin")
    assert windows.splitlines()[2] == "The tab is now in front. (if its window didn't come up, look for it in the taskbar)"
    assert mac.splitlines()[2] == "The tab is now in front."
    live = render_check(check, "t2", "http://127.0.0.1:8770/live?token=abc", system="win32")
    assert live.splitlines()[2] == ("The tab is now in front. (if its window didn't come up, look for it in the "
                                    "taskbar) The user can solve it in the live view: http://127.0.0.1:8770/live?token=abc")


def test_no_macos_paths_outside_platforms():
    pattern = re.compile(r'Application Support|/Applications/|"open", "-R"|os\.kill\(\s*[^,()]+,\s*0\s*\)')
    found = [f"{path.relative_to(SRC).as_posix()}:{number}: {line.strip()}"
             for path in sorted(SRC.rglob("*.py")) if path != SRC / "platforms.py"
             for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if pattern.search(line)]
    assert not found, "macOS-only paths, or a liveness probe, outside platforms.py:\n" + "\n".join(found)


WINDOWS_312 = {"implementation_name": "cpython", "implementation_version": "3.12.10", "os_name": "nt",
               "platform_machine": "AMD64", "platform_python_implementation": "CPython", "platform_release": "10",
               "platform_system": "Windows", "platform_version": "10.0.26100", "python_full_version": "3.12.10",
               "python_version": "3.12", "sys_platform": "win32", "extra": ""}


def _windows_wheel(url: str) -> bool:
    name = url.rsplit("/", 1)[-1].split("#", 1)[0]
    if not name.endswith(".whl"):
        return False
    python, abi, platform = name[:-4].split("-")[-3:]
    if platform == "any":
        return True
    return "win_amd64" in platform.split(".") and ("cp312" in python.split(".") or abi in ("abi3", "none"))


def test_voice_extra_has_windows_wheels():
    import tomllib

    from packaging.markers import Marker

    packages = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8")).get("package", [])
    if not any(package["name"] == "faster-whisper" for package in packages):
        pytest.skip("uv.lock has no voice extra (faster-whisper): the user hasn't chosen to install it")
    by_name: dict[str, list] = {}
    for package in packages:
        by_name.setdefault(package["name"], []).append(package)
    root = next(package for package in packages if package["name"] == "ai-browser")

    def applies(dependency) -> bool:  # left out when its marker is false for 64-bit Windows and CPython 3.12
        return "marker" not in dependency or Marker(dependency["marker"]).evaluate(WINDOWS_312)

    def find(dependency):
        found = by_name.get(dependency["name"], [])
        if "version" in dependency:
            found = [package for package in found if package["version"] == dependency["version"]] or found
        return found[0] if found else None

    todo = [dependency for dependency in root.get("optional-dependencies", {}).get("voice", []) if applies(dependency)]
    seen, missing = set(), []
    while todo:
        dependency = todo.pop()
        package = find(dependency)
        if package is None:
            missing.append(f"{dependency['name']} (not in uv.lock)")
            continue
        extras = tuple(dependency.get("extra", ()))
        key = (package["name"], package.get("version"), extras)
        if key in seen:
            continue
        seen.add(key)
        if not any(_windows_wheel(wheel["url"]) for wheel in package.get("wheels", [])):
            missing.append(f"{package['name']} {package.get('version', '')}")
        todo += [dep for dep in package.get("dependencies", []) if applies(dep)]
        for extra in extras:
            todo += [dep for dep in package.get("optional-dependencies", {}).get(extra, []) if applies(dep)]
    assert not missing, "no Windows (win_amd64, cp312) or pure wheel for: " + ", ".join(sorted(set(missing)))
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_portable.py -k "hand_off or macos_paths or windows_wheels" -q -p no:randomly`
Expected: FAIL in `test_the_hand_off_says_where_to_look_on_windows`, with `TypeError: CheckGate.handoff() got an
unexpected keyword argument 'system'`.
- Guard 3 may already pass after Tasks 4, 10, 16 and 20. If it lists lines from waves 1 and 2, fix them in Step 3.
- Guard 6 skips unless the user chose the voice extra (`uv lock` with it).

- [ ] **Step 3: Implement**

`src/ai_browser/render.py`:
- add `import sys` to the imports and, near the top:

```python
TASKBAR = " (if its window didn't come up, look for it in the taskbar)"  # Windows' focus rules may only flash it
```

- in `render_check`, add the parameter `system: str | None = None` after `live_url`, and right after
  `front = "The tab is now in front."` add:

```python
    if (system or sys.platform) == "win32":
        front += TASKBAR
```

  Everything else in the hand-off stays word for word: it is safe-browsing's.

`src/ai_browser/checks.py`, `CheckGate.handoff` becomes:

```python
    @staticmethod
    def handoff(check: Check, tab_key: str, live_url: str | None = None, system: str | None = None) -> str:
        return render_check(check, tab_key, live_url, system)
```

`tests/test_render.py`, `test_the_hand_off_has_nothing_to_click` compares the text exactly. To keep it exact on every
OS, its two `render_check(...)` calls pass `system="darwin"`:
- `render_check(Check("google", "www.google.com"), "t2", system="darwin")`;
- `render_check(Check("captcha", "shop.example.com"), "t3", "http://127.0.0.1:8770/live?token=abc", system="darwin")`.

`tests/test_checks_browser.py`, safe-browsing's `test_in_the_sandbox_the_hand_off_gives_the_live_view` (no Chrome, no
pipe fixture, so it runs on `windows-latest`) asserts one literal that the taskbar words split on Windows:

```python
    assert "The tab is now in front. The user can solve it in the live view: http://127.0.0.1:8770/live?token=abc" in text
```

Replace that line with:

```python
    assert "The tab is now in front." in text  # on Windows the taskbar words follow it
    assert "The user can solve it in the live view: http://127.0.0.1:8770/live?token=abc" in text
```

Then `grep -rn "now in front" tests` lists only `test_render.py` (with `system="darwin"`), this file's two lines,
and `test_portable.py`. Any other test that compares the hand-off with a literal gets the same treatment; the ones
that compare against `render_check(...)` or `CheckGate.handoff(...)` computed on the same computer hold on Windows
as they are.

Every line guard 3 lists:
- a macOS folder or install path: take it from `platforms` (`user_data_dir`, `browser_candidates`,
  `claude_desktop_dir`);
- an `os.kill(<pid>, 0)`: use `platforms.pid_alive(<pid>)`;
- a comment or docstring naming a macOS path: reword it ("the browser's profile folder"), since the guard reads
  the text.

If guard 6 fails, stop here. Report to the main session which packages lack Windows wheels: the README must then say
voice can't be installed on Windows yet. Nothing is built from source.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_portable.py -q -p no:randomly`
Expected: PASS (guard 6 skipped, or passed).

Run safe-browsing's tests of the hand-off: `uv run pytest tests/test_checks.py tests/test_render.py tests/test_checks_browser.py::test_in_the_sandbox_the_hand_off_gives_the_live_view -q -p no:randomly`.
Expected: PASS: on the Mac, the hand-off text is unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/render.py src/ai_browser/checks.py tests/test_render.py tests/test_checks_browser.py \
  tests/test_portable.py
git commit -m "Windows: the bot-check hand-off points to the taskbar; guards for macOS paths and voice wheels"
```

(Also `git add` any file guard 3 made you change.)

---

### Task 23: `ai-browser doctor --setup`, and a console that prints ✓ anywhere

**Files:**
- Modify: `src/ai_browser/cli.py` (`main`; new `_utf8_console`, `_first_free`, `_doctor_setup`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes:
  - `claudecli.claude_argv` and `ClaudeNotUsable`;
  - `chrome.chrome_binary` and `brave_binary`;
  - everyday-brave's `chrome.own_browser_dir`, `browser_name`, `inspect_address` and `switch_on`;
  - `app.server.APP_PORTS`, `config.LIVE_PORTS` and `live._bind`.
- Produces:
  - `ai-browser doctor --setup`: no Docker, and no DevTools connection;
  - it exits 1 when Python, Claude Code or Chrome fails;
  - `cli._utf8_console()`, run for every command except `mcp`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def _browser_port_stand_in():
    """A local socket in place of a browser's debugging port: it records each connection and the bytes sent."""
    import socket
    import threading

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    seen = {"connections": 0, "bytes": b""}

    def serve():
        while True:
            try:
                connection, _ = server.accept()
            except OSError:
                return
            with connection:
                seen["connections"] += 1
                connection.settimeout(1)
                try:
                    while chunk := connection.recv(1024):
                        seen["bytes"] += chunk
                except OSError:
                    pass

    threading.Thread(target=serve, daemon=True).start()
    return server, seen


def _setup_env(tmp_path, monkeypatch, port) -> dict:
    claude, chrome, profile = tmp_path / "claude-bin", tmp_path / "chrome-bin", tmp_path / "everyday"
    claude.write_bytes(b"")
    chrome.write_bytes(b"")
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text(f"{port}\n/devtools/browser/x\n", encoding="utf-8")
    env = {"AIB_CLAUDE": str(claude), "AIB_CHROME_BINARY": str(chrome), "AIB_CHROME_DIR": str(profile)}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


def test_doctor_setup_checks_without_docker_or_a_browser_connection(tmp_path, monkeypatch, capsys):
    import time

    server, seen = _browser_port_stand_in()
    try:
        _setup_env(tmp_path, monkeypatch, server.getsockname()[1])
        code = main(["doctor", "--setup"])
        for _ in range(20):
            if seen["connections"]:
                break
            time.sleep(0.1)
    finally:
        server.close()
    out = capsys.readouterr().out
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("✓ Python      3.")
    assert lines[1] == f"✓ Claude Code {tmp_path / 'claude-bin'}"
    assert lines[2] == f"✓ Chrome      {tmp_path / 'chrome-bin'}"
    assert lines[3].startswith(("✓ Brave", "- Brave"))  # information only
    assert lines[4].startswith("✓ everyday") and "remote debugging is on" in lines[4]
    assert lines[5] == "✓ ports       app 8792-8811 and live view 8770-8790 have free ports"
    assert lines[6] == "- Docker      not checked here: run `uv run ai-browser doctor`"
    assert lines[-1] == "all good"
    assert seen["connections"] >= 1 and seen["bytes"] == b""  # a TCP check only: no DevTools request, so no Allow


def test_doctor_setup_fails_without_claude_code_or_chrome(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AIB_CLAUDE", str(tmp_path / "no-claude"))
    monkeypatch.setenv("AIB_CHROME_BINARY", str(tmp_path / "no-chrome"))
    assert main(["doctor", "--setup"]) == 1
    out = capsys.readouterr().out
    assert "✗ Claude Code" in out and "✗ Chrome" in out and "AIB_CHROME_BINARY" in out
    assert out.splitlines()[-1] == "some checks failed"


def test_doctor_setup_prints_its_marks_on_any_console(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    server, _ = _browser_port_stand_in()
    try:
        _setup_env(tmp_path, monkeypatch, server.getsockname()[1])
        env = {**os.environ, "PYTHONIOENCODING": "ascii"}  # a console or file that can't hold ✓, as cp1252 can't
        env.pop("PYTHONUTF8", None)
        result = subprocess.run([sys.executable, "-m", "ai_browser.cli", "doctor", "--setup"], env=env,
                                capture_output=True, timeout=60)
    finally:
        server.close()
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "✓ Python" in result.stdout.decode("utf-8")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_cli.py -k doctor_setup -q -p no:randomly`
Expected: FAIL. argparse exits with code 2 (`unrecognized arguments: --setup`).

- [ ] **Step 3: Implement**

In `src/ai_browser/cli.py`:
- add `import contextlib` and `from pathlib import Path` to the imports;
- after the `doctor` parser's other arguments (everyday-brave's `--own`/`--chrome`), add:

```python
    doctor.add_argument("--setup", action="store_true",
                        help="check what `ai-browser app` needs, without Docker and without connecting to a browser")
```

- right after `args = parser.parse_args(argv)`, add:

```python
    if args.command != "mcp":  # the mcp library writes its own UTF-8 stream
        _utf8_console()
```

- in the `if args.command == "doctor":` branch, before its `asyncio.run(...)`, add:

```python
            if args.setup:
                return _doctor_setup()
```

- add these functions after `_elapsed`:

```python
def _utf8_console() -> None:
    """✓ and ✗ print on any console and into files (`doctor > log.txt`): Windows' code page can't encode them."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError, OSError):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _first_free(ports: range) -> int | None:
    from .live import _bind

    for port in ports:
        sock = _bind("127.0.0.1", port)
        if sock is not None:
            sock.close()
            return port
    return None


def _doctor_setup() -> int:
    """What `ai-browser app` needs, checked without Docker and without opening a DevTools connection, so no browser
    asks Allow. Python, Claude Code and Chrome must pass; the rest is information."""
    import platform

    from .app.server import APP_PORTS
    from .chrome import brave_binary, browser_name, chrome_binary, inspect_address, own_browser_dir, switch_on
    from .claudecli import ClaudeNotUsable, claude_argv
    from .config import LIVE_PORTS

    failed = False

    def report(mark: str, label: str, detail: str, required: bool = False) -> None:
        nonlocal failed
        failed |= required and mark == "✗"
        print(f"{mark} {label:<11} {detail}")

    version = platform.python_version()
    if sys.version_info >= (3, 12):
        report("✓", "Python", version, True)
    else:
        report("✗", "Python", f"{version}: ai-browser needs 3.12 or newer (`uv sync` installs it)", True)
    try:
        claude = claude_argv()[0]
    except ClaudeNotUsable as exc:  # an npm claude.cmd on Windows: its message says what to do
        report("✗", "Claude Code", str(exc), True)
    else:
        if Path(claude).is_file():
            report("✓", "Claude Code", claude, True)
        else:
            report("✗", "Claude Code", f"not found ({claude}): install Claude Code, then sign in once with `claude`",
                   True)
    chrome = chrome_binary()
    if chrome and Path(chrome).is_file():
        report("✓", "Chrome", chrome, True)
    else:
        found = f"{chrome} doesn't exist" if chrome else "not found"
        report("✗", "Chrome", f"{found}: install Google Chrome, or set AIB_CHROME_BINARY to the full path of chrome",
               True)
    brave = brave_binary()
    report("✓" if brave else "-", "Brave", brave or "not installed (optional: the Brain's watcher and your everyday "
                                                    "browser use it)")
    folder = own_browser_dir()
    name = browser_name(folder)
    if not folder.is_dir():
        report("-", "everyday", f"{name}: no profile folder at {folder}")
    elif switch_on(folder):  # a TCP check of DevToolsActivePort's port: no DevTools session, so no Allow question
        report("✓", "everyday", f"{name}: profile folder found; remote debugging is on")
    else:
        report("-", "everyday", f"{name}: profile folder found; remote debugging is off ({inspect_address(folder)})")
    ranges = f"app {APP_PORTS.start}-{APP_PORTS.stop - 1} and live view {LIVE_PORTS.start}-{LIVE_PORTS.stop - 1}"
    if _first_free(APP_PORTS) and _first_free(LIVE_PORTS):
        report("✓", "ports", f"{ranges} have free ports")
    else:
        report("✗", "ports", f"no free port in {ranges}: see \"no free port\" in the README")
    report("-", "Docker", "not checked here: run `uv run ai-browser doctor`")
    print("some checks failed" if failed else "all good")
    return 1 if failed else 0
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_cli.py -q -p no:randomly`
Expected: PASS (the Docker tests skip themselves without Docker).

Run it by hand, pointed at an empty folder so that it doesn't even make its TCP check of the user's Brave (this plan
never connects to the user's browsers):
`mkdir -p "$TMPDIR/aib-no-browser" && AIB_CHROME_DIR="$TMPDIR/aib-no-browser" uv run ai-browser doctor --setup`
Expected: the seven lines and `all good`. The `everyday` line says `- everyday    Chrome: profile folder found; remote
debugging is off (chrome://inspect/#remote-debugging)`, and the Brave line only says whether Brave is installed.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/cli.py tests/test_cli.py
git commit -m "Windows: doctor --setup checks Python, Claude Code, Chrome, Brave, the everyday folder and ports; UTF-8 console"
```

---

### Task 24: The CI workflow, run by hand

**Files:**
- Create: `.github/workflows/tests.yml`
- Test: `tests/test_portable.py`

**Interfaces:**
- Consumes: nothing.
- Produces: one workflow, **tests**:
  - its only trigger is `workflow_dispatch`, with the inputs `os` (`windows` by default, `macos` or `both`) and
    `voice` (boolean);
  - `permissions: contents: read`;
  - each action is pinned to a full commit SHA, with the release tag in a comment.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_portable.py`:

```python
def test_the_ci_workflow_runs_only_by_hand():
    import yaml

    text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    triggers = workflow[True]  # PyYAML reads the `on:` key as True
    assert list(triggers) == ["workflow_dispatch"]  # never on a push, a pull request or a schedule
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert inputs["os"]["options"] == ["windows", "macos", "both"] and inputs["os"]["default"] == "windows"
    assert inputs["voice"]["type"] == "boolean" and inputs["voice"]["default"] is False
    assert workflow["permissions"] == {"contents": "read"}
    assert "windows-latest" in text and "macos-latest" in text
    job = workflow["jobs"]["test"]
    assert job["strategy"]["fail-fast"] is False and job["timeout-minutes"] == 40
    runs = [step.get("run", "") for step in job["steps"]]
    assert any(run.startswith("uv sync --locked") for run in runs)
    assert any(run.startswith("uv run --no-sync pytest") for run in runs)
    assert "secrets." not in text and "PYTHONUTF8" not in text  # no secrets; Windows' own encoding is what's tested
    uses = [step["uses"] for step in job["steps"] if "uses" in step]
    assert [use.split("@")[0] for use in uses] == ["actions/checkout", "astral-sh/setup-uv", "actions/upload-artifact"]
    assert all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", use) for use in uses), uses
    assert len(re.findall(r"uses: \S+@[0-9a-f]{40} +# v\d", text)) == 3  # each pin names its release
    upload = job["steps"][-1]
    assert upload["if"] == "always()" and upload["with"]["path"] == "pytest.xml"
    assert upload["with"]["retention-days"] == 7
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_portable.py::test_the_ci_workflow_runs_only_by_hand -q -p no:randomly`
Expected: FAIL with `FileNotFoundError` for `.github/workflows/tests.yml`.

- [ ] **Step 3: Implement**

Read each action's latest release and the commit SHA its tag points to. This reads public data only:

```bash
for action in actions/checkout astral-sh/setup-uv actions/upload-artifact; do
  tag=$(gh release view --repo "$action" --json tagName --jq .tagName)
  echo "$action $tag $(gh api "repos/$action/commits/$tag" --jq .sha)"
done
```

If `gh` isn't signed in on this machine, read the same data with git:
`git ls-remote https://github.com/<action> "refs/tags/<tag>^{}" "refs/tags/<tag>"`. The `^{}` line, when present,
is the commit.

Create `.github/workflows/tests.yml`:
- put each 40-character SHA in place of `<sha>`, and its tag (for example `v5.0.0`) in place of `vN` in the comment;
- the upload step's `with:` is written as a block, because `${{ … }}` inside a one-line `{ … }` map isn't valid YAML.

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
      - uses: actions/checkout@<sha>  # vN
      - uses: astral-sh/setup-uv@<sha>  # vN
      - run: uv sync --locked ${{ inputs.voice && '--extra voice' || '' }}
      - if: inputs.voice
        run: uv run --no-sync python -c "import faster_whisper"
      - run: uv run --no-sync pytest -q --junitxml=pytest.xml
      - if: always()
        uses: actions/upload-artifact@<sha>  # vN
        with:
          name: pytest-${{ matrix.os }}
          path: pytest.xml
          retention-days: 7
```

`--no-sync` makes the test steps use exactly what the sync step installed, the voice extra included. The workflow
never runs by itself; it uses the user's Actions minutes only when they click **Run workflow**.

- [ ] **Step 4: Run it to see it pass**

Run: `uv run pytest tests/test_portable.py::test_the_ci_workflow_runs_only_by_hand -q -p no:randomly`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/tests.yml tests/test_portable.py
git commit -m "Windows: a tests workflow on GitHub Actions that runs only by hand (windows, macos or both)"
```

---

### Task 25: The README's Windows section, then the whole suite and the bench

**Files:**
- Modify: `README.md`
- Test: `tests/test_portable.py`

**Interfaces:**
- Consumes: every earlier task.
- Produces: the README's **Windows** section, its troubleshooting, the two `.mcp.json` fixes, the Brave example's
  Windows line, `doctor --setup` in **Commands**, and how to run the workflow.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_portable.py`:

```python
def test_the_readme_has_the_windows_steps():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for needed in ("## Windows", "winget install --id astral-sh.uv -e", "irm https://claude.ai/install.ps1 | iex",
                   "gh auth login", "git clone https://github.com/nanotechs001/ai-browser.git C:\\dev\\ai-browser",
                   "uv run ai-browser doctor --setup", "-e PYTHONUTF8=1", "%USERPROFILE%\\.ai-browser\\app\\watcher",
                   "brave://inspect/#remote-debugging", "any program on this PC can reach your Brave", "wsl --install",
                   "uv sync --extra voice", "netsh interface ipv4 show excludedportrange protocol=tcp", "AIB_CLAUDE",
                   "AIB_CHROME_BINARY", "$env:USERPROFILE", "Run workflow", ".mcp.json.example"):
        assert needed in text, needed
    assert "This folder has a `.mcp.json`" not in text and "This repo's `.mcp.json`" not in text
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_portable.py::test_the_readme_has_the_windows_steps -q -p no:randomly`
Expected: FAIL on `## Windows`.

- [ ] **Step 3: Implement**

In `README.md`:

1. In **Use it from Claude Code**, the sentence "This folder has a `.mcp.json`. Open Claude Code in this folder and
   approve the **ai-browser** server when asked; its tools then appear in every chat here. To use it from any folder:"
   becomes:

   > Copy `.mcp.json.example` to `.mcp.json` and put this folder's path in it (git ignores your copy). Then open
   > Claude Code in this folder and approve the **ai-browser** server when asked; its tools then appear in every chat
   > here. To use it from any folder:

2. The own-browser section. Everyday-brave replaced the baseline's whole `## Use your own Chrome` section (with its
   "This repo's `.mcp.json` already does that…" sentence and its `AIB_CHROME_DIR=… doctor --chrome` example) with
   `## Use your everyday Brave (the default)`, which ends with the paragraph "Google Chrome works the same way
   (`chrome://inspect/#remote-debugging`). The folder is found by itself, Brave first; set `AIB_CHROME_DIR` to pick
   one. Turn the switch on in one browser only."
   - if a "This repo's `.mcp.json`" sentence is still anywhere in the README, it becomes "Your `.mcp.json` (copied
     from `.mcp.json.example`) can do that for the MCP server too:";
   - right after that last paragraph of the section, add the Windows line (the spec's "Brave example gains its
     Windows line"):

   ````markdown
   On Windows ai-browser finds Brave's folder (`%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data`) by itself. To
   pick one in PowerShell:

   ```powershell
   $env:AIB_CHROME_DIR = "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\User Data"; uv run ai-browser doctor --own
   ```
   ````

3. In **Commands**, add this line after the `doctor` line (everyday-brave's `doctor [--own]`):

   ```bash
   uv run ai-browser doctor --setup     # quick check, no Docker: Python, Claude Code, Chrome, Brave, ports
   ```

4. In **Development**, add after its code block:

   ```markdown
   **Tests on Windows (GitHub):** the private repo's Actions tab has one workflow, **tests**. It runs only when you
   click **Run workflow**, never on a push. Pick `windows` (the default), `macos` or `both`; tick **voice** to also
   install the voice extra (no model is downloaded). It uses your Actions minutes only then: Windows and macOS minutes
   cost more than Linux ones, macOS the most. The test report is kept for 7 days, inside the private repo. Tests that
   need macOS or Linux (the DevTools pipe) show as skipped, with that reason.
   ```

5. Add this section right after **Setup**, before **Use it from Claude Code**:

````markdown
## Windows

ai-browser runs natively on Windows 10 (22H2) and Windows 11, 64-bit. In PowerShell:

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
2. **Sign in, yourself:** `gh auth login`, for the private repo, and `claude` once, to log in to Claude Code in the
   browser. Nothing here asks for a password or a token in a file.
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
   - Drag that folder onto the page, or click **Load unpacked** and paste the path into the address bar at the top
     of the folder window.
   - The page then says **All set**. The chat shortcut is **Ctrl+Shift+Y**.
   - **Google sign-in:** sites can see that AI Browser is automated, and Google refuses to sign in there. For Google
     work, use your everyday Brave (step 6), chosen before the task.
6. **Brave, once, after step 5** (the first `ai-browser app` makes the watcher's folder):
   - open `brave://extensions`, turn on **Developer mode**, click **Load unpacked** and pick
     `%USERPROFILE%\.ai-browser\app\watcher`;
   - for the everyday-Brave mode, open `brave://inspect/#remote-debugging` and tick **Allow remote debugging for this
     browser instance**. While the switch is on, any program on this PC can reach your Brave, so untick it when
     agents aren't working.
7. **Optional, for the sandbox and the shell tool:**
   - run `wsl --install` and reboot;
   - run `winget install --id Docker.DockerDesktop -e`;
   - start Docker Desktop (WSL 2 backend, Linux containers);
   - then run `uv run ai-browser build` and `uv run ai-browser doctor`.

   The work folder lives on NTFS, so it is slower and case-insensitive (`Report.html` and `report.html` are one
   file), and names Windows can't hold (`CON`, `a:b`, `x?`) are refused with a plain message.
8. **Optional, for voice input:**
   - run `uv sync --extra voice` (the speech packages; plain `uv sync` removes them again, so keep the flag);
   - allow desktop apps to use the microphone (Settings → Privacy & security → Microphone);
   - the voice model itself (148 MB, the size the **Download** button shows; the "about 142 MB" quoted when you chose
     it is the same files counted in MiB) is downloaded from inside the app, only after you click **Download**.

   On Windows on Arm the speech packages can't install: Voice Access (Windows 11) works instead.

**Troubleshooting:**
- **"no free port":** Hyper-V or Docker may have reserved the port range.
  `netsh interface ipv4 show excludedportrange protocol=tcp` shows the reserved ranges.
- **"Claude Code was found at …claude.cmd":** install the native Claude Code (step 1), or set `AIB_CLAUDE` to the
  full path of `claude.exe`.
- **Chrome in an unusual place:** set `AIB_CHROME_BINARY` to the full path of `chrome.exe`.
- **`~` in PowerShell:** native programs don't expand it. Use `$HOME` or `$env:USERPROFILE`.
- **Files that hold tokens** (the extension's `config.json`, each agent's `mcp.json`, `link.json`) keep Windows'
  per-user permissions on your folder: you, SYSTEM and Administrators.
- **Running inside WSL2** works with the Linux code, but needs Linux Chrome and Brave inside WSL.
````

- [ ] **Step 4: Run it, then everything, to see it pass**

Run: `uv run pytest tests/test_portable.py -q -p no:randomly`
Expected: PASS.

Run the whole suite, writing its output to a file and printing only the tail:
`uv run pytest -q -p no:randomly > /tmp/aib-wave3-suite.txt 2>&1; tail -30 /tmp/aib-wave3-suite.txt`
Expected:
- every test passes;
- the `windows_only` tests are skipped with "Windows behaviour (junctions, msvcrt, Win32 APIs)";
- the Docker tests run, or skip with their reason if Docker isn't running.

Run: `uv run ai-browser bench`
Expected: every row `PASS`, as before this plan. It needs Docker and the sandbox image. If Docker isn't running, say
so in your report, and don't count it as a failure of this plan.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_portable.py
git commit -m "Windows: the README's Windows steps, troubleshooting, and the manual tests workflow"
```

---

## After Task 25: the repo (main session only)

The implementer stops at Task 25. The main session does this (spec, Decision 17), in this order. Nothing is pushed
until the user's yes in chat.

1. **Checks.** If any fails, stop and report:
   - `git status --porcelain` prints nothing;
   - `uv run pytest tests/test_portable.py -q -p no:randomly` passes, the hygiene test included;
   - `gh auth status` shows the account `nanotechs001`;
   - `gh repo view nanotechs001/ai-browser` fails, so the name is free. If it is taken, ask the user for another.
2. **Show what would go up:**
   - the number of tracked files and their top folders (`git ls-files | cut -d/ -f1 | sort | uniq -c`);
   - the commit author's name and email (`git log -1 --format='%an <%ae>'`), which every commit carries. If GitHub's
     "Block command line pushes that expose my email" is on, the push is refused with GH007, and the user decides
     then;
   - the flagged items:
     - `docs/google-flights-cgy-mnl.jpg`: a signed-out Google Flights search, CGY → MNL, one adult, 16 October;
     - the same route named in the own-Chrome spec and plan.
3. **Ask, plainly:**
   - "Create a **private** GitHub repo `nanotechs001/ai-browser` and push the code?"
   - "The flights screenshot `docs/google-flights-cgy-mnl.jpg` shows your CGY → MNL search. Keep it, remove it, or
     remove it from the history too?"

   The two ways to remove it:
   - **from the repo:** `git rm --cached docs/google-flights-cgy-mnl.jpg`, a `.gitignore` line for it, and a commit.
     The file stays on the Mac;
   - **from the history too:**
     - first `git filter-branch --index-filter 'git rm --cached --ignore-unmatch docs/google-flights-cgy-mnl.jpg'
       -- --all`;
     - then the `.gitignore` line;
     - then delete `refs/original/`, expire the reflog, and run `git gc --prune=now`.

     This is safe only because nothing was pushed yet. The file on disk stays.
4. **Only after a clear yes:**
   ```bash
   gh repo create nanotechs001/ai-browser --private --source=. --remote=origin --push \
     --description "AI Browser: a Claude-driven browser, the Brain and Mission Control"
   gh repo view nanotechs001/ai-browser --json visibility,url   # must say PRIVATE
   ```
   If the visibility isn't `PRIVATE`, tell the user at once.
5. **Nothing else:** no secrets, deploy keys, Pages, webhooks or collaborators. The workflow runs only when the user
   clicks **Run workflow**.

Then the user's manual Windows check, from the spec's Testing section:
- `doctor --setup` is all ✓;
- **All set** after Load unpacked, which proves the Windows extension ID;
- the watcher connects in Brave, with no mismatch line;
- the everyday-Brave tab groups;
- an agent task, then Ctrl-C leaves no `claude.exe` and no `ai_browser.cli mcp` in Task Manager;
- optional: Docker with `doctor`, and a refused link the sandbox made;
- the claude.ai skills;
- mission-visuals' performance pass and voice input.
