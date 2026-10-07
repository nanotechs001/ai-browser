# Agent powers: report

Date: 2026-10-05 (written 2026-10-07 from the builder's ledger and hand-backs: subagents can't write report files).

## What the user asked

- **The request:** "make it so they are able to run bash command and able to summon sub agent. This app will be the
  replacement of the claude code app, an all in one app workflow automation best browsing capability for faster
  navigation and all feature of the claude app, should be also able to pull the claude artifacts."
- **Their answers:** "Ask first, with "always allow" (Recommended)", "Pick a folder per task (Recommended)", "Yes, both
  (Recommended)" (Web Search and Web Fetch); then "good proceed" to the spec.
- **Later:** "dont ask me for input for now use any recommended for decisions."

**The work:**
- **Spec:** `docs/superpowers/specs/2026-10-05-agent-powers-design.md`.
- **Plan:** `docs/superpowers/plans/2026-10-05-agent-powers.md`, 15 tasks. The planner dry-ran it on main: 1941 passed.

## What changes for the user

- **Agents get Claude Code's own tools,** alongside the browser:
  - Bash, Read, Edit, Write, Glob and Grep;
  - Web Search and Web Fetch;
  - sub-agents;
  - the to-do list.
- **A Folder picker** sits next to the model and account when starting a task: No folder (the agent's scratch
  folder), recent folders, or Choose… (the system's dialog in the app).
- **Trust:** "Trust this folder?" the first time. A trusted folder loads its own `CLAUDE.md`, agents and settings; an
  untrusted one loads nothing of its own.
- **Approval cards:**
  - a card shows the exact command, a red/green diff, the path or the site;
  - its buttons: **Allow once · Always allow for this folder · Deny**, and Deny can carry a note;
  - **don't ask:** reads and searches inside the folder, the to-do list, starting a sub-agent, and `ls`, `cat`,
    `pwd`, `git status`, `git diff` and `git log` (where the folder's git config runs nothing);
  - **ask every time** (never "always"):
    - `rm`, `chmod`, `sudo` and other launchers, and inline code;
    - compound commands and substitutions;
    - anything that writes outside the folder;
    - deleting or work-discarding uses of `find` and `git`;
    - edits to `.git`, `.claude` and `.mcp.json`.
- **Refused folders:** `/`, the home folder itself, `~/Library`, system folders, `~/.claude`, and AI Browser's own home.
  They're matched by identity, so a case variant is refused too.
- **Sub-agents and to-do lists** show live in the agent's drawer ("3 / 5 steps"), and each action gets a badge.
- **Settings → Permissions** lists the rules and trusted folders, with Remove.

## How it was built and checked

- **The build:** branch `powers` from 2b0a68d; every task's test was seen failing for its stated reason, then passing.
  - **Task 1:** the hand probe, deferred (it needs a Claude login the user signs in by hand). `tests/probe_powers.py`
    is written and compiled, not run.
  - **Task 2:** `classify` and `rule_for`, 489b9ea.
  - **Task 3:** the card, 5869e0e.
  - **Task 4:** rules, refused folders and settings, 6ff88cc.
  - **Task 5:** the bridge starts Claude Code with its own tools, 8d1b4d6.
  - **Task 6:** the stream (badges, to-do list, sub-agents), 248a953.
  - **Task 7:** every request decided, 3c97346.
  - **Task 8:** agents, 67a5f8d.
  - **Task 9:** the server, 9 new app-only messages, a1e5606.
  - **Task 10:** the card on the pages, cb5ece4.
  - **Task 11:** badges, plan and sub-agents on the pages, bb52e6e.
  - **Task 12:** `chooseFolder` in the Electron app, 17ba411.
  - **Task 13:** the Folder picker and trust question, eb5ee18.
  - **Task 14:** Settings → Permissions, 85449a2.
  - **Task 15:** the README, 3272c42.
- **The builder's self-review:** three Important findings, fixed in 0336b8f, each with a test that failed first.
  - **Short options:** a path packed into short options (`curl -so/tmp/x`) read as inside the folder.
  - **Stop:** after Stop, a harmless or ruled request could still run.
  - **The picker:** it showed "No folder" after Choose….
- **The fresh review** (opus, read-only, about 200 hostile commands through `classify`): "Ready to merge, with one fix
  recommended". Re-graded by effect, one fix pass of three, in 9ec59cb:
  - **F1:** a case variant of a refused folder was allowed on a case-blind disk. Folders are now compared by identity
    (device and inode), and containment too. Tests: `test_a_case_variant_of_a_refused_folder_is_refused`,
    `test_containment_is_blind_to_case_where_the_disk_is`.
  - **F2:** `find -delete` or `-exec`, `git clean`, `git reset --hard`, `git checkout --`, `git restore`, `git push
    --force` and `git branch -D` could be "always allowed". They now ask every time.
    Test: `test_deleting_files_or_discarding_work_never_offers_always` (19 cases).
  - **F3:** padding could push a command's end off the card. Runs of spaces show as `⟨N spaces⟩`, and the card wraps.
    Tests: `test_padding_can_never_push_a_commands_end_out_of_sight`, `test_every_page_wraps_the_command_on_its_card`.
  - **README:** "Always allow trusts the whole program".
- **The reviewer's verdicts:** all four provisional values sound; both Final rulings accepted as Claude Code's own
  "always allow" semantics; all deferred minors agreed.
- **Suites:**
  - **after the build:** 1 failed, 1967 passed. The failure was a live-view frame-timing flake: 3/3 alone, the branch
    doesn't touch it;
  - **after the fix pass:** 1993 passed, 11 skipped.
- **Merged** into main as 852cd30 (on GitHub; the user's running app was left alone until they restarted it).

## Rulings made on the user's behalf

- **Setup:** Ruling: the branch is `powers` (worktree made by the main session), not the plan's `agent-powers` — the
  main session created it and merges it — cost if wrong: none (a name).
- **Task 1:** Ruling: the probe is deferred to the user (it needs a hand sign-in); the build uses the safest values
  until it runs — R1 SANDBOX = False (the cards are the guard; the sandbox code path stays, off), R2
  UNTRUSTED_SOURCES = "" (nothing of the folder's own loads), R3 ASK_ALL = True (every use goes to the app's own
  check), R4 SUBAGENT_TOOL accepts both "Agent" and "Task" — cost if wrong: a follow-up fix after the probe; never a
  looser default.
- **Task 1:** Ruling: tests/probe_powers.py written verbatim and compiled; its two refusal runs (`/` and `~`) were not
  run — they're left for the user with the probe — cost if wrong: none.
- **Task 2:** Ruling: R4 is held as SUBAGENT_TOOL = "Agent", while every reader takes both "Agent" and "Task" — the
  plan's default, and nothing downstream depends on the name — cost if wrong: if 2.1.263 knew only "Task", no
  sub-agent tool would be offered until the probe's one-constant fix.
- **Task 12:** Ruling: main.js's header now says its pages may ask it for "three things" — the comment would
  otherwise contradict itself — cost if wrong: none.
- **Task 15:** Ruling: the README's sandbox paragraph says commands don't run in a sandbox and the cards are the guard
  — R1 is False until the probe — cost if wrong: one README line after the probe.
- **Task 15:** Ruling: this report is written by the main session from the hand-backs — subagents can't write report
  files — cost if wrong: none.
- **Final:** Ruling: an "Edit" rule plus a run rule lets an agent change what that command runs (a package.json
  script) and run it without a card — Claude Code's own "Always allow" carries the same trade-off; edits to .git,
  .claude and .mcp.json still ask every time — cost if wrong: a prompt-injected agent holding both rules in a folder
  could run code of its choosing there.
- **Final:** Ruling: after an allowed `cd`, saved rules still answer and relative paths are still judged from the
  task's folder (the harmless list is voided) — the plan decided it, and the `cd` itself needed a click — cost if
  wrong: a ruled command could run in a subfolder.
- **Final:** Ruling: per-program rules can't see inside a program's own options (curl -T/-d @/-F @, sed 'w', tar
  entries, make) — accepted as Claude Code's "always allow <program>" semantics; the README says so — cost if wrong:
  after one Always for such a program, a prompt-injected agent could read or send a file through it without a card.

## Deferred minors

- The Brain's `talk.py` `tool_label` still words a power card as "permission to use a tool", while scene.js says the
  card's title.
- Removing a rule from, or untrusting, a folder with no entry creates an empty "Not asked yet" entry.
- Rules keys use realpath without case folding, so on a case-blind disk the same folder in another case is a second
  entry (asked again: the safe side).
- Recent folders aren't re-broadcast when a task starts in a folder.
- A program run by an absolute path outside the folder (`/tmp/x.sh`) is offered Always.
- Glob or Grep inside the folder can list file names through a symlink that leaves it (reading those files still
  asks).
- The Bash card doesn't say when a command runs in the background.
- `Rules.add` validates a rule's shape only (inert: there's no way to inject one).

## What only the user can do

- **The deferred probe:**
  1. sign in a throwaway Claude login:
     - `mkdir -p /tmp/aib-powers-probe/config`;
     - `CLAUDE_CONFIG_DIR=/tmp/aib-powers-probe/config claude`;
     - `/login`, then `/exit`;
  2. `uv run python tests/probe_powers.py /tmp/aib-powers-probe > /tmp/aib-powers-probe/report.json`.

  What each answer changes in `src/ai_browser/app/powers.py`:
  - **R1:** `SANDBOX = True` if the sandbox held;
  - **R2:** a redesign if `""` loads anything;
  - **R3:** `ASK_ALL = False` if the ask rule doesn't send every use to the app;
  - **R4:** `SUBAGENT_TOOL = "Task"` if only Task is listed.

  Afterwards: `/logout`, and delete the folder.
- **Hand checks in a real project folder:**
  1. Choose… and the trust question;
  2. Allow once, then Always, then Remove the rule in Settings;
  3. Deny an edit with a note;
  4. a sub-agent and its to-do list, and Stop;
  5. the floating chat's Folder picker;
  6. if the sandbox turns on, `touch ../outside.txt` fails.
