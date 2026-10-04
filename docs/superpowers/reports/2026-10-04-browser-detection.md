# Finding your browsers and their profiles (browser detection): report

Date: 2026-10-04.

You asked: "the app should be able to ask and ask which browser it would connect and control there should be a setting
on that because sometimes i open multiple browser profile or even use a chrome instead of brave". This is the first part
of the answer: finding what there is to choose from. It was built from the browser-detection spec
(`docs/superpowers/specs/2026-10-03-browser-detection-design.md`) and its plan
(`docs/superpowers/plans/2026-10-03-browser-detection.md`), in wave A of "The app as an app", after the relay.

## What it does

A new module, `src/ai_browser/browsers.py`, answers these questions by reading files only:

- **Which browsers are installed:** the app itself, not a leftover data folder. Brave and Chrome with their other
  channels, and Chromium, are marked usable by agents. Edge, Arc and Vivaldi are listed as not supported yet. On Windows
  it also reads the registry, never writing to it.
- **Whether each one runs, and whether its remote-debugging switch is on:** from the browser's own lock file and its
  `DevToolsActivePort`. For a browser that runs, or whose lock can't tell, it adds one TCP connection to 127.0.0.1 that
  sends nothing.
- **Its profiles:** each by name and colour, in the browser's own order. Never an email or any account field.
- **Which profile holds the Brain's watcher:** only enabled copies count.
- **A first guess at your browser:** the system's default for https links. It is only a guess; you choose.

What it never does:

- open a DevTools session, so it can't make your browser ask "Allow remote debugging?" or show the automation bar;
- open cookies, saved passwords, history or web data;
- write, lock, rename or create anything in a browser's folder, or start a program;
- keep or show your account's email.

## What changes for you

Nothing yet. There is no new page, message, setting or command, and nothing in the app calls the module. Wave B (the
app window) and wave C (Settings, "Where agents browse", and the profile choice) build on it. The README's
"Development" section has a command that prints what it finds on your computer.

## How it was built and checked

- **The build:** branch `browser-detection`, from main `b8de841` (the relay merged). Each task's tests were seen failing
  for the stated reason, then passing. One commit per task:
  1. `b6babc2`: the table of known browsers, their data folders and app folders (`platforms.py`).
  2. `e4fc725`: `open_shared`, a read that never blocks the browser's own saves on Windows.
  3. `a88ce4d`: the registry readers, read only.
  4. `5d1c71f`: the module, its table lookups and one capped reader.
  5. `46cb77e`: `installed()`, apps on macOS and programs on Windows.
  6. `7036185`: `os_default()`, the first guess.
  7. `5482009`: `profiles()`, name and colour only.
  8. `4efc356`: `watcher_places()`.
  9. `6b25a47`: running, switch on or off, and the silent TCP check.
  10. `4202254`: `detect()` and `public()` (the only shape meant for pages), with the read-only guards.
  11. `e9db21d`: the README paragraph.
- **Mutation checks during the build:** the agreement test for `for_data_dir` fails when `realpath` is dropped, and the
  read-only audit guard fails when a Cookies file is opened.
- **Review 1, the builder's own (no subagent was allowed):** one important finding, fixed in `9308bc0`.
  - **Invisible characters in source:** the shell commands used to append code turned the plan's escapes into the
    invisible bidi characters themselves, in `browsers.py` and two test lines. The values were the same, but invisible
    bidi controls in source are "Trojan Source": code that reads differently from what runs. They are written as
    escapes again. Test: `test_the_detection_files_hold_no_invisible_characters`, RED→GREEN.
- **Review 2, a fresh reviewer (read-only, on a git-archive copy):** three important findings and one wording fix, all
  fixed test-first in one pass.
  - **I1, quadratic work on a hostile file** (`12533f9`): `profiles()` matched `info_cache` against `profiles_order`
    pair by pair, and `watcher_places()` resolved a recorded path of any length. Both grew with the square of a file
    under the 16 MB cap. Now the order is a set, and a path over 4096 characters isn't resolved. Tests:
    `test_profiles_fail_safely[48,000 profiles under the size cap]` (7.6 s) and
    `test_watcher_places_fail_safely[a path of 320,000 parts under the size cap]` (6.1 s), RED against a 2 s bound,
    then GREEN.
  - **I2, text a page can't send or show** (`c6e97a8`): a lone surrogate in a name would break the page socket's
    encoding; zero-width names showed blank; U+061C was missing from the bidi controls; and a folder with a bidi
    override, an email or nothing visible came out as a label. Now surrogates are dropped, a name with nothing visible
    in its first 64 characters shows its folder, and `plain_folder()` refuses `@`, control, format and surrogate
    characters and names with nothing visible. Tests: `test_profile_names_are_cleaned` (five new cases, each also
    encoding `json.dumps(public(...), ensure_ascii=False)`) and `test_a_profile_folder_a_page_cannot_show_is_skipped`,
    RED→GREEN.
  - **I3, the top two guarantees not pinned** (`a9b9ebc`, tests only): `open_shared` opening `"r+b"`, or a `state()`
    that sends `GET /json/version`, both passed the suite. The audit guard now checks each open's flags, and the state
    and detect tests accept on their port and check that every connection sent nothing. The code was right, so RED
    was shown against those two changes, then reverted:
    - `test_detection_reads_only_its_files_and_writes_nothing` failed on `"r+b"`;
    - five tests failed on the `GET`: `test_state_combines_the_lock_and_the_switch` (two cases),
      `test_detect_lists_installed_browsers_with_their_state_profiles_and_watchers`,
      `test_public_has_no_paths_or_emails` and `test_detection_reads_only_its_files_and_writes_nothing`.
  - **W, a false privacy sentence** (`f463085`): the README said detection "never reads your account's email", but it
    parses `Local State` and `Preferences`, which hold account fields. It now says it "reads only what it needs, and
    never keeps or shows your account's email", and that the TCP check also runs when a browser's lock can't tell.
    Test: `test_the_readme_says_what_detection_reads`, RED→GREEN.
  - **Its view of the rulings:** it agreed with the pre-flight, Task 4, Task 11, suite, finish and TypeError rulings.
    It partly disagreed with the "@ folder" ruling and disagreed with deferring lone surrogates and invisible-only
    names. I2 fixed all three.
- **Whole suite:**
  - after the build (`e9db21d`): 2 failed, 1350 passed, 9 skipped. The two failures,
    `test_brain_ui.py::test_hand_and_run_take_one_click` and
    `test_cdprelay_chrome.py::test_live_view_and_thumbnails_through_the_relay`, pass alone and 3 times out of 3 after
    `tests/test_browsers.py` (ruled timing flakes, below);
  - after review 1's fix (`9308bc0`): 1353 passed, 9 skipped;
  - after review 2's fixes (`f463085`): 1361 passed, 9 skipped, no failures.
- **Merge:** the branch is merged into main as `63ad51f`.
- **Not run:** the bench (see the Task 11 ruling).

## Rulings made on your behalf

Every decision taken on your behalf, in order, with what it costs if wrong:

- **Pre-flight:** Ruling: public(found, connected=...) keeps the plan's shape, an iterable of browser ids; wave C maps each relay to an id with for_data_dir(relay.folder), and a new test (Task 4) checks that for_data_dir agrees with chrome._same_folder on this host — the plan says ids, and the mapping plus an agreement test closes the gap without widening this wave's message — cost if wrong: a relay on an AIB_CHROME_DIR folder outside the table maps to no id (no card shows "connected"), and the relay's asking/refused/lost read as the detected state (switch_on); wave C would then widen connected to {id: link_state} and the state value set, one function and its test.
- **Pre-flight:** Ruling: chrome.py stays untouched (the plan never repoints it at the new helpers), so switch_on stays a port + TCP check with no lock read and the relay's off/ready can't drift from browsers.state() through this branch; the one designed difference stays: state() never TCP-checks a browser whose lock says it isn't running (spec Decision 8), where switch_on would — cost if wrong: wave C, when it repoints chrome._port_of/_listening at devtools_port/listening, must not add running() to switch_on.
- **Pre-flight:** Ruling: the hand check's "no 'Allow remote debugging?' question and no automation bar at any point" (plan, after Task 11's commit step) is carried as "no new question or bar from detection" (run it with the ai-browser app quit to see no bar at all): the relay's own connection shows the bar while the app is connected; the plan and spec files are not edited (not on this track's file list), the reworded expectation goes in the final report, and the README paragraph claims only that detection never makes the browser ask, which holds either way — cost if wrong: the person running the hand check reads the app's own bar as a detection failure.
- **Task 4:** Ruling: added test_for_data_dir_agrees_with_the_relays_folder_rule (not in the brief) — carries the pre-flight ruling: wave C maps each relay to an id with for_data_dir(relay.folder), so its folder rule must name the same folders as chrome._same_folder on the host OS (exact folder, trailing separator, "..", a link, other letter case, a sibling, an unknown folder); a mutation dropping realpath fails it — cost if wrong: one extra test that pins for_data_dir to the relay rule; if wave C changes _same_folder, this test fails and points at the mapping.
- **Task 11:** Ruling: `uv run ai-browser bench` is not run — cli._bench starts the "default" sandbox under the user's real ~/.ai-browser (Sandboxes(home())) and stops it at the end (boxes.stop(info.name)), a side effect outside this worktree that could stop a sandbox the user or a parallel builder is using, and the plan itself says this branch adds no code to any path the bench times — cost if wrong: a speed regression elsewhere goes unmeasured until the main session runs the bench after the merge.
- **Task 11:** Ruling: Task 11's completion line runs the README test plus the spec's build-time files; the whole suite runs once afterwards, as the main session asked, into suite.txt, with its tail in this ledger — the suite takes ~20 minutes (over a foreground call's limit) and is the branch's check, not this task's — cost if wrong: none beyond order; a suite failure still gets a test-first fix and a ledger line.
- **Suite:** Ruling: the two failures are timing flakes under load, not this branch's — both pass alone, and 3/3 when run after tests/test_browsers.py (its audit hook installed); the branch changes no code they use (no change to chrome.py, app/, brain/ or conftest.py; nothing outside browsers.py calls the new platforms names); the run shared the machine with two other builders' suites; not re-run on main, since they don't fail on this branch — cost if wrong: a real ordering bug in the Brain page's hand/run clicks, or a slow relay live view, goes unreported by this branch.
- **Final:** Ruling: a profile folder named with "@" (a hand-made folder listed in a hostile Local State) would show in public()'s folder field — stands: Chromium names folders Default and Profile N, so only someone who can already write the data folder could cause it — cost if wrong: an email-like folder name reaches Settings. *(Superseded: review 2 disagreed in part, and I2 now refuses such folders.)*
- **Final:** Ruling: public(found, connected=None), or a watcher folder that isn't a path, raises TypeError — stands: those are the app's own arguments, not file contents, and the never-raises promise is about files — cost if wrong: a wave C caller bug shows as a TypeError instead of an empty result.
- **Finish:** Ruling: the plan workspace is kept, not deleted, and finishing-a-development-branch is not run — the main session merges, forbade merge and push, and named suite.txt in this workspace — cost if wrong: a git-ignored folder to delete after the merge.

## Deferred minors

- **Final:** minor (deferred): _profile_name's 64-character cut can leave a trailing space or split an emoji or combining sequence.
- **Final:** minor (deferred): a name made only of other invisible format characters (U+200B, U+2060, U+FEFF) survives the spec's exact cleaning list and shows as a blank-looking label. *(Now fixed by I2.)*
- **Final:** minor (deferred): a lone-surrogate escape in a hostile Local State survives name cleaning; json.dumps' default ensure_ascii copes, but a UTF-8 encode with ensure_ascii=False in wave C would raise. *(Now fixed by I2.)*
- **Final:** minor (deferred): test_for_data_dir_agrees_with_the_relays_folder_rule's trailing-separator case is a no-op (pathlib drops the separator).
- **Final:** minor (deferred): the check-then-open race with a pipe: a FIFO swapped in between os.path.isfile and the open would block _read (fix: open with O_NONBLOCK and check S_ISREG on the handle).
- **Final:** minor (deferred): the audit hook of test_detection_reads_only_its_files_and_writes_nothing stays installed for the rest of the pytest process (it records nothing outside its block).
- **Final:** minor (deferred): detect() reads each Local State twice (profiles(), then again inside watcher_places()).
- **Final:** minor (deferred): devtools_port() may read up to 16 MB where only the first line counts.
- **Final:** minor (deferred): public(connected="brave") as a bare string is iterated by character and marks nothing connected.
- **Final:** minor (deferred): the two designed differences from chrome.switch_on (state() never TCP-checks a browser whose lock says it isn't running; devtools_port() takes only 1-5 ASCII digits) are wave C's to keep when it repoints chrome.py at these helpers.

## What only you can check

Nothing here was run on Windows or against your own browsers. Three checks are yours:

- **The Windows CI run:** on GitHub, open Actions, then **tests**, then **Run workflow**, and pick `both`. It runs
  `open_shared`'s Windows half (a plain open blocks the browser's rename; `open_shared` doesn't), the real registry
  readers and the Windows paths.
- **Your Mac:** run the command in the README's "Development" section. It only reads files and makes at most one silent
  TCP check per running browser; it opens no DevTools session. Expect:
  - Brave and Chrome only, with Brave `default` true;
  - Brave's profiles (`Default`, `Profile 1`) by name and colour, and no email anywhere;
  - `watcher` true on the profile where you loaded the watcher;
  - Brave `switch_on` while its switch is ticked, `switch_off` after unticking it, and `not_running` after quitting it;
  - no new "Allow remote debugging?" question and no new bar from detection. While the ai-browser app is connected,
    its own connection shows the bar; quit the app to see no bar at all.
- **Your Windows laptop:** the same command. Expect:
  - Chrome, and Edge with `agents` false; Brave too if it is installed;
  - Brave's state following you opening and quitting it (this checks the lockfile rule);
  - `default` true on the browser chosen in Windows' Settings, Default apps (this checks the `UserChoiceLatest` read
    on Windows 11);
  - every Windows path in the spec's Decision 2 that is installed there, found.

If anything differs, wave C's Settings page would show it wrong, so the table or the reader gets fixed first.
