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

## Deferred minors

- minor (deferred): when the app quits while Brave is still asking, the question stays, and an Allow there afterwards
  opens a connection nobody holds (the bar stays until Brave restarts). A line in the terminal at quit could tell the
  user to click Cancel there.

## The user's check

- **On 2026-10-04, 07:58 to 08:12**, the app ran from this branch. A read-only log of Brave's debugging connections
  showed only the app's one connection the whole time.
- **Still to confirm on screen:**
  - start the app, click Allow once, then start two agents: no new question;
  - close the bar, then start another agent: the bar stays closed;
  - optionally, wait more than a minute before clicking Allow: the first Allow still connects.
