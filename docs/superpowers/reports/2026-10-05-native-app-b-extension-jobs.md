# Report: the extension's jobs move into the app (native app, part b)

Date: 2026-10-05. Branch `native-b`, cut from `main` at ac44f81 (part a and its two fixes merged), merged into `main`
as f712344.

## What the user asked

- **The request:** "then in app I want it built in, no need to install the extensions it is such a hassle find a way
  to build it natively we can switch to standalone app if necessary".
- **Their answers:** "Keep Brave, app does it all (Recommended)", "Open tabs, after one OK (Recommended)" and
  "Electron (Recommended)". On the design: "all good".
- **On the plan's two open questions:**
  - "A window per AI tab (Recommended)": if Brave can't keep the AI's tabs in one window, each new AI tab gets a
    window of its own;
  - "Yes, I mostly use one profile (Recommended)": agents open tabs only in the profile Brave used last, and say so
    otherwise.
- **Scope** (`docs/superpowers/specs/2026-10-04-native-app-design.md`, part b): Decisions 5, 6, 7 and 9.

## What changes for you

- **Nothing to install in Brave.** The watcher extension retires: its folder, its socket, its setup steps, the `ai`
  keyword and the tab groups. The setup page has one step left, Brave's switch.
  - AI Home says you can remove "AI Browser Watcher" in `brave://extensions`, until you click **Got it**.
  - AI Browser never removes the extension or its old folder itself.
- **Settings → Brain → Read my Gmail, Slack and Asana tabs.** It is off until you turn it on.
  - While it is on, AI Browser reads those tabs in Brave through its one connection, in an isolated world. Page text
    is data.
  - It shows how reading goes ("Reading your open tabs", "Waiting for Brave", "Off"), and a line for each site.
  - Turning it off stops reading at once, and a read under way keeps nothing.
  - AI Home's Brain section says "Reading your tabs is off", with **Turn it on in Settings**.
- **Use draft** (the old Approve). **Draft reply** reads the thread in your tab (or a background tab marked "Brain").
  - **Use draft** brings the tab forward and puts the reply in the box: above the signature in Gmail, on one line in
    Slack, in Asana's comment box.
  - AI Browser never clicks Send. You do.
- **Pick the part to watch.** In Settings → Brain, pick one of your open tabs and click the button. The tab comes
  forward, an outline follows the mouse, a click picks and Escape cancels. A pick nobody finishes ends after 2
  minutes.
- **Settings → Where agents browse.** Brave's profiles by name and colour (never an email), or "The profile you used
  last".
  - AI Home lists that profile's tabs and only counts the others.
  - Brave can't be told a profile. After you click in a window of it once, AI Browser learns it within about 30 s.
- **The AI's tabs open in windows of their own,** a new window for each new tab, never among your windows. When
  Brave's last window is in another profile, the agent is told to click a window of the right one. The words never
  name a profile.
- **Notifications** come only from AI Browser's own app. Without it, AI Home shows them.

## The probe (Task 1)

- **Where:** throwaway headless Chrome 154 and throwaway headless Brave (Chromium 152), each with its own temporary
  profile. Never your Brave.
- **What it found:**
  - every way of opening a later tab from the AI window (middle click, Cmd-click, `window.open`, middle click from
    behind) landed the tab in that window;
  - but every way also made the AI window the one Brave used last;
  - the clicks left no opener; `window.open` did.
- **The profiles half** needs a visible browser, so Local State's lag wasn't measured.
- **So:** `SHARED_WINDOW = False` (your "A window per AI tab"), Task 12 skipped, and `SETTLE = 30`.

## How it was built and checked

- **Test-first, 12 tasks built, one commit each:**
  1. 7a411b0: the probe;
  2. 16daacf: the sites the Brain reads, the three new settings, the fake sites on their own addresses;
  3. acdad34: the watcher retires from the app: one role, no watcher socket, no setup steps, no `ai` keyword;
  4. 5056c8d: the watcher's folder goes, and AI Home says it can be removed;
  5. 74f4241: the readers move into the engine, in an isolated world;
  6. bcd2d86: BraveLink's one gate for the readers (`brain_tabs`, `may_run`, `run_reader`);
  7. 4442ef7: the engine reads your tabs while the switch is on, and stops at once when it goes off;
  8. d29e0d7: Draft reply reads the thread, and Use draft fills the reply box;
  9. a3c340a: Settings → Brain, and Pick the part to watch;
  10. 539b7bb: Where agents browse;
  11. baf61e4: the AI's new tabs open through the app, each in a window of its own; the tab groups retire;
  12. skipped: one AI window for every agent (`SHARED_WINDOW = False`);
  13. 48aa065: the README.
- **Two commits were amended:** Tasks 4 and 11 first committed only their deletions, because a `git add` stopped on
  an already-removed path. Each was amended before its tests ran.
- **My own review** (no subagents in that run): no Critical or Important findings, and four minors (below).
- **A fresh review** (Opus, read-only, on a copy of 48aa065): "Ready to merge with fixes".
  - **These held up under its probes:** the gate is narrow and complete, the isolated world resists clobbering, Send
    is never clicked, the site check is exact, `/agent-tab` checks the token and the Host, the retirement is clean,
    and `test_approval_mode` passes.
  - **Six findings were fixed in one test-first pass.** Each test failed first for the stated reason:
    - **F1 (Important), a tab could open in the wrong profile for about 1.5 s after a window switch** (f53eafe). The
      profile is now read again just before the tab opens, and the new tab's profile is checked. One that landed
      elsewhere is closed. RED→GREEN: `test_a_tab_never_opens_in_another_profile_even_right_after_a_switch`.
    - **F2, switching off while a thread opened left the Brain's tab open in Brave** (f53eafe). The relay now lets the
      app close a tab it opened itself, and nothing wider. The tab is recorded the moment Brave makes it. RED→GREEN,
      through the real relay: `test_reading_off_while_a_thread_is_read_closes_its_tab_in_brave` and
      `test_reading_off_while_brave_makes_the_threads_tab_closes_it_once_made`.
    - **F3, switching off during a sort still listed, notified and started workflows** (dc8e231). RED→GREEN:
      `test_reading_turned_off_during_a_sort_keeps_nothing_of_that_batch`.
    - **F4, Gmail's fill could type into an open New message** (e907d81, f53eafe). Only the thread's own reply box is
      used, and only while the tab shows that thread. Otherwise: "the thread isn't open in this tab", and the draft is
      kept. RED→GREEN: `test_a_gmail_reply_never_goes_into_a_new_message_or_another_thread`.
    - **F5, a page could make the picker pick** (e907d81). Only your own click and Escape count. RED→GREEN:
      `test_the_picker_ignores_what_the_page_itself_dispatches`.
    - **F6, a thread could open at a link off its item's site** (f53eafe). Nothing opens then, and the item says why.
      RED→GREEN: `test_a_link_off_the_items_site_opens_nothing_and_says_why`.
  - **Its verdicts:**
    - it agreed with every ruling;
    - SETTLE = 30 was agreed: from Chromium's source, Brave writes `profile.last_used` on window activation and saves
      Local State within about 10 s. This is not measured: hand check 4 confirms it;
    - Task 10's `isinstance` fix was agreed as a real bug fix.
- **Whole suite:**
  - after the build: 1739 passed, 17 skipped (20 min 45 s);
  - after the fix pass: 1746 passed, 17 skipped (20 min 38 s).

## The merge

- **Into main:** f712344, pushed by the main session. The updated app runs on your Mac, and Brave has one connection.

## Rulings I made

Every decision taken on your behalf, in order, with what it costs if wrong:

- **Setup:** Ruling: the ledger lives in the sdd-workspace folder, not the plan's named one. The coordinator ordered
  that script — cost if wrong: none (git-ignored scratch).
- **Setup:** Ruling: the branch is `native-b`, not the plan's `native-app-b`. Main had part a plus two fix commits
  (150ce6d, 0dfed9f) — cost if wrong: none.
- **Task 1:** Ruling: the visible run (`--headful --profiles`) was not run. The coordinator ordered headless, and a
  subagent couldn't warn you first to leave the mouse alone — cost if wrong: focus, a window coming forward and Local
  State's lag are unmeasured; the hand checks carry them.
- **Task 1:** Ruling: `SHARED_WINDOW = False`. Chrome and Brave both made the AI window the one used last, and you had
  chosen "A window per AI tab" — cost if wrong: an agent's second tab gets a second window (a popup its page opens
  stays in its window).
- **Task 1:** Ruling: `SETTLE = 30`. The lag was unmeasured, and the profile learning is unproven until hand check 4.
  The main session tells you this before you rely on Where agents browse — cost if wrong: see Task 10.
- **Task 3:** Ruling: `_notify_desktop`'s docstring now says "AI Home shows it then" instead of "Brave's watcher". This
  follows plan decision 11 and the step's grep check — cost if wrong: none (a comment).
- **Task 4:** Ruling: an AI-accounts comment that named `WATCHER_AGENT_FIELDS` now ends "(public: AI Browser's own
  pages show them)" — cost if wrong: none (a comment).
- **Task 4:** Ruling: two AI-accounts comments lost their watcher words (accounts.py's rows docstring, accountui.js).
  home.js's group reasons stayed for Task 11 — cost if wrong: none (comments).
- **Task 5:** Ruling: four code lines over 120 characters in the readers stay. They are the extension's DOM code,
  moved as it was — cost if wrong: none (style).
- **Task 10:** Ruling: `place.SETTLE = 30.0`, not the brief's 12.0, per Task 1 — cost if wrong: with two or more
  profiles, up to about 30 s after a click in the chosen profile's window before its tabs list.
- **Task 10:** Ruling: the brief said "the four tests" to replace, but the named range holds three. All three were
  replaced — cost if wrong: none.
- **Task 10:** Ruling: the `agents_profile` check tests `isinstance(value, str)` first. A list from a page would have
  raised inside the socket's handler; it is now refused in plain words. Tested RED→GREEN — cost if wrong: none.
- **Task 11:** Ruling: stale tab-group words in comments the plan didn't quote now say what happens without groups —
  cost if wrong: none (comments).
- **Task 13:** Ruling: the whole suite runs once, after the final review (the coordinator's order) — cost if wrong:
  none; it ran twice in the end.
- **Task 13:** Ruling: the hand checks can't be done by the builder, which must never touch your Brave. They are below
  — cost if wrong: none.
- **Final:** Ruling: whether a new AI window takes the focus from yours in a visible Brave was left to hand check 5 —
  cost if wrong: each agent's first tab may pull its window to the front.
- **Final:** Ruling: whether SETTLE = 30 learns the right profile was left to hand check 4 — cost if wrong: AI Home
  lists the wrong profile's tabs, or learns slowly. Raise `SETTLE` in `app/place.py`.
- **Final:** Ruling: the ledger was kept for the fresh reviewer — cost if wrong: none (git-ignored).
- **Final:** Ruling: Asana's comment box (`asana.js` takes the first `.ProseMirror[contenteditable]`) can't be verified
  without Asana's real page, so it goes to your hand checks — cost if wrong: a draft lands in a task's description,
  which Asana saves by itself, instead of a comment.
- **Final:** Ruling: with two profiles and none chosen, the Brain reads whichever profile was used last (plan decision
  8). This stands — cost if wrong: items from two profiles mix.
- **Final:** Ruling: a second pick on the same host replaces the first (the site key is `custom:<host>`). This stands —
  cost if wrong: you pick again.

## Deferred minors

- **From my review:**
  1. the picker took synthetic events: **fixed as F5**;
  2. a thread's link wasn't checked against its site: **fixed as F6**;
  3. `open_user_tab` says "Brave's last window is in another profile" also when the chosen profile just isn't learned
     yet. "isn't open in Brave yet" would be truer;
  4. a server stop during a pick runs its clean-up and answers, instead of ending as cancelled.
- **From the fresh review:**
  1. a fill under way when the switch goes off can still type the reply, because the page's wait keeps running. It is
     still your own Use draft, so the effect is the note's wording;
  2. `/agent-tab` doesn't check whether you disconnected that client, so it could still make the app open blank
     windows;
  3. the readers don't check their own origin in the moment before the isolated world is made. Pass the expected
     origin into the fill, later.

## What only you can do

On the Mac, then Windows, with your own Brave. AI Browser never answers Brave's question or touches its bar.

1. **The inbox switch:** turn on Settings → Brain → **Read my Gmail, Slack and Asana tabs**. New mail in your Gmail
   tab reaches AI Home's Brain section. Turn it off in the middle of a read: nothing more comes in.
2. **A draft:** click **Draft reply** on an item, edit it, then **Use draft**. The reply is in the box above the
   signature, the tab is in front, and nothing is sent until you press Send.
3. **Pick the part to watch:** pick an open tab in Settings and click the button. The outline follows the mouse in
   Brave, a click picks, and Escape cancels.
4. **Where agents browse, with two profiles:** pick the profile you aren't using now. AI Home lists none of its tabs,
   and Settings says it isn't open yet.
   - Click in a window of it: within about 30 s, AI Home lists its tabs.
   - An agent's task then opens its tab in that profile, in a window of its own.
   - With the other profile's window in front, the agent's error says to click a window of the profile where agents
     browse, naming no profile.
   - If a profile is ever learned wrong, raise `SETTLE` in `app/place.py`.
5. **The AI's windows:** run two agents at once. Each new tab opens in a window of its own, never among yours, and your
   own window keeps the focus.
6. **The old extension:** AI Home's note names "AI Browser Watcher". **Got it** hides it for good, and Brave keeps the
   extension until you remove it.
7. **On Windows only:** if a new AI window comes to the front, set `WINDOWS_TAKE_FOCUS` to `true` in `home.js`, so AI
   Home says so.
8. **Asana's comment box:** **Use draft** on an Asana item lands in a comment, not in the task's description.
9. **Gmail with a New message open:** **Use draft** fills only the thread's own reply box, never the New message.
