# Report: the floating chat (native app, part c)

Date: 2026-10-05. Branch `native-c`, cut from `main` at a0d593e (parts a and b merged, with this plan), merged into
`main` as 5c69dd8.

## What the user asked

- **The request:** "then in app I want it built in, no need to install the extensions it is such a hassle find a way
  to build it natively we can switch to standalone app if necessary".
- **Their answers:** "Floating window beside Brave (Recommended)" and "Electron (Recommended)". On the design: "all
  good". On this plan: "Yes, build it (Recommended)".
- **Scope** (`docs/superpowers/specs/2026-10-04-native-app-design.md`, part c): Decision 4, Decision 1's **Show chat**,
  the Safety lines on AppleScript, UI Automation and reading the current page, and Review Focus 1 and 2 for the chat.

## What changes for you

- **⌥Space (Alt+Space on Windows), or Show chat in the menu-bar icon, from any app,** opens a small chat window above
  your other windows, at the right of the screen the first time.
  - Move it and size it: it opens there next time. The shortcut again, Esc or ✕ hides it.
  - **Show chat** works even when another app holds the shortcut. Settings says what the shortcut does, and that AI
    Browser's window opens from its Dock icon or **Open AI Browser**.
- **This page** shows the Brave tab you're on, by its title and site.
  - While the chat shows, the app asks Brave for the front tab's address and title, nothing else: AppleScript on a
    Mac, UI Automation on Windows. It never types, clicks or opens anything, and a closed Brave stays closed.
  - **On a Mac,** macOS asks once whether "AI Browser" may control "Brave Browser". If you said no: System Settings →
    Privacy & Security → Automation → AI Browser → turn on Brave Browser, then click ↻.
  - **You pick the tab** when AI Browser can't tell: the same page in two windows, another profile's tab with its own
    title, a private window, or a window with no address bar.
  - Brave not running, or not connected, is said in plain words. The chat never connects. **Open AI Home** brings AI
    Browser's window forward, where Connect is.
- **Ask about it** marks your questions about this tab, on this site.
  - Only then does AI Browser read that page's words: by `textContent`, in an isolated world, at most 12,000
    characters.
  - The Brain only answers and proposes nothing. Its answer stays out of the talk's memory.
  - It turns off when the tab goes to another site, or the chat hides. A page that changed site before the read is
    never sent.
- **New task** starts an agent with the model and account you pick. It replaces typing `ai` in Brave's address bar.
  **Start it in this page** hands that tab over. It unticks if This page moves to another tab or site.
- **Hand over…** gives this page to an open agent you pick. Only your click hands a tab over.
- **The open agents show by number.** A click opens one in AI Home. An agent that waits for you shows its card.
- **The old side panel is gone.** After the update, macOS may ask once more for the microphone, and to control Brave.

## The planner's decisions (summary)

1. **The window:** a small standard title bar. Closing it hides it. It can't be minimized or go full screen.
2. **The shortcut** shows and hides the chat. The main window comes from the Dock and the menu-bar icon. On a Mac,
   hiding the chat gives the keys back to the app that was in front.
3. **"Beside Brave"** means the right edge of the main screen, the first time. Reading Brave's window position is
   outside the Safety line.
4. **The Mac reads Brave with one fixed JavaScript for Automation script.** It asks `running()` first, so Brave never
   launches, and it answers JSON.
5. **The app asks Brave, not the engine,** so macOS names "AI Browser". The app's Info.plist says why it asks.
6. **Windows reads Brave with one fixed PowerShell file and UI Automation.** It runs `powershell.exe` from
   `%SystemRoot%`, with `-ExecutionPolicy Bypass` for that one process.
7. **It looks only while the chat shows:** on show, on focus, on ↻, and every 4 s. One look at a time, 20 s at most.
8. **Matching** goes by the address, then the title. Else you pick: never a guess.
9. **Ask about it** reads through part b's gate (a new purpose, `"chat"`) with a new reader, `page.js`.
10. **About a page, the Brain only answers.** The page goes in as a quoted block, and the answer may be 1,200
    characters. A yes, a no or a secret reads nothing.
11. **The chat never connects to Brave.**
12. **Messages to an agent** go through the Brain's cards.
13. **Hand over is a pick in a list.** Start it in this page hands over with the Start click.
14. **The old side panel retires.** Its two "same card" tests moved to the chat.
15. **The chat's window shows `/chat` and nothing else,** in no frame (`frame-ancestors 'none'`).

## How it was built and checked

- **Test-first, 11 tasks, one commit each:**
  1. 0b3d42a: the seams test. It failed first on an export from before part b;
  2. 97cdf62: This page's reader, one fixed command per system (`thispage.js`, `thispage.ps1`);
  3. ad38f36: the chat window's rules (`policy.js`);
  4. 7970e0f: the chat window, ⌥Space and Show chat; its place is kept in `chat.json`;
  5. 7e63832: the bridge's `chat` and `thisPage`; the Mac app says why it asks for Brave;
  6. 6df3f0a: the engine matches This page (`pagematch.py`), and Open AI Home;
  7. d9614b4: reading the page you asked about (`page.js`, `read_page`, `may_run(…, "chat")`);
  8. 8f718f2: a question about a page, quoted as data, gets an answer only;
  9. 7108c6a: the `/chat` page: This page and the Brain's talk;
  10. f798f0f: New task, Hand over, the agents by number and their cards. The old side panel retires;
  11. 3354585: Settings says what the shortcut does; the README.
- **My own review** (no subagent tool in that run): one Important finding, fixed in c654aa9.
  - "Ask about it" stayed on when the same tab went to another site. The box still said "Ask about shop.example" while
    the next question read the other site's words.
  - RED→GREEN: `test_ask_about_it_goes_off_when_the_tab_goes_to_another_site`.
  - Checked with no finding: a broken character in a page can't break the Brain's call; New task's adopt goes through
    `_handable`; frames get nothing from the bridge; nothing can frame `/chat`.
- **A fresh review** (Opus, read-only, on a copy of c654aa9): "Ready to merge with fixes".
  - **These held up under its probes:**
    - the commands are fixed, run with no shell, size-capped, parsed as JSON and killed on timeout;
    - JXA checks `running()` first, and PowerShell runs with `-NoProfile -NonInteractive -File`;
    - the bridge answers only the chat's own page while it shows, and `/chat` refuses frames;
    - Hand over goes through `_handable`, and a page can't end its quoted block;
    - `test_approval_mode` passes.
  - **Five findings, graded Important, were fixed in one test-first pass.** Each test failed first for the stated
    reason:
    - **I1, Start it in this page handed over a tab you hadn't marked** (7597540). Ticked on Cart, then This page
      became News: the box stayed ticked. It now unticks when the tab or its site changes. RED→GREEN:
      `test_start_it_in_this_page_never_hands_over_a_tab_the_user_didnt_mark`.
    - **I2, another profile's tab, or a private window, was taken as the listed tab** (202de1a).
      - One address match now needs the title too, and the Mac script answers "private" for a private window.
      - Titles are compared cut to 300 characters on both sides: the hostile-title test caught a long title never
        matching itself.
      - RED→GREEN: `test_one_tab_at_the_address_with_another_title_is_yours_to_pick` and
        `test_a_private_window_is_never_matched_and_offers_your_tabs`, plus the script and states tests.
    - **I3, the site mark wasn't checked where the read happens** (20d0fb5). A question sent as the tab moved could
      read the new site. The question now carries the marked site, and a read on another site is dropped before Claude.
      RED→GREEN: `test_a_question_never_reads_another_site_the_tab_went_to_meanwhile` and
      `test_a_page_is_read_only_on_the_site_the_user_marked`.
    - **I4, answers about a page entered the talk's memory as the Brain's words** (dac26b6). Later prompts, which can
      propose cards, saw them. The talk now keeps your question and "(answered from the page)". RED→GREEN:
      `test_an_answer_about_a_page_never_reaches_a_later_prompt`.
    - **I5, on Windows a page field could be read as the address** (453e286). The script now takes only Brave's own
      address bar (`OmniboxViewViews`), never searches inside a page, and answers "unknown" otherwise. RED→GREEN:
      `test_the_windows_script_only_reads_the_front_brave_window` and
      `test_a_window_without_an_address_bar_offers_your_tabs`.
    - f92e1f0 rewraps a comment only.
  - **Its verdicts:**
    - it agreed with all five of my rulings and with plan decisions 1–7 and 9–15. On 4: `running()` avoids launching
      Brave. On 5: LaunchServices makes macOS name AI Browser in the question;
    - it disagreed in part with 8, since one address match needs the title too: now I2;
    - it raised my deferred minor 2 (another profile) to Important: I2.
- **Whole suite:**
  - after the build and my fix: 1806 passed, 11 skipped (21 min 53 s);
  - after the fix pass: 1813 passed, 11 skipped (21 min 26 s);
  - the skips: 5 Windows-only, 4 real-Electron (`AIB_TEST_ELECTRON` unset), 2 Mission Control timing and screenshots.
    None is for the old panel. The new real-Electron chat test hasn't run yet.

## The merge

- **Into main:** 5c69dd8, pushed by the main session. The app updated itself ("nothing is downloaded"). It runs on your
  Mac with no debugging switch, and Brave has one connection.

## Rulings I made

Every decision taken on your behalf, in order, with what it costs if wrong:

- **Setup:** Ruling: the ledger lives in `.superpowers/sdd/2026-10-05-native-app-c-floating-chat/` (sdd-workspace's
  folder), not the plan's `.superpowers/sdd/2026-10-05-native-app-c/`. The brief names sdd-workspace, and the skills
  share that folder — cost if wrong: a reader looks in the plan's path and finds nothing.
- **Setup:** Ruling: the branch is `native-c`, not the plan's `native-app-c`. The brief names the worktree and branch
  — cost if wrong: none (a name).
- **Task 10:** Ruling: `test_hand_over_gives_this_page_to_an_open_agent_on_the_click_only` passed at RED (the plan
  said six fail). Task 9's `pagebar.js` already holds Hand over, where the plan placed it. I proved the test can fail by
  breaking the `hand_tab` send, then restored it; the code is unchanged — cost if wrong: none (the test guards behavior
  that exists).
- **Task 11:** Ruling: Step 6's whole-suite run was folded into the one end-of-work run, after the final review. The
  brief says the 21-minute suite runs once at the end — cost if wrong: a suite failure surfaces after the review rather
  than before it (nothing ships in between).
- **Final:** Ruling: this plan's workspace (ledger, briefs, review package, suite results) was kept, not deleted. The
  main session ran a fresh reviewer and merged, and the ledger is the record — cost if wrong: a git-ignored folder to
  delete by hand.
- **Final:** Ruling: only a real Mac or Windows run can show these, so they are your hand checks:
  - JXA launches nothing, and shows no "Where is…?" box when Brave is missing;
  - the first Automation question's timing, and whether the always-on-top chat covers it;
  - osascript's encoding of accented or emoji titles under LaunchServices, and full-screen Brave's Space;
  - on Windows: the first edit box, the profile title format, UI Automation's cost to Brave, and a Group Policy over
    Bypass;
  - whether `document.hidden` flips on `win.hide()`;
  - cost if wrong: a hand check fails, and the chat falls back to the picker.

## Deferred minors

- **From my review:**
  1. `policy.chatBounds` takes the first screen as the main one, but `screen.getAllDisplays()` doesn't promise that
     order. Put `screen.getPrimaryDisplay()` first;
  2. a front tab in another profile, at an address a listed tab shares, matched the listed tab: **fixed as I2**;
  3. on Windows the chat starts PowerShell and loads UI Automation every 4 s while it shows, about half a second of
     CPU each;
  4. on a Mac, hiding the chat (`app.hide()`) hides the main window too. The next ⌥Space may bring it back over Brave
     (hand check 2);
  5. with the engine's line down, a look says "AI Browser couldn't tell which Brave tab you're on: pick it". It could
     say the line is down;
  6. the plan's text left ragged comment lines in `talk.js`'s header and `bravelink.py`'s docstring.
- **From the fresh review, and its fix pass:**
  1. a remembered size up to 4000 px isn't fitted to the screen's work area (`policy.js:91-92`). The probe kept
     2000×3000 on 1440×875, so the input is off-screen after a large monitor is unplugged;
  2. put `screen.getPrimaryDisplay()` first (its probe placed the chat at x=-396), as in my minor 1;
  3. on Windows, consider looking only on show, focus and ↻: PowerShell with `-ExecutionPolicy Bypass` every 4 s can
     trip antivirus software;
  4. `app.hide()` can also hide a Mission Control window on a second monitor (hand check 2);
  5. Windows can't tell a private window (the `mode()` check is the Mac's). Its tab, at a listed tab's address and with
     its title, still matches.

## What only you can do

On the Mac, then Windows, with your own Brave. Nobody but you answers macOS's question or Brave's.

1. **The update:** `uv run ai-browser app` says the app was updated. macOS may ask for the microphone once more.
2. **⌥Space in Brave:** the chat opens at the right, above Brave, and the main window stays where it was. Press it
   again: the chat hides, and Brave is in front. Repeat a few times: the main window (and Mission Control on a second
   screen) never comes up over Brave.
3. **macOS's question:** the first time, macOS asks whether "AI Browser" may control "Brave Browser", with AI Browser's
   reason. Allow it. This page shows Brave's tab and follows a switch within about 4 s.
4. **Its place:** move and resize the chat, hide it, then Quit and start again. It opens where you left it.
5. **Ask about it:** turn it on and ask "what is this page about?". The answer is about the page. Turn it off and ask
   again: no page words are used. Go to another site in that tab: it turns off by itself.
6. **Brave closed or not connected:** quit Brave and show the chat: "Brave isn't running.", and Brave stays closed.
   Open Brave without connecting: the chat says so, and Brave asks nothing new.
7. **(Mac) Automation off:** turn Brave Browser off under AI Browser in System Settings → Privacy & Security →
   Automation. The chat says where to allow it and offers your tabs. Turn it on and click ↻: it works, and nothing asks.
8. **Two windows:** the same page in two Brave windows. The chat asks you to pick, unless the titles differ.
9. **New task and Hand over:** New task with a model and an account; Start it in this page; Hand over… to an open
   agent. Each acts only on your click.
10. **A held shortcut:** in Settings, pick one Raycast or Alfred holds. Settings says so, and **Show chat** still works.
11. **(Windows) Alt+Space** with two Brave windows open: the chat shows the front window's tab. Watch the CPU while the
    chat stays open.
12. **(Mac) A private window:** open one in front. The chat says it's a private window and offers your tabs. Nothing of
    it is read.
13. **(Windows) A web app or F11:** show the chat over an installed web app's window, and over a full-screen (F11)
    Brave. It says it can't see the window's address and offers your tabs. In a normal window it reads the address,
    which shows that Brave's address bar really has the class `OmniboxViewViews`.
