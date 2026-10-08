# Saved agents, and Mission Control without AI Home (design)

Date: 2026-10-08. Status: for the user's review. The user's standing word: decide with the recommended option and say
each one; every decision below says why, and what it costs if it's wrong.

## What the user asked (verbatim)

"each agent have an assigned browser profile, there should be settings for each agent on what skills they can access
and preload for context so they. can start working immediately. they should also have an auto schedule setting for each
agent. and have a confirm delete if user deletes an agent. basically they are like dots agent same concept. the AI home
you can remove that since all features can be access now in mission control page. and add a settings for agent a
preconfigured instruction for them too. Plan this changes so they dont overlap with others and override the previous
changes that needs to override if necessary"

## How this reads (the decisions the rest follows)

1. **"Like dots agent" = Claude Code's saved agents** (the `~/.claude/agents/<name>.md` files: a name, a description,
   an instruction, skills, a model). An agent stops being only a run: it becomes a **saved agent** the user sets up
   once and runs many times. A run is still a desk in Mission Control; a run *of a saved agent* carries its settings.
   One-off runs (today's Build a Mission) stay. *If wrong:* the user meant something else by "dots" — the rest still
   holds for persistent agents.
2. **A saved agent is a file** `~/.ai-browser/agents/<slug>.md` (0600): YAML front matter, and the body is its
   instruction — the same shape as Claude Code's agent files and AI Browser's own templates
   (`brain/workflows.py`, which already reads and writes this format). *Why:* one format the user already has, easy
   to read, copy or back up. *If wrong:* a file per agent instead of one JSON; nothing else depends on it.
3. **"Assigned browser profile" = a Brave profile**, per agent: agents drive the user's own Brave, and Settings →
   *Where agents browse* already picks one Brave profile for all agents (`app/place.py`, which learns each profile's
   browser context). Each saved agent picks its own, or "Settings' choice". *Why not a separate sandbox browser per
   agent:* app agents can't use the sandbox today (`sandbox_start` is disallowed for them), and without Docker it
   needs the paused no-Docker work; a Brave profile keeps the user's logins per profile, which is what a profile is
   for. *If wrong:* a later change can add "its own sandbox profile" as a second kind of place.
4. **"Auto schedule" reuses templates' schedules.** Templates (`brain/workflows.py`) already have a schedule
   ("daily 09:00", "weekdays 09:00", "mon,wed 17:00", "every 2h"), a 30-second ticker and the Calendar. A template
   gains **Runs as** (a saved agent, or "a new agent" as today), and an agent's settings show its **Tasks** — the
   templates that run as it — with Add, Edit, Run and Remove. *Why:* one scheduler, one format; the Brain's inbox
   already suggests templates by their id, so nothing there breaks. *If wrong:* two places to set a schedule is what
   this avoids.
5. **AI Home goes.** Mission Control becomes the window's first tab; `/home` opens Mission Control. Everything that
   exists *only* in AI Home today moves into Mission Control or Settings first (section 6), then AI Home is removed.
   This **overrides** two earlier changes: templates leaving Mission Control for AI Home (brain delegation, Task 2)
   come back inside Mission Control's new **Agents** page (not as the old Templates menu item the user removed), and
   AI Home's hand-off slot (brain delegation, Task 10) goes with AI Home.

## The design

### 1. Saved agents (the Agents page)
- Mission Control's left menu gains **Agents** (between My Missions and Knowledge). It lists the saved agents as
  cards — name, what it works on, its Brave profile, its next scheduled task, and whether a run of it is working —
  with **New agent**.
- Below the agents: **Tasks for any agent** — the templates that run as "a new agent" (today's templates), with Run,
  Edit and Delete as today (`workflows.js`, mounted here instead of AI Home).
- A click on an agent opens its **settings** (a panel over the page, like the drawer):
  - **Name** (at most 60 characters) and **What it works on** (at most 160), cleaned as a mission's are
    (`workspaces.one_line`).
  - **Instruction**: the agent's standing instruction (at most 8,000 characters), the user's own words.
  - **Browser profile**: the Brave profiles (names and colours, as Settings lists them), or "Settings' choice".
  - **Web** (Web + Brave / Brave only / No web), **Model**, **Account** (with two or more), **Folder** (its trust
    question as in Build a Mission).
  - **Skills**: every installed skill with two boxes — **Can use** and **Load at start**; "Load at start" implies "Can
    use". Nothing ticked under Can use means "every skill" (today's behaviour).
  - **Tasks**: its templates (when, what to do, last run), with **Add task**, Edit, Run, Remove.
  - **Delete agent** (section 5).
- Saved with **Save**; the page shows the app's refusal words if a value is refused. Only AI Browser's own pages can
  save or delete an agent (new page messages, app-only in `MESSAGE_RULES`, with their copy in
  `tests/test_watcher_rules.py`). The Brain, templates and pages never write an agent.
- **Save as agent** in a run's drawer makes a saved agent from a one-off run: its name, what it works on, model,
  account, folder, web and the skills it loaded (as Load at start); its instruction starts empty.

### 2. Running a saved agent
- **Build a Mission** gains **Agent ▾**: "New agent" (today's Name and What it works on fields) or a saved agent (its
  name shows instead of the two fields, and its settings apply to the run: profile, web, model, account, folder,
  skills, instruction). The task box stays the task.
- **One run at a time per saved agent.** A task given to a saved agent whose run is working goes to that run as a
  message (as the drawer's Send does). A scheduled task that comes due while it works is skipped with today's note
  ("Skipped 09:00: the last run is still going").
- The run's desk, Current Task, My Missions, History and the drawer show the saved agent's name and what it works on
  (the named-missions places).
- Auto-approve stays a per-run switch the user clicks; a saved agent never turns it on (as templates never do).

### 3. What the agent knows when it starts
- **Instruction:** added to the agent's system prompt after AI Browser's own (`BRAVE_PROMPT`), under a fixed line:
  "The user's standing instruction for this agent:". It is the user's own words, written only in the agent's
  settings. Cleaned of control and invisible format characters (line breaks kept), at most 8,000 characters.
- **Load at start:** the chosen skills' SKILL.md text (paths rewritten as `load_skill` does) goes into the run's first
  message, before the task, under a fixed line: "Skills the user loaded for you:" — so the agent doesn't spend turns
  finding and loading them. At most 60,000 characters in all; a skill past that is named in a line asking the agent
  to load it with `load_skill` (today's path). A skill no longer installed is skipped with a note on the run.
  *Why the first message, not the system prompt:* the system prompt travels on the command line, which on Windows is
  limited to about 32,000 characters; the first message goes through the process's input.
- **Can use:** enforced by AI Browser's own tools, not by the prompt: the agent's tool server gets the agent's list,
  and `find_skills` lists only those, while `load_skill` and `read_skill_file` refuse others with "This agent can't use
  that skill: change it in its settings". An empty list is every skill.

### 4. The agent's Brave profile
- A run of a saved agent opens its own tabs in its profile's browser context, which `app/place.py` already learns per
  profile (Brave names a profile only by the one it used last; the app learns a profile's context once Brave has used
  it on this connection).
- **A profile not learned yet:** the agent's first page says, in fixed words, "Agent 2 browses in Brave's Work
  profile. Open a window of that profile once; AI Browser learns it in about 30 seconds." The agent's settings show
  each profile as "ready" or "open it once". Nothing opens Brave windows by itself.
- Settings → *Where agents browse* stays: it is the default for one-off runs and "Settings' choice".
- The user's own tabs handed to an agent stay where they are; Fewer tabs (two of its own) holds per run.

### 5. Confirm before deleting
- **Delete agent** opens a dialog in the page (focus inside it, Escape and Keep do nothing): "Delete <name>? Its
  settings, its instruction and its N tasks are deleted (listed by name). Its runs and their files stay." Buttons:
  **Delete** and **Keep** (Keep is the default).
- A working run of it keeps going as a one-off run; the dialog says so.
- **Close** on a run that is still working asks the same way ("End agent 2 while it works? Its tabs close; your own
  tabs stay."). A finished run closes at once, as today.
- Deleting a template keeps its two-click Delete.

### 6. Mission Control without AI Home
Everything only AI Home has today moves first; then AI Home is removed.
- **Brave's connection** (Connect, Try again, Show me how, the steps): a bar at the top of Mission Control while Brave
  isn't connected or is asking; **connected clients with Disconnect** and the old-watcher note go to Settings → Brave.
- **The full tab list** (owners, Hand over → New agent… / Give to …, Take back): a **Tabs** page in Mission Control's
  left menu (`tablist.js`'s `mountTabList`).
- **Skills for a one-off run:** Build a Mission gains a Skills picker (Load at start); Knowledge gains "in use by",
  **Use in new mission** and **Ask an agent to use it**.
- **Save as skill**, **cost** and **skills loaded**: in a run's drawer.
- **The Brain's limit card** ("Continue on…"): in the Brain's inbox (the globe's drawer), with "Turn it on in
  Settings" when the Brain is off.
- **A notification's click and the floating chat's "Open…"**: Mission Control handles `focus` (opens that run's
  drawer, or the Brain's inbox). The floating chat's button says **Open Mission Control**.
- **The window's count and badge** ("(2) …"): read from Mission Control's title.
- **Words that name AI Home** (notifications, the agent's system prompt, the CLI, the relay's and the setup's
  messages, the README): name Mission Control or Settings instead.
- **Settings' base styles** (now borrowed from `home.css`): their own shared stylesheet.
- `/home` (and an old bookmark of it) opens Mission Control; the hand-off views are Mission Control and the floating
  chat.

## Safety rules that change, and those that stay
- **New:** a saved agent's instruction reaches its system prompt — it is the user's own words, written only in the
  agent's settings by a click on Save in AI Browser's own page.
- **Stays:** pages, messages, the Brain and templates never write an agent's instruction or settings; page text is
  data; auto-approve only by the user's click per run; a run's tabs open only in the profile the user chose; never
  open, close or change the user's Brave profiles or settings; downloads need the user's OK; every new page message
  is app-only in `MESSAGE_RULES` with its copy in `tests/test_watcher_rules.py`; tests never touch the user's real
  browsers, `~/.ai-browser`, `~/.claude`, `~/Downloads` or port 8792; never run the real `claude`.

## Order, and what this overrides
- **After the brain-delegation batch merges** (it is finishing now; this plan is written against main with it).
- **No-Docker** (paused at its save point) touches `engine.py`'s skill tools and the shell, Settings → Sandbox, the
  README and `doctor`. This batch touches `engine.py`'s skill tools too (Can use) and the README. Recommended order:
  finish no-Docker first, then this batch, so neither re-plans the other; the plan marks the tasks that touch
  no-Docker's files so they can wait for it if this batch goes first.
- **Overrides:** brain delegation's "Templates stay in AI Home" (they move into Agents) and AI Home's hand-off slot
  (gone with AI Home); the composer keeps having no Use a Template mode (the user's earlier ask).

## Testing
- Saved agents: the file (fields, limits, cleaning, 0600), save and delete over the socket (app-only), refusal words.
- Running: Agent ▾ applies every setting; one run per agent (a second task becomes a message; a due schedule is
  skipped); auto-approve never on from a saved agent.
- What it knows: the instruction in the system prompt (fake claude records argv); Load at start in the first message
  with its cap; Can use enforced by `find_skills`, `load_skill`, `read_skill_file`.
- Profile: a run's tabs open in its profile's context (fake Brave with two contexts); a profile not learned gives the
  fixed words.
- Delete and Close confirm: the dialog's words, Keep by default, Escape keeps.
- AI Home's features found in Mission Control (each moved item), `/home` opens Mission Control, no page or word
  still names AI Home, the test fixture opens Mission Control.

## Out of scope
- An agent with its own sandbox browser; importing `~/.claude/agents/` files; agents talking to each other beyond the
  Brain's hand-offs; a per-agent usage budget.
