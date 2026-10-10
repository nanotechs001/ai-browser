# Report: the Brain's chat as a floating panel, its History, and each agent's profile indicator

Spec `docs/superpowers/specs/2026-10-10-brain-chat-panel-design.md`, plan `docs/superpowers/plans/2026-10-10-brain-chat-panel.md`. Built subagent-driven on 2026-10-10 on branch `brainchat` (from main 96375f0): 7 tasks, each reviewed (opus for the security-sensitive ones), a pre-review fix wave, a final whole-branch review (opus) and one fix wave, re-reviewed.

## Result
- Whole suite at 1e34b4c: **2871 passed, 10 skipped, 111 deselected** (`-m "not docker"`).
- Final review: 0 Critical, 3 Important (fixed, re-reviewed), 6 Minor.

## Rulings and deferred items (from the build's ledger)
- Task 1: Ruling (re-graded by effect): fix Minors 1–2 — CHAT_ID with fullmatch (a trailing newline passed $); catch RecursionError in get() so a deeply nested file can't crash a listing or a Brain answer; and drop test_brain_chats.py's unused EVENTS import — cost if wrong: none
- Task 1: minor (deferred): every add parses up to 51 files to trim; settle drops an outcome if its write fails; card_ended edge cases untested
- Task 2: Ruling (re-graded, ⚠️ → fix): a reopened chat must never re-arm a card even in the same run — server-side: brain_chat_open (and brain_chat_new) drop the talk's live proposal/asking/handoff for that id before answering, so an old card's id + yes can't run it (the spec's 'cards are never re-armed'; don't rely on the page) — cost if wrong: a card left open when the user switched chats can't be answered after switching back
- Task 2: Ruling: fold Minor 1 — delete also forgets the talk in memory (Talks.forget), so a deleted chat's words never reach the Brain again; and Minor 4 — delete's error in fixed words — cost if wrong: none
- Task 2: minor (deferred): restore reads the file every question; the list broadcasts to every app page; _made unbounded; delete broadcast/open-deleted untested
- Task 2: Ruling: a reopened chat unlinks (not cancels) a live hand-off: the hand-off keeps its own card and countdown, seen and answerable there — cost if wrong: a yes typed in the reopened chat doesn't reach it
- Task 3: Ruling I-1: fix — the panel's default place never covers the right column or an open drawer (at ≥1280 it sits left of the right column; a drawer open moves it or the drawer sits above it); tests with real clicks on #current-chat and hits() at the drawer body's centre — why: the user's own complaint was not being able to click agents — cost if wrong: none
- Task 3: Ruling I-2: fix — open() scrolls the log to the newest line; test close/reopen
- Task 3: Ruling I-3: carried into Task 4 now (it owns onToggle): the chat opens itself only for a hand-off or card id it hasn't shown yet, never on a known card's change to waiting
- Task 3: minor (deferred): LINES unused in test_chat_panel.py; stale composer.js:600 comment
- Task 2: minor (deferred): forget can race an in-flight answer that recreates the talk (harmless: delete → no write; reopen → the card was just asked for)
- Task 4: Ruling: a held countdown stays held and waits for Send when the chat reopens (the existing hand-off rule: a hold never restarts by itself) — cost if wrong: one click on Send
- Task 4: minor (deferred): two fixed 0.5 s sleeps before asserting visible() False; shownCards at module scope; link.seen name
- Task 3: Ruling: a chat the user dragged may sit over the drawer (900–1279 px): the user put it there — cost if wrong: they drag it away
- Task 3: minor (deferred): 900–1100 px with the drawer open, the default chat covers part of the left menu
- Task 5: minor (deferred): #chat-list aria-label on a role-less div; words sent before the first automatic brain_chat stay unkept until New chat
- Task 6: Ruling: fix — look() returns True when it clears a non-empty learned set on a new connection (so the existing broadcast fires); also don't report ready for a connection the place loop hasn't looked at yet; tests in test_place.py (new connection with a learned profile → True, ready False) and a socket test (learn, lose, reconnect → ready False on the page) — why: a false 'it will work' is exactly what the user asked the dot to prevent — cost if wrong: none
- Task 6: Ruling: fold Minor 1 — 'Settings' choice' with none chosen shows Ready only when Brave has a default context (default_ready), else Open it once — cost if wrong: none
- Task 6: minor (deferred): hint display:none for screen readers on cards; drawer's focusable span has no role; snapshot rebuild per broadcast; grey flash before first saved_agents
- Ruling: one fix wave now (opus) for: Task 6's Important + Minor 1; the stale test_powers_pages test (drop the ask/template loop, keep the build check); Task 5's carries (focus after a History click/Delete, 'That chat is gone' shown, Esc closes History first) — then the final whole-branch review
- Ruling (final 1): the chat moves aside for #agent-panel exactly as for #drawer (all widths), hit-tested
- Ruling (final 2): under 900 px a card counts as seen only when the chat is open and no drawer/agent panel covers it; re-report when they open/close (the card then waits for Send)
- Ruling (final 3): no profile dot for agents with web 'none'
- Ruling (final, adopted): a counting hand-off keeps counting after New chat/reopen (Brain's, its card stays on top); README says typed no/other words reach it only in its own chat
- Ruling: fold Minors — clear shownCards on snapshot; README: the last 6 exchanges go to Claude as context; History's list never covers a fresh hand-off card (close it when a card arrives)

## Hand checks (the user's, in their own app)
1. Ask AI opens the chat beside the office; agents, the right column, an open drawer and an agent's settings stay clickable.
2. Drag the chat; close with × or Esc; reopen at the newest line.
3. A Brain hand-off opens the chat and counts down; × holds it until Send.
4. New chat; History lists past chats; reopen one (old cards as text); Delete asks first.
5. Each agent's dot: Ready / Open it once / Brave not connected; quit and reopen Brave: no stale Ready; a No-web agent shows none.
