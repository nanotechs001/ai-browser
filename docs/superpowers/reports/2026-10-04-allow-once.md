# Report: Brave asks once, even when the answer comes late (allow-once)

Date: 2026-10-04. Branch `allow-once`, cut from `main` at d022fd2 (after the relay merged).

## What the user asked

- "Brave will still ask "Allow" for each agent and the bar will keep coming back. resolve this, it should only ask
  once and display once"
- "after you finish make sure you test, the debugging alllow should only appear once then the notice for debugging
  should only appear once too. Apply any neccesrry changes in order to fix it. DO it if you still see it"

## What was still wrong after the relay

The relay (2026-10-03) already gave everyone one shared connection. But it gave up on Brave's question after 60 s,
and in Chromium that question isn't tied to the handshake that asked:
- **The question has no time limit** (`devtools_connection_dialog.cc`). Allow answers yes. Cancel, "Disable" and
  closing the question all answer no.
- **A late Allow pins the bar.** A client is added only once the user allows (`devtools_http_handler.cc`,
  `HandleDebuggingApproval`). When the handshake has already closed, that client belongs to a dead connection and never
  leaves. The count of connections stays above zero, so the automation bar stays, or comes back, until Brave restarts
  or the switch is turned off and on.
- **The next try asks again.** After the app gave up, Connect or Try again opened a second question.

That is what the user's Brave did on 2026-10-04 at 00:51: the app asked, nobody answered within 60 s, and the app
closed its handshake with the question still on screen.

## What changed

- **7b332c0, the relay waits for the answer.**
  - Its handshake has no time limit.
  - Agents and sessions wait at most 60 s. Then they hear: 'Brave is asking "Allow remote debugging?" for AI Browser:
    ask the user to click Allow there, then try again'.
  - Connect and Try again join the same question.
  - A handshake that ends with no answer (Brave quit) is "lost", not "refused".
- **66e3088, the real-browser test** (throwaway Chrome and Brave in approval mode): one question for the app, two
  agents, a session and a second Connect, and the question stays open while nobody answers.
- **fe53d36, sessions without the app do the same.**
  - A call waits 60 s and says Brave is still asking.
  - The next call joins the same handshake.
  - A session that ends closes it.
  - AI Home's "not allowed" note now says only "Brave said no.", the one way to get there.
- **The relay spec's amendment:** `docs/superpowers/specs/2026-10-03-cdp-relay-design.md`, "Amendment (2026-10-04)".

## Tests

Each test was seen failing first, for the stated reason, and then passing:
- `test_the_question_stays_open_until_the_user_answers` (test_cdprelay). RED: the client heard "Brave said no" after
  the wait.
- `test_a_question_cut_short_by_the_browser_quitting_is_lost_not_refused` (test_cdprelay). RED: "refused".
- `test_no_answer_keeps_the_one_question_open` (test_bravelink). RED: a second question (2 handshakes for 1).
- `test_one_question_for_the_app_two_agents_and_a_session` (test_approval_mode, Chrome and Brave). RED with the old
  relay in both: the state went to "refused".
- `test_a_direct_question_stays_open_and_the_next_call_joins_it` (test_engine). RED: the session gave up with a
  TimeoutError.
- `test_a_session_that_ends_while_brave_asks_leaves_no_connection_behind` (test_engine). RED: the connection stayed open.
- `test_the_browser_card_says_one_question` (test_home). RED: "said no, or nobody answered."

`test_deny_is_refused_and_never_retried` replaces the old parametrized test's Deny case unchanged.

**Affected files:** test_cdprelay, test_bravelink, test_engine, test_home, test_app_server and test_cdprelay_chrome:
242 passed, 1 skipped (Windows only). The whole suite runs on `main` after the wave A merge.

## Rulings

- Ruling: the relay's handshake has no time limit, and `allow_wait` limits only a client's wait — the question has
  none, and a handshake given up on causes both of the user's symptoms — cost if wrong: a browser that never answers
  keeps the app "asking" until the user acts in it (Allow, Cancel, or quitting Brave).
- Ruling: a handshake that ends with no answer at all is "lost", not "refused" — nobody said no, and "lost" offers
  Connect — cost if wrong: one click.
- Ruling: a session without the app keeps one waiting handshake per browser address across its calls, and closes it
  when it ends — cost if wrong: a waiting handshake lives as long as its session.
- Ruling: the fake port gains the answer "vanish" (the handshake ends with no answer) for the cut-short test — cost if
  wrong: none (a test helper).

## Final review and the fix pass

A fresh reviewer (opus) said "Ready to merge" and listed five Minor findings. It checked the fix against Chromium's
sources and a real headless Chrome (one question held 70 s), and all five mutations it was asked to try were caught.
Re-graded by what the user gets, these were fixed, each test seen failing first:
- **Fixed: quitting while Brave asks leaves the question on screen.** An Allow there afterwards pins the bar (the
  user's exact symptom). The app now prints at quit: 'Brave is still showing "Allow remote debugging?" from this AI
  Browser: click Cancel there…'. Test: `test_quitting_while_brave_asks_says_to_click_cancel`.
- **Fixed: a session that asked by itself before the app started.** After Allow, it kept its own connection unused, so
  Brave counted two and its bar came back whenever either one opened or closed. Once the app serves the session, that
  connection is closed (a question still open is left to the user, and closed the moment it is allowed). Test:
  `test_a_session_that_asked_before_the_app_started_holds_no_second_connection`.
- **Fixed: two behaviours no test pinned.** A dropped direct connection is asked for again, never reused, and a
  connection allowed after the last call closes with the session. Tests:
  `test_a_direct_connection_that_dropped_asks_again_instead_of_reusing_it` and
  `test_a_connection_allowed_after_the_last_call_closes_with_the_session`. Each failed under its mutation.
- **Fixed:** the fake port no longer drops a waiting handshake after 10 s (Brave doesn't); `bravelink`'s docstring and
  the spec's list of 409 texts; and the session-end test's name (it checks the session's own socket).

**Affected files after the fix pass:** test_cdprelay, test_bravelink, test_engine, test_home, test_app_server,
test_cdprelay_chrome, test_app_run and test_approval_mode: 266 passed, 1 skipped (Windows only).

**Rulings on what the reviewer set aside:**
- Ruling: if the window holding Brave's question closes without an answer and Chromium doesn't count that as a Deny
  (not in the sources read), the relay waits until Brave quits — stands: AI Home shows "waiting for Allow" the whole
  time, and quitting Brave ends it — cost if wrong: "asking" until Brave restarts.
- Ruling: turning the switch off and on while Brave asks leaves a dead question on screen — stands: that is
  Chromium's, and answering it does nothing — cost if wrong: none.
- Ruling: the bar on screen is the user's check — a headless browser can't show it, and nothing here may click
  Allow — cost if wrong: the on-screen check finds it.

## Deferred minors

- minor (deferred): if a client's 60 s wait ends at the same moment as Allow, its 409 says "click Connect" while the
  state is already "connected"; the next call works.
- minor (deferred): the setup text's "Only click Allow right after you started AI Browser…" reads a little oddly now
  that the app's question can wait; AI Home's "waiting for Allow" says which question is the app's.
- minor (deferred): a session that asked by itself before the app started still makes two questions (both were asked
  before either was answered); its connection no longer lingers.

## The user's check

- **On 2026-10-04, 07:58 to 08:12**, the app ran from this branch. A read-only log of Brave's debugging connections
  showed only the app's one connection the whole time.
- **Still to confirm on screen:**
  - start the app, click Allow once, then start two agents: no new question;
  - close the bar, then start another agent: the bar stays closed;
  - optionally, wait more than a minute before clicking Allow: the first Allow still connects.
