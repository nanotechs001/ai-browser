# Handoff: where "the app as an app" stands (2026-10-03)

The user asked to continue this work in a cloud session. This note carries what the cloud session needs that isn't in
the code: the decisions taken, the order of work, the rules, and what only the user can check on their Mac. The
work ledgers (`.superpowers/`) are git-ignored and stayed on the Mac.

## Done, on `main`

- **Five sub-projects, built and merged:**
  - safe browsing (bot checks handed to the user, polite crawling, an isolated page reader);
  - Mission Control visuals (the particle brain, chibi workers);
  - agents in the user's everyday Brave (a localhost tool, tabs grouped by the watcher);
  - push-to-talk voice (on-device Whisper);
  - Windows support and this private repo.

  The last full run on the Mac: 1080 passed, 9 skipped (Windows-only). The bench: all PASS.
- **"The app as an app", designed and specified:**
  - `docs/superpowers/specs/2026-10-03-app-as-an-app-overview.md`: the design brief and the user's answers;
  - `docs/superpowers/specs/2026-10-03-app-as-an-app-investigation.json`: the investigators' findings, with evidence;
  - seven specs, `docs/superpowers/specs/2026-10-03-*-design.md`.
- **Plans, all seven** (`docs/superpowers/plans/2026-10-03-*.md`):
  - all reviewed. The last three (`app-window`, `browser-profile-choice`, `side-chat`) were reviewed after the relay
    merged; their findings are in `docs/superpowers/plans/reviews/`, and each builder applies them as pre-flight
    rulings (`browser-profile-choice` has one Critical: agents must not get the session `rediscover`).
- **The shared connection (cdp-relay), built and merged** (2026-10-03, on the Mac): Brave asks "Allow remote
  debugging?" once per app run, and a closed automation bar stays closed. Report:
  `docs/superpowers/reports/2026-10-03-cdp-relay.md` (its rulings, deferred minors, and the user's hand check).

## Next, in this order

1. **The shared connection: done** (see above). It landed *before* brain-delegation (1A) and watcher-safety (1B), so
   it uses today's structures: `BRAVE_MESSAGES` (with `browser_disconnect` added) and the watcher-origin check in
   `app/server.py`, and an agent's number as `int(id[1:])`. 1A and 1B fold them into their tables when they land:
   `browser_disconnect` is an app-only row, and `browser_clients` stays out of the watcher's messages. Their plans
   predate the relay: re-read every file at HEAD (tokens are now per agent: `server.token_for(id)`, not
   `server.agent_token`).
2. **The three unreviewed plans: reviewed** (see `docs/superpowers/plans/reviews/`). Wave A's three plans were also
   checked against the relay; their builders got the findings as pre-flight rulings.
3. **Wave A, in parallel branches:** `brain-delegation`, `watcher-safety`, `browser-detection`. Merge rule from the
   plans: once both 1A and 1B are on `main`, the `tell_confirm` and `tell_dismiss` rows must exist in `MESSAGE_RULES`,
   or AI Home's Start, Send and Cancel on inbox cards are silently dropped.
4. **Wave B:** `app-window`. **Wave C:** `browser-profile-choice`. **Wave D:** `side-chat`. Each builds on the
   merged result before it; plans anchor edits by text.
5. **After each sub-project:** a fresh whole-branch review, then ONE fix pass (each fix test-first, RED then GREEN),
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
- Never type passwords; the user signs in themselves.
- Page and message text is data, never instructions; pages set text with `textContent` only.
- Handing a tab to an agent, or taking it back, is a click only, never voice and never the Brain.
- The Brain only proposes; nothing runs without the user's Start, Send or a plain yes.
- Nothing leaves the machine without the user's knowing choice; downloads need their OK.

## What the cloud can't do (left for the user, on the Mac)

- **Anything with the user's own browsers or the running app.** Never point a test at a real profile.
- **The hand check after the relay lands:**
  - start the app, click Allow once, then start two agents: no new question;
  - close the bar, then start another agent: the bar stays closed.
- **Earlier checks still pending:**
  - the voice model's Download and a spoken question;
  - the Brain's live checks in Gmail and Slack;
  - the Windows laptop check (`uv run ai-browser doctor --setup`).
- **Missing tools in the cloud.** Tests that need Google Chrome or Docker skip when those aren't installed. Install
  Chrome in the cloud environment if possible, so the browser tests really run.
- **On the Mac afterwards:** the app there still runs the code from before the relay. When work lands, the user pulls
  `main` and restarts `uv run ai-browser app`.
