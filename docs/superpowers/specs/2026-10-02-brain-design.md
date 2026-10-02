# The Brain — watch your messages, tell you what needs you, and ask what to do (project 5)

Date: 2026-10-02 · Status: design approved in chat. The user chose:
- "The Brain first";
- watch "slack, asana or maybe some selected websites that i can add and instruct on specific workflow, Gmail";
- "Your everyday browser";
- actions: "Draft replies for my OK", "Hand it to an agent", "Just tell me";
- "It fills it in, I press Send";
- "Read the page";
- part 1: "something like that but what I want to display emails are the emails that needs my response or new email not
  the whole inbox";
- part 2: "Looks right".

Then, reviewing this spec: "I want it be able to add my own workflow, agents can connect to tools like MCP too same on
claude code app". The user also chose:
- tool rights: "Ask me, with 'always allow'";
- workflow triggers: "A matching new message", "Me, from AI Home", "A schedule";
- then: "make it so the brain can create a skill whenever i want to train a new agent and assign a workflow, afer that
  then proceed".

**Two phases, one plan:**
- **Phase 1:** the watcher, the inbox, drafts and hand-off.
- **Phase 2:** workflows, agents using the user's MCP tools, and skills the Brain writes to train agents.

Builds on AI Browser (projects 3 and 4): the local app (`ai-browser app`), its server and its agents. Voice and the 3D
Mission Control are later projects.

## Goal

A Brain on the user's Mac:
- it watches the sites the user picks, in the browser the user lives in (Brave);
- it notices new messages;
- it tells the user only about what is new or needs them;
- it asks what to do, and then does the chosen thing.

Beyond that:
- **the user's own workflows**, named recipes in plain words, run as agents;
- **agents can use the user's MCP tools**, as in the Claude Code app, asking before anything that isn't always allowed;
- **training agents:** whenever the user wants, the Brain writes a skill (an agent's know-how, in Claude Code's
  `SKILL.md` format) from a description or from a finished agent's run. Workflows name the skills their agent uses.

Success means:
1. **Something that needs you:** with Gmail open in Brave, a new email that asks the user something produces, within
   about 10 seconds:
   - a notification in Brave with a one-line summary;
   - a line in the Brain inbox marked **needs your reply**.

   A newsletter produces neither; it only adds to the "others" count.
2. **Draft reply:**
   1. **Draft reply** opens that thread in a tab.
   2. A draft in the user's tone appears in the Brain inbox to edit and approve.
   3. On approval, the text is placed in Gmail's reply box. Nothing is sent: the user presses Send.
   4. The item clears once the reply is sent.
3. **Slack and Asana:**
   - a Slack direct message or @mention behaves the same way;
   - a new Asana task assigned to the user shows as **new**, with its summary.
4. **A site the user adds:** the user adds a site, clicks the part of the page to watch (for example an orders list),
   and writes an instruction. New rows in that part are handled per the instruction.
5. **Hand to agent:** this starts an AI Browser agent with the item and the user's instruction. The inbox item shows
   the agent's state and its result.
6. **Pause:** **Pause watching** stops all reading. Nothing reaches Claude while it is paused.
7. **Restart:** after `ai-browser app` restarts, the inbox and the watch list are still there.
8. **Never on its own:**
   - no API keys;
   - the calls that sort and draft have no tools;
   - the Brain never sends a message;
   - an agent starts only when the user clicks, or from a workflow the user wrote.
9. **Tools:** an agent can use an MCP server the user enabled (for example ClickUp).
   1. The first time it wants a tool that isn't always allowed, AI Home and the chat panel show the tool and its
      arguments, with **Allow once**, **Always allow** and **Deny**.
   2. The agent waits for the answer.
   3. **Always allow** is remembered across restarts.
10. **A workflow from a message:** a workflow triggered by a message (for example "a new Asana task tagged website") is
    offered as **Run <workflow>** on the matching inbox item. It runs as an agent when the user says yes, or at once
    when the workflow is set to run right away.
11. **A workflow by hand:** the user runs a workflow from AI Home's Workflows list, or with `ai <workflow name>` in the
    address bar.
12. **A scheduled workflow** (for example "weekdays 09:00") runs on time while `ai-browser app` is running. It still
    stops at any tool that isn't always allowed, until the user answers.
13. **Train a new agent:**
    1. The user describes a job ("build Elementor landing pages the way I like").
    2. The Brain drafts a skill: name, description, instructions.
    3. The user edits it and saves.
    4. It appears in AI Home's skills and in Claude Code's own (`~/.claude/skills/<name>/SKILL.md`), and agents can load
       it.
14. **Save as skill:** on a finished agent's chat, the Brain drafts a skill from that run (what it did, what worked,
    the user's corrections). The user reviews and saves it.
15. **Assign a workflow:** a workflow lists skills. Its agent loads them before it starts, so a trained agent is
    "assigned" to that workflow.

## What the user sees

### One-time setup in Brave

The app keeps a second small extension, the **watcher**, in `~/.ai-browser/app/watcher`. It refreshes that folder's
files and its `config.json` (the server address and token, mode 0600) at every start.

The first time, the app:
- opens the folder in Finder;
- prints the steps.

The steps are:
1. Open `brave://extensions` and turn on Developer mode.
2. Drag the **watcher** folder onto the page.

Brave keeps the watcher installed after that. It computes the watcher's ID from the folder path, so the app knows the
origin to allow.

### The watch list

The watch list is in the watcher's **Brain** page (`brain.html`), which also has the inbox. Each entry has:
- **the site:** Gmail, Slack, Asana, or one the user adds. Added sites ask Brave for permission for that one site only,
  when they are added;
- **what counts as new:**
  - **Gmail:** new emails in the inbox;
  - **Slack:** direct messages and @mentions;
  - **Asana:** tasks assigned to the user, and comments on the user's tasks;
  - **added sites:** the part of the page the user picked (a click-to-pick overlay stores a CSS selector);
- **the user's instructions, in plain words**, for example "Always tell me about clients; skip newsletters and
  receipts", or "When a new order appears, summarize it";
- **an on/off switch.**

A **Pause watching** switch stops everything. A **How I write** box holds style notes for drafts.

### The Brain inbox

The inbox is the watcher's `brain.html`, also shown as a section in AI Home. It **never mirrors the user's inbox**. It
lists only:
- **new**: messages that arrived since the user last looked;
- **needs your reply**: someone asked the user something or is waiting on them. These stay listed until the user
  replies or marks them Done.

Everything else is skipped and only counted ("14 others, nothing needs you").

Each item shows:
- the site, who it's from, and the subject;
- the Brain's one-line summary;
- why it matters (which instruction matched);
- a suggested action;
- buttons for **Draft reply**, **Hand to agent** and **Done**;
- a **Tell the Brain** box, where the user writes what to do in their own words.

**When items leave the list:**
- A **needs your reply** item clears when the watcher sees the user's reply in that thread. That means the user
  appearing as the latest sender in the Gmail row, the user's message after theirs in Slack, or the user's comment in
  Asana. It also clears when the user marks it Done.
- A **new** item stays until Done, or for 24 hours.

### Notifications

The watcher shows a Brave notification for each item that matters:
- a one-line summary;
- two buttons: **Draft reply** and **Open**, or **Hand to agent** and **Open** when the instruction suggests web work.

Items the Brain skips never notify.

### Tools (AI Home → Tools)

- **The list:** the MCP servers the user's Claude Code has, read from its configuration (user and project scope, and
  the claude.ai connectors it uses). Each one is switched on or off for AI Browser's agents. ai-browser's own tools are
  always on.
- **Always allowed:** the tools the user marked always allowed, which can be removed again. Read-only tools can be
  marked up front.
- **Permission requests:** an agent's request shows in three places:
  - on its AI Home row ("needs you");
  - in the chat panel for its tab;
  - as a Brave notification through the watcher.

  It shows the server, the tool and the arguments, as text, with **Allow once**, **Always allow** and **Deny**.

### Workflows (AI Home → Workflows)

**What a workflow has:**
- a **name**;
- **instructions** in plain words, for example "Open the site in AI Browser, make the change the task asks for, then
  post what you did in #web-team";
- **a trigger:**
  - **by hand:** AI Home's Run button, or `ai <name>` in the address bar, each with optional extra text;
  - **a message:** a site from the watch list, and when it applies, in plain words ("an Asana task tagged website"),
    with **ask me first** (the default) or **run right away**;
  - **a schedule:** "daily 09:00", "weekdays 09:00", "mon 08:30" or "every 2h";
- **the tools it may use:** MCP servers, still asked per tool unless always allowed;
- **a model.**

**Files:** each workflow is a file, `~/.ai-browser/workflows/<name>.md`, with front matter plus the instructions. The
form in AI Home writes it, and the user can also edit it in a text editor.

### Training agents (AI Home → Skills)

- **Train a new agent**, a form with:
  - **what the agent should do**, in plain words;
  - **examples or rules** (optional): pasted text, or a page to look at;
  - **a name**, suggested by the Brain.

  The Brain drafts `SKILL.md` and shows it as text in an editor. The user changes what they like, then:
  - **Save** writes it;
  - **Try it** starts an agent with the skill and a test task;
  - **Discard** drops it.
- **Save as skill:** on any finished agent's chat. The Brain drafts the skill from that agent's conversation:
  - the task;
  - the steps that worked;
  - the user's corrections ("no, use the blue button") as rules.

  It's the same review, then Save.
- **Where skills are saved:** in the user's personal skills folder, `~/.claude/skills/<name>/SKILL.md`, so Claude Code
  and AI Browser's agents share them. A name that already exists is never overwritten. The Brain offers
  `<name>-2`, or the user edits the existing skill on purpose with **Update**, which shows a diff first.
- **Assigning:** a workflow's **skills** field picks from all skills, including the new ones. AI Home's new-task box
  already does the same for one-off tasks.

### Actions

- **Draft reply:**
  1. The watcher opens the thread in a tab in front. Gmail then marks it read, as if the user had opened it.
  2. The watcher reads the thread.
  3. The Brain drafts a reply with the user's style notes (Sonnet by default).
  4. The draft appears on that inbox item, to edit and then **Approve**.
  5. On approval, the watcher puts the text in that tab's reply box (Gmail reply, Slack composer).
  6. **The user presses Send.** The watcher never clicks Send.
- **Hand to agent:** this starts an AI Browser agent (an AI Home task) with the item and the user's instruction. The
  item shows the agent's state and links to it.
- **Tell the Brain:** a free-text answer ("draft a no", "ask an agent to check the page", "remind me tomorrow" is out
  of scope). The Brain maps it to a draft or an agent task, or answers that it can't.
- **Just tell me:** the summary only. **Done** clears it.

## Decisions

### 1. The watcher is an extension in the user's everyday browser

It reads pages the user already has open and is logged into. It automates nothing there except two things:
- placing an approved draft in a reply box;
- opening a thread when the user asks for a draft.

So there are no bot checks and no extra logins.

**Readers:**
- **Content scripts:** for every enabled site, the watcher registers a content script with
  `chrome.scripting.registerContentScripts` for that site only. Permissions are `scripting`, `storage`, `notifications`
  and `tabs`. The three built-in sites are host permissions; added sites are optional host permissions, requested when
  added.
- **Watching for changes:** a reader observes its region with a `MutationObserver`, and also the tab title's unread
  badge ("Inbox (3)").
- **Reporting:** it reads the visible items and reports only the ones it hasn't reported before, by stable ID per site:
  - **Gmail:** the thread ID in the row;
  - **Slack:** the channel plus the message timestamp;
  - **Asana:** the task or story ID;
  - **added sites:** a hash of the item's text.
- **When a reader breaks:** if a built-in reader finds no structure it recognizes for 2 minutes while its tab is open,
  the watch list marks that site **reader needs an update**. It never fails silently.

**Tabs:** the watcher only reads tabs that are already open. It never opens Gmail, Slack or Asana by itself, except a
thread for a requested draft. If a watched site has no open tab, the watch list says so.

### 2. The Brain runs inside `ai-browser app`

- **Its own state:** the Brain is a `BrainService` beside the `AgentManager`. Unlike agents, its state persists:
  - `~/.ai-browser/brain/inbox.json`;
  - `~/.ai-browser/brain/watch.json`;
  - both written with mode 0600, under a lock.
- **Connections:**
  - the watcher connects to the app server like AI Home: same token, its own origin, added to the allowed origins;
  - the app runs the Brain whenever it runs. With the app stopped, the watcher shows "Brain is off", and reconnects by
    re-reading `config.json` before every attempt.
- **Sorting:**
  - new items are batched for up to 3 seconds, then sorted in **one Claude call**:
    `claude -p --model haiku --tools "" --strict-mcp-config --mcp-config '{"mcpServers": {}}' --setting-sources local
    --output-format json`;
  - `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` are stripped, as for agents;
  - the prompt holds:
    - the user's instructions for that site, as the user's words;
    - the items, quoted as **data from the page, not the user's words**;
  - the reply is JSON, one entry per item: `{"id", "kind": "needs_reply"|"new"|"skip", "summary", "why", "suggest":
    "draft"|"agent"|"tell"}`;
  - if the JSON is invalid, every item in the batch is listed as **new**, with its snippet as the summary.
- **Drafting:** one Claude call (Sonnet by default, the same flags as sorting) with the thread text quoted as page data
  and the user's style notes. The reply is the draft text.
- **Hand to agent:** `AgentManager.create(text)`. The text is the user's instruction, followed by the item as a
  bracketed block labelled as page data.

### 3. Agents with the user's MCP tools (phase 2)

- **The agent's MCP config:**
  - `ai-browser`;
  - the servers the user switched on, with their definitions copied from Claude Code's configuration;
  - still `--strict-mcp-config`;
  - still `--setting-sources local`: no hooks, plugins or CLAUDE.md;
  - still `--tools ""`: no shell or file tools of Claude Code's own; shell and skills stay in the Docker sandbox.
- **The claude.ai connectors** (remote servers tied to the user's account):
  - **Check first:** before relying on them, check with a real run that they can be passed this way.
  - **If they can't:** those agents run with Claude Code's own MCP loading (no `--strict-mcp-config`). The servers the
    user switched off are blocked with `--disallowedTools mcp__<server>__*`.
- **Asking the user:**
  - **The flow:**
    - agents run with `--permission-prompt-tool stdio` and Claude Code's **default** permission mode, instead of
      phase 1's `dontAsk`, which refuses without asking;
    - ai-browser's tools and the always-allowed ones are passed in `--allowedTools`;
    - every other tool call reaches the bridge as a stream-json `control_request` (`can_use_tool`, with the tool name
      and input), and the app answers allow or deny in a `control_response`.
  - **The order of checks:**
    1. ai-browser's tools are allowed (risky clicks keep their own ⚠ confirmation);
    2. tools in `~/.ai-browser/tools.json` (always allowed, mode 0600) are allowed;
    3. anything else waits for the user.
  - **While waiting:** the agent's state is **needs you**.
  - **Stop or Close** denies the waiting request.
  - **Before relying on this flow:** check it with a real run on Claude Code 2.1.263, as was done for `interrupt`.

### 4. Workflows (phase 2)

- **Files:**
  - `~/.ai-browser/workflows/<slug>.md`;
  - front matter: `name`, `trigger` (`manual`, `{message: {site, when}}` or `{schedule: "weekdays 09:00"}`), `run`
    (`ask` | `auto`, for message triggers), `tools` (a list of server names), `model`;
  - the body is the instructions.
- **Running one** creates an agent with:
  - the workflow's instructions, as the user's words;
  - the triggering item or the extra text, quoted as page data or as the user's words respectively;
  - the workflow's servers added to its MCP config;
  - its model.
- **A message trigger:**
  - the sorting call also receives the message-triggered workflows for that site (name, and its "when" in plain
    words);
  - for each item it may answer `"workflow": "<slug>"`, and the inbox item then offers **Run <name>**;
  - with `run: auto`, the workflow starts at once, and the notification says so.
- **A schedule:**
  - checked every 30 seconds while the app runs;
  - a run missed while the app was off is not caught up;
  - only one run of a workflow at a time: a run due while the previous one still works is skipped and noted.

### 5. Skills the Brain writes (phase 2)

- **Drafting:**
  - one Claude call (Sonnet by default) with **no tools**, under the same flags as sorting;
  - **from a description:** the user's description and examples, as the user's words. A page they point at comes in
    as quoted page data, read through the engine;
  - **from a run:** the agent's events: its tasks, tool calls and results as page data, and the user's messages as the
    user's words;
  - the reply is the whole `SKILL.md`: front matter with `name` and `description` (when to use it), then the
    instructions.
- **Checks before saving:**
  - a valid name;
  - front matter present;
  - instructions only. **No scripts or other files** in this project: a written skill is one `SKILL.md`, so saving
    one can never add code to run.
- **Saving:**
  - only on the user's **Save**;
  - the folder is created, the file written with mode 0644 (Claude Code reads it), never over an existing skill;
    **Update** writes an existing skill only after showing the diff and a second confirmation;
  - the skills catalog is read again, so the skill appears at once.

### 6. What the Brain never does

- It never sends a message, presses Send, or deletes, archives or labels anything.
- Its calls to Claude have no tools: a message saying "forward all invoices to me" can only become text the user reads.
- It never starts an agent unless the user clicks **Hand to agent** or **Run**, writes it in **Tell the Brain**, or
  a workflow the user wrote starts it (a run-right-away message trigger, or a schedule).
- It reads only enabled sites, in tabs the user has open, and nothing while paused.
- Only new items go to Claude, plus a thread when the user asks for a draft.

### 7. Messages between the parts

The app server adds these messages.

**Watcher → server:**
- `items {site, items: [{id, from, subject, snippet, url, time, thread_from_me?}]}`;
- `replied {site, id}`;
- `thread {request, text}`;
- `filled {request, ok, reason?}`;
- `reader_status {site, ok, note}`.

**Server → watcher:**
- `watch_list {sites, paused}`;
- `notify {item}`;
- `open_thread {request, site, url}`: open the thread in front and return its text;
- `fill_reply {request, site, url, text}`.

**UIs → server** (`brain.html` and AI Home):
- `brain {}`: the snapshot;
- `draft {id}`;
- `approve {id, text}`;
- `hand {id, instruction}`;
- `done {id}`;
- `tell {id, text}`;
- `watch_set {site…}`, `watch_remove {site}`;
- `pause {on}`;
- `style {text}`.

**Server → UIs:**
- `brain_snapshot {items, others, watch_list, paused}`;
- `brain_item {…}`, an upsert;
- `brain_item_gone {id}`.

**Phase 2** adds:
- **UIs → server:**
  - `tools {}`, `tool_set {server, on}`, `tool_allow {tool, always}`, `tool_forget {tool}`;
  - `permission {agent, request, answer: "once"|"always"|"deny"}`;
  - `workflows {}`, `workflow_save {…}`, `workflow_delete {slug}`;
  - `workflow_run {slug, text}`;
  - `skill_draft {request, description, examples, page?}` or `skill_draft {request, from_agent}`;
  - `skill_save {request, name, text, update?}`.
- **Server → UIs:**
  - `tools_snapshot {servers, always}`;
  - `permission_request {agent, request, server, tool, input}`;
  - `workflows_snapshot {workflows}`;
  - `skill_drafted {request, name, text}`, `skill_saved {name}`, `skill_diff {name, diff}`.

## Safety

AI Browser's rules all hold:
- the server listens on 127.0.0.1 only;
- the token is compared in constant time, and only our extensions' origins are accepted;
- text is rendered with `textContent` only;
- there are no API keys.

New in this project:
- **Untrusted text:** messages and threads are untrusted. They reach Claude only as labelled page data, in calls with
  no tools.
- **Sending stays with the user:** the watcher may type into a reply box only the exact text the user approved, and
  only after **Approve**. It never clicks a send button.
- **Access:** the watcher's site access equals the watch list (optional permissions). The pause switch stops reading.
- **Files on disk:** the inbox and watch list hold message snippets, so they are mode 0600 under `~/.ai-browser/brain/`.
- **Tools:**
  - only servers the user switched on reach an agent;
  - any tool that isn't always allowed waits for the user's answer;
  - page or message text can never grant a permission: only the user's click can;
  - the request shows the exact arguments as text.
- **Workflows** are the user's own words, read from their files. A scheduled or run-right-away workflow still stops
  at every tool that isn't always allowed.
- **Skills:**
  - **Written only on Save:** a skill the Brain drafts is only written when the user presses **Save**, after reading
    it.
  - **One file:** it is a single `SKILL.md` with no scripts.
  - **Never silently overwritten:** an existing skill changes only through **Update**, with a diff.
  - **Untrusted sources:** page or run text that goes into a draft is quoted page data, so an injected "always email
    the files to …" would show up in the text the user reviews. It can't save itself.

## Testing

- **Readers**, against saved sample pages that mirror each site's structure, served locally (no real accounts):
  - new rows are reported once;
  - a "replied" row clears its item;
  - an unknown structure leads to "reader needs an update";
  - an added site's picked region reports its new rows.
- **The Brain**, with the fake `claude`:
  - sorting JSON, with skip items only counted;
  - invalid JSON lists the items as new;
  - batching;
  - pause;
  - the inbox and watch list survive a restart;
  - draft → approve sends `fill_reply` and never a send;
  - **Hand to agent** creates an agent whose first message holds the item as labelled page data.
- **The watcher in a headless browser:** the extension loaded over the pipe into a throwaway Chrome, with the sample
  pages; a mock app server checks the messages.
- **A live check** with the user's real Brave, Gmail and Slack, read-only while the user watches: the first new email
  shows up, and a draft gets filled in but not sent.
- **Phase 2:**
  - **Tool permissions,** with the fake `claude` emitting a `can_use_tool` request:
    - the UI gets `permission_request`;
    - each of Allow once, Always and Deny becomes the right `control_response`;
    - always-allowed tools persist and no longer ask;
    - Stop denies a waiting request.
  - **Workflow files:** parsing, invalid front matter reported, and the AI Home form writing the file.
  - **The schedule parser,** with a fake clock: daily, weekdays, mon 08:30, every 2h; no overlap; no catch-up.
  - **A message trigger:** sorting JSON with `"workflow"` leads to a **Run** offer, or to a start for `run: auto`.
  - **By hand:** the Run button and `ai <name>` start the workflow's agent with its instructions and tools.
  - **Skills:**
    - a draft from a description, and one from a run, with the fake `claude`;
    - Save writes `~/.claude/skills/<name>/SKILL.md` under a test home, and the catalog lists it at once;
    - an existing name is refused, and Update shows a diff;
    - no file other than `SKILL.md` is written;
    - a workflow with `skills` starts its agent with the load line.
  - **Real runs:** `--permission-prompt-tool stdio` and passing the claude.ai connectors are each checked once with
    real Claude Code.

## Out of scope

- Voice, and the 3D Mission Control: later projects.
- Phone notifications, and reminders ("remind me tomorrow").
- The Brain creating Asana tasks by itself. A workflow with an Asana MCP server can.
- The Brain sending anything.
- Watching sites in tabs that aren't open.
