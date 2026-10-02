# ai-browser

A browser and shell that Claude drives directly: by default your everyday Brave, or a sandboxed Chromium in Docker.
Claude is the worker, so no LLM API keys are needed.

- **Your Brave by default, signed in as you:** once you turn on Brave's remote-debugging switch
  ([Use your everyday Brave](#use-your-everyday-brave-the-default)), Claude works in your everyday Brave (or Chrome),
  with your logins. It works only in background tabs it opens itself and tabs you hand it; it never reads your other
  tabs. While the switch is on, any program on this computer can reach your Brave.
- **Or a sandbox, apart from your logins:** the Docker sandbox runs Chromium inside Docker. It can't see your files,
  your Brave, or your Claude login ([Which browser](#which-browser)). Shell commands and skill scripts always run in
  Docker.
- **Fast, compact page reading:** every page becomes a short numbered list (`e3 button "Publish" ⚠`). Claude acts by number, many steps per call, and gets back only what changed.
- **Guarded actions:** before every click or keystroke, the target is re-checked to make sure it's still there, unchanged, enabled and not covered. Risky buttons (publish, delete, submit, pay…) need an explicit confirmation.
- **All your Claude skills, on demand:** the 400+ installed skills are searchable. Nothing loads until it's needed, and skill scripts run inside the sandbox.

Three parts, with designs and plans in `docs/superpowers/`:
- **the engine** (tools, sandbox, your-own-browser mode);
- **Website QA** (`qa` tool and skill);
- **the AI Browser app** (a Chrome with a Claude side panel).

WordPress and Elementor skills come next.

## Setup

Requires Docker Desktop (running), [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
uv sync
uv run ai-browser build     # builds the sandbox image (~1.7 GB, once)
uv run ai-browser doctor    # checks everything end to end
```

## Use it from Claude Code

This folder has a `.mcp.json`. Open Claude Code in this folder and approve the **ai-browser** server when asked; its tools then appear in every chat here. To use it from any folder:

```bash
claude mcp add ai-browser -- uv run --directory <path-to-this-folder> ai-browser mcp
```

Then just ask, for example: *"Open example.com and list its links"*. That opens in your Brave, in a background tab
of its own; ask for the sandbox (*"…in the sandbox"*) to keep the work apart from your logins.

## Which browser

Agents use **your everyday Brave** by default, the browser you are already signed in to. They work in background
tabs of their own, grouped and named after their task. Which browser is chosen up front, for every site, and never
as a way around a block:
- **Your Brave (the default):** for `ai-browser app` agents, and for Claude Code sessions with no `AIB_BROWSER` set.
  It needs Brave's remote-debugging switch (see "Use your everyday Brave" below). Google Chrome works too: the
  browser's folder is found by itself, Brave first, or set `AIB_CHROME_DIR`.
- **The Docker sandbox:** call `sandbox_start()` in a session, or set `AIB_BROWSER=sandbox` for one. Setting only
  `AIB_PROFILE` (a sandbox profile, see [Logging in to sites](#logging-in-to-sites)) chooses it too.
- **AI Browser:** `ai-browser app --browser app` (or `AIB_APP_BROWSER=app`). Agents then browse in AI Browser's own
  Chrome, as before.

If your Brave can't be reached, the agent says how to turn the switch on and asks you. It never moves to another
browser by itself. Website QA (`qa`) crawls in the Docker sandbox, unless you ask for your own browser first
(`sandbox_start(chrome=true)`).

## Logging in to sites

In your Brave you are already signed in. In the Docker sandbox, logins live in **profiles** (Docker volumes), one per
client if you like. You log in yourself, never Claude:

```bash
uv run ai-browser live --profile client-acme
```

Open the printed link, click into the page and log in. Your typing goes only to the sandbox and is never logged. Press
Ctrl-C when done; the login stays saved. In Claude Code, use `sandbox_start(profile="client-acme")`, or set
`AIB_PROFILE=client-acme` for the session: with no `AIB_BROWSER` set, that chooses the sandbox up front, with that
profile's logins. If `AIB_BROWSER` names your Brave, the profile isn't used, and the status line says so.

## AI Browser (a browser with AI Home and Claude agents)

```bash
uv run ai-browser app            # add --model haiku for the fastest replies, or opus for the most capable
```

AI Browser is a Google Chrome with a profile of its own (`~/.ai-browser/browser/`), with its own logins and
extensions, apart from your everyday browser. Agents drive it through Chrome's debugging port, and that port alone puts
Chrome in automation mode: every page reads `navigator.webdriver` as true (measured with Chrome 154). Sites can see
that AI Browser is automated, and Google refuses to sign in there ("This browser or app may not be secure"). Nothing
hides this. Agents browse in your everyday Brave by default ([Which browser](#which-browser)), where you are signed in
yourself: chosen before the task, for your logins, and nothing switches browsers on its own after a block. AI Browser
is their control room: AI Home, Mission Control and the chat panel. With `--browser app`, agents browse in AI Browser
itself, as before. When a site answers with a bot check, the agent stops and hands it to you
([Bot checks](#bot-checks)).

**First start (once).** AI Browser opens a setup page and `chrome://extensions`, and a Finder window shows the
extension folder:
1. Turn on **Developer mode** (top right of `chrome://extensions`).
2. Drag the **extension** folder from Finder onto that page. Alternatively, click **Load unpacked**, press ⌘⇧G, paste
   `~/.ai-browser/app/extension`, press Enter, then click **Select**.
3. Pin the AI Browser icon from the puzzle-piece menu.

If AI Browser is already listed there but switched off, switch it on. When Chrome asks whether to keep the new tab
page, choose **Keep it**: AI Home is the new tab page, and "Change it back" switches AI Browser off.

The extension stays installed. From then on, AI Browser opens on AI Home.

**AI Home** is the pinned first tab, and every new tab.
- **Start a task:** pick skills and a model if you like. You can also type `ai`, a space and the task in the address
  bar.
- **Agents:**
  - Up to 3 work at once (`AIB_APP_MAX_AGENTS`); the rest wait in line.
  - Each row shows what the agent is doing now, its last action with timing, a small picture of its tab, and its time
    and cost.
  - Each row has **Watch**, **Chat**, **Stop** and **Close**.
- **Your browser:** a card at the top says where agents browse and whether your Brave is connected. When Brave's
  switch is off, it shows the steps; when Brave asks "Allow remote debugging?", it says so.
- **Tabs:** your Brave's web tabs, each marked with whose it is: an agent's, Claude Code's, the Brain's, or yours.
  - A click brings a tab to the front.
  - **Hand over** gives one of your tabs to a new or running agent (it reads that tab and acts in it).
  - **Take back** ends that.
- **Skills:**
  - every one of Claude's skills (personal, plugins, claude.ai, ai-browser), and which ones each agent loaded;
  - add one to a new task, or ask a running agent to use it.

**In the browser:**
- Each agent's tabs sit in a coloured tab group in your Brave, named after its task. The Brain's watcher makes the
  groups. Without the watcher, each tab the AI opens gets a window of its own.
- The toolbar badge shows how many agents are working.
- The chat beside the page in AI Browser (its toolbar icon, or ⌘⇧Y) shows the agent that was active last, and a
  task typed there starts an agent that works in your Brave. With `--browser app`, it follows the tab you are on,
  shows that tab's agent, or starts one right there, in your tab, which the agent never closes.

How it works:
- **Claude:** each agent is Claude Code on this Mac (`claude -p`), signed in with your Claude account, with no API
  keys. Its only tools are ai-browser's. Shell commands and skill scripts run in the Docker sandbox.
- **Background agents:** tasks from AI Home or the address bar work in background tabs. They never take your focus,
  and they stay at full speed. **Watch** brings one to the front.
- **Stop and Close:** **Stop** interrupts an agent and keeps its tabs. **Close** ends it and closes the tabs it
  opened; your own tabs stay open.
- **Logins:** log in yourself, in the window. Claude never types passwords, and risky buttons (⚠) need your yes in
  that agent's chat.
- **Downloads** go to your Downloads folder.
- **Closing:** quit AI Browser (⌘Q), close its last window, or press Ctrl-C in the terminal. The Docker shell
  container keeps running for the next start; stop it with `uv run ai-browser stop chrome`.
- **Debugging port:** like any Chrome started with a debugging port, other programs on this Mac could connect to AI
  Browser while it runs. Use it for your work, not for your bank.

## The Brain (watches your messages, tells you what needs you)

The Brain runs inside `ai-browser app`. It reads Gmail, Slack, Asana and sites you add in **Brave**, your everyday
browser, through a small extension called the watcher. It shows you only new messages and the ones that need your
reply, never your whole inbox. Everything else is only counted ("14 others, nothing needs you").

**Setup in Brave (once).** At the first start, a Finder window shows the watcher folder (`~/.ai-browser/app/watcher`)
and AI Browser opens the setup page:
1. In Brave, open `brave://extensions` and turn on **Developer mode**.
2. Drag the **watcher** folder onto that page.
3. Click the watcher's icon (the orange dot) to open **the Brain**, and switch on the sites to watch.

**The Brain page** (the watcher's icon) and AI Home's Brain section show:
- **The inbox:** each item has the site, who it's from, the Brain's one-line summary, why it matters and a suggested
  action.
  - A **needs your reply** item stays until you reply, or click **Done**.
  - A **new** item stays a day.
- **The watch list:** Gmail, Slack, Asana, or **Add a site**. To add one, type its address, allow Brave to read that
  one site, then click the part of the page to watch (for example an orders table).
  - Each site has your **instructions** in plain words, for example "Always tell me about clients; skip newsletters
    and receipts".
  - Each site has an on/off switch.
- **Pause watching**, and **How I write** (style notes for drafts).

**What you can do with an item:**
- **Draft reply:**
  1. The watcher opens the thread.
  2. The Brain drafts a reply in your style.
  3. You edit it, then **Approve**.
  4. The watcher puts the text in the reply box. **You press Send**: the Brain never sends anything.
- **Hand to agent:** an AI Browser agent gets your instruction and the message.
- **Tell the Brain:** your own words ("draft a polite no", "check the page") become a draft or an agent task.
- **Done.**

Notifications in Brave show the summary with **Draft reply** (or **Hand to agent**) and **Open**. Many items at once
are one notification ("7 need you").

How it works:
- **Sorting:** the watcher reports new items in the tabs you have open, and nothing while paused. The Brain sorts them
  with Claude Code (Haiku), in calls that have **no tools at all**. Message text is passed as page data, never as your
  words, and isn't kept in Claude Code's history.
- **Drafts:** written with Sonnet in the same tool-less way.
- **Files:** the inbox and the watch list are kept in `~/.ai-browser/brain/` (only you can read them), so they survive
  a restart.
- **Readers:** they find messages by each site's page structure, in any language. If a site changes its layout, the
  watch list says "reader needs an update" instead of failing silently. A watched site without an open tab says
  "no open tab", and a tab on another page of the site (Gmail's Settings, an Asana board) says "open the inbox".
  - Gmail is read in the inbox and its category tabs only: never Spam, Sent, labels or searches.
  - An approved Gmail reply goes at the top of the reply box, above your signature. Slack gets it on one line, since
    Enter sends there.
- **When the app is off:** the watcher keeps what it read and sends it once the app is back.

### Tools: your MCP servers for the agents (AI Home → Tools)

Agents can use the same MCP tools as your Claude Code app. The Tools section lists:
- the servers in Claude Code's configuration (`~/.claude.json` and your projects' `.mcp.json`);
- your claude.ai connectors (ClickUp, Google Drive…). Claude Code is asked which ones you have the first time you open
  the section.

Switch on the servers agents may use. Nothing else reaches them. ai-browser's own tools are always on.

**Asking first:**
- The first time an agent wants a tool that isn't allowed always, it waits ("needs you").
- AI Home's agent row, the chat beside its tab, and the watcher's Brain page all show the tool and its exact input,
  with **Allow once**, **Always allow** and **Deny**. Brave also shows a notification (Review / Deny).
- **Always allow** is remembered in `~/.ai-browser/tools.json`. **Forget** removes it.
- **Stop** or **Close** denies a request that is still waiting.
- Nothing a page or a message says can answer for you.

### Workflows: your own recipes (AI Home → Workflows)

A workflow is a name and instructions in your words, for example "Open the site in AI Browser, make the change the
task asks for, then post what you did in #web-team". It has:
- **a trigger:**
  - **by hand:** **Run** in AI Home, or `ai <workflow name> …` in the address bar;
  - **a message:** a site from the Brain's watch list and when it applies ("an Asana task tagged website"). The
    matching inbox item offers **Run <name>**, or the workflow starts at once if you chose "Run right away";
  - **a schedule:** `daily 09:00`, `weekdays 09:00`, `mon,wed 17:00`, `every 2h` or `every 30m`. It runs while
    `ai-browser app` runs. A missed run isn't caught up, and a run never starts while the last one is still going;
- **the tools it may use:** it still asks before each tool, scheduled runs too;
- **skills** its agent loads first;
- **a model.**

Each workflow is a file, `~/.ai-browser/workflows/<name>.md` (front matter, then the instructions), which you can also
edit in a text editor:

```markdown
---
name: Footer fix
trigger:
  message:
    site: asana
    when: an Asana task tagged website
run: ask
tools: [claude_ai_ClickUp]
skills: [personal:elementor-landing]
model: sonnet
---
Open the site in AI Browser, fix what the task asks, then post what you did in #web-team.
```

### Train a new agent (AI Home → Skills)

- **Train a new agent:** describe the job, add examples or rules, and point at an AI Browser tab to learn from if you
  like.
  1. The Brain drafts a skill (`SKILL.md`, Claude Code's format), with Claude and no tools.
  2. Read it and change what you like.
  3. **Save** writes it to `~/.claude/skills/<name>/SKILL.md`, where Claude Code and AI Browser's agents both find it.

  **Try it** starts an agent with the draft and a test task, without saving.
- **Save as skill**, on any agent's chat: the Brain drafts a skill from that run. Your corrections ("no, use the blue
  button") become rules.
- **Writing safely:**
  - a skill is one file, with no scripts;
  - an existing skill is never overwritten: **Save as <name>-2**, or **Update**, which shows the diff and asks again.
- **Assign it:** pick it in a workflow's skills (or for one task in AI Home's Skills menu), and that workflow's agent
  loads it first.

## Mission Control (your agents at work, in 3D)

**Mission Control**, in AI Home's header, opens a dark control room:
- **Stations:** every agent works at its own little desk, where a chibi office worker in a tie of the agent's colour
  sits beside the monitor. The art is drawn in code on this computer: nothing is downloaded.
  - Its monitor shows the tab it works in (the same pictures as AI Home), and the ticker its last action
    ("click e14 · 38 ms").
  - The light shows its state: green working, amber waiting in line, ✓ done, red failed. The worker shows it too: he
    types while the agent works, checks his watch while it waits, gives a thumbs up when it is done, slumps on the
    desk when it failed, and dozes when it was stopped.
  - A station that **needs you** (a tool waiting for your permission) glows, and its worker turns to you and waves.
  - A new agent arrives with a short scene: the Brain flares, a spark flies to its desk, the monitor switches on, and
    the worker pops up and waves.
  - Click a station, or pick it from **List**: the drawer shows its state, **Watch**, **Stop**, **Close**, its
    permission card (**Allow once**, **Always allow**, **Deny**) and its chat.
- **The Brain** floats in the middle as a brain of glowing points, turning slowly:
  - it drifts while idle, sends a wave of light across itself while it sorts messages or writes a draft, and beats
    like a heart, in amber, while something needs you, its signals gathering on the side of the agent that waits (the
    count shows under it); each word it speaks sends a ring of light across it;
  - without WebGL it is a dotted brain in the same colours, and on a slower computer it draws fewer points;
  - click it for its inbox (Draft reply, Approve, Hand to agent…).
- **Talking back:** the Brain's updates show in a speech bubble, one at a time: a new message that needs your reply, a
  draft that is ready, an agent that is done, failed, or waits for a permission. More than three at once become one
  summary. Only names and the Brain's one-line summaries are used, never a message's text.
- **Voice** (top bar): the updates are also spoken, only with a voice that runs on this Mac, so nothing is sent
  anywhere. It is off by default and remembered. Without such a voice, it says so and stays off.
- **The task bar** at the bottom starts an agent, like AI Home's box. The mic button beside **Start** talks to the
  Brain (see "Talking to the Brain", below).
- **Moving around:** drag to turn the room, scroll to zoom, double-click to reset. Keys: ← → turn, ↑ ↓ tilt, + − zoom,
  0 resets. With Reduce Motion on (System Settings → Accessibility → Display), the room, the workers and the Brain
  stand still: a change is a short colour fade, and a new agent's desk simply appears.

## Talking to the Brain (push-to-talk, speech to text on this computer)

In Mission Control, hold **Space** (while no text box or button has focus) and talk to the Brain, then let go. Or
hold the **mic button** beside Start, or click it once to start and again to stop. **Esc** throws the turn away, and a
turn stops by itself at 30 seconds. The **Ask the Brain** box does the same, typed.
- **Your voice stays on this computer.** The microphone is open only while you talk: no wake word, nothing in the
  background. The sound goes to `ai-browser app` over 127.0.0.1, and Whisper (faster-whisper, `base.en`, on the CPU)
  turns it into text there. The sound is kept in memory for that turn only, never saved or logged, and no cloud speech
  service is used, not even as a fallback.
- **Your words go to Claude**, like typed text: the Brain answers about your agents and your inbox in one or two
  sentences, in its bubble and the talk panel, and aloud when Voice is on.
- **It only proposes.** Asked for work, it offers to **start an agent** with your own words as its task, or to **draft
  a reply** to an inbox item. Nothing happens until you press **Start** (or **Draft it**) or say "yes". Voice never
  approves or sends a draft, answers a permission card or a bot check, confirms a ⚠ action, marks items Done, pauses
  watching, or changes a setting: those stay clicks. Words that sound like a password or a code are never sent: log in
  yourself, in the site's own tab.
- **Setup, once:**
  1. In this folder, run `uv sync --extra voice`, then restart `ai-browser app`. It installs faster-whisper and the
     Python packages it needs, from PyPI. Sync with `uv sync --extra voice` (or `--all-extras`) from then on: a plain
     `uv sync` removes the extra again (`uv run` keeps it).
  2. The first time you hold Space, Mission Control offers the English speech model: **Download 148 MB** (Whisper
     base.en from Hugging Face, pinned to one revision and checked before use), saved in
     `~/.ai-browser/models/faster-whisper-base.en` (or under `$AIB_HOME`). Nothing else is downloaded, and only when
     you click.
  3. AI Browser then asks to use the microphone: choose **Allow while visiting the site**, not **Allow this time**.
     macOS may also ask once whether Google Chrome may use the microphone.
- **Speed:** a 5-second question becomes text in about 1.5 s on an Apple silicon Mac (an estimate, until it is
  measured here). The first turn after the app starts takes a few seconds longer while the model loads.
- **Windows:** the same on 64-bit Windows. On Windows on Arm the extra can't install (CTranslate2 has no wheel there),
  so Mission Control stays at its setup card; use Voice Access instead, as that card suggests.
- **No setup at all:** macOS Dictation types into any text box in AI Browser (the task bar, an agent's message box,
  Tell the Brain): press the Microphone key, use Edit → Start Dictation, or the shortcut in System Settings → Keyboard
  → Dictation. On Apple silicon it runs on the Mac for supported languages, and that settings page shows whether it
  does. On Windows, Voice Access (Windows 11) runs on the PC, while Win+H voice typing sends audio to Microsoft.

## What sites can see

| Mode | What sites can see |
|---|---|
| Sandbox | Headless Chromium in Docker. Its user agent says `HeadlessChrome`, the clock is UTC, there is no GPU, and the profile is often new. |
| AI Browser | Google Chrome on its own profile; `navigator.webdriver` is true. |
| Your everyday Brave | Your own browser, logins and history, with Brave's remote-debugging switch on. Pages read `navigator.webdriver` false (measured with Brave on a Chromium 152 base). That is Brave's own behaviour, not something ai-browser sets, and sites can still notice automation in other ways. |

Nothing is faked in any mode.

## Bot checks

When a site asks "are you a robot?" (Google's "unusual traffic" page, a CAPTCHA picture check, Cloudflare's "verify
you are human", a "Press & Hold" check, an Akamai block page), the agent stops and hands it to you:
- the tab comes to the front (in the sandbox, the agent gives you the live-view link);
- nothing else runs until you've dealt with it: no reload, no retry, no other tab, browser, profile or tool;
- in AI Browser the agent shows **needs you** on AI Home, in the chat panel and in Mission Control, with **Show me**,
  **Continue** and **Skip this site**, and a Brave notification when the watcher is connected.

Solve it in the tab yourself, then click **Continue** (in Claude Code, tell the agent it's done). If you'd rather not,
**Skip this site** (or tell the agent "skip it") closes that tab, and the site is off-limits for the rest of the task.
An "I'm not a robot" box inside a form is yours to tick: the agent fills in the rest and asks you.

Checks are never solved or dodged: no solver services, no faked browser, no switching browsers or profiles after a
block. If Google keeps asking in Brave, Brave's fingerprinting protection is a known cause (Brave issue #55197).
Turning it off for google.com is your own privacy choice, and ai-browser never changes it.

## Use your everyday Brave (the default)

Agents and Claude Code sessions drive your own Brave with the same fast tools. It is the browser you are signed in
to, so no agent ever needs your password. It is chosen up front, for your logins, and never as a way around a site
that blocked another browser.

1. Once: in Brave, open `brave://inspect/#remote-debugging` and tick **Allow remote debugging for this browser
   instance**.
2. When Brave asks **Allow remote debugging?**, click **Allow**. Brave may ask when `ai-browser app` starts and when
   each agent or Claude Code session first uses the browser, and again after Brave restarts.
3. Check it any time with `uv run ai-browser doctor --own`.

**While this switch is on, any program on this computer can reach your Brave, not only ai-browser.** That includes
the sites you are signed in to.
- Turn it off when agents aren't working: untick the same box.
- Only click Allow right after you started AI Browser or gave an agent a task; if Brave asks at any other time, click
  Deny.
- While an agent is connected, Brave may show a bar saying it is being controlled by automated software. That is
  Brave telling you the truth; ai-browser never hides it.

What happens in your Brave:
- **Background tabs only:**
  - each agent works in background tabs it opens itself, in a tab group named after its task, in its colour;
  - nothing comes to the front unless you click **Watch**, or a site shows a bot check (handed to you, see
    "Bot checks");
  - a Claude Code session's tabs go in a group called "Claude Code" while `ai-browser app` runs, and in a window of
    their own otherwise.
- **Your other tabs:** never read, listed to an agent or touched. AI Home shows them, and **Hand over** gives one to
  an agent; **Take back** ends that at its next step. A tab the agent's own click opens from a handed tab is the
  agent's: it sits in its group and closes with it.
- **Closing:**
  - closing an agent closes the tabs it opened; a tab you handed it stays open, ungrouped;
  - quitting `ai-browser app` leaves the groups in Brave, so nothing an agent left for you is lost;
  - a Claude Code session's tabs close when the session ends.
- **Downloads ask first:** a download would land in your Downloads folder, so download buttons and links are ⚠. A
  download that starts on its own is cancelled, and the agent asks you.
- **Only web pages open there:** Claude can't open files on your computer (`file://`) or Brave's own pages.
- **The sandbox's place:** shell and skill scripts still run in the Docker sandbox. The work folder is
  `~/.ai-browser/sandboxes/chrome/work/<task>`.
- **If Brave isn't reachable** (closed, or the switch is off), the agent says so and asks you. It never switches to
  the sandbox on its own.

Google Chrome works the same way (`chrome://inspect/#remote-debugging`). The folder is found by itself, Brave first;
set `AIB_CHROME_DIR` to pick one. Turn the switch on in one browser only.

## Tools

| Tool | What it does |
|------|--------------|
| `sandbox_start` · `sandbox_stop` · `sandbox_status` | Start or reuse the sandbox (profile or throwaway), stop it, show its work folder, live-view link and tabs |
| `open` · `observe` | Open a URL / read the page as numbered elements; `observe(find="…")` searches the whole page |
| `act` | Steps in one call: `click e5`, `type e4 "text"`, `append`, `key Enter`, `select`, `check`, `drag e7 e12`, `upload e5 file.png`, `scroll`, `wait "Saved"`, `goto`, `back`… |
| `screenshot` | JPEG at desktop / tablet / mobile / all, full page, or one element |
| `tabs` · `page_log` · `extract` · `js` | Tabs; console errors and failed requests; links / tables (CSV) / SEO meta; run JavaScript |
| `qa` | Website QA in one call: crawls the site, checks layout on desktop/tablet/mobile, page errors and every link, writes `report.html`, `issues.csv` and screenshots |
| `shell` · `read_file` · `write_file` | Bash and files inside the sandbox's work folder |
| `find_skills` · `load_skill` · `read_skill_file` | Search and load installed Claude skills |

Example page read:

```
page  "Form test"  http://localhost:8000/form.html
view  1440×900 · y 0/900 · 0 above · 0 below
e1   textbox  "Full name" = "Ada"
e4   select   "Size" = "Medium" (Small|Medium|Large)
e9   button   "Submit order" ⚠
⏱ 4 ms
```

## Website QA

Ask Claude to *"QA client-site.com"*. It calls `qa(url, max_pages=30)`, which:
- visits same-site pages in a tab of its own, one at a time. It never clicks, types or submits, and skips links
  such as log out, delete or add to cart;
- checks each page on desktop, tablet and mobile. It reports sideways scrolling, naming the elements that stick
  out, along with script and console errors, failed or blocked requests, broken images and insecure `http://`
  content;
- checks every link once (internal ones with your logins, external ones without), politely: one request at a time
  per site, with a short pause, following robots.txt and Retry-After. A site that answers 429, 403 or a bot check
  isn't asked again in that run, and links to big sites such as Google, or to a site you skipped at a bot check,
  aren't checked: they are listed under "Not checked", not as broken. `qa(url, ignore_robots=true)` only for a site
  you say is yours (staging sites often ask every crawler to stay out);
- visits the site's pages first and checks the site's other links after them, so the pages always get their turn.
  30 pages take about three minutes; a site with many links takes longer, about six minutes at most (it stops
  visiting pages after five). The summary says where it stopped and why;
- writes `qa/<site>-<time>/report.html` (one shareable file with screenshots), `issues.csv` and full-page shots.

The skill `ai-browser:website-qa` (in `skills/`) tells Claude how to verify each finding before reporting it, and how
to write it up for a client.

## Speed

From `uv run ai-browser bench` (medians, local test pages, MacBook):

| Operation | Median | Budget |
|---|---|---|
| read a page | 1 ms | 100 ms |
| read a 3,000-control page | 10 ms | 300 ms |
| one click step (guards + settle + diff) | 49 ms | 150 ms |
| one type step | 51 ms | 150 ms |
| open a local page | 13 ms | 500 ms |
| viewport screenshot | 49 ms | 300 ms |
| Website QA, 30 pages × 3 sizes (one request at a time per site, 1 s apart) | 80 s; 140 s with 61 more links; 6 min with 1,171 | visits stop at 5 min, link checks at about 6 |

The QA row is not from `bench`: it was measured in a throwaway headless Chrome on a local test site whose pages each
link 1, 3 or 40 more of its own, so 1, 61 or 1,171 links are left after the 30 visits (with 1,171, about 280 are
checked before the limit and the rest are listed as not checked). Those pages load in under a second; real pages load
slower, so 30 pages of a typical site take about three minutes.

## Commands

```bash
uv run ai-browser app [--browser brave|app]  # AI Browser; agents browse in your Brave (default) or in AI Browser
uv run ai-browser doctor [--own]             # health check (the sandbox, or your own Brave or Chrome)
uv run ai-browser bench                      # speed vs budgets
uv run ai-browser live [--profile P]         # watch / log in
uv run ai-browser stop [P | --all]           # stop containers (logins kept); `stop chrome` = own-Chrome shell
uv run ai-browser build                      # rebuild the image
```

## Safety notes

- ⚠ risky buttons are refused unless `confirmed=true`; Claude asks you first. Page dialogs are treated the same way:
  - Alerts are accepted and reported.
  - `confirm()`, `prompt()` and "leave page with unsaved changes?" are dismissed unless the step was confirmed.
- To change the defaults, edit `~/.ai-browser/config.json`:
  - the risky word list: `"risky_words": […]`
  - skills to block: `"blocked_skills": ["ecc:some-skill"]`
- Each profile runs as **two containers** on a network where containers can't reach each other:
  - the **browser** (`aib-<profile>`), which alone holds the logged-in profile;
  - the **shell** (`aib-<profile>-sh`), where Claude's commands and skill scripts run. It sees only the work folder and the skills (read-only).
- The shell can't read the browser's cookies or reach its debugging port. That port is published on 127.0.0.1 behind a token only the engine on your Mac knows.
- To view a file the shell made, open it in the sandbox browser as `file:///work/<task>/…`. That browser opens no
  other local files, and your own Chrome opens none (use `read_file` there).
- Host-side file tools never follow symbolic links in the work folder, so the shell can't point them at your files.
- The shell refuses a command that sends a browser's user agent (`curl -A "Mozilla/…"`), runs curl or wget in
  parallel (`xargs -P`), or names a site you skipped after a bot check: it keeps curl's own user agent, one URL at a
  time.
- The page reader runs in a JavaScript world of its own: a page can't replace it or change what it reads, where a
  click lands, whether ⚠ applies, or which file input gets an upload.
- Both containers run as normal users with no capabilities and capped memory and CPU.
- Chromium runs with `--no-sandbox` inside its container, so the container is the isolation boundary.
- Live view: what you type there isn't logged. Password, card-number and one-time-code fields are always masked in what Claude reads.
- Every tool call is logged to `~/.ai-browser/tasks/<task>/log.jsonl`, with screenshots in `shots/`.

## Limits (MVP)

- Frames from other sites (cross-origin iframes) are listed but not read.
- Pressing Enter in a form isn't ⚠-gated; only clicks on risky buttons and page dialogs are.
- Headless Chromium can trigger more bot checks on some sites (each one is handed to you: see
  [Bot checks](#bot-checks)), and mobile screenshots keep the desktop user agent.
- One browser lane per Claude session (calls are serialized).

## Development

```bash
uv run pytest        # Docker tests skip themselves when Docker or the image is missing
```

Layout: `src/ai_browser/` (engine), `docker/` (sandbox image), `src/ai_browser/pages/` (local test pages), `tests/`.
