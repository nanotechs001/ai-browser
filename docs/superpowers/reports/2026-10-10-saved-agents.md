# Report: saved agents, and Mission Control without AI Home

Spec `docs/superpowers/specs/2026-10-08-saved-agents-design.md`, plan `docs/superpowers/plans/2026-10-08-saved-agents.md`.
Built subagent-driven on 2026-10-09/10 on branch `saved-agents` (from main fe324ee), in two lanes (`agents-a`,
`agents-b`) joined at M1–M3. Every task had its own review (opus for the security-sensitive ones); a final whole-branch
review (opus) and one fix wave followed.

## Result
- 21 tasks done. Whole suite on `saved-agents` at 7b9c232: **2809 passed, 10 skipped, 111 deselected** (`-m "not docker"`).
- Final review: 0 Critical, 2 Important (both fixed in the fix wave, re-reviewed), 9 Minor.
- Not merged to main and not pushed: waiting for the user.

## Rulings (every decision taken during the build, with what it costs if wrong)
- Ruling: Task 7 fix round 2 on saved-agents — the fixture registers a real one-off a1 (no profile) before connecting; and the fixer must prove from the code (and a test) that a real run is in AgentManager.agents before its engine can reach the relay (else fail-closed would refuse real agents) — cost if wrong: none
- Ruling (final review 1, adopted): a run started from inbox text (run: auto, or the inbox's Run click) starts with Auto-approve off; scheduled and by-hand runs keep the agent's setting — why: the user's tick covers work on their own words, not any sender's email (same rule as plan decision 9) — cost if wrong: one click on the drawer's switch for a trusted inbox run
- Ruling (final review 2, adopted): Agent ▾ moves out of #pickers into the modes row before #mission-words; .mission-words may shrink; test with a saved agent at (20, 1024x700) — cost if wrong: none
- Ruling: fold the cheap deferred items into the one fix wave: folderpick's late answer vs No folder; a note on an inbox item whose auto-run was refused; a task given while its run is closing starts a new run instead of being dropped; README lines 719-721 and 725; Save as agent follows the default account
- Final: parked — a close() that raises or is cancelled before agents.pop leaves the run marked closing forever (invisible to run_of; a second run can start beside it) — Ruling: deferred (no second fix wave; before the fix such a run swallowed new tasks, which was worse) — cost if wrong: in that rare failure, a saved agent can have two runs
- Ruling: base is main fe324ee, not the plan's 8d5fb44 — the iframes merge landed since; only its files drifted and the pre-flight re-checks their quotes — cost if wrong: a step's quote misses and its implementer records a deviation.
- Ruling: Tasks 1 and 9 start before the pre-flight returns — they touch only new files and pages, none of the drifted files — cost if wrong: a pre-flight finding on them becomes a fix round.
- Ruling: Task 19 also changes cdprelay.py's `_one_shot` docstring "(an agent's and AI Home's thumbnail)" to "(an agent's and Mission Control's thumbnail)", and the same words in tests/test_cdprelay.py (Task 19 owns it) — why: the iframes merge added it and Task 19's no-AI-Home test reads all of cdprelay.py — cost if wrong: none (words). tests/test_cdprelay_chrome.py's docstring is left (no task owns it, no test reads it); Task 21's final check notes it.
- Ruling: Lanes-table rows omit test files tasks only append to (test_saved_agents.py, test_mission_home.py, test_agents_page.py); each stays in its own lane in order — no change — cost if wrong: none.
- Task 11: Ruling: accept the ownerOf deviation — the brief's constant would show an agent's tab as "you" in AI Browser mode and offer Hand over on it — cost if wrong: none
- Task 12: Ruling: accept pickSkill as its own method (the brief's replacement would have nested it inside focus()) — cost if wrong: none
- Task 14: Ruling (plan conflict): no fix now — the plan moves the start tab in Task 20 (app.js FIXED = [["/mission", …], ["/settings", …]]), which must wait for M2 (the templates' UI lives in AI Home until Task 15); the gap exists only on this intermediate branch, never merged alone — carry to Task 20: add a tab-menu test (fresh shell, a working agent, /mission never picked by the test → the window's title shows "(1) …"; and a `focus` opens the agent's drawer) — cost if wrong: none for the user (M3 merges after Task 20)
- Ruling: Task 1's _BREAKS keys written as  /  escapes, not raw characters — same value; raw ones are invisible and easy to lose — cost if wrong: none
- Task 1: Ruling: fix finding 2 (plan-mandated code): an edit whose slug names a file that doesn't load is refused with NOT_AN_AGENT and the file is left as it is — why: the brief says the store never writes over a file it can't read; a crafted slug could replace a hand-edited broken file — cost if wrong: none (a broken file is never listed, so the page never sends its slug)
- Task 1: Ruling: fold finding 1 in the same fix (test U+2029 and a bare \r in the instruction) — cheap, and the _BREAKS keys are otherwise unguarded — cost if wrong: none
- Task 2: Ruling: accept the deviation — _saved_check compares profile against a list, not a set, and the socket test gains profile=["Profile 1"] refused — why: a list-valued profile raised TypeError and closed the window's socket — cost if wrong: none
- Task 4: Ruling: Can use is enforced by AI Browser's skill tools only, as the spec says; skill folders stay mounted, so the shell can still read one by path — carry to Task 21: the README must not call it a hard boundary — cost if wrong: a user may think Can use hides a skill's files
- Task 4: Ruling (re-graded by effect, Minor 1 → fix): with Auto-approve on and Docker off, a narrowed agent's Bash treats every installed skill's folder as its own (skills.skill_folders hides only blocked ones), so it could run a script of a skill outside Can use without a card. Fix: when the run's AIB_APP_SKILLS names skills, the folders of installed skills outside it join `hidden` (same as blocked) — why: Auto-approve must not trust what the agent may not use; consistent with the spec's "only those" — cost if wrong: one more card when a narrowed agent runs another skill's script by path
- Task 4: Ruling: fold Minor 2 (tests: read_skill_file by short name refused; two skills sharing a short name, only one allowed) into the same fix — cost if wrong: none
- Task 4: Ruling (round 2): for a narrowed run (allowed is not None), the roots Auto-approve trusts are only the folders of the allowed, non-blocked skills (hidden kept as is) — why: an allowlist must fail closed for folders the catalog can't name — cost if wrong: a narrowed run's scripts in odd plugin layouts ask with a card. The implementer checks every consumer of SkillFolders.roots (e.g. whether the Docker sandbox mounts come from it) and changes only the Auto-approve side.
- Task 7: Ruling: a deleted agent's working run keeps its profile (forget_saved clears saved, not profile) — why: the safety rule says a run's tabs open only in the profile the user chose; switching mid-run could open one elsewhere — cost if wrong: that run keeps using the deleted agent's profile until it ends
- Task 7: Ruling: the not-learned note shows once per run, also after a reconnect loses the profile (the brief's "once") — cost if wrong: the user isn't told again; Claude still hears NOT_OPEN
- Task 7: Ruling (re-graded, Minor 1 → fix): _placed_only returns False for an agent id not in self.agents (fail-open in the window between AgentManager.close's pop and the relay's forget) — fix: an agent-shaped identity not in agents is refused (True) — why: the safety rule is "nothing opens in the wrong profile", so unknown must fail closed — cost if wrong: none (a closing run's tab request is refused)
- Task 7: Ruling: fold the note's profile-name cap ([:60]) into the same fix — cost if wrong: none
- Task 7: Ruling: a popup from a tab the user handed to a profile-bound run lands in that tab's profile — the user's own act, predates this branch — no change — cost if wrong: such a run can have a tab outside its profile, only from a tab the user gave it
- Task 15: Ruling: AI Home's templates list (home.js, default mountWorkflows) drops a template's runs_as on save — transitional, AI Home goes in Task 20 before anything merges to main — no fix — cost if wrong: none for the user
- Task 15: Ruling: fix — set(path) keeps the path and value() returns it until the user picks again; the server's _saved_check then judges it (a missing folder is refused with words, nothing written) — why: only the user changes the folder — cost if wrong: none
- Task 15: Ruling: fold Minor 1 — a saved account no longer listed is kept as an extra option (as profiles are), never silently cleared — cost if wrong: none
- Task 16: Ruling: fix — cap #task-agent's width in CSS (ellipsis) and test the picker rows stay 3 with a 60-character agent name — cost if wrong: a long name shows cut in the select
- Task 16: Ruling: the picker reorder (deviation) stands; tab order changed accordingly — cost if wrong: Auto-approve sits two pickers after Folder
- Task 17: Ruling: fix (a)–(d): confirm.js stops keydown from leaving the dialog and puts focus back on Keep after a click that isn't on a button; mission.js's Command-K capture listener ignores keys while a modal dialog is open; test that Escape in the Close dialog leaves the drawer open and that a stray click keeps Keep focused — why: spec "Escape and Keep do nothing", plan decision 12 "the page behind can't be reached" — cost if wrong: none
- Task 17: Ruling: fold Minors 1–2 — Delete says "Not connected…" when the send fails; the Delete dialog uses stateOf() (as the drawer) to say the run keeps going — cost if wrong: none
- Task 17: Ruling (round 2): talk.js's capture pointerdown leaves focus alone when the target is inside a dialog (one shared exemption, root cause); test a right-click on the dialog's text keeps Keep focused — cost if wrong: none
- Task 16: parked — residual: with ≥1 saved agent, at ~1024 wide the pickers take 3 rows and ~20 desks may cover nameplates (untested) — Ruling: the final whole-branch review fixes it properly (move Agent ▾ out of #pickers, or size the room for the composer's real height) and adds the parametrized test with a saved agent — cost if wrong: step cards may cover desk names in a crowded room on a narrow window
- Task 17: Ruling: accept the deviation — confirm.js also preventDefaults a mousedown on the dialog off a button (Chrome otherwise moves focus to the <dialog>, so Enter no longer keeps) — cost if wrong: the dialog's words can't be selected with the mouse

## Parked, deferred and flagged (the per-task reviews' minors; the final review triaged them)
- Final: parked — a close() that raises or is cancelled before agents.pop leaves the run marked closing forever (invisible to run_of; a second run can start beside it) — Ruling: deferred (no second fix wave; before the fix such a run swallowed new tasks, which was worse) — cost if wrong: in that rare failure, a saved agent can have two runs
- Task 9: minor (deferred): bravebar.js duplicates home.js's SAYS/ACTIONS/steps/notes until Task 20 deletes home.js (plan-mandated)
- Task 9: minor (deferred): bravebar.js rebuilds the list on every browser message under aria-live=polite (may re-announce); skip render when unchanged
- Task 9: minor (deferred): the "any program can reach your Brave" warning shows in refused/lost too (as AI Home did)
- Task 9: minor (deferred): test_mission_home.py leaves lost state, warning text, non-Brave kind unasserted; one long test
- Task 10: minor (deferred): "unticking the switch cuts off everything" (bravesettings.js:42, copied from home.js) doesn't say the switch is Brave's own remote-debugging switch
- Task 10: minor (deferred): settings.css lacks home.css's `.empty` style (permsettings.js's empty line loses its 14px size and margin)
- Task 10: minor (deferred): bravesettings.js's `client` class is unused; Brave's not-connected line shows in both the Brave section and Where agents browse (plan-mandated)
- Task 11: minor (deferred): Tabs page chips go stale in AI Browser mode until the next tabs message (no re-render on agents)
- Task 11: minor (deferred): the ownerOf branch (no tab.owner) has no test
- Task 11: minor (deferred): #handing keeps a closed tab's target until Start; and stays visible in Ask AI mode, where adopt isn't sent
- Task 12: minor (deferred): Knowledge's Ask gives no sign it was sent (double click sends twice); its agent list includes finished agents
- Task 12: minor (deferred): usedBy's bare-name match marks same-named skills in use (as home.js); refreshUses comment says the list is never rebuilt; the Skills <details> doesn't close on Escape
- Task 12: minor (deferred): no test that choosing an agent in the select alone sends nothing
- Task 13: minor (deferred): drawer totals show "0 s" on a fresh run
- Task 14: minor (deferred): mission.js comments at ~317/~345 and app.js's header line cut or over 120 columns; tests/test_home.py may keep unused json/EVENTS imports
- Task 14: complete (commits e42d120..4288242, 1 Important parked with ruling → Task 20)
- Task 19: minor (deferred): a few docstring/string lines grew past ~120 columns (cdprelay.py:781, test_cdprelay.py:860, server.py:395/499, settings.py:78, run.py:89)
- Task 19: minor (deferred): _show_app docstring wraps choppily and still says "agent's row" (→ "that agent's drawer, or the Brain's inbox")
- Task 19: minor (deferred): server.py calls them templates while brain/workflows.py says workflows
- Task 20: minor (deferred): test_home's bookmark test may pass on the old document (mark window before assign); app.js:10 comment 161 columns (brief's text); the carried test was seen failing only at its fixture
- Task 1: minor (deferred): savedagents.py front-matter end matches "\n---" followed by anything (e.g. "\n----"); only hand-edited files hit it
- Task 1: minor (deferred): skill lists' dedupe, sort and SKILLS_MOST cap untested
- Task 2: minor (deferred): a failed saved_agent_delete's OSError says "Couldn't save that" (server.py ~1899; brief-mandated wording)
- Task 2: minor (deferred): _saved_check refuses any profile when self.brave is None (Chrome mode: _profiles() is []); in Brave mode profiles come from Brave's folder on disk (place.profiles → browsers.profiles), so a disconnected Brave is fine — checked by the controller
- Task 2: minor (deferred): socket test lacks a delete of an unknown slug and an edit keeping its file
- Task 1: minor (deferred): NOT_AN_AGENT for a present-but-unreadable file says the agent doesn't exist
- Task 3: minor (deferred): the bridge re-cleans the instruction but doesn't cap it at 8,000 (savedagents._load's check() does for every file-loaded agent)
- Task 3: minor (deferred): clean_instruction keeps Co/Cn code points (harmless on a command line)
- Task 4: minor (deferred): Engine.catalog re-reads AIB_APP_SKILLS from the process env while allowed is None; the mcp.json env test is the guard
- Task 5: minor (deferred): _preload's `except Exception` drops Load at start silently (no note, no log)
- Task 5: minor (deferred): Docker asked once per app run (plan decision 21) while load_skill asks each time; docker_answers duplicates engine._docker_running
- Task 5: minor (deferred): the 60,000 cap counts skill text only (+~35 chars of heading); a blocked skill may get the "no longer installed" note
- Task 6: minor (deferred): a task for an agent given while its run is closing joins that run and is dropped silently (mark closing runs and skip them in run_of)
- Task 6: minor (deferred): server drops _hand's "why not" for a tab handed to a run at work; no test of that path
- Task 6: minor (deferred): run_as docstring's skills sentence should say "a new run only"
- Task 7: minor (deferred): _told_profile is never pruned (one id per not-learned run per app run)
- Task 8: FLAG for the final review and the user: a message-triggered template with run: auto that runs as an idle agent with Auto-approve on starts an Auto-approve run from an email's text (labelled page data; the always-ask list still applies) — allowed by spec decision 8; the final review weighs it on purpose
- Task 8: minor (deferred): inbox auto-run skip has no note on the item; a partial OSError in _forget_tasks reports "Couldn't save that" without broadcasting; BAD_RUNS_AS checks only the slug's shape; delete test doesn't assert auto_approve is absent from the saved file
- Task 15: minor (deferred): the skills list doesn't redraw from the saved row; profile labels go stale while the panel is open; a template whose runs_as names a missing agent is shown nowhere (only via hand edit: deleting an agent deletes its tasks); "Next:" time locale-formatted
- Task 16: minor (deferred): #task-agent isn't cleared after Start (next Start goes to the same agent); untested: deleted selected agent falls back, attachment with agent
- Task 15: minor (deferred): a late folder answer to set()'s check can overwrite a later "No folder" (pre-existing)
- Task 17: minor (deferred): a stale dialog can send a delete the app refuses (error dropped); no test for Close on a run waiting in line or a double click on .go
- Task 17: minor (deferred): Escape with a live voice turn cancels the turn and the dialog stays open (a second Escape keeps); ⌘W posts close-tab behind the dialog (no effect on Mission Control)
- Task 16: parked — residual: with ≥1 saved agent, at ~1024 wide the pickers take 3 rows and ~20 desks may cover nameplates (untested) — Ruling: the final whole-branch review fixes it properly (move Agent ▾ out of #pickers, or size the room for the composer's real height) and adds the parametrized test with a saved agent — cost if wrong: step cards may cover desk names in a crowded room on a narrow window
- Task 16: complete (commits f944dc5..532c10e + 1008369..b63e871 + 92f4f9b..bdba1b7, 2 fix rounds, 1 residual parked → final review)

## Hand checks (the user's, on their own computer)
Each on the user's own computer, with AI Browser running and their Brave connected, and a second Brave profile opened
once:
1. **The window:** it opens on Mission Control; the tab row is Mission Control, then Settings. With Brave's switch
   off, the bar at the top shows **Show me how**; turned on, **Connect** connects and the bar goes.
2. **Settings → Brave:** lists AI Browser, each agent and a Claude Code session using Brave, each with
   **Disconnect**.
3. **Tabs:** Mission Control → **Tabs** lists your tabs and whose each is; **Hand over** → **New agent…** opens Build
   a Mission with the tab; **Take back** ends it.
4. **A saved agent:** (before any exists, Build a Mission shows no **Agent ▾**.) Agents → **New agent**: name
   "Prices", instruction "Always answer in one short paragraph.", the second Brave profile, **Load at start** one
   skill, **Can use** two. Save. Build a Mission → **Agent ▾** → Prices, "open example.com and say its title": its
   tab opens in a window of the second profile; the answer is one paragraph; the drawer lists the loaded skill. Ask
   it to load a third skill: it says it can't use that skill.
5. **One run at a time:** while Prices works, give it another task through **Agent ▾**: it arrives in its chat as a
   message, and no second run starts.
6. **A profile not learned yet:** pick a profile you haven't opened since AI Browser started, and run the agent: its
   chat says to open a window of that profile once.
7. **A task that runs as it:** on Prices' card, **Add task** with a schedule; **Run** it: it runs as Prices (its
   profile, its instruction). The Calendar shows the next run; a click on it opens the Agents page there.
8. **Auto-approve:** set Prices' folder to a test folder you trust and turn on **Auto-approve in its folder**; a task
   that writes a file there runs with no card, and its line carries the **auto** mark.
9. **Close and Delete:** **Close** on a working run asks "End agent … while it works?"; Escape keeps it; **Close**
   closes it. **Delete agent** names its tasks; **Keep** keeps; **Delete** removes the agent, its tasks and
   `~/.ai-browser/agents/prices.md`.
10. **Save as agent / Save as skill:** a one-off run's drawer **Save as agent** opens a new agent's settings filled
    from it; **Save as skill** opens Knowledge's Train with a draft from its chat.
11. **Notifications:** a notification's click opens Mission Control at that agent's drawer; the floating chat's
    **Open Mission Control** does too.

Windows waits until all changes are in (HANDOFF 2c): the GitHub workflow **tests** on `windows` runs then.

12. **An email never starts an Auto-approve run (from the final review):** a message-triggered template that runs as a
    saved agent with Auto-approve on starts its run with Auto-approve off, and the run's chat says why.
13. **The composer at 1024×700 with a saved agent:** Agent ▾ sits beside Name in the top row; the options stay in their
    rows and the room keeps its size.
