# The Brain's chat as a floating panel, with history; a profile indicator per agent (design)

Date: 2026-10-10. Status: for the user's review. The user's standing word: decide with the recommended option and say
each one; every decision below says why, and what it costs if it's wrong.

## What the user asked (verbatim)

- "problem i cannot click the agent in UI due to chat with brain is blocking it, ask AI let's change the UI, let's make
  it a popuo window inside the app instead of what we have not this way all promtped by brain is now a popup . We should
  also add a histort chat or new session chat with the brain."
- "And also on each agent add an indicator if the profile they are working is active and can be access or do they
  launch the browser themselve automatically if it is not opened?"
- Their answers: a **floating panel** (the office stays clickable behind it); when the Brain needs them the panel
  **opens itself**; history keeps the **last 50 chats**; "yes go" to the design below.

## What exists today

- Mission Control's composer (`ui/mission.html` `#composer`) has two modes: **Build a Mission** and **Ask AI**. Ask
  AI's talk (`#talk`: `#talk-log`, `#talk-status`, `#talk-notice`, `#talk-card`, `#talk-form`; `ui/talk.js`,
  `ui/composer.css` `.talk`) sits above the composer over the bottom of the office, and covers desks.
- The talk is kept in memory per page load (`brain/talk.py` `Talks`: `KEEP = 6` exchanges, forgotten after
  `FORGET_AFTER` = 15 minutes; one open proposal, one "which agent?" question, one hand-off per talk). Messages:
  `brain_ask`, `brain_confirm`, `brain_dismiss` (app-only), answered by `brain_answer`.
- Hand-off cards count down only while a page of a `HANDOFF_VIEWS` kind is visible (`server.py`).
- A saved agent's profile is "ready" when `ProfilePlace.ready(folder)` (`app/place.py`) knows its browser context;
  only the agent's settings show it ("ready" / "open it once"). Nothing ever opens a Brave window by itself.

## Decisions

1. **The talk leaves the composer.** The composer keeps Build a Mission only; its Ask AI tab becomes an **Ask AI**
   button (same place, same keyboard reach) that opens the panel. *Why:* the talk covered the desks. *If wrong:* the
   user opens the panel to talk, one click.
2. **A floating panel inside the window** (`ui/brainchat.js`, `ui/brainchat.css`, markup in `mission.html`): about
   380×520, bottom-right by default, dragged by its title bar (kept on screen; its place remembered per window size in
   `localStorage`, read and written in try/catch), closed with **×** or Esc. It is **not modal**: the office, the
   desks and the drawers stay clickable behind it. Under 900 px wide it fills the width at the bottom, 70 % of the
   height. It holds everything `#talk` held (log, status, notice, card, form, the voice button and note) — the same
   elements moved, so `talk.js` keeps working on them.
3. **The panel opens itself when the Brain needs the user**: a hand-off card, a suggestion card, or a "which agent?"
   question for Mission Control's talk. A countdown runs only while the panel is open and the page visible (the
   panel counts as a `HANDOFF_VIEWS` view only while open). *Why:* a countdown must never run unseen. *If wrong:*
   the panel pops up during other work; × closes it and holds the countdown.
4. **Chats are kept: the last 50.** Each Mission Control chat is a file `<home>/brain/chats/<id>.json` (0600): id,
   title (the user's first words, one line, at most 60 characters), created and updated times (ISO 8601 UTC), and its
   exchanges (said, answer, time), at most 200 exchanges. Saving a 51st drops the least recently updated. Only the
   app writes them; pages ask with app-only messages. The inbox's per-item talks and the floating ⌥Space chat are not
   kept (unchanged).
5. **New chat and History** in the panel's header. **New chat** starts an empty chat (a new talk id). **History ▾**
   lists the chats, newest first, title and date; a click reopens one; **Delete** asks first (the `confirm.js`
   dialog) and removes its file. A reopened chat shows its whole log; the Brain gets only its last `KEEP` exchanges as
   context (today's cost). Cards are never re-armed: a past hand-off, suggestion or question shows as text ("Sent to
   agent 2", "Cancelled", "Not answered").
6. **New page messages**, app-only in `MESSAGE_RULES` with their copy in `tests/test_watcher_rules.py`: `brain_chats`
   (list), `brain_chat_open` (one chat's log), `brain_chat_new`, `brain_chat_delete`. A chat's id is the talk id the
   page uses; the server keeps talk ids it made and refuses unknown or malformed ones (`_TALK_ID`).
7. **A profile indicator on each agent**: the Agents page's cards, each run's desk nameplate and its drawer show a dot
   and a word: **Ready** (green: the profile's context is learned), **Open it once** (amber: open a Brave window of
   that profile), **Brave not connected** (grey). Hover (and focus) says what to do. "Settings' choice" shows the
   profile Settings picks. One-off runs show it in their drawer only. It updates with the agents and Brave messages
   the pages already get (within about 30 s of the user opening a window). Colours from `theme.css` tokens only.
   Nothing opens Brave by itself (unchanged).

## Safety rules
- **Stays:** only the user's own clicks and words reach the Brain from the panel; a hand-off counts down only while
  the user can see it; page and message text is data, set with `textContent`; no inline script or style; the Brain
  and templates never write a chat file; tests never touch the user's real browsers, `~/.ai-browser`, `~/.claude` or
  port 8792, and never run the real `claude`.
- **New:** chat files hold the user's words and the Brain's answers: 0600, in `<home>/brain/chats/`, never sent
  anywhere but AI Browser's own pages.

## Testing
- Pages (throwaway Chrome, the `stack` fixture): Ask AI opens and × / Esc close the panel; a desk behind it is
  clickable while it's open; it can be dragged and stays on screen; a hand-off opens it and counts down only while
  open; New chat empties the log; History lists, reopens (old cards shown as text, never live) and deletes after the
  question; the composer no longer has the talk; narrow width layout; the indicator's three states on a card, a desk
  and a drawer.
- Server: chats are written 0600, capped at 50 and 200 exchanges, listed newest first, deleted; a reopened chat gives
  the Brain only its last `KEEP` exchanges; the four messages are app-only rows; unknown talk ids are refused.
- Room height: the office's step-card and composer-height tests stay green (the composer gets shorter).

## Out of scope
- The Brain's inbox drawer, the floating ⌥Space chat, and the inbox items' talks: unchanged.
- Searching chats, exporting them, or naming them by hand.
