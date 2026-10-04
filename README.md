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
- **the AI Browser app** (its own window: AI Home, Mission Control and the Brain).

WordPress and Elementor skills come next.

## Setup

Requires Docker Desktop (running), [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
uv sync
uv run ai-browser build     # builds the sandbox image (~1.7 GB, once)
uv run ai-browser doctor    # checks everything end to end
```

## Windows

ai-browser runs natively on Windows 10 (22H2) and Windows 11, 64-bit. In PowerShell:

1. **Tools, once each.** Each line installs one tool; Windows may ask for permission for some of them.
   ```powershell
   winget install --id Git.Git -e
   winget install --id astral-sh.uv -e
   winget install --id GitHub.cli -e
   winget install --id Google.Chrome -e
   winget install --id Brave.Brave -e
   irm https://claude.ai/install.ps1 | iex      # Claude Code, the native claude.exe
   ```
   Then open a new PowerShell window, so the new commands are on PATH.
2. **Sign in, yourself:** `gh auth login`, for the private repo, and `claude` once, to log in to Claude Code in the
   browser. Nothing here asks for a password or a token in a file.
3. **The code**, in a short folder outside OneDrive:
   ```powershell
   git clone https://github.com/nanotechs001/ai-browser.git C:\dev\ai-browser
   cd C:\dev\ai-browser
   uv sync                        # Python 3.12 from .python-version; uv fetches it once
   uv run ai-browser doctor --setup
   ```
4. **Claude Code's tools:**
   ```powershell
   claude mcp add ai-browser --scope user -e PYTHONUTF8=1 -- uv run --directory C:\dev\ai-browser ai-browser mcp
   ```
5. **AI Browser:** `uv run ai-browser app`. It opens in a window of its own, drawn by Microsoft Edge (or the
   browser you pick in AI Browser's Settings), with nothing to load by hand. Close the window, or press Ctrl-C in
   the terminal, to stop it.
6. **Brave, once, after step 5** (the first `ai-browser app` makes the watcher's folder):
   - open `brave://extensions`, turn on **Developer mode**, click **Load unpacked** and pick
     `%USERPROFILE%\.ai-browser\app\watcher`;
   - for the everyday-Brave mode, open `brave://inspect/#remote-debugging` and tick **Allow remote debugging for this
     browser instance**. While the switch is on, any program on this PC can reach your Brave, so untick it when
     agents aren't working.
7. **Optional, for the sandbox and the shell tool:**
   - run `wsl --install` and reboot;
   - run `winget install --id Docker.DockerDesktop -e`;
   - start Docker Desktop (WSL 2 backend, Linux containers);
   - then run `uv run ai-browser build` and `uv run ai-browser doctor`.

   The work folder lives on NTFS, so it is slower and case-insensitive (`Report.html` and `report.html` are one
   file), and names Windows can't hold (`CON`, `a:b`, `x?`) are refused with a plain message.
8. **Optional, for voice input:**
   - run `uv sync --extra voice` (the speech packages; plain `uv sync` removes them again, so keep the flag);
   - allow desktop apps to use the microphone (Settings → Privacy & security → Microphone);
   - the voice model itself (148 MB, the size the **Download** button shows; the "about 142 MB" quoted when you chose
     it is the same files counted in MiB) is downloaded from inside the app, only after you click **Download**.

   On Windows on Arm the speech packages can't install: Voice Access (Windows 11) works instead.

**Troubleshooting:**
- **"no free port":** Hyper-V or Docker may have reserved the port range.
  `netsh interface ipv4 show excludedportrange protocol=tcp` shows the reserved ranges.
- **"Claude Code was found at …claude.cmd":** install the native Claude Code (step 1), or set `AIB_CLAUDE` to the
  full path of `claude.exe`.
- **Chrome in an unusual place:** set `AIB_CHROME_BINARY` to the full path of `chrome.exe`.
- **`~` in PowerShell:** native programs don't expand it. Use `$HOME` or `$env:USERPROFILE`.
- **Files that hold tokens** (the watcher's `config.json`, each agent's `mcp.json`, `link.json`) keep Windows'
  per-user permissions on your folder: you, SYSTEM and Administrators.
- **Running inside WSL2** works with the Linux code, but needs Linux Chrome and Brave inside WSL.

## Use it from Claude Code

Copy `.mcp.json.example` to `.mcp.json` and put this folder's path in it (git ignores your copy). Then open Claude
Code in this folder and approve the **ai-browser** server when asked; its tools then appear in every chat here. To use
it from any folder:

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

## AI Browser (its own window: AI Home, Mission Control and the Brain)

```bash
uv run ai-browser app            # add --model haiku for the fastest replies, or opus for the most capable
```

AI Browser opens in a window of its own: a title bar only, with no tabs and no address bar. An installed browser
draws it in its app mode, on a profile of AI Browser's own (`~/.ai-browser/app/window/<browser>/`), with no
debugging port. Nothing drives that window, so it never asks "Allow remote debugging?" and shows no automation bar,
and no agent browses there. Agents browse in your everyday Brave ([Which browser](#which-browser)), where you are
signed in yourself: chosen before the task, for your logins, and nothing switches browsers on its own after a
block. When a site answers with a bot check, the agent stops and hands it to you ([Bot checks](#bot-checks)).

**Which browser draws the window:** Settings → App window offers **Auto**, **Google Chrome**, **Brave**, and
**Microsoft Edge** on Windows. Auto picks Google Chrome on a Mac whose everyday browser is Brave, so a link clicked
in another app never lands in AI Browser's window, and Microsoft Edge on Windows. The Dock (the taskbar on Windows)
shows that browser's icon while AI Browser is open. A change applies at the next start;
`uv run ai-browser app --window brave` picks one for a single run.

**First start (once):** there is nothing to load in the window. The terminal shows the watcher's steps for Brave,
and Finder (File Explorer on Windows) shows the watcher's folder. AI Home's browser card and the Brain's **Set it
up** open the same steps in a small window.

**AI Home** is the window's first page.
- **Start a task:** pick skills and a model if you like. In Brave you can also type `ai`, a space and the task in
  the address bar: the watcher passes it on, and Brave says "Started 4 · Fix the footer".
- **Agents:**
  - Up to 3 work at once (`AIB_APP_MAX_AGENTS`); the rest wait in line.
  - Each row shows what the agent is doing now, its last action with timing, a small picture of its tab, and its
    time and cost.
  - Each row has **Watch**, **Chat**, **Stop** and **Close**.
  - The window's title counts the agents at work: "(2) AI Home".
- **Your browser:** a card at the top says where agents browse and whether your Brave is connected. When Brave's
  switch is off, it shows the steps; when Brave asks "Allow remote debugging?", it says so.
- **Tabs:** the web tabs of the Brave profile the watcher is in (without the watcher, the profile you used last),
  each marked with whose it is: an agent's, Claude Code's, the Brain's, or yours. Other profiles and private windows
  are only counted, never listed.
  - A click brings a tab to the front.
  - **Hand over** gives one of your tabs to a new or running agent (it reads that tab and acts in it).
  - **Take back** ends that.
- **Skills:**
  - every one of Claude's skills (personal, plugins, claude.ai, ai-browser), and which ones each agent loaded;
  - add one to a new task, or ask a running agent to use it.
- **Settings** (beside **Mission Control**): which browser draws the window. The model you pick and Voice are
  remembered by AI Browser itself, in every window and across restarts.

**Windows and links:** Mission Control, Settings, the setup steps and an agent's live view open as small windows of
their own; a second click brings the open one forward. A link to a website opens in your Brave, never in AI
Browser's window. Each agent's tabs sit in a coloured tab group in your Brave, named after its task. The Brain's
watcher makes the groups. Without the watcher, each tab the AI opens gets a window of its own.

How it works:
- **Claude:** each agent is Claude Code on this computer (`claude -p`), signed in with your Claude account, with no
  API keys. Its only tools are ai-browser's. Shell commands and skill scripts run in the Docker sandbox.
- **Background agents:** tasks from AI Home, Mission Control or Brave's address bar work in background tabs. They
  never take your focus, and they stay at full speed. **Watch** brings one to the front.
- **Stop and Close:** **Stop** interrupts an agent and keeps its tabs. **Close** ends it and closes the tabs it
  opened; your own tabs stay open.
- **Logins:** log in yourself, in that tab in Brave. Claude never types passwords, and risky buttons (⚠) need your
  yes in that agent's chat.
- **Downloads** go to your Downloads folder, and only after your OK.
- **Only the window gets in:** AI Browser's window starts with a one-time code that the app swaps for a cookie
  only that window holds. The same address typed into Brave shows "AI Browser's pages open only in its own window".
- **Closing:** close the window (⌘Q on a Mac), or press Ctrl-C in the terminal: the agents end with it. A Mission
  Control or Settings window still open keeps AI Browser running until the last of its windows closes. The Docker
  shell container keeps running for the next start; stop it with `uv run ai-browser stop chrome`.
- **The microphone** is asked for once, in the window, and kept across restarts: AI Browser comes back on the same
  address.
- **Old folders:** `~/.ai-browser/browser/` (AI Browser's old Chrome profile, which may hold logins you made there)
  and `~/.ai-browser/app/extension/` (its old extension) are no longer used. AI Browser never deletes them; delete
  them by hand if you like.

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
- **Tell the Brain:** your own words ("draft a polite no", "check the page", "give this to agent 2") become a draft, or
  a card that starts a NEW agent or sends your words to an open one. Press **Start** or **Send** on it (or type yes)
  in AI Home or Mission Control; the watcher's Brain page shows the card only.
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
- AI Home's agent row, Mission Control and the chat beside its tab show the tool and its exact input, with **Allow
  once**, **Always allow** and **Deny**. The watcher's Brain page in Brave shows them with **Allow once** and **Deny**
  only, because Always allow is kept for AI Home's Tools. Brave also shows a notification (Review / Deny).
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

**Mission Control**, in AI Home's header, opens a dark control room in a window of its own (a second click brings
it forward):
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
  - Each nameplate shows the agent's number and name ("1 · Fix the footer"). The number stays the same while the app
    runs, so "agent 2" always means the same agent; numbers start at 1 again when the app restarts.
  - Click a station, or pick it from **List**: the drawer shows its state, **Watch**, **Stop**, **Close**, its
    permission card (**Allow once**, **Always allow**, **Deny**), **Your tabs** and its chat. When agents work in
    your Brave, **Give to this agent** under **Your tabs** hands it one of your own tabs, as AI Home's **Hand over**
    does.
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
  anywhere. It is off by default, and AI
  Browser remembers it. Without such a voice, it says so and stays off.
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
- **It only proposes.** Asked for work, it offers one card: **start a NEW agent** with your own words, **send your
  words to an agent that's already open** (say its number, "agent 2", its colour, "the blue one", a word of its name,
  or "it"), or **draft a reply** to an inbox item. Nothing happens until you press **Start**, **Send** or **Draft
  it**, or say "yes"; a "yes" with no card open does nothing. A message to a busy agent waits until it finishes what
  it's doing now; one waiting at a bot check isn't sent, and its card's Continue stays yours. Voice never approves or
  sends a draft, answers a permission card or a bot check, confirms a ⚠ action, marks items Done, pauses watching,
  changes a setting, or hands over or takes back a tab: those stay clicks. Words that sound like a password or a code
  are never sent: log in yourself, in the site's own tab.
- **Setup, once:**
  1. In this folder, run `uv sync --extra voice`, then restart `ai-browser app`. It installs faster-whisper and the
     Python packages it needs, from PyPI. Sync with `uv sync --extra voice` (or `--all-extras`) from then on: a plain
     `uv sync` removes the extra again (`uv run` keeps it).
  2. The first time you hold Space, Mission Control offers the English speech model: **Download 148 MB** (Whisper
     base.en from Hugging Face, pinned to one revision and checked before use), saved in
     `~/.ai-browser/models/faster-whisper-base.en` (or under `$AIB_HOME`). Nothing else is downloaded, and only when
     you click.
  3. AI Browser's window then asks to use the microphone: choose **Allow while visiting the site**, not **Allow
     this time**. It asks once: AI Browser comes back on the same address after a restart. macOS may also ask once
     whether the browser that draws the window (Google Chrome on a Mac) may use the microphone.
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
2. When Brave asks **Allow remote debugging?**, click **Allow**. Brave asks once when `ai-browser app` connects, and
   again after Brave restarts. While the app runs, agents and Claude Code sessions share its one connection; without
   it, each Claude Code session asks once.
3. Check it any time with `uv run ai-browser doctor --own`.

**While this switch is on, any program on this computer can reach your Brave, not only ai-browser.** That includes
the sites you are signed in to.
- While AI Browser is connected, a program that can read AI Browser's files can also use your Brave through it without
  a new question. AI Home lists everything connected, with Disconnect.
- Turn it off when agents aren't working: untick the same box.
- Only click Allow right after you started AI Browser, clicked Connect, gave an agent a task, asked Claude Code to
  browse, or opened Brave again while an agent was working. If Brave asks at any other time, it isn't AI Browser:
  click Deny, unless you just started another browser tool yourself.
- While AI Browser is connected, Brave shows a bar saying it is being controlled by automated test software. That is
  Brave telling you the truth; AI Browser never hides or closes it. If you close it yourself, it comes back only when
  AI Browser or Brave restarts.

What happens in your Brave:
- **Background tabs only:**
  - each agent works in background tabs it opens itself, in a tab group named after its task, in its colour;
  - nothing comes to the front unless you click **Watch**, or a site shows a bot check (handed to you, see
    "Bot checks");
  - a Claude Code session's tabs go in a group called "Claude Code" while `ai-browser app` runs, and in a window of
    their own otherwise.
- **Your other tabs:** never read, listed to an agent or touched. AI Home shows the ones in the agents' profile (other
  profiles and private windows only as a count), and **Hand over** gives one to an agent; **Take back** ends that at its
  next step. A tab the agent's own click opens from a handed tab is the agent's: it sits in its group and closes with
  it.
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

On Windows ai-browser finds Brave's folder (`%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data`) by itself. To
pick one in PowerShell:

```powershell
$env:AIB_CHROME_DIR = "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\User Data"; uv run ai-browser doctor --own
```

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
uv run ai-browser app [--window auto|chrome|brave|edge]  # AI Browser's window; agents browse in your Brave
uv run ai-browser doctor [--own]             # health check (the sandbox, or your own Brave or Chrome)
uv run ai-browser doctor --setup             # quick check, no Docker: Python, Claude Code, the window's browser, Brave, ports, config
uv run ai-browser bench                      # speed vs budgets
uv run ai-browser live [--profile P]         # watch / log in
uv run ai-browser stop [P | --all]           # stop containers (logins kept); `stop chrome` = own-Chrome shell
uv run ai-browser build                      # rebuild the image
```

## Safety notes

- AI Browser's window has no debugging port, and no agent browses there. Its pages need a cookie only that window
  holds, every request must name `127.0.0.1:<port>` exactly, and a strict content policy runs no script but the
  pages' own.
- ⚠ risky buttons are refused unless `confirmed=true`; Claude asks you first. Page dialogs are treated the same way:
  - Alerts are accepted and reported.
  - `confirm()`, `prompt()` and "leave page with unsaved changes?" are dismissed unless the step was confirmed.
- To change the defaults, edit `~/.ai-browser/config.json`:
  - the risky word list: `"risky_words": […]`
  - skills to block: `"blocked_skills": ["ecc:some-skill"]`
  - A file that can't be read (a typo, or an encoding other than UTF-8 or UTF-16) is ignored and the defaults apply.
    `uv run ai-browser doctor --setup` tells you when that happens.
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

**Tests on Windows (GitHub):** the private repo's Actions tab has one workflow, **tests**. It runs only when you
click **Run workflow**, never on a push. Pick `windows` (the default), `macos` or `both`; tick **voice** to also
install the voice extra (no model is downloaded). It uses your Actions minutes only then: Windows and macOS minutes
cost more than Linux ones, macOS the most. The test report is kept for 7 days, inside the private repo. Tests that
need macOS or Linux (the DevTools pipe) show as skipped, with that reason.

**Browser detection** (`src/ai_browser/browsers.py`): finds which browsers are installed (Brave and Chrome with their
other channels, and Chromium; Edge, Arc and Vivaldi are listed as not supported yet), whether each one runs with its
remote-debugging switch on, its profiles by name and colour, and which profile holds the Brain's watcher. It only
reads files, and for each browser that runs, or whose lock can't tell, opens a TCP connection to 127.0.0.1 that sends
nothing, so it never makes your browser ask "Allow remote debugging?". It never opens cookies, saved passwords or
history; it reads only what it needs, and never keeps or shows your account's email. Nothing in the app uses it yet.
To see what it finds on your computer (it only reads, and opens no DevTools session):

```bash
uv run python -c "import json; from ai_browser import browsers; from ai_browser.appbrowser import extension_id_for; from ai_browser.config import home; w = home() / 'app' / 'watcher'; print(json.dumps(browsers.public(browsers.detect({extension_id_for(w): w})), indent=1))"
```

Layout: `src/ai_browser/` (engine), `docker/` (sandbox image), `src/ai_browser/pages/` (local test pages), `tests/`.
