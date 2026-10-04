# The Brain sends work to an agent that is already open (brain delegation): report

Date: 2026-10-04.

You asked: "when i talk to brain it automatically spawn an agent event though i was asking it to delegate a task to an
existing agent it says to me that i have to provide the tab to him, the existing agent it spawned he cannot command it
back". This is that fix, built from the brain-delegation spec (`docs/superpowers/specs/2026-10-03-brain-delegation-design.md`)
and its plan (`docs/superpowers/plans/2026-10-03-brain-delegation.md`).

## What changes for you

- **A send card for an open agent:** say or type "tell agent 1 to also check the mobile layout". The Brain shows "Send
  to 1 · Fix the footer:" with your own words in a box you can edit. Nothing is sent until you press **Send** or say a
  plain yes, and it never starts a new agent in that agent's place.
- **The app speaks for the card, not Claude:** "I can send your words to 1 · Fix the footer. Press Send, or say yes." A
  start card says "I can start a NEW agent with your words."
- **Every agent has a number:**
  - "1 · Fix the footer" shows on its station, in the List, in the drawer, in AI Home's rows and chat, on "Give to"
    buttons, on owner chips and on inbox items;
  - the number is the agent's id (a3 is 3), and it never changes while the app runs.
- **Picking the agent:**
  - by its number ("agent 2"), its colour ("the blue agent"), a word of its name, or "it" (the last agent this talk
    dealt with);
  - words inside the task don't count: "give the flights agent one of my tabs" stays with the flights agent;
  - when it's unclear, the Brain asks "Which agent: 1 · Fix the footer (blue), or 3 · Flights to Manila (cyan)? Say its
    number." Your first words stay on the card it makes next.
- **What happens depends on the agent's state:**
  - a busy agent gets your words queued, and reads them when it finishes what it's doing now;
  - a waiting permission is never answered by them;
  - an agent at a bot check gets nothing, and the Brain points to Continue;
  - a closed agent gets nothing either, and the Brain says so.
- **One fixed first line:** every message starts with "The user said this to the Brain, for you:", then your words.
- **A yes or no with nothing open never reaches Claude:**
  - "yes" answers "There's nothing open to say yes to.";
  - "stop" answers "Nothing is open to cancel. To stop an agent, press Stop in its drawer.";
  - "send it" sends an open send card; "no, agent 3" moves it to agent 3 with its words.
- **Handing a tab over stays your click:**
  - ask for work on "this tab", and the Brain says how and opens that agent's drawer at **Your tabs**;
  - there, **Give to this agent** hands it one of your tabs. The Brain never hands a tab over itself.
- **Agents in Brave offer two ways to a page you have open:** "hand me that tab (Give to this agent, under Your tabs in
  my drawer in Mission Control), or tell me its address and I'll open it in a tab of my own."
- **The inbox's Tell the Brain gets the same cards:**
  - a start or send card on the item, with **Start** or **Send** in AI Home and Mission Control;
  - the watcher's Brain page in Brave shows the card without buttons, and a yes typed there runs nothing.
- **Speech reads " · " as a pause:** "1, Fix the footer".

## How it was built and checked

- **Test-first:** 17 tasks, one commit each, on branch `brain-delegation` from main b8de841, after the relay merged.
  Each test was seen failing for its stated reason, then passing.
- **The commits:**
  - pre-flight: 4084d8e (the plan corrected against the merged relay);
  - Task 1, c0f613d: agents carry a fixed number and a queued count, and `send` says whether it sent;
  - Task 2, 4b15c80: the agents' Brave prompt gains the hand-over sentence;
  - Task 3, 040292b: the resolver that reads which agent you mean;
  - Task 4, 5da0c08: the closed set gains `message_agent`, with fixed lines and a numbered state;
  - Task 5, d63b2f7: the app words every card, and a bare yes or no never reaches Claude;
  - Task 6, 661542e: send cards, run by the agent's state;
  - Task 7, 4c56235: "Which agent?" keeps your first words, and "it" means the last agent;
  - Task 8, f3efc89: Hand over is a pointer, never a hand;
  - Task 9, 324954e: Tell the Brain proposes the same cards;
  - Task 10, aab0290: only AI Browser's own pages run an inbox card;
  - Task 11, b920f09: numbers on every page;
  - Task 12, 2215023: the relay's list of what is connected uses the same numbers;
  - Task 13, 2ce8f28: the talk's send card;
  - Task 14, e69778b: Your tabs in Mission Control's drawer;
  - Task 15, 2db6260: speech reads the dot as a pause;
  - Task 16, 0da9a12: inbox cards on the pages;
  - Task 17, d374352: the README.
- **First review:** a self-review of the whole branch, since that run had no subagents. It found nothing Critical or
  Important.
- **A fresh review (opus, read-only):** "With fixes". It found no consent hole. But delegation misfired on ordinary
  phrasings, which was exactly your complaint. It found two Important issues, and two of its Minors were re-graded to
  Important:
  - **I1, words inside the task picked the agent.** "give the flights agent one of my tabs" opened agent 1's Your
    tabs. "ask the flights agent two questions" answered "There's no agent 2". "book the red one" refused.
    - The fix: a number word counts only where the reference ends, and a colour only next to "agent". When your
      reference and Claude's pick differ, the Brain asks which agent and keeps your words.
    - RED→GREEN: `test_numbers_and_colours_inside_the_task_are_not_agent_references`,
      `test_task_words_never_retarget_claudes_pick` and `test_a_number_or_colour_against_claudes_pick_asks_which_agent`.
      `test_resolve_agent_reads_numbers_colours_and_back_references` was also updated.
  - **I2, replies replaced your words:**
    - (a) "send it" on a send card made a new card holding "send it". Now it sends the card
      (`test_send_it_is_a_yes_for_a_send_card_only`, RED→GREEN).
    - (b) after "There's no agent 7", the answer "agent 3" made a card holding "agent 3". Now your first words stay, in
      the talk and in the inbox (`test_after_no_such_agent_the_next_number_keeps_the_first_words` and
      `test_tell_after_no_such_agent_the_next_number_keeps_the_first_words`, RED→GREEN).
    - (c) "no, agent 3" on a send card made a card holding "no, agent 3". Now the card moves to agent 3 and keeps its
      words (`test_an_agent_reference_on_a_send_card_moves_it_and_keeps_its_words`, RED→GREEN).
  - **I3, a yes could run a card no longer on screen.** This was re-graded from Minor because it broke the consent
    rule.
    - A setup or problem card had replaced the send card, and a typed "ok" ran it unseen.
    - The fix: a yes now carries a card only while that card is on screen.
    - RED→GREEN: `test_a_yes_never_runs_a_card_that_left_the_screen`. In the RED run the hidden card ran, and agent 1
      got the message.
  - **I4, a bare "stop" with nothing open said "OK, I won't."** This was re-graded from Minor because it was a
    misleading answer about stopping. Now it says how to stop an agent
    (`test_a_bare_stop_with_nothing_open_points_to_the_stop_button`, RED→GREEN).
  - **The fix commits:**
    - d95138b first merged main d022fd2 into the branch;
    - a4b0f4f fixes I3;
    - dc812aa fixes I1, I2 and I4, which change the same functions.
- **The whole suite:**
  - main before the branch (b8de841): 1239 passed, 9 skipped (the relay's report);
  - after the build (d374352): 1279 passed, 9 skipped, 1 failed. The failure was `test_hand_and_run_take_one_click`.
    It was flaky on main too, and main's d022fd2 fixed it;
  - after the fix pass (dc812aa): 1290 passed, 9 skipped. `test_approval_mode`, with a throwaway Chrome and a
    throwaway Brave, still counts one "Allow remote debugging?" for the app, two agents and a Claude Code session;
  - main with wave A merged: 1511 passed, 9 skipped.
- **The bench:** not run. The reason is a ruling below.
- **The merge (977518c, by the main session):**
  - `TELL_CARD_MESSAGES` went. The Brain's `from_watcher` now comes from watcher-safety's `_role(ws)`, and its table
    makes `tell_confirm` and `tell_dismiss` app-only. Its guard tests, `test_rights_go_by_role_through_the_table` and
    `test_only_the_role_reads_the_watchers_origins`, were red on the merged tree and green after;
  - Mission Control's Your tabs now shows watcher-safety's scope lines (7ff4f5d,
    `test_your_tabs_say_what_the_list_leaves_out`, RED→GREEN). Before, it said "None of your tabs are open." while your
    tabs were in other profiles.

## Rulings I made

Every decision taken on your behalf, in order, with what it costs if wrong:

- **Pre-flight:** Ruling: the plan's lines ~57-61 describe the relay's client rows wrongly; Relay.clients() rows are {id, kind, number, tabs, connected, cut_off} (cdprelay.py) and AppServer._browser_clients() adds name and color — the merged code wins; plan text corrected — cost if wrong: none (description only)
- **Pre-flight:** Ruling: Task 12 imports agent_number from app.agents into cdprelay.py (no import cycle); this departs from the relay's "the relay stays ignorant of agents" — one numbering rule beats two copies of int(id[1:]) — cost if wrong: one import to move back
- **Pre-flight:** Ruling: Task 12's [1:] grep also hits _number()'s int(part[1:], 8) in cdprelay.py (IPv4 octal parsing); it stays; only _order and clients() number agents — cost if wrong: none
- **Pre-flight:** Ruling: Task 12 Step 3.2's example doesn't match HEAD; home.js has clientLabel(row); only its `who` line changes, to `const who = row.kind === "agent" ? agentLabel(row) : "Claude Code";` (the session row's text stays) — cost if wrong: none
- **Pre-flight:** Ruling: agent_number's pattern is a([0-9]{1,9}) (fullmatch), so it accepts exactly what server.AGENT_ID and cdprelay._AGENT_ID accept (^a[0-9]{1,9}$) — cost if wrong: none
- **Pre-flight:** Ruling: brave_connect and browser_disconnect join the plan's "No new path" list and its final review list (the Brain and voice never send them); browser_disconnect also joins Task 6's SHAPES beside brave_connect — cost if wrong: none
- **Pre-flight:** Ruling: 1B's MESSAGE_RULES rows tell_confirm/tell_dismiss: this branch has no 1B, so the plan's own branch applies (BRAIN_MESSAGES + TELL_CARD_MESSAGES, from_watcher via _watcher_origins); the main session reconciles 1A and 1B at merge — cost if wrong: a merge-time rework the plan already describes
- **Task 1:** Ruling: the test also asserts that the queued count drop is broadcast before the agent reads the message (the plan settles on the snapshot, which reads len(pending), so removing _run's _changed passed; mutation-checked RED with it removed) — cost if wrong: none; the test is stricter
- **Task 6:** Ruling: SHAPES also carries "browser_disconnect" beside "brave_connect" (pre-flight ruling 5): Claude answering it is CLICK_ONLY like every action outside the closed set — cost if wrong: none
- **Task 7:** Ruling: the plan's "asking_which_agent" checks read the whole prompt, whose own instructions name that key, so its "in" check passed with no question kept and its "not in" check could never pass; both (and the last_agent check) now read the state block only, via a state_block helper — cost if wrong: none; the test now fails without the feature
- **Task 10:** Ruling: the new server test reads AI Home's socket while it waits (quiet(page, 0.5) instead of asyncio.sleep(0.5)) — an unread websockets client (max_queue 16) stalls its close for the 10 s close_timeout, so the test took 11.5 s; now 1.5 s, same checks — cost if wrong: none
- **Task 12:** Ruling: _order sorts on agent_number(identity) is not None rather than _AGENT_ID.match, so an id the two rules disagree on (a trailing newline: re.match with $ accepts it, fullmatch does not) can never compare None with an int — cost if wrong: none
- **Task 14:** Ruling: the test clears the stack fixture's own TabWatch callbacks before attach_brave — the stack attaches AI Browser's TabWatch, which run.py never attaches in brave mode, and its empty listing reached the page after Mission Control opened and replaced Brave's list ("Your tabs (0)"); a test-harness artifact, not a product path; RED re-checked with the fix in place — cost if wrong: the test reaches into TabWatch._callbacks, a private name
- **Final:** Ruling: colour words anywhere in the words pick an agent ("tell the footer agent to pick the green one" makes a card for the green agent, over Claude's pick) — stands: Decision 4 step 1 defines a colour reference as "<colour> agent/one/station" and puts it before Claude's pick, and the card and its spoken line name the agent before anything is sent — cost if wrong: a user who says yes without listening sends their words to the wrong open agent
- **Final:** Ruling: a yes carrying an older card's id closes a newer card another page made, and answers "This has expired: ask again" — stands: Decision 12 step 3 and _respond's "any other words close the card" — cost if wrong: the user asks again on the other page
- **Final:** Ruling: Mission Control's spoken background updates and its permission card still name agents without their numbers — stands: the spec puts numbers in the spoken updates out of scope and doesn't list the permission card — cost if wrong: one agent named two ways on one page
- **Task 17:** Ruling: the bench (uv run ai-browser bench) was not run — it starts and then stops the "default" sandbox under the user's own ~/.ai-browser (a side effect outside this worktree, under the user's or another session's feet), the caller named only the whole suite, and its timing budgets would measure two other builders' suites running beside it; this plan changes nothing in the sandbox's reading or acting — cost if wrong: a sandbox speed regression from elsewhere stays unseen until the next bench
- **Final (fix pass):** Ruling: I1 (c) governs send cards and the hand-over pointer (a conflict there asks, or gives HAND_OVER_ANY_SAY and opens no drawer); for a plain view (open, target agent) the user's explicit reference still picks what is shown, as Decision 4 says, since nothing runs from a view and (a) and (b) removed its false positives — cost if wrong: a view shows the agent the user named where Claude meant another; nothing runs
- **Final (fix pass):** Ruling: I1 (a) reads a number word after "please", "thanks" and "thank you" are dropped, so "send this to agent three please" still names agent 3 — without it the reference-end rule refuses a polite reference — cost if wrong: a task like "agent one please more…" reads as a reference
- **Final (fix pass):** Ruling: I1 (b) applies to references inside a request; a colour that is the whole answer to "Which agent?" ("blue", "the blue one") still picks, as Decision 5 lists "the blue one" as an answer — cost if wrong: none
- **Final (fix pass):** Ruling: I2 (a) "send it" over a start or draft card is no yes and goes on as a new question; with the id of a card that is gone it is a bare yes ("This has expired: ask again") — cost if wrong: "send it" over a start card gets Claude's answer
- **Final (fix pass):** Ruling: I2 (b) also covers the inbox's Tell (_tell_pick): after "There's no agent 7" on an item, the next number in its box picks with the first words — the same failure as in the talk — cost if wrong: none
- **Final (fix pass):** Ruling: I2 (c) a reference reply that names no open agent ("no, agent 7") answers NO_SUCH_SAY and keeps the card's words as the question's; a shared colour asks among those agents; only send cards move (a start card has no agent) — cost if wrong: none
- **Final (fix pass):** Ruling: I3 talk.js attaches the card's id only while the card is on screen (proposal.node.isConnected); setCard is unchanged — cost if wrong: none
- **Final (fix pass):** Ruling: I4 a "no" carrying the id of a card that is gone still answers "OK, I won't." (that card was on the page); only a no with nothing open points to Stop — cost if wrong: none
- **Final (the main session, on the fresh review):** Ruling: the watcher can still send send/new_task/stop/close/model on this branch — stands here: 1B's MESSAGE_RULES makes them app-only, and the main session merges 1A only together with 1B — cost if wrong: none once both are on main.
- **Final (the main session, on the fresh review):** Ruling: the watcher's Hand to agent starts an agent with no card — stands: it is the user's own click on the watcher's Brain page, and the spec keeps it "works as today" — cost if wrong: one click starts an agent from the watcher, as before this branch.
- **Final (the main session, on the fresh review):** Ruling: TELL_CARD_MESSAGES and the origin test fold into 1B's MESSAGE_RULES at merge (from_watcher = self._role(ws) == "watcher") — the main session does it; a trial merge passes test_watcher_rules, test_app_server and test_talk (180 passed) — cost if wrong: none.
- **Final (the main session, on the fresh review):** Ruling: an answer to "Which agent?" that is a whole new request naming an agent still gets the first words — stands: spec Decision 5 — cost if wrong: the user says the new request again.
- **Final (the main session, on the fresh review):** Ruling: a yes carrying an older card's id closes a newer card (ruling 48) — stands: the spec says so — cost if wrong: the user asks again.
- **Final (the main session, on the fresh review):** Ruling: a queued Brain message still runs as the next turn after a bot check appears — stands: the send is refused at card and send time, as the spec requires — cost if wrong: one refused line.
- **Final (the main session, on the fresh review):** Ruling: Send while a newer question is in flight answers "expired" — stands: the card closes first, as before this branch — cost if wrong: one retry.
- **Final (the main session, on the fresh review):** Ruling: numbers in spoken updates and on the permission card, the queued count, a To: picker, messages to Claude Code sessions and numbers across restarts stay out — out of scope per the spec — cost if wrong: none now.
- **Final (the main session, on the fresh review):** Ruling: ruling 47 stands only for a real colour reference to an agent; its false positives are fixed by I1 — cost if wrong: none.

## Deferred minors

- **Final:** minor (deferred): Give to this agent stays disabled after the server refuses a hand-over (the tab closed or was taken meanwhile) until the next tabs or browser message; reopening the drawer re-enables it
- **Final:** minor (deferred): Your tabs rebuilds its rows on every tabs message, so a click that lands during a re-render (titles changing while pages load) can be lost and needs a second click; AI Home's tab list updates its rows in place
- **Final:** minor (deferred): AgentManager.stop clears pending without broadcasting the row, so a page's queued count catches up only when the turn ends (no page shows the count yet; Claude's state reads the snapshot)
- **Final:** minor (deferred): service.py:825: DRAFT_SAY reads up to 200 characters of the From name aloud — clip it to about 40 characters, first sentence only, later
- **Final:** minor (deferred): the TELL_START and TELL_SEND notes outlive their card: after the 2-minute expiry and after a restart (_recover)
- **Final:** minor (deferred): layering: cdprelay.py:35 imports app.agents (→ bridge → brain.tools, claudecli); a small app/ids.py would do
- **Final:** minor (deferred): tab_hint misses "the page I am on" and "the tab I have open"

## What only you can check (in your own Brave, after you restart the app on main)

Nobody has tried these with your voice, your agents or your inbox yet. The tests used throwaway browsers and a stand-in
for Claude. While you try them, Brave should not ask "Allow remote debugging?" again: a Send uses the app's one
connection.

1. Open Mission Control with two agents. Hold Space and say "tell agent 1 to also check the mobile layout".
   - The card says "Send to 1 · …", with your words in the box;
   - the Brain says "I can send your words to 1 · …", and with Voice on you hear "1, …";
   - say "yes": agent 1's chat shows "The user said this to the Brain, for you:" and your words, and no new agent
     appears.
2. Type the same in the Ask box, then edit the card's box and press **Send**. The edited words go, once.
3. Say "tell the flights agent one more thing: check the return date", then "give the flights agent one of my tabs".
   - Both stay with the flights agent;
   - the second opens its drawer at **Your tabs**, and nothing is handed over until you press **Give to this agent**.
4. Say "tell agent 7 to stop" when there is no agent 7, then "agent 1". The card holds your first words.
5. With nothing open, say "stop". You hear how to stop an agent, never "OK, I won't."
6. For a Gmail item and a Slack item in AI Home, type "give this to agent 1" in its **Tell the Brain** box.
   - A send card shows. **Send** gives agent 1 your words, then the message as page data;
   - "ask an agent to check the launch page" shows a start card instead;
   - on the watcher's Brain page in Brave, the same card shows with no buttons, and a "yes" typed there runs nothing.

If any of these differs, say which step, and the texts or the resolver get corrected before the next wave.
