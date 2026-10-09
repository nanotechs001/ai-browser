# Working inside iframes from another site (design)

Date: 2026-10-09. Status: the user approved the approach ("yeah plan it").

## What the user asked

- "one limitation I noticed, when tool is controlling the browser that have an iframe builder just like the GHL builder
  it cannot control the iframe builder" (GoHighLevel's page builder).
- After a hand test in the browser pane (the GHL header rebuilt by clicks): "based on this test what do you think is the
  best approach if the agent encountered an iframe that he needs to work on?" → the layered approach below, "yeah plan
  it".

## What the test showed (2026-10-09)

- GHL's whole builder is one iframe from another site: `page-builder.leadconnectorhq.com` inside `app.gohighlevel.com`.
  AI Browser's reader (`reader.js`) reaches an iframe only through `contentDocument`, which another site's frame refuses,
  so `observe` shows `frames: [… (cross-site, not readable)]` and the agent sees nothing inside (pinned today by
  `tests/test_observe.py`).
- Clicks, drags and keys are sent as real input at top-level screen positions (`Input.dispatchMouseEvent`), and they
  land inside any frame. Seeing is the only gap.
- By screenshots alone the header took ~140 actions; native `<select>` menus (GHL's Sticky, a column's layout) are
  OS-drawn and never appear in screenshots, so they couldn't be set at all.

## The design

### 1. Reading every frame of the agent's own tab
- The tab's CDP session turns on `Target.setAutoAttach` (`autoAttach: true, flatten: true, waitForDebuggerOnStart:
  false`, filtered to `iframe` targets), so each frame from another site (an out-of-process iframe) gets its own child
  session. Frames from another site that share the page's process need no session: the reader runs in them through
  `Page.createIsolatedWorld` with their `frameId`.
- The reader (`reader.js`, unchanged in what it reads) runs in each readable frame, in AI Browser's isolated world,
  and returns its rows with positions in that frame's viewport. The engine places them on the page: a frame's offset is
  its `<iframe>` element's content box in its parent, read by the parent's reader, plus the parent's own offset;
  a CSS transform or zoom on the iframe (a scaled builder canvas) is applied from the element's box versus its client
  size. Nested frames add up, at most 5 deep.
- Rows keep one number space for the page: the agent sees `[12] button "Book now" [page-builder]` as today's same-site
  frames are labelled. A row remembers its frame (its session or execution context), so `act` reaches it there.
- `observe`'s frames line names a frame from another site as readable (`[page-builder]`) when it was read, and keeps
  `(not readable)` only for a frame that couldn't be (still loading, crashed, detached).
- Limits: at most 20 frames read per observe; a frame whose box is under 20×20 px or not in view is skipped as today;
  the reader's time budget is shared, so a page with many frames can't stall observe.

### 2. Acting inside a frame
- `click`, `dblclick`, `hover`, `drag`: as today, real input at the element's top-level position (now computed with the
  frame's offset); before acting, the element's position is re-read in its frame, as same-site frames are today.
- `type`, `append`: focus the element in its frame, then `Input.insertText` (input follows focus across frames).
- `select`: sets a native `<select>`'s option inside its frame and fires `input` and `change`, as a person's pick does,
  without opening the OS menu (the case the screenshots couldn't do). Today's `select` step, reaching frames.
- `scroll` inside a frame: the frame's own element is scrolled into view (`scrollIntoView` in its frame), not guessed
  with the wheel.
- `check`, `uncheck`, `upload`: as today, in the element's frame.

### 3. What stays the same (safety)
- **Bot-check frames are never read or touched.** A frame whose address matches the check list (`CHECK_FRAME`:
  reCAPTCHA, hCaptcha, Turnstile, Arkose…) is never attached, never read, never acted in; it stays `[bot check box: the
  user ticks it]`. The engine refuses an action whose element sits in such a frame.
- **Page text is data**, from any frame, as today.
- **Only the agent's own tab's frames.** A child session belongs to its tab's owner; another client's or the user's
  other tabs' frames are never attached through the relay.
- **The relay** (`app/cdprelay.py`) gains `Target.setAutoAttach` on a page session and routes each child session to
  the client whose page it belongs to; a child session gets the same per-session policy as a page (`Runtime`, `DOM`,
  `Input`, `Log`, the listed `Page.*` methods), and the same address checks on navigation. Nothing else is opened.
  This is security-sensitive and gets the strict review.
- Downloads, file pickers, dialogs, permission prompts in a frame keep today's rules (the user's OK).

### 4. Fallback
- An editor drawn on `<canvas>` (Figma, Canva) has nothing to read: `observe` says so, and the agent keeps working from
  screenshots and positions, as today.

## Testing
- A throwaway headless Chrome (never the user's Brave) with the test server on two hosts (`127.0.0.1` and `localhost`,
  so the frame is from another site and runs out of process with `--site-per-process`): a fake builder page whose
  canvas is a scaled iframe with buttons, an input, a native `<select>`, a scrollable panel, and a nested frame.
- `observe` numbers the elements inside, with the frame's label; `click` and `type` land on the right element in the
  scaled frame; `select` sets the native option and fires `change`; scrolling reaches an element below the fold of the
  panel; a nested frame reads; a frame that detaches mid-observe is reported, not crashed on.
- A bot-check frame stays unread and an action into it is refused.
- The relay: `Target.setAutoAttach` allowed only on a page session; a child session's commands pass the page policy and
  nothing else; a client can't reach another client's child sessions; the existing relay tests stay green.
- The same through the relay (the app's agents' path) and directly (a Claude Code session's path).

## Out of scope
- Reading `<canvas>` content; frames in the user's tabs the agent wasn't handed; changing GHL's own UI.
