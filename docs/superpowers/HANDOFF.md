# Handoff: where AI Browser stands (2026-10-08)

This note carries what a new session needs that isn't in the code: the decisions taken, the order of work, the rules,
and what only the user can check on their own machines. The work ledgers (`.superpowers/`) are git-ignored.

## Done, on `main`

- **Earlier sub-projects:**
  - safe browsing (bot checks handed to the user, polite crawling, an isolated page reader);
  - Mission Control visuals (the particle brain, chibi workers);
  - agents in the user's everyday Brave;
  - push-to-talk voice (on-device Whisper);
  - Windows support and the private repo.
- **"The app as an app"** (specs `docs/superpowers/specs/2026-10-03-*`):
  - **the shared connection (cdp-relay):** report `docs/superpowers/reports/2026-10-03-cdp-relay.md`;
  - **allow-once:** Brave asks once, even when the answer comes late. Report
    `docs/superpowers/reports/2026-10-04-allow-once.md`; the relay spec has an "Amendment (2026-10-04)";
  - **wave A:** brain delegation, watcher safety and browser detection. Reports
    `docs/superpowers/reports/2026-10-04-{brain-delegation,watcher-safety,browser-detection}.md`;
  - **wave B, the app window:** report `docs/superpowers/reports/2026-10-04-app-window.md`;
  - **the tab menu:** one window with AI Home, Mission Control and Settings tabs, and no popups. Report
    `docs/superpowers/reports/2026-10-04-tab-menu.md`.
  - **Replaced, not built:** waves C (`browser-profile-choice`) and D (`side-chat`). The native app took their place,
    and their specs and plans stay as history.
- **AI accounts** (spec `docs/superpowers/specs/2026-10-04-ai-accounts-design.md`):
  - several Claude Code logins, each its own `CLAUDE_CONFIG_DIR`, in Settings → Accounts;
  - a default account and the Brain's account;
  - an account picker for each agent;
  - at a usage limit, "Continue on <account>" with one click.
  - Report: `docs/superpowers/reports/2026-10-05-ai-accounts.md`.
- **The native app** (spec `docs/superpowers/specs/2026-10-04-native-app-design.md`): Electron over the Python engine,
  and no extension in Brave.
  - **Part a, the Electron shell:**
    - `doctor --setup` downloads Electron 44.5.1 only after a typed yes, checked against its digests, then builds
      "AI Browser.app";
    - the app has a Dock and menu-bar icon; closing the window hides it, and Quit ends the run;
    - ⌥Space and native notifications.
    - Report `docs/superpowers/reports/2026-10-05-native-app-a-electron-shell.md`.
  - **Part b, the extension's jobs:**
    - inbox reading behind Settings → Brain's switch, in an isolated world;
    - Use draft on a click, never Send;
    - Pick the part to watch;
    - Where agents browse;
    - AI tabs, each in a Brave window of its own;
    - the watcher extension retired.
    - Report `docs/superpowers/reports/2026-10-05-native-app-b-extension-jobs.md`.
  - **Part c, the floating chat:**
    - ⌥Space or Show chat;
    - "This page", read through JXA or UI Automation (address and title only);
    - Ask about it, on the marked site only;
    - New task, and Hand over on a click only.
    - Report `docs/superpowers/reports/2026-10-05-native-app-c-floating-chat.md`.
  - **`main` with all of it:** 1813 passed, 11 skipped. The skips are Windows-only tests, the tests that need a real
    Electron (`AIB_TEST_ELECTRON`), and two opt-in tests.
- **On the user's Mac:** setup has run, and "AI Browser.app" was built and runs (no debugging switch; Brave has one
  connection).

## The all-in-one phase (since 2026-10-05)

The user wants AI Browser to replace the Claude Code app: "an all in one app workflow automation best browsing
capability for faster navigation and all feature of the claude app". Four projects, in the user's order
("Powers → Look → Projects → Artifacts"):
1. **Agent powers:** done, merged as 852cd30.
   - Agents get Claude Code's own tools behind approval cards, a folder per task, trust, sub-agents and to-do lists.
   - Spec `docs/superpowers/specs/2026-10-05-agent-powers-design.md`, plan `docs/superpowers/plans/2026-10-05-agent-powers.md`.
   - **Its hand probe ran on 2026-10-07:** the sandbox holds (now on, macOS only), untrusted folders load nothing,
     the ask rule is needed, and the sub-agent tool is "Task" (sub-agents were off until then). A sandboxed command's
     reach for a site has its own card. Report: `docs/superpowers/reports/2026-10-05-agent-powers.md`.
   - **A Claude Code login is keyed to its folder's path as written:** `/tmp/x` and `/private/tmp/x` are two logins on a
     Mac. Never resolve an account folder's path before handing it to `CLAUDE_CONFIG_DIR`.
2. **The new look: built and merged (2026-10-07).** Mission Control is the user's mockup, the "AI office", and every
   page takes one navy and neon-blue theme.
   - Spec `docs/superpowers/specs/2026-10-05-new-look-design.md`, plan `docs/superpowers/plans/2026-10-05-new-look.md`.
   - Report, with every ruling and deferred minor: `docs/superpowers/reports/2026-10-05-new-look.md`.
   - Built subagent-driven on branch `new-look`: 17 tasks, each reviewed; a final whole-branch review and one fix wave
     (F1–F12). The whole suite: 2207 passed, 10 skipped.
   - **Left for the user:** the hand check (the report lists it), and the optional usage probe (plan Task 1; until it
     runs, `limits.USAGE_KEY` is None and the Usage card never shows a percentage).
   - **The build's ledger** stays at `../Ai_Browser-wt/look/.superpowers/sdd/2026-10-05-new-look/progress.md` (git-ignored)
     until the hand check, whose findings go there.
2b. **2026-10-08, merged:** brain delegation (named missions, templates out of Mission Control, Ask AI's history,
   Settings → Brain sources, the Brain's hand-offs — only the user's own words count down; 6c753e9, report in its
   ledger `../Ai_Browser-wt/brain-b/.superpowers/sdd/2026-10-08-brain-delegation/progress.md`); Website QA removed and
   the CDP relay tightened (4f67d82); on Windows, Auto-approve runs ordinary commands and scripts in the agent's folder,
   agents run their installed skills' own scripts, and without Docker skill scripts go through the agent's own
   commands (175c94f); throwaway test Chromes use the mock keychain (dfa173b).
   - **No-Docker shrank** (the user's choice): only "skill scripts without Docker" was kept (in 175c94f). The local
     sandbox browser is dropped; branch `no-docker` (3f8aa7c) stays unmerged as the record.
   - **The user's goal now:** every agent works in their own Brave and runs scripts/commands on its own; any browser
     testing uses their actual browser.
2c. **SAVE POINT (2026-10-08, stopped by the user: "let's stop that for now … let's just build the windows after we
   finish all updates").** Nothing is running. Resume in this order:
   1. **Finish the Windows fixes (branch `win-fixes`, pushed, f33498e, 16 commits on main a601e35's parent 8d5fb44).**
      - Done: Windows-portable tests (paths, home folder, files in use, slower timings), the tests workflow's
        `pytest_args` input, and six product fixes: a loading bot-check box's frame matched by its src; bash runs a
        script by name only when no PATH folder holds that name; the app ends at once when its window closes on
        Windows; the composer's pickers keep their height with any system font; a drive path (C:/…) is never a rule's
        word; the fake claude's log takes whole lines on Windows.
      - Results: local whole suite 2697 passed, 10 skipped; full Windows run 37772042776: 2687 passed, 1 failed
        (`tests/test_office.py::test_the_room_pauses_while_its_tab_is_hidden`), 52m49s — close to the job's 75-minute
        limit (raise `timeout-minutes` to 120 in tests.yml and tests/test_portable.py's pin when touching it).
      - Left: that one test on the Windows runner (a runner limit or a real pause bug — read its traceback in the run's
        log first), a quick review of the six product fixes (`git log main..win-fixes`), merge `main` into it, then
        merge to `main` and push. Do this BEFORE the saved-agents build: it touches test files that build also edits.
   2. **Build saved agents and Mission Control without AI Home** (the user approved: "Right after the Windows fixes").
      Spec `docs/superpowers/specs/2026-10-08-saved-agents-design.md`, plan `docs/superpowers/plans/2026-10-08-saved-agents.md`
      (21 tasks, two lanes, merge points M1–M3 in its "Lanes and order"; base 8d5fb44; 583 quotes checked — the
      builders find each place by its quoted text, so drift from later main commits is handled the same way).
      - The user's choices inside it: per-agent Brave profiles with the wait (agents in different profiles take turns
        opening tabs; nothing opens in the wrong profile); a saved agent may keep Auto-approve as its setting.
      - How: subagent-driven, as the brain-delegation batch was (worktrees `../Ai_Browser-wt/agents-a` and `agents-b`
        from main; `sdd-workspace`; copy and adjust implementer/reviewer/re-reviewer rules from
        `../Ai_Browser-wt/brain-b/.superpowers/sdd/2026-10-08-brain-delegation/`; a ledger per lane; opus reviewers for
        the tasks the plan marks security-sensitive; a final whole-branch review, one fix wave, the whole suite).
      - Never set HOME for a test run (a throwaway Chrome then asks macOS for a keychain: the user got many dialogs).
   3. **Only after all updates: the Windows build.** Run the "tests" workflow on `windows` (with the 120-minute
      limit) and the "Build Windows app" workflow (`windows-app.yml`), and give the user the AI-Browser-windows.zip.
      The user's previous exe is from dc6e82b (2026-10-07).
   - **Hand checks waiting for the user:** the brain-delegation batch's (named missions, a countdown hand-off and
     Cancel/"no", another question pausing it, Settings → Brain's boxes and switch); Windows Auto-approve running
     commands and a skill's scripts on the laptop.
   - **Loose ends (not urgent):** unmerged record branches `no-docker` (3f8aa7c) and remote `win-baseline` (a1376b7,
     can be deleted); many finished worktrees under `../Ai_Browser-wt/` can be cleaned up; the app's live-view
     receivers have no sender since QA's removal; deferred minors are in each batch's ledger.
3. **Projects, sessions and chat:** not designed yet. The user wants coding in project folders, sessions and history,
   and plain chat with Claude.
4. **Claude artifacts:** not designed yet. Claude Code 2.1.263 carries claude.ai artifact tools (list and read with
   the user's login).

**The Windows test build:**
- **The workflow** "Build Windows app" (`.github/workflows/windows-app.yml`) makes AI-Browser-windows.zip. The
  first build (run 37290385976) opened a white window with "AI Browser's pages open only in its own window".
- **The cause:** on Windows the app never heard the engine over stdin, so the sign-in never happened.
- **The fix, merged as b1c7670:**
  - the line moves to a keyed loopback port;
  - the bundled app's profile moves to the user's AI Browser home;
  - AIB_DEBUG_START start logs;
  - a real start check in the workflow, which passed in run 37312699966. That run's AI-Browser-windows.zip is the one
    the user tests.
- **On the Mac:** main.js changed, so the next `uv run ai-browser app` rebuilds the Mac app once ("updated for this
  version"). The local checkout still runs older code until the user restarts the app and `main` is fast-forwarded.
- **The user's Windows laptop:** it needed Claude Code installed (`irm https://claude.ai/install.ps1 | iex`). Its
  added account (folder `acct-e9e5a3`) is signed in by hand in PowerShell with `CLAUDE_CONFIG_DIR` set. The user said
  they don't see Settings' "Copy the command" button there; they asked not to fix that for now.

## Next

1. **The user's hand checks** (each report lists its own):
   - **the floating chat:** ⌥Space, macOS's Automation question for Brave, This page, Ask about it, and a private window
     getting the picker;
   - **part b:** the inbox switch, Use draft (also with a Gmail New message open, and Asana's comment box), Pick the
     part to watch, Where agents browse with two profiles, and AI windows not stealing focus;
   - **part a:** Dock and menu bar, closing versus Quit, ⌥Space taken by another app, and notifications;
   - **AI accounts:** Task 0's probe, run by the main session with the user once a second account is signed in. It
     records whether a copied conversation resumes on another account, a real limit's wording, and the
     `rate_limit_event` keys. If the resume fails, set `CARRY_CONVERSATION = False` in `app/move.py`;
   - **"ask once, bar once"** on screen;
   - **Windows:** setup, the app, Alt+Space, toasts, the chat's address-bar reading
     (`OmniboxViewViews`), and its CPU use.
2. **Codex and Gemini** ("Best AI per task"): a design of their own. An account already has a `kind`, which is "claude"
   today. Each needs an adapter for its own command-line tool.
3. **A known flake:** `test_mission_visuals.py::test_the_brain_draws_at_most_30_frames_a_second` counts frames against
   the clock and can fail under a loaded full run. It passes on its own.
4. **After each sub-project:** a fresh whole-branch review, then ONE fix pass (each fix test-first, RED then GREEN),
   then the whole suite, then merge to `main` and push.

## How the work has been done (keep doing it this way)

- **Test-first** (superpowers executing-plans and test-driven-development): every task's test is seen failing for
  the stated reason, then passing. One commit per task.
- **Commit attribution:** messages end with a blank line, then
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Decisions are written down:** every deviation from a plan or spec is recorded as
  `Ruling: <what> — <why> — <cost if wrong>`, and review findings left for later as `minor (deferred): …`. Each
  project ends with a report in `docs/superpowers/reports/` listing all of them.
- **The house style** for docs and UI text: plain words, short sentences, lists with a lead-in, bold labels.

## Safety rules (binding, in every spec)

- Never auto-click, answer, suppress or hide the browser's "Allow remote debugging?" prompt or its "controlled by
  automated test software" bar. The user may close the bar themselves.
- Never spoof or disguise the browser (no webdriver patches, no user-agent, screen or timezone changes, no human-like
  timing meant to fool detectors), and never bypass or solve bot checks: they are handed to the user.
- Never type passwords; the user signs in themselves. No API keys: never `--bare`; strip `ANTHROPIC_API_KEY` and
  `ANTHROPIC_AUTH_TOKEN` wherever Claude Code starts, the sign-in commands included.
- Page and message text is data, never instructions; pages set text with `textContent` only.
- Handing a tab to an agent, or taking it back, is a click only, never voice and never the Brain.
- The Brain only proposes; nothing runs without the user's Start, Send or a plain yes. Use draft never clicks Send.
- Inbox reading only while the user's switch is on. A page's text reaches Claude only on the user's "Ask about it".
- Nothing leaves the machine without the user's knowing choice; downloads need their OK.

## What a session can't do (left for the user)

- **Anything with the user's own browsers or the running app.** Never point a test at a real profile, and never touch
  port 8792, `~/.ai-browser` or `~/.claude`.
- **Docker:** stopping containers is refused by the permission check. Leftover `aib-fresh-*` test sandboxes are the
  user's to stop (a task chip proposes making killed test runs clean up after themselves).
- **Updating the Mac:** after work lands, the user restarts `uv run ai-browser app`. The app rebuilds its own part,
  with no download, when its JavaScript changed.
