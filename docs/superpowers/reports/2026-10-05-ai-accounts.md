# Report: several Claude logins, picked per agent, carried past a usage limit (AI accounts)

Date: 2026-10-05. Branch `ai-accounts`, cut from `main` at 7123816 (after the tab menu merged), merged into `main` as
b9d4a81.

## What the user asked

- **The request:** "How I will be able to switch account on my AI? I have a second claude that I launch from open -n
  -a 'Claude' --args --user-data-dir="$HOME/.claude-second" and also possibly a codex AI to use or gemini."
- **Later:** "the auto switching of AI acc is there? where can i see all the connected ai acc?"
- **Their answers:** "Ask me with one click (Recommended)", "One account, set in Settings (Recommended)" and "Both:
  move, else hand over (Recommended)". Why switch: "Keep working past a limit", "Separate work and personal", "Best AI
  per task".
- **On the plan:** "Build it next (Recommended)".
- **Scope** (`docs/superpowers/specs/2026-10-04-ai-accounts-design.md`): Claude accounts now. Codex and Gemini join
  the same list in the next design.

## What changes for you

- **Settings → Accounts** lists your Claude logins:
  - each shows **Signed in · Pro** or **Not signed in**, and which one new agents and the Brain use. Nothing else is
    kept: never your email or your organisation;
  - **Add** makes an account with a folder of its own. **Use a Claude Code folder I already have** takes yours. A
    browser's data folder, such as the Claude app's `--user-data-dir`, is refused;
  - **Sign in** offers **Open Terminal** (Terminal on a Mac, a command window on Windows) or **Copy the command**. You
    sign in there and in your browser. AI Browser never sees a password or a token, and both commands clear
    `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` themselves;
  - **Remove** only forgets an account. Its folder, conversations and sign-in stay;
  - "Default account for new agents" and "The Brain's account" are picked here.
- **The pickers.** AI Home and Mission Control have an **Account** picker beside the model, when you have two or more
  accounts. A signed-out account says "Sign in first"; one at its limit says "at its limit until 3:00 pm". Each agent
  shows its account's name, and keeps it until you move it.
- **The row's ask at a usage limit.** The agent pauses, its partial answer stays, and its row (and its drawer in
  Mission Control) says "Personal hit its usage limit (resets 3:00 pm).":
  - **Continue on Work** carries its conversation there: "Moved to Work with its conversation". When it can't, it
    starts fresh with a hand-over note: "Started fresh on Work with a hand-over note";
  - **Wait for the reset** leaves it paused. With no other signed-in account, the row says "Add an account in
    Settings";
  - moving back carries the conversation too. The older copy is kept beside it, never overwritten or deleted;
  - nothing moves without your click. The watcher, the Brain and voice never move an agent.
- **The Brain's card.** "The Brain hit its limit on Personal. Continue on Work?" in AI Home's Brain area. The click
  sets the Brain's account and runs the refused call once more.
- **Tools per account.** AI Home → Tools shows one account's servers, switches and **Always allow** list at a time.
- **Statuses stay fresh.** A page asks again when its tab is shown, and a change any check finds (an agent's start, a
  move) reaches every page.

## How it was built and checked

- **Test-first, 15 tasks, one commit each** (Task 0, the hand probe, is yours: below):
  1. 2bec900: the fake `claude` learns accounts; every test's Default folder is a throwaway;
  2. eed0106: `accounts.py`: `accounts.json`, a folder per account, Claude Code's environment on each;
  3. a73dae1: the sign-in command and Open Terminal (`platforms.py`);
  4. ac89564: a status from `claude auth status` (never the email), limits for this run, the rows pages show;
  5. dafcc37: a usage limit noticed once per turn (`limits.py`, the bridge); unknown events logged by their keys;
  6. 7e2f583: agents run on an account; a signed-out account stops them plainly; a limit pauses them;
  7. 1d56ea3: each account's tools;
  8. 20f23b7: `move.py`: the conversation's copy, and the hand-over note;
  9. e185a3c: `AgentManager.move`: Continue on another account;
  10. 811f590: the server's eight app-only messages, a task on an account, Open Terminal, the sign-in watch;
  11. 823998c: the Brain's account, its card, and one retry;
  12. 6e2d5b5: Settings → Accounts;
  13. f6e11cd: AI Home: the picker, the row's ask, the Brain's card, Tools per account;
  14. 339e57d: Mission Control: the picker, and the drawer's account and ask;
  15. ccab261: `ai-browser app` runs on accounts; the README.
- **A usage limit cut the builder off** after the whole suite and its self-review, before its report. The commits and
  the ledger were complete, so nothing was lost.
- **My own review of the whole branch** (no subagents were allowed in that run): no critical or important findings,
  eight minors (below).
- **A fresh review** (Opus, read-only, run by the main session): "Ready to merge with fixes". Three findings were
  graded Important, two of them raised from its own minors, and all three were fixed test-first in one pass:
  - **I1, statuses never refreshed after a page's first load** (bcdb091). Pages asked only on their snapshot, and the
    tab menu loads each page once. An agent's sign-in check and a move's check updated nothing on screen, a new
    account said "Checking…", and a refused **Continue on** stayed disabled. Now any status that changes is sent to
    every page, a new account is checked at once, each page asks again when it gains the focus, and a refused
    **Continue on** can be clicked again. RED→GREEN, inside the tab menu with each page loaded once
    (`tests/test_accounts_tabs.py`): `test_a_sign_out_found_by_an_agent_shows_in_the_settings_tab`,
    `test_a_sign_in_outside_the_watch_shows_once_the_user_is_back`,
    `test_continue_on_comes_back_once_the_account_is_signed_in_again`,
    `test_a_refused_continue_on_can_be_clicked_again`,
    `test_a_refused_continue_on_in_mission_control_can_be_clicked_again` and
    `test_each_page_asks_for_the_statuses_again_when_its_tab_is_shown`.
  - **I2, raised from its minor 2: an API key could reach `claude` through Open Terminal** (c08d6bc). Terminal runs
    the command in your login shell, which may export one. Both commands now clear both variables: `env -u` on a Mac
    and Linux, `set "X="` in the Windows command line, `$env:X = $null` in PowerShell. RED→GREEN:
    `test_the_sign_in_command_never_hands_claude_an_api_key` (a real shell with both exported; the fake got
    `sk-test` before), `test_the_sign_in_command_quotes_every_part`,
    `test_open_terminal_on_a_mac_runs_the_quoted_command_in_terminal` and
    `test_open_terminal_on_windows_keeps_the_folder_off_the_command_line`.
  - **I3, raised from its minor 6: moving back always started fresh** (8ad4c52), because the first account still held
    the older copy. Now a file whose bytes start the newer one's is kept as `<id>.jsonl.before-<UTC time>`, and the
    newer copy takes its name. Any other file of that name still means the hand-over note. RED→GREEN:
    `test_a_move_back_sets_the_older_copy_aside` and `test_moving_back_and_forth_carries_the_conversation_both_ways`.
  - **Its verdicts on the rulings:** it agreed with Task 0 and with Task 15 (the README line, one suite run). It
    disagreed with Task 12: opening Settings on its own hid I1, so the I1 tests run in the tab menu. It agreed with
    the plan's decisions D1-D16: D4 with the retry-timeout nit, D5 within the spec but its cost is I3, D10 with the
    chat-name gap, D12 with the PowerShell-quote gap, D14 as no regression. It agreed the eight deferred minors are
    minor.
- **Whole suite:**
  - after the build: 1662 passed, 15 skipped (20 min 21 s);
  - after the fix pass: 1671 passed, 15 skipped (20 min 35 s).

## The merge

- **Into main:** b9d4a81, pushed by the main session.

## Rulings I made

Every decision taken on your behalf, in order, with what it costs if wrong:

- **Task 0:** Ruling: the hand probe runs later with the user (main session); CARRY_CONVERSATION stays True as the
  plan's default — the move falls back to the hand-over note by itself whenever the resume fails — cost if wrong: one
  failed resume per move until the probe sets it False.
- **Task 12:** Ruling: test_accounts_pages.py opens Settings by itself (open_page on /settings, then waits for the
  socket) instead of the plan's click on AI Home's #settings plus wait_targets for a new window — main's tab menu
  replaced popups (openTab moves a page opened by itself, test_home.py no longer has wait_targets) and HEAD's own
  test_home.open_settings does the same — cost if wrong: the accounts tests don't exercise Settings inside the tab
  menu's frame (test_tab_menu.py covers the tab itself). (The fresh review disagreed: this hid I1.)
- **Task 15:** Ruling: the README's Settings line keeps main's wording ("(a tab, and a button beside **Mission
  Control**)", "in every tab") and only adds "and your AI accounts" — the plan's line predates the tab menu and would
  have undone its words — cost if wrong: one README line differs from the plan's text.
- **Task 15:** Ruling: Step 4's whole-suite run happens once, after the final review (the user's order for this run),
  not twice — a 20-minute run twice buys nothing the later run doesn't — cost if wrong: a Task 15 regression is found
  an hour later, still before the report.
- **Final:** Ruling: Task 12's ruling (Settings opened on its own) is superseded for these probes: the I1 tests run
  inside the tab menu (/app); the Task 12 tests stay as they are, for Settings by itself — the coordinator's order
  after the fresh review — cost if wrong: none beyond the two kinds of test both running.

## The planner's decisions

The plan ruled where the spec left a choice (16 decisions, D1-D16), in nine groups:

- **Status (D1, D2):** `claude auth status` runs async, never raises, and says "Couldn't check: is Claude Code
  installed?" when Claude Code can't tell. The rows add `checked` and `command`.
- **The hand-over note (D3)** takes the tabs' titles and addresses from the server.
- **The Brain's retry (D4):** a refused call waits for the card's click for the rest of its own time limit, then runs
  once more; without a click it ends with "<name> hit its usage limit".
- **Never overwrite (D5, D6):** a copy goes in only where nothing has its name, and the same bytes count as copied. A
  resume "ends at once" before Claude Code's init event, or with "No conversation found". (D5's cost was I3.)
- **Moves (D7, D8):** a move needs an idle agent and a signed-in target, and a message sent meanwhile waits for it.
  Removing an account an open agent uses is refused.
- **Limits (D9, D10):** a limit pauses the agent: "paused", its queued messages wait, your next message tries the same
  account, and a turn that ends well clears it. The account's name stays in the rows, never in chat events.
- **One account (D11):** no picker, account chip or Tools picker.
- **The sign-in commands (D12):** PowerShell's form on Windows, a POSIX shell's elsewhere. Open Terminal on Windows
  keeps the folder in the environment. Linux has no Open Terminal.
- **Default, the tests and the probe (D13-D16):** Default's tools come from `$CLAUDE_CONFIG_DIR/.claude.json` when it
  is set; personal skills stay in `~/.claude/skills`; every test's Default folder is a throwaway; Task 0 is a hand
  probe, and both ways of carrying on are built whatever it finds.

## Deferred minors

- **From my review (the fresh review agreed they are minor):**
  1. a message sent while a move runs stays queued if that move is then refused (Work signed out between the page's
     refresh and the click): it runs only with your next message;
  2. the bridge logs unknown events and the `rate_limit_event`'s key names at INFO, and the app configures no logging
     handler, so the running app never shows them;
  3. Open Terminal answers "opened" as soon as `osascript` starts: a refused macOS Automation permission for Terminal
     isn't noticed (the row waits; **Copy the command** still works);
  4. a rejected `rate_limit_event` mid-turn shows the row paused, with its ask, while the turn is still finishing (the
     server refuses a move until the turn ends);
  5. an account's "at its limit until" stays for the app's run, even after a later turn on it ends well;
  6. `limits.from_text` knows only the spec's texts ("usage limit reached", "reached your weekly usage limit", "limit
     reached|<epoch>"); another wording becomes a plain error, and the idle row still offers **Continue on**;
  7. the sign-in check trusts `loggedIn: false`, so a Claude Code without a claude.ai login (Bedrock, Vertex) would be
     stopped as "not signed in" (unverified);
  8. if the first turn after a move is stopped by the sign-in check and a later resume then fails, that message is
     replaced by the hand-over note instead of being sent after it.
- **From the fresh review:**
  1. `_ps_quote` doubles only `'`, but PowerShell also treats U+2018–U+201B as single quotes: a path like O’Brien
     breaks **Copy the command**. Double those too;
  2. the Brain's card never clears after the reset (only a switch clears it). Clear it on the next good call there;
  3. the signed-out error puts the account's name in the chat. Moot now: the native-app design retires the watcher;
  4. nits: a deeply nested `accounts.json` raises RecursionError, against "never raises"; `RETRY_WAITS =(` in
     `platforms.py`; the Brain's retry gets a fresh full time limit;
  5. D14: with `CLAUDE_CONFIG_DIR` set, skills come from `~/.claude/skills`, not Default's folder. Pass Default's
     folder to the engine;
  6. on my minor 2: log the first unknown event of each type at WARNING.

## What only you can do

1. **Task 0, the probe on your Mac** (the plan's Task 0). In your own Terminal:
   - sign a new folder in with your second account (`~/.claude-aib-probe`, never `~/.claude-second`, the Claude app's
     data);
   - copy a conversation into it, resume it there, and note what a resume of a missing conversation prints;
   - the reviewer's additions: also resume a longer conversation, with thinking; record a real limit's wording, the
     `rate_limit_event`'s keys and any overage keys;
   - why it matters: `_not_resumed` catches only "ended before init" and "No conversation found", so a resume that
     starts and then fails at its first call isn't caught;
   - if the copy doesn't resume: set `CARRY_CONVERSATION = False` in `src/ai_browser/app/move.py`, and the README's
     **Continue on** line says a move always starts fresh with a hand-over note.
2. **The hand check, in the real app:**
   - start `uv run ai-browser app`. In Settings → Accounts, type a name, **Add**, then **Sign in** → **Open
     Terminal**, and sign in with your second account. Allow AI Browser to control Terminal if your Mac asks;
   - come back to AI Browser's window: the row turns **Signed in · <plan>** by itself. The window regaining the focus
     is not tested headless, so this step is the check;
   - AI Home's **Account** picker shows both accounts. Start a task on the second one: its row names that account;
   - when an account hits its limit, the row says "<name> hit its usage limit (resets <time>)". Click **Continue on
     …**: "Moved to … with its conversation", or "Started fresh on … with a hand-over note". Then move it back.
3. **On Windows,** run **Copy the command** in PowerShell and **Open Terminal** once. Both strings are checked only as
   exact text: no Windows machine has run them.
