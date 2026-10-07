# After the new look's hand check: report

Date: 2026-10-07. Everything here is merged on `main` (a9bbdf0) and the user's app was restarted on it.

## What the user asked, and what they chose

- **The look's polish** (a screenshot with five boxes): "just remove the one i boxed also the face of worker chibi is
  covered you got the incorrect placement of it the remove the grid background and wall too. For usage i want you to
  display the current session limit and weekly limit bars for my account connected".
- **Permissions:** "is there option now to always allow or skip permission when agent is working?" → chose
  **Auto-approve in its folder**.
- **Windows:** "the previous version is keeping opening a new window of browser instead of using the first window of
  browser" → chose **one window per agent**; a spike showed it can't be done quietly, then chose **fewer tabs per agent**.
- **More polish** (a screenshot with arrows): "remove this below the globe graphic … add a watch button on the right side
  of hand over … allow user to be able to paste images on any chat".
- **Docker:** "any way we can integrate it without using the docker?" → chose **all three without Docker** (design
  `docs/superpowers/specs/2026-10-07-no-docker-design.md`, approved: "yeah"; its plan is the next step).

## What changed for the user

- **Mission Control:** no heading, lamp, sign, big plants, keys line, grid, wall, or rings and disc under the globe; each
  chibi sits behind its laptop with its whole face showing; **Watch** beside **Hand over** (brings the agent's tab to the
  front).
- **The Usage card:** each signed-in account's **Current session** (5-hour) and **Weekly** bars, with reset times, from
  what Claude Code reports with each request (`rate_limit_event` → `unifiedWindows`, found by a one-request probe on
  2026-10-07, Claude Code 2.1.292). The last reading is kept in `~/.ai-browser/usage.json` with its time; a passed reset
  is never shown as a number.
- **Fewer tabs per agent:** at most 2 tabs of an agent's own; a third reuses the one used least recently. Handed tabs
  never count and are never reused; a tab held for a bot check is never reused under the user.
- **Auto-approve in its folder:** a per-task switch (Build a Mission, and the agent's drawer).
  - On a Mac: file edits inside the folder, and commands from an allow-list of ordinary uses (reading and listing,
    making files inside the folder, everyday git, build/test/lint runners, running a script file inside the folder) run
    without a card; Claude Code's sandbox holds what they do.
  - On Windows and Linux: file edits only; every command keeps its card.
  - Always a card: deleting, sudo and launchers, inline code, anything outside the folder, force-push and discarding
    git work, edits to `.git`/`.claude`/`.mcp.json`/`.husky`/`.vscode`/`.idea`/`.pre-commit-config.yaml`/the hooks
    folder, reaching a site, the user's own tools. Only the user's click turns it on (never the Brain, templates or
    sessions). Each auto-run action is marked "auto".
- **Pictures in every chat:** paste (⌘V) or drop into Build a Mission, an agent's chat (drawer and AI Home), AI Home's
  New task and the floating chat's New task; they're attached like Attach (10 per message, 20 MB each) and placed in the
  agent's folder under `attachments/`. Spreadsheet cells paste as text. Ask AI and Use a Template show a note.

## How it was checked

- Each change built test-first by a fresh builder, reviewed (security-sensitive ones by the most capable model), fixed,
  re-reviewed, then the whole suite.
- **Auto-approve** had two security reviews and a hostile probe of about 290 commands built from the allow-listed
  programs: no command on the must-never list ran without a card.
- **Suites:** the polish 2226 passed; the polish with fewer tabs 2244 passed; auto-approve with the globe/Watch/pictures
  2466 passed (the 8 Docker sandbox tests that collided with a parallel run passed when run alone: 16 passed).

## Rulings made on the user's behalf (each with what it costs if wrong)

- **The usage probe:** run with the user's own login (one tiny request) — it was the only way to learn what Claude Code
  reports — cost: a sliver of the user's limit.
- **Polish:** all three big plants removed, not only the one boxed — a cleaner room — cost: none (the desks keep theirs).
- **Polish:** the room sits low in its space (`LOW = 0.75`), so 16–20 desks' names stay readable — cost: one desk leaves
  empty navy under the switch (hand check).
- **Polish:** the failed pose leans instead of dropping, so its face stays above the lid — cost: none.
- **Polish:** at the limit the bar is red and the words amber — cost: one colour.
- **Polish:** a reading is shown after a restart with its time, and a passed reset never as a number; a fresh reading
  needs an agent's request (the app never spends the user's limit on its own) — cost: "Updates when an agent works"
  until the first request.
- **Windows:** the one-window-per-agent spike was stopped (no CDP way keeps the user's focus); the user chose fewer tabs
  instead — cost: none.
- **Fewer tabs:** "oldest" means used least recently; `tabs new` is capped too; a failed load in the reused tab switches
  back and says which tab it tried — cost: none.
- **Auto-approve:** commands only from an allow-list (a gap costs a card, never a silent run); file edits only where
  the sandbox is off; guarded paths and `git config` writes always ask; the mark fails closed; a shell that moved stops
  auto until restart; `git commit --amend` keeps auto — cost: a few more cards than "everything in the folder".
- **Pictures:** AI Home's boxes included ("any chat"); a page may stage 20 files, 10 per message; a send with files waits
  for the app's answer (no timer); spreadsheet cells are text; the Brain keeps a note instead of taking pictures — cost:
  none.

## Deferred minors

- The Usage card with three accounts is tall (~380 px); a reading without a reset time never ages out.
- `touch x` / `mkdir run` get a card under auto (a first argument that is a runner word).
- The LEAVE_BLOCKED words still say "confirmed=true", which `open` doesn't take.
- AI Home's New task keeps its 10 s wait for `created`.
- A real clipboard (Finder files, Excel) is checked only with synthetic events: hand check.

## The user's hand check

1. The laptop at normal zoom (does it still read as a laptop?); one desk's empty space under the switch.
2. The Usage card after a mission (session and weekly numbers and reset times).
3. Auto-approve on a Mac task: ordinary commands run with the "auto" mark; a delete still asks.
4. Watch; paste a screenshot into an agent's chat; paste spreadsheet cells.
5. An agent that opens several tabs: at most two windows.
