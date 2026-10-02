# The Brain and Mission Control: rulings and deferred minors

Date: 2026-10-02.

Both plans were run without asking you, as you asked ("do not ask for my input for now"). Every decision made on your behalf is a **Ruling** line below: what was decided, why, and what it costs if it was the wrong call. **Deferred minors** are review findings left for later.

The full records are the two ledgers:
- `.superpowers/sdd/2026-10-02-brain/progress.md`;
- `.superpowers/sdd/2026-10-02-mission-control/progress.md`.

## The Brain (project 5)

### Rulings

- Setup: Ruling: no git (as in every plan here); ledger by hand; native execution (the user's choice for the last plan, "Native, in one go"); the user said "afer that then proceed" after the spec update, so the plan is built without a separate review pause — cost if wrong: the user reviews the plan after the fact; fresh opus reviewer at the end. Spec: docs/superpowers/specs/2026-10-02-brain-design.md.
- **Pre-flight:** T3/T4 produce BrainService hooks send_watcher(dict)->bool, broadcast, on_items/on_replied/on_thread/on_filled, set_watch(fields)->str → T5 server routes them: conflict — T5 routes reader_status {site, ok, note} to "that entry's status", but T3 defines no method for it. Ruling: T5 adds BrainService.reader_status(site, ok, note) (sets WatchEntry.status, broadcasts brain_state) — cost if wrong: none
- **Task 4:** Ruling: Tell the Brain passes the user's own words on (as draft guidance, or as the agent's instruction); the tool-less mapping call only picks the action (draft / agent / none + a reply) — the plan had the model's "instruction" passed on, which would let message text (quoted in that call) write an agent's instructions as if they were the user's — cost if wrong: the agent gets the user's raw sentence instead of a cleaner paraphrase
- **Task 4:** Ruling: approve stores the approved (edited) text as the item's draft, so a failed fill goes back to the text the user approved — cost if wrong: none
- **Task 5:** Ruling: a socket from the watcher's origin no longer sets extension_seen (AI Browser's own extension): otherwise Brave's watcher connecting within EXTENSION_WAIT would hide AI Browser's setup steps — cost if wrong: none
- **Task 5:** Ruling: the setup page's Brave section has its own Finder button (POST /setup/reveal?which=watcher, same key) and its own status line — cost if wrong: none
- **Task 6:** Ruling: a site the user adds starts from what it already shows: the region reader's first report is a baseline (items {baseline: true}), which the Brain only marks seen — otherwise adding an orders page would report every existing row as new at once; the watcher remembers per site that its baseline was taken (storage.local) — BrainService.on_items(site, items, baseline=False) — test_a_baseline_is_remembered_without_sorting + test_a_picked_region_reports_new_rows — cost if wrong: a row added between picking and the first read is skipped
- **Task 6:** Ruling: "replied" for a conversation is "<channel or task>:*" (Slack, Asana): the Brain clears every item of that conversation — Slack's per-unread-spell ids and Asana's per-entry ids can't be known from the open conversation — test_a_reply_in_a_conversation_clears_all_its_items — cost if wrong: none
- **Task 6:** Ruling: readers send "replied" for every row whose newest sender is the user (once per page), not only for rows reported from this page — a thread read before a reload and answered after it would otherwise stay listed; the Brain ignores ids it doesn't have — cost if wrong: a few small messages per page load
- **Task 6:** Ruling: Gmail item links use #all/<thread id> (works whatever label the thread is under) instead of the plan's #inbox/ — cost if wrong: none (the live check confirms)
- **Task 6:** Ruling: the watcher keeps the watch list in storage.local (not session): registered readers persist across browser restarts and must find their site's settings while the app is still off — cost if wrong: none (no message text there)
- **Task 7:** Ruling: one text box per inbox item serves both "Tell the Brain" and "Hand to agent" (the agent's instruction), instead of the plan's separate hand box — fewer fields; an empty box hands the item with a default instruction — cost if wrong: none
- **Task 7:** Ruling: the Brain's styles are a shared brainui.css (copied into the watcher with brainui.js), and AI Home's stack fixture (test_home.py) now always has a BrainService — cost if wrong: none
- **Task 8:** Ruling: the watcher's Finder window and the setup page's Brave section open once (watch.json remembers watcher_prompted), only when AI Browser's own extension is installed (one Finder window at a time); the printed Brave steps repeat at each start until the watcher has connected — cost if wrong: a user who skipped it sees the steps in the terminal only
- **Task 8:** Ruling: a conftest autouse fixture replaces run.reveal and server.reveal_in_finder with no-ops for every test (the new first-start paths would otherwise open Finder on the machine running the suite) — cost if wrong: none
- **Task 9:** Ruling: the connector list comes from a probe: `claude -p … --output-format stream-json --verbose` without strict, read the init event, then the process is ended (no answer is waited for) — run at app start and when the Tools page asks — cost if wrong: one short Claude Code start per probe
- **Task 9:** Ruling: a permission request for a server that isn't switched on is denied without asking ("That tool's server isn't switched on in AI Browser (AI Home → Tools)"); a tool allowed always since the agent started is answered "once" at once — cost if wrong: none
- **Task 9:** Ruling: --allowedTools/--disallowedTools are passed comma-joined (Claude Code: "comma or space-separated"); without ToolsConfig the phase-1 command is unchanged — cost if wrong: none (the live run below used them)
- **Task 10:** Ruling: WorkflowRunner.run(slug, text=None, page=None) takes the message as the Brain's ready labelled block (the same block Hand to agent uses) instead of the plan's item= — one place formats page data — cost if wrong: none
- **Task 10:** Ruling: a workflow's agent gets the workflow's tools ∩ the servers switched on in Tools; a workflow listing no tools gets none of the user's servers (ai-browser's own only) — the spec's "the tools it may use" — cost if wrong: a workflow that should use every switched-on server must list them
- **Task 10:** Ruling: schedules "every N" are bounded (1h–24h, 15m–720m) and workflow files are written 0600 (they hold the user's instructions) — cost if wrong: none
- **Task 10:** Ruling: the fake agent of the 2nd scheduled run was left "working" in test_a_schedule_never_piles_up, so the 3-day-gap run was rightly skipped; the test now ends that run first (test fix, code unchanged)
- **Task 11:** Ruling: a skill drafted from a run gets the run as: the user's messages listed as the user's words (task and corrections), everything else (actions, results, Claude's replies) as one quoted page-data block, the newest 30 000 characters; a page to learn from is the text of one of AI Browser's open tabs (TabWatch.page_text, 20 000 characters) — cost if wrong: very long runs lose their beginning in the draft
- **Task 11:** Ruling: Update answers skill_diff first and writes only with confirm: true (the spec's "a diff first and a second confirmation"); a name that exists answers an error with exists + suggest (name-2) — cost if wrong: none
- **Task 12:** Ruling: the Brave notification for a tool request has Review and Deny only; allowing happens on a card that shows the tool's exact input (the Brain page, AI Home, the chat panel) — a notification can't show the arguments — cost if wrong: one more click to allow from Brave
- **Task 12:** Ruling: a workflow's skills are picked with a search (at most 8 matches shown, chosen ones as removable chips) and stored as refs (namespace:name) — the plan's multi-select of every skill was a 470-checkbox wall on the user's machine (screenshot), and a bare name can match two skills — cost if wrong: hand-written workflow files may still use bare names (load_skill accepts both)
- **Task 12:** Ruling: Tools, Workflows and Train are collapsed sections under Skills in AI Home's side column; the Tools section asks for a probe of the claude.ai connectors the first time it is opened (not at every AI Home load) — cost if wrong: none
- **Task 13:** Ruling: the scheduled-workflow ticker starts before run_app's ready hook (it first started after it: no tick ran during start-up) — test_scheduled_workflows_tick_while_the_app_runs RED→GREEN — cost if wrong: none
- **Task 13:** Ruling: the claude.ai connector probe runs when AI Home's Tools section is first opened (and on its refresh), not at every app start — no Claude Code start the user didn't ask for; agents use the list saved in tools.json — cost if wrong: a connector added in claude.ai shows after opening Tools
- **Task 13:** Ruling: ask_claude runs without extended thinking unless think=True (sorting, Tell and reply drafts); skill drafts keep it (think=True: quality over a few seconds); the sort prompt asks for JSON on one line — test_thinking_is_off_unless_asked_for RED→GREEN — cost if wrong: slightly plainer reply drafts
- **Final:** Ruling: declined "real Gmail/Slack/Asana selectors" and "Gmail's sender order for from_me" — stand until the live check with the user's Brave; the watch list says "reader needs an update" rather than failing silently — cost if wrong: a reader that reads nothing until corrected
- **Final:** Ruling: declined "Slack's composer may treat an inserted line break as Enter (send)" — the watcher must never send, and that can't be checked offline: the Slack reader fills a one-line reply (line breaks joined) and says so in its note; to revisit after the live check — cost if wrong: multi-line Slack drafts arrive as one line
- **Final:** Ruling: declined "an orphaned reader after an extension reload could block re-injection" — rare (only after an app upgrade with the page open); a page reload ends it — cost if wrong: one watched tab silent until reloaded
- **Final:** Ruling: declined "Claude Code 2.1.263 behaviors measured in the ledger" and "auto-approval of an unknown connector's read-only tools" — measured live; any request for a server not switched on is denied by the bridge without asking — cost if wrong: none found
- **Final:** Ruling: declined "handed messages stay in agents' Claude Code sessions" — agents are ordinary Claude Code sessions, like any AI Browser task; "never saved" is about the Brain's own calls — cost if wrong: email text in the user's own Claude Code history
- **Final:** Ruling: declined "AI Home behavior that predates this project" and CSS styling — outside this plan — cost if wrong: none here
- **Final:** Ruling: declined "message text steering which workflow the Brain picks" — inherent in a message trigger; the workflow is the user's own, run-right-away is their choice, and its tools still ask — cost if wrong: a workflow offered or started for the wrong message
- **Final:** Ruling: a reader may add a word to a successful fill (Slack: "it's on one line"), shown in the item's note — the Slack ruling above says the note says so — test_a_fill_shows_the_readers_word_on_it RED→GREEN — cost if wrong: none
- **Final:** Ruling: the Gmail reply goes in a block the reader builds at the top of the box (lines as divs, then an input event) rather than typed with the caret at the top — Gmail's editor holds the signature and quoted text in the same box, and a block of its own is what a later approval can replace; Gmail sends the box's content — cost if wrong: Gmail might not notice the text until the user types in the box (the live check covers it)
- **Final:** Ruling: added sites keep text-based ids unless a row has its own data id (data-id, data-key, data-item-id, data-row-key); links are not used as ids — a link shared by rows (or added later) would merge or renumber rows — cost if wrong: a row whose words change (besides times) is reported again
- **Final:** Ruling: an empty Gmail inbox is recognized by Gmail's main region with no unread count in the tab title — a reader that stops finding rows while mail is unread is still flagged; one that breaks on an all-read inbox is flagged when mail arrives — cost if wrong: a broken reader shows as fine until the next unread email
- **Final:** Ruling: deferred minor 8 (Train: edit after the diff, then confirm) stays deferred; train.js unchanged — cost if wrong: an edited update is written after the user saw an older diff
- **Final:** Ruling: the workspace folder stays — there is no git here, so this ledger is the only record of the rulings and deferred minors — cost if wrong: a few KB

### Deferred minors

- **Final:** minor (deferred): 1 Pause stops reading only; a Draft or Tell the user clicks while paused still runs (README to say so)
- **Final:** minor (deferred): 4 items accepted but not yet sorted are lost if the app stops before the batch and they can't be reported again; an extension reload clears the watcher's unsent queue
- **Final:** minor (deferred): 8 Train: editing after the diff then confirming writes the edited text
- **Final:** minor (deferred): 9 "ai <workflow>" can start a plain agent when the AI Browser worker has just woken and has no workflow names yet
- **Final:** minor (deferred): 11 a burst of run-right-away messages starts one agent per item (3 at a time, the rest wait)
- **Final:** minor (deferred): 12b-d the Brave permission notification's Review doesn't deep-link the card, isn't cleared once answered elsewhere; brain.html gets every AI Browser broadcast (thumbnails included)
- **Final:** minor (deferred): 13b ToolsConfig re-reads ~/.claude.json and every project's .mcp.json on each call
- **Final:** minor (deferred): 14 the live check must use an email from another account (a self-sent row is from_me)

## Mission Control (project 6)

### Rulings

- **Pre-flight:** Ruling: the room's look uses the prototype values checked by screenshot (scratchpad room-proto.png), not the plan's first numbers: perspective 1800px from 50% 20%, the room at 58% of the height, default tilt 58° (clamped 35–70), station cards 176px wide with a 92px monitor; stations in rings around the Brain at room (1000, 540): up to 6 at radius 470 over ±100° (the prototype's horseshoe), then 8 at 720 over ±110°, then the rest at 970 over ±115°, outer rings offset half a step so their cards fall between the inner ones — the plan's radii (520/760/1000 over ±60°) put the second arc in front of the first, covering it — cost if wrong: a different arrangement after the screenshots
- **Pre-flight:** Ruling: the blob's shader is the prototype's (noise sphere ray-marched in 40 steps, colours per state mixed through u_mix, a halo from r 0.42 masked at the edges): checked by screenshot in all four states — cost if wrong: none
- **Task 1:** Ruling: the busy signal is a context manager (_busy(what)) rather than _busy/_idle methods, and the Brain's snapshot and state carry "activity" (what it is doing now) so a Mission Control opened mid-sort shows it — cost if wrong: none
- **Task 2:** Ruling: stations sit in rows, not on the prototype's horseshoe — screenshots (scratchpad mission/room-6-small.png, first version) showed the horseshoe's side stations stacking on screen (at ±60° and ±100° their x differs by 56 room px); now the first six sit side by side 240 room px apart on an arc in front of the Brain (oldest on the left), the next rows take turns behind the first (beside the Brain, 440 apart, leaving its place free) and in front of it (340 apart), each half a seat over from the row before; the room's zoom is fitted (the real perspective projection) so every station's foot is above the task bar and the farthest card and the Brain are below the top bar — supersedes the pre-flight ruling's rings — cost if wrong: a different arrangement
- **Task 2:** Ruling: stations are ordered by the agent's creation time, not by the snapshot's order (newest first): an agent keeps its seat when the page is opened again — cost if wrong: none
- **Task 3:** Ruling: the agent drawer also has AI Home's message box (send), since the spec's "its chat (the same chat AI Home shows)" includes writing to the agent; Enter starts a task from the task bar (Shift+Enter: a new line); the model picked is shared with AI Home (chrome.storage.local "model") — cost if wrong: none
- **Task 4:** Ruling: the blob draws at most 30 frames a second (a slow-moving blob; less GPU for an always-open page); with reduced motion its surface stands still and frames are drawn only while it eases to a new state; the CSS orb has its own states (breathe, swirl, warm, talk), stopped by reduced motion — cost if wrong: none
- **Task 4:** Ruling: "N needs you" under the blob counts the Brain's items that need a reply; agents waiting for a permission make it glow too (alert) and show at their stations — cost if wrong: none
- **Task 5:** Ruling: with Voice on, an update moves on when its speech ends (plus 0.6 s), with a 12 s limit for a voice that never says it ended; with Voice off, after 5 s; a summary counts every update it stands for (8 at once: the first, then "7 more updates: open the Brain"); clicking the bubble opens the Brain's inbox — cost if wrong: none
- **Task 5:** Ruling: updates have no closing period (summaries often end with one already) and name a connector's server without "claude_ai_" and tools with spaces ("ClickUp: create task") — cost if wrong: none
- **Final:** Ruling: "Declined to judge: speech after a reload with Voice remembered on" is a finding — Chrome lets a page speak only after the user clicked it, so a reopened Mission Control would stay silent without saying why; now a refused speech ("not-allowed") shows "Click anywhere on this page to let the Brain speak" and the first click lets the next update speak — test_voice_waits_for_a_click_when_chrome_asks_for_one RED→GREEN — cost if wrong: none
- **Final:** Ruling: declined "rows instead of arcs" — the Task 2 ruling stands (screenshots) — cost if wrong: a different arrangement
- **Final:** Ruling: declined "N need you counts only the Brain's items" — the Task 4 ruling stands; agents waiting show at their glowing stations and in the top bar's counts — cost if wrong: the user looks at two places
- **Final:** Ruling: declined "the summary says open the Brain even for agent updates" — the plan's wording; the bubble opens the Brain and agent updates are on their stations — cost if wrong: a word to change
- **Final:** Ruling: declined "the AI Home link replaces Mission Control in its tab" — a link back, as the spec says; the Mission Control button reopens it — cost if wrong: one click
- **Final:** Ruling: declined "Enter starts a task here, Cmd+Enter in AI Home" — the Task 3 ruling stands — cost if wrong: none
- **Final:** Ruling: declined "the blob's GPU cost at up to 2× pixel density" — the spec's bound (at most 360 CSS px, ratio at most 2, 30 frames a second, nothing while the tab is hidden) — cost if wrong: some battery on a Retina Mac while the page is in front
- **Final:** Ruling: declined "accessibility beyond the List" (focus into and back from the drawer, a role for the scene's label) — stations are buttons with labels and the List is a plain list; focus handling is polish for later — cost if wrong: keyboard users press Tab to reach the drawer
- **Final:** Ruling: declined "stations change seats when one in the middle closes" — placeOf keeps the oldest first by design — cost if wrong: none
- **Final:** Ruling: declined "the blob is soft at the highest zoom (antialias off)" — a soft glowing object; antialiasing costs GPU on an all-day page — cost if wrong: none

### Deferred minors

- **Final:** minor (deferred): 10 the blob's shader is mediump with an ever-growing time: on a GPU where mediump is 16-bit the motion could coarsen after a long session (headless reports 23-bit; not testable here)

## Still to do together

These need your Brave, Gmail, Slack and connectors:
1. Load the watcher in Brave.
2. Send yourself an email from **another** account. One sent from your own account counts as "from me" and is skipped.
3. Draft and Approve a reply to it in Gmail. Check that it lands above your signature, and press Send yourself.
4. Open Spam, then an empty inbox. Neither should raise an alarm or bring in mail.
5. Approve a multi-line Slack draft. It should arrive on one line, and nothing is sent.
6. Run a workflow that uses a claude.ai connector, to see its permission card.
7. In Mission Control, turn Voice on, reload the page and click it once: the next update should be spoken.
