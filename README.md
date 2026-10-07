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
6. **Brave, once, after step 5:**
   - nothing to install in Brave: AI Browser reads your Gmail, Slack and Asana tabs itself, once you turn on Settings →
     Brain → **Read my Gmail, Slack and Asana tabs**. An earlier AI Browser's extension can be removed: open
     `brave://extensions` and click **Remove** on "AI Browser Watcher" (`%USERPROFILE%\.ai-browser\app\watcher` is its
     old folder; AI Browser never removes either);
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
- **Files that hold tokens** (each agent's `mcp.json`, `link.json`) keep Windows'
  per-user permissions on your folder: you, SYSTEM and Administrators.
- **Running inside WSL2** works with the Linux code, but needs Linux Chrome and Brave inside WSL.

## Windows test build (AI Browser.exe, built by GitHub)

A temporary way to try the current version on a Windows PC (64-bit) without Python, uv or the code. It isn't
signed, and it has no voice input.

1. **Build it:** on GitHub, open the repo's **Actions** tab → **Build Windows app** → **Run workflow** (pick the
   branch to test). It runs only when you click, and takes a few minutes.
2. **Download it:** open that run's page. Under **Artifacts**, click **AI-Browser-windows.zip** (kept for 14 days).
3. **Start it:** unzip it (right-click → **Extract All**) into a folder of yours outside OneDrive, open the
   `AI Browser` folder and double-click **AI Browser.exe**. The first time, SmartScreen says
   "Windows protected your PC", because the build isn't signed: click **More info**, then **Run anyway**.
   - A console window opens with AI Browser's log, then AI Browser's own app. Quitting the app (its icon by the clock
     → Quit), or closing the console window, stops everything.
   - Start it from `AI Browser.exe`, not from the Start menu entry the app adds (that one is for its notifications).
   - The app keeps its sign-in and settings in your own folder (`%USERPROFILE%\.ai-browser\desktop-profile`), so it
     works wherever you unzip it, and a newer zip keeps them.
   - With a command, it works as `ai-browser` does: in PowerShell, in that folder, `& ".\AI Browser.exe" …` (for
     example `& ".\AI Browser.exe" doctor --setup`). AI Browser's messages name its commands that way.
4. **The PC needs:**
   - Claude Code, installed and signed in: `irm https://claude.ai/install.ps1 | iex`, then `claude` once;
   - Brave, with remote debugging on: open `brave://inspect/#remote-debugging` and tick **Allow remote debugging for
     this browser instance** (untick it when agents aren't working);
   - Docker Desktop only for skills and the shell tool, then `& ".\AI Browser.exe" build` once.
5. **Not in this build:** voice input (talking to the Brain).

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

AI Browser opens in a window of its own: a title bar and a row of AI Browser's own tabs under it, with no browser
tabs and no address bar. An installed browser draws it in its app mode, on a profile of AI Browser's own
(`~/.ai-browser/app/window/<browser>/`), with no debugging port. Nothing drives that window, so it never asks "Allow
remote debugging?" and shows no automation bar, and no agent browses there. Agents browse in your everyday Brave
([Which browser](#which-browser)), where you are signed in yourself: chosen before the task, for your logins, and
nothing switches browsers on its own after a block. When a site answers with a bot check, the agent stops and hands it
to you ([Bot checks](#bot-checks)).

**Which browser draws the window:** Settings → App window offers **Auto**, **Google Chrome**, **Brave**, and
**Microsoft Edge** on Windows. Auto picks Google Chrome on a Mac whose everyday browser is Brave, so a link clicked
in another app never lands in AI Browser's window, and Microsoft Edge on Windows. The Dock (the taskbar on Windows)
shows that browser's icon while AI Browser is open. A change applies at the next start;
`uv run ai-browser app --window brave` picks one for a single run.

**First start (once):** there is nothing to load in the window, and nothing to install in Brave. AI Home's browser
card opens Brave's one step (its remote-debugging switch) in a tab of its own, with a × to close it. If an earlier AI
Browser's extension is still in Brave, AI Home says you can remove it, until you click **Got it**.

**AI Home** is the window's first tab.
- **Start a task:** pick skills and a model if you like.
- **Agents:**
  - Up to 3 work at once (`AIB_APP_MAX_AGENTS`); the rest wait in line.
  - Each row shows what the agent is doing now, its last action with timing, a small picture of its tab, and its
    time and cost.
  - Each row has **Watch**, **Chat**, **Stop** and **Close**.
  - The window's title counts the agents at work, whichever tab is shown: "(2) AI Home · AI Browser".
- **Your browser:** a card at the top says where agents browse and whether your Brave is connected. When Brave's
  switch is off, it shows the steps; when Brave asks "Allow remote debugging?", it says so.
- **Tabs:** the web tabs of the Brave profile where agents browse (Settings → **Where agents browse**; until you
  pick one, the profile you used last), each marked with whose it is: an agent's, Claude Code's, the Brain's, or yours. Other profiles and private windows
  are only counted, never listed.
  - A click brings a tab to the front.
  - **Hand over** gives one of your tabs to a new or running agent (it reads that tab and acts in it).
  - **Take back** ends that.
- **Skills:**
  - every one of Claude's skills (personal, plugins, claude.ai, ai-browser), and which ones each agent loaded;
  - add one to a new task, or ask a running agent to use it.
- **Settings** (a tab, and a button beside **Mission Control**): which browser draws the window, your AI
  accounts, **Where agents browse** (your Brave profiles, by name and colour) and the **Brain** (reading your
  Gmail, Slack and Asana tabs). The model you pick and Voice are remembered by AI Browser itself, in every tab and across restarts.

**Tabs and links:** AI Home, Mission Control and Settings are tabs in a row under the title bar, and the window's
title follows the one shown ("Mission Control · AI Browser"). A tab loads the first time you pick it, and then stays
as you left it while you look at another: a half-typed message, the scroll and Mission Control's room are all still
there when you come back. The setup steps and an agent's live view (**Show me** on a bot check in QA's sandbox) open
as tabs at the end of the row, each with a × to close it; a second **Show me** for the same agent goes to its open
tab. Nothing opens a window: a link between AI Browser's pages switches tabs, and a link to a website opens in your
Brave, never in AI Browser's window. The AI's tabs open in windows of their own in your Brave, never among your
windows, and AI Home and Mission Control say which agent owns each one.

How it works:
- **Claude:** each agent is Claude Code on this computer (`claude -p`), signed in with one of your Claude accounts
  (AI accounts, below), with no API keys. Besides ai-browser's tools it has Claude Code's own, each asked first
  ([Agent powers](#agent-powers-commands-file-edits-the-web-sub-agents-and-to-do-lists)). Skill scripts run in the
  Docker sandbox.
- **Background agents:** tasks from AI Home or Mission Control work in background tabs. They
  never take your focus, and they stay at full speed. **Watch** brings one to the front.
- **Stop and Close:** **Stop** interrupts an agent and keeps its tabs. **Close** ends it and closes the tabs it
  opened; your own tabs stay open.
- **Logins:** log in yourself, in that tab in Brave. Claude never types passwords, and risky buttons (⚠) need your
  yes in that agent's chat.
- **Downloads** go to your Downloads folder, and only after your OK.
- **Only the window gets in:** AI Browser's window starts with a one-time code that the app swaps for a cookie
  only that window holds. The same address typed into Brave shows "AI Browser's pages open only in its own window".
- **Closing:** closing the window stops AI Browser: close it (⌘Q on a Mac), or press Ctrl-C in the terminal, and
  the agents end with it. ⌘W (Ctrl+W on Windows and Linux) closes only the tab you're on, and only if it has a ×
  (the setup steps, a live view); on AI Home, Mission Control and Settings it does nothing. Switching tabs, or closing
  the setup steps' or a live view's tab, never ends AI Browser. The Docker shell container keeps running for the next
  start; stop it with `uv run ai-browser stop chrome`.
- **The microphone** is asked for once, in the window, and kept across restarts: AI Browser comes back on the same
  address.
- **Old folders:** `~/.ai-browser/browser/` (AI Browser's old Chrome profile, which may hold logins you made there)
  and `~/.ai-browser/app/extension/` (its old extension) are no longer used. AI Browser never deletes them; delete
  them by hand if you like.

### Agent powers: commands, file edits, the web, sub-agents and to-do lists

Agents have Claude Code's own tools besides the browser: shell commands, reading and editing files, Web Search and
Web Fetch, sub-agents, and a to-do list.

- **The folder:** New task's **Folder** picker sits beside the model and the account, in AI Home, Mission Control and
  the floating chat:
  - **No folder**, the default: the agent's own scratch folder, `~/.ai-browser/app/agents/<id>/work`;
  - a folder you used lately;
  - **Choose…**: the system's folder dialog in AI Browser's own app; in a browser window, you type the path.

  The agent works there, and its row and drawer show it. Some folders are refused: your home folder itself,
  `~/Library`, the system's folders, Claude Code's folders (`~/.claude` and your accounts' folders) and
  `~/.ai-browser`.
- **Trust this folder?** The first time a folder is used, AI Browser asks.
  - A folder you trust loads its own `CLAUDE.md`, `.claude` agents and settings, as in Claude Code, with their hooks
    and their rules.
  - A folder you don't trust loads none of them.
- **Asked first:** anything that isn't allowed yet shows a card with exactly what will happen:
  - the command and its folder;
  - the edit as a diff, removed lines red and added green (a huge or binary file shows its size);
  - the path, the site or the query.

  A sub-agent's card names the sub-agent. Answer **Allow once**, **Always allow for this folder** or **Deny**, with a
  note to the agent if you like. In an agent's own scratch folder, Always lasts for that agent only.
- **Allowed without asking:**
  - reading inside the folder;
  - the to-do list;
  - starting a sub-agent (its own actions still ask);
  - `ls`, `cat`, `pwd`, `git status`, `git diff` and `git log`.
- **Asked every time, never "Always":**
  - `sudo`, `rm`, `chmod`, `chown`, `dd` and `mkfs`;
  - uses that delete files or throw work away: `find -delete` or `-exec`, `git clean`, `git reset --hard`,
    `git checkout -- …`, `git restore`, `git push --force` and `git branch -D`;
  - a download piped into a shell;
  - anything that reads or writes outside the folder, including edits to its `.git` or `.claude` settings;
  - anything that is more than one plain command (`;`, `&&`, `|`, `$(…)`, a redirect).
- **Always allow trusts the whole program:** once you always-allow a program (`curl`, `sed`, `tar`, `make`), later
  uses run without a card, and AI Browser can't see inside that program's own options: `curl -T` or `-d @file`,
  `sed 'w …'`, an archive's `../` entries. Allow only programs you trust with any input.
- **Your answers are kept per folder** in `~/.ai-browser/permissions.json`. **Settings → Permissions** lists each
  folder with your trust answer and the rules you allowed always, each with **Remove**. A folder that was deleted,
  renamed or unplugged keeps its rules until you remove them.
- **Live:**
  - every action shows a badge (Bash, Edit, Write, Read, Web Search, Web Fetch, Browser Agent, Sub-agent, Skill) and
    its time;
  - Mission Control's drawer shows the agent's plan ("3 / 5 steps · 60%") and each sub-agent's task and current
    action, and AI Home's row says how many sub-agents are working;
  - **Stop** stops its sub-agents too.
- **Commands and the sandbox:** on a Mac, commands run in Claude Code's sandbox, so they can't write outside the
  task's folder. A command that needs more asks, every time, on a card of its own: reaching a site ("let a command
  reach a site") or running outside the sandbox. You still answer each command's card. On Windows, commands don't run
  in a sandbox; the cards are the guard.
- **Workflows** still run in a scratch folder of their own.

### AI accounts (Settings → Accounts)

Agents can run on more than one Claude login: to keep working past a usage limit, or to keep work and personal
apart.
- **Default** is your own login: the folder in `CLAUDE_CONFIG_DIR` if your environment sets it, else `~/.claude`. It
  can't be removed.
- **Add** makes an account with a folder of its own (`~/.ai-browser/accounts/<id>/`). **Use a Claude Code folder I
  already have** takes one you made yourself. A browser's data folder, such as the Claude app's `--user-data-dir`, is
  refused.
- **Sign in** has two ways:
  - **Open Terminal** opens a terminal running `claude` for that account: Terminal on a Mac, a command window on
    Windows;
  - **Copy the command** is for your own terminal.

  You sign in there and in your browser. AI Browser never sees a password or a token.
- Each account shows **Signed in · Pro** or **Not signed in**. That is all AI Browser keeps: never your email or your
  organisation.
- **Choosing:** Settings sets the default account for new agents, and the Brain's account. AI Home and Mission
  Control have an **Account** picker next to the model when you have two or more. An agent keeps its account until
  you move it.
- **At a usage limit,** the agent stops, and its row says "Personal hit its usage limit (resets 3:00 pm).":
  - **Continue on Work** carries its conversation to the other account, and it goes on there. When the conversation
    can't come along, it starts fresh there with a hand-over note: the task, its last steps and its tabs;
  - **Wait for the reset** leaves it paused.

  Nothing moves without your click. The Brain and voice never move an agent. When the Brain hits its
  limit, a card in AI Home's Brain area asks the same.
- **Per account:** the login, Claude Code's settings, MCP servers and connectors (AI Home → Tools shows one account's
  at a time), and conversations. **Shared:** AI Browser's skills, workflows, the browser and the Brain's inbox.
- **Remove** only makes AI Browser forget an account. Its folder, its conversations and its sign-in stay.

### AI Browser's own app (a menu-bar icon, a shortcut and notifications)

AI Browser can run as an app of its own, built on Electron, instead of in a browser window. It has its own Dock
icon (a taskbar icon on Windows) and an icon in the menu bar (by the clock on Windows). It also adds the floating
chat, which a shortcut shows and hides from any app, and native notifications. The engine stays the same:
`uv run ai-browser app` starts it, then the app.

**Setting it up (once):** run `uv run ai-browser doctor --setup` in a terminal.
- It shows what it would download: Electron 44.5.1 for your computer, its size (about 130 MB on a Mac, 158 MB on
  Windows) and its address on GitHub. Nothing is downloaded until you type `y`.
- The download is checked against Electron's `SHASUMS256.txt` from the same release. If it doesn't match, or it
  stops halfway, nothing is kept, the browser window still works, and Settings says what happened.
- The app is built in `~/.ai-browser/desktop/`: "AI Browser.app" on a Mac, signed on your Mac, ad hoc, so macOS
  remembers its microphone permission, and its permission to see Brave's tab; an "AI Browser" folder on Windows.
  Running it needs no Node.js and no npm.
- On Windows it also adds AI Browser to the Start menu: Windows shows an app's notifications only then. AI Browser.exe
  keeps Electron's icon in File Explorer. Its window, its icon by the clock and its notifications show AI Browser's.
- When an update of AI Browser changes the app's own files, `ai-browser app` builds the app again before it starts,
  with no download. macOS may then ask for the microphone, and for Brave, once more.

**Using it:**
- **Closing the window hides it.** The app keeps running in the menu bar (by the clock on Windows), and agents keep
  working. Its Dock icon (the taskbar on Windows), or **Open AI Browser** in the menu-bar icon, brings it back.
- **Quit** stops the app and every agent, as Ctrl-C in the terminal does. Quit is in the menu-bar icon's menu, or
  press ⌘Q on a Mac.
- **The shortcut** is ⌥Space (Alt+Space on Windows): it shows and hides the floating chat. Settings → AI Browser app
  offers two others, and Off. If another app already uses it, Settings says so: pick another one. Press it once after
  a change, to check it.
- **Notifications** say only what needs you: "An agent is waiting for you", "A bot check on example.com", "The Brain
  has 2 new notes". Never a message's text or a page's. A click opens AI Home at that agent's row, or brings the
  agent's tab forward in Brave.
- The menu-bar icon offers **Open AI Browser**, **Show chat** and **Quit**. **Show chat** works even when another app
  holds the shortcut.
- Until it is set up, or with `--window`, AI Browser opens in a browser window as before, and AI Home offers the
  setup.
- Started by a double-click (Finder, or the Start menu), it asks you to start AI Browser from a terminal. A
  double-click start comes later.

**Locked down:** its pages are AI Browser's own (`http://127.0.0.1:<port>`) and nothing else. A website link opens in
Brave, and no page opens a window. Pages may use the microphone, and write to the clipboard on a Copy button; nothing
else. It has no debugging port and no DevTools, and it refuses to start with a debugging switch.

### The floating chat (⌥Space, beside Brave)

Press ⌥Space (Alt+Space on Windows), or **Show chat** in the menu-bar icon, from any app: a small chat window opens
above your other windows, at the right of the screen. Move it and size it as you like: it opens there next time.
Press the shortcut again, Esc or ✕ to hide it. It needs AI Browser's own app (above).

- **This page** shows the Brave tab you're on, by its title and site. While the chat shows, AI Browser asks Brave for
  the address and title of its front tab, and nothing else: through AppleScript on a Mac, through UI Automation on
  Windows. It never types, clicks or opens anything in Brave, and when Brave isn't running, Brave stays closed.
  - **On a Mac,** macOS asks once whether "AI Browser" may control "Brave Browser". If you said no: System Settings →
    Privacy & Security → Automation → AI Browser → turn on Brave Browser.
  - When AI Browser can't tell which tab you're on (the same page in two windows, a tab in another profile with its
    own title, a private window), pick it from your tabs. If Brave isn't running, or isn't connected to AI Browser, the chat says so: the chat never
    connects by itself.
- **Ask about it:** turn it on, then ask. Only then does AI Browser read that page's words (at most 12,000
  characters, never its scripts), and the Brain answers from them. Page text is data: about a page, the Brain only
  answers, and proposes nothing.
- **Talk to the Brain:** type, or hold the mic button. "Tell agent 2 to check the footer" makes a card: press **Send**
  or **Start**, or say yes. The open agents show by number; a click opens one in AI Home.
- **New task** starts an agent with the model and the account you pick. It replaces typing `ai` in Brave's address
  bar. **Start it in this page** hands this tab over to it as it starts.
- **Hand over…** gives this page to an open agent. Only your click hands a tab over, as in AI Home.
- An agent that waits for you (a tool to allow, a bot check) shows its card in the chat too.
- The old side panel is gone: the floating chat takes its place.

## The Brain (reads your messages, tells you what needs you)

The Brain runs inside `ai-browser app`. It reads Gmail, Slack and Asana, and parts of pages you pick, in your open
tabs in **Brave**, your everyday browser. Nothing is installed in Brave. It shows you only new messages and the ones
that need your reply, never your whole inbox. Everything else is only counted ("14 others, nothing needs you").

**Turn it on (once):** Settings → **Brain** → **Read my Gmail, Slack and Asana tabs**. It is off until you turn it
on. While it is on, AI Browser reads those sites in your open tabs, in the profile where agents browse, through its
one connection to Brave. Turning it off stops reading at once, and a read under way keeps nothing. AI Home's Brain
section says when reading is off, or waiting for Brave.

**Settings → Brain** shows:
- **The sites:** Gmail, Slack and Asana, each with how reading goes ("no open tab", "reader needs an update").
- **Parts of pages you watch:** each with **Turn off** and **Remove**. To add one, pick one of your open tabs and
  click **Pick the part to watch**: that tab comes to the front in Brave, an outline follows your mouse, a click picks
  the part (for example an orders table), and Escape cancels.

**AI Home's Brain section** shows:
- **The inbox:** each item has the site, who it's from, the Brain's one-line summary, why it matters and a suggested
  action.
  - A **needs your reply** item stays until you reply, or click **Done**.
  - A **new** item stays a day.
- **How I write** (style notes for drafts), and each site's **instructions** in plain words, for example "Always tell
  me about clients; skip newsletters and receipts".

**What you can do with an item:**
- **Draft reply:**
  1. AI Browser reads the thread in your tab (or opens it in a background tab marked "Brain").
  2. The Brain drafts a reply in your style.
  3. You edit it, then click **Use draft**.
  4. AI Browser puts the text in the reply box and brings that tab to the front. **You press Send**: the Brain never
     sends anything.
- **Hand to agent:** an AI Browser agent gets your instruction and the message.
- **Tell the Brain:** your own words ("draft a polite no", "check the page", "give this to agent 2") become a draft, or
  a card that starts a NEW agent or sends your words to an open one. Press **Start** or **Send** on it (or type yes)
  in AI Home or Mission Control.
- **Done.**

AI Browser's own app shows a notification when new items need you ("The Brain has 7 new notes"), never their text.

How it works:
- **Reading:** the readers run in an isolated world of each tab: the page's own scripts can't see or change them, and
  what they read comes back as plain text, which the Brain treats as page data, never as your words.
- **Sorting:** the Brain sorts new items with Claude Code (Haiku), in calls that have **no tools at all**. Message
  text isn't kept in Claude Code's history.
- **Drafts:** written with Sonnet in the same tool-less way.
- **Files:** the inbox, the watch list and what the readers keep between reads are in `~/.ai-browser/brain/` (only
  you can read them), so they survive a restart.
- **Readers:** they find messages by each site's page structure, in any language. If a site changes its layout, the
  site says "reader needs an update" instead of failing silently. A site without an open tab says "no open tab", and
  a tab on another page of the site (Gmail's Settings, an Asana board) says "open the inbox".
  - Gmail is read in the inbox and its category tabs only: never Spam, Sent, labels or searches.
  - A Gmail reply goes at the top of the reply box, above your signature. Slack gets it on one line, since Enter
    sends there.
- **When the app is off:** nothing is read.

### Tools: your MCP servers for the agents (AI Home → Tools)

Agents can use the same MCP tools as your Claude Code app. The Tools section lists:
- the servers in Claude Code's configuration (`~/.claude.json` and your projects' `.mcp.json`);
- your claude.ai connectors (ClickUp, Google Drive…). Claude Code is asked which ones you have the first time you open
  the section.

Switch on the servers agents may use. Nothing else reaches them. ai-browser's own tools are always on. With two or
more AI accounts, a picker at the top shows one account's tools at a time: each account has its own servers, switches
and **Always allow** list.

**Asking first:**
- The first time an agent wants a tool that isn't allowed always, it waits ("needs you").
- AI Home's agent row, Mission Control and the chat beside its tab show the tool and its exact input, with **Allow
  once**, **Always allow** and **Deny**. AI Browser's own app also shows a notification, in fixed words.
- **Always allow** is remembered in `~/.ai-browser/tools.json`, for that account. **Forget** removes it.
- **Stop** or **Close** denies a request that is still waiting.
- Nothing a page or a message says can answer for you.

### Workflows: your own recipes (AI Home → Workflows)

A workflow is a name and instructions in your words, for example "Open the site in AI Browser, make the change the
task asks for, then post what you did in #web-team". It has:
- **a trigger:**
  - **by hand:** **Run** in AI Home;
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

**Mission Control**, a tab of AI Browser's window (or its button in AI Home's header), is a dark control room:
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
  - click it for its inbox (Draft reply, Use draft, Hand to agent…).
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
  sends a draft, answers a permission card or a bot check, confirms a ⚠ action, marks items Done,
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
  **Continue** and **Skip this site**, and a notification from AI Browser's own app.

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
  - each agent works in background tabs AI Browser opens for it, in windows of their own, in the profile where agents
    browse;
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
uv run ai-browser app [--window auto|chrome|brave|edge]  # AI Browser's own app, or a browser window; agents browse in your Brave
uv run ai-browser doctor [--own]             # health check (the sandbox, or your own Brave or Chrome)
uv run ai-browser doctor --setup             # quick check, no Docker; offers AI Browser's own app (asks first)
uv run ai-browser bench                      # speed vs budgets
uv run ai-browser live [--profile P]         # watch / log in
uv run ai-browser stop [P | --all]           # stop containers (logins kept); `stop chrome` = own-Chrome shell
uv run ai-browser build                      # rebuild the image
```

## Safety notes

- AI Browser's window has no debugging port, and no agent browses there. Its pages need a cookie only that window
  holds, every request must name `127.0.0.1:<port>` exactly, and a strict content policy runs no script but the
  pages' own.
- AI Browser's own app has no debugging port and no DevTools, and refuses to start with a debugging switch. Its
  fuses keep any other program from running it as Node.js or with an inspector. Its pages are AI Browser's own
  only. They may use the microphone, and write to the clipboard on a Copy button.
- The floating chat reads only the address and title of Brave's front tab, only while it shows, through AppleScript
  (a Mac) or UI Automation (Windows): one fixed command, never built from a page's or your words. It reads a page's
  words only when you ask about that page, and an agent works in your tab only after your Hand over.
- Agents' own commands, edits and reads ask first, on a card that shows exactly what will happen. Only clicks in AI
  Browser's own pages answer: never the Brain, voice or a page. The app reads each command without running it. Only
  one plain command whose paths are all inside the task's folder can be harmless or allowed always. Paths are
  compared after resolving symlinks and `..`.
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

Tests that drive a real Electron run only when `AIB_TEST_ELECTRON` names an Electron 44 program you already have (an
Electron.app's `Contents/MacOS/Electron`, or `electron.exe`). They start it unpackaged, in throwaway folders, and a
window shows for a moment. The tests of the app's rules run under Node.js when it is installed. The app itself never
needs Node.js.

**Tests on Windows (GitHub):** the private repo's Actions tab has the workflow **tests** (and **Build Windows app**,
the [Windows test build](#windows-test-build-ai-browserexe-built-by-github)). It runs only when you
click **Run workflow**, never on a push. Pick `windows` (the default), `macos` or `both`; tick **voice** to also
install the voice extra (no model is downloaded). It uses your Actions minutes only then: Windows and macOS minutes
cost more than Linux ones, macOS the most. The test report is kept for 7 days, inside the private repo. Tests that
need macOS or Linux (the DevTools pipe) show as skipped, with that reason.

**Browser detection** (`src/ai_browser/browsers.py`): finds which browsers are installed (Brave and Chrome with their
other channels, and Chromium; Edge, Arc and Vivaldi are listed as not supported yet), whether each one runs with its
remote-debugging switch on, and its profiles by name and colour. It only
reads files, and for each browser that runs, or whose lock can't tell, opens a TCP connection to 127.0.0.1 that sends
nothing, so it never makes your browser ask "Allow remote debugging?". It never opens cookies, saved passwords or
history; it reads only what it needs, and never keeps or shows your account's email. Settings → Where agents browse
lists its profiles.
To see what it finds on your computer (it only reads, and opens no DevTools session):

```bash
uv run python -c "import json; from ai_browser import browsers; print(json.dumps(browsers.public(browsers.detect()), indent=1))"
```

Layout: `src/ai_browser/` (engine), `docker/` (sandbox image), `src/ai_browser/pages/` (local test pages), `tests/`.
