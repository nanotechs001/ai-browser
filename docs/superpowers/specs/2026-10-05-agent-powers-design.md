# Agent powers: commands, file edits, web tools, sub-agents and to-do lists

Date: 2026-10-05.

## Status

The user approved the design's three sections in chat ("yes proceed", "good", "good"). This spec writes them down. The
user reviews it before the plan is written.

**The user's request**, verbatim: "make it so they are able to run bash command and able to summon sub agent. This app
will be the replacement of the claude code app, an all in one app workflow automation best browsing capability for
faster navigation and all feature of the claude app, should be also able to pull the claude artifacts."

**It came while designing a new look for Mission Control** (the user's mockup: a dark navy and neon-blue "AI office"
with chibi agents, step cards, Mission Progress and a live checklist). The work was split into four projects, built in
this order (the user's choice, "Powers → Look → Projects → Artifacts"):
1. **Agent powers:** this spec.
2. **The new look:** the mockup. Its first two design sections were agreed in chat; they are written into its own spec
   after this one, designed around these powers.
3. **Projects, sessions and chat:** project folders, sessions kept and resumed, and plain chat with Claude.
4. **Claude artifacts:** see, open and pull the user's claude.ai artifacts.

**The user's answers for this project:**
- **Approval:** "Ask first, with "always allow" (Recommended)".
- **The folder:** "Pick a folder per task (Recommended)".
- **Web tools:** "Yes, both (Recommended)", meaning Web Search and Web Fetch.
- **From the look's design:** each agent's own plan (Claude Code's to-do list) shown live, to match the mockup's
  checklist with pending steps.

## Facts this rests on

- **How an agent starts today** (`app/bridge.py`, `_command`): `claude -p` with stream-json in and out.
  - `--tools ""`: none of Claude Code's own tools;
  - only `mcp__ai-browser__*` (the browser, and the Docker shell for skills), plus the user's allowed tools;
  - `--setting-sources local`;
  - the working folder is `<home>/app/agents/<id>/chat`;
  - API variables are stripped (`clean_env`).
- **Permission cards already exist** for the user's tools. With `--permission-prompt-tool stdio`, Claude Code sends a
  `control_request` with subtype `can_use_tool`; the app shows a card (`permission.js`), and
  `AgentManager.answer_permission` answers it. The watcher can't send "Always allow" (watcher safety); the watcher has
  since retired.
- **Claude Code's built-in tools:** Bash, Read, Edit, Write, Glob, Grep, WebSearch, WebFetch, TodoWrite, and the
  sub-agent tool (Agent/Task).
  - Sub-agents' events stream with a `parent_tool_use_id`.
  - TodoWrite's input holds the list: `todos: [{content, status, activeForm}]`.
- **Claude Code 2.1.263** also carries artifact tools for claude.ai. That's project 4's concern, not this one.

## Decisions

1. **Agents get Claude Code's own tools**, alongside the browser's:
   - Bash, Read, Edit, Write, Glob and Grep;
   - WebSearch and WebFetch;
   - the sub-agent tool;
   - TodoWrite.

   The browser's MCP tools and the Docker shell for skills are unchanged.
2. **Every use that isn't allowed asks the user,** through the existing `can_use_tool` card, extended. The card shows
   exactly what will happen, as plain text:
   - **Bash:** the full command and its folder;
   - **Edit and Write:** a diff (removed lines red, added green) or the new file's content;
   - **Read, Glob or Grep outside the task's folder:** the path;
   - **WebFetch:** the site;
   - **WebSearch:** the query;
   - **a sub-agent's request:** the same card, naming the sub-agent ("Agent 2 · sub-agent: Research").

   **Buttons:** Allow once · Always allow for this folder · Deny. Deny can carry a short note to the agent.
3. **Allowed without asking:**
   - Read, Glob and Grep inside the task's folder;
   - TodoWrite;
   - starting a sub-agent (its own tool uses still ask);
   - harmless commands: `ls`, `cat`, `pwd`, `git status`, `git diff` and `git log` with their arguments.
4. **Never offered "Always allow"** (they ask every time):
   - any command with `sudo`, `rm -rf`, `chmod -R`, `chown`, `mkfs` or `dd`;
   - a download piped into a shell (`curl … | sh`);
   - a command that writes outside the folder;
   - Edit or Write outside the folder.
5. **"Always allow for this folder"** saves one rule:
   - **for Bash:** the command's first words, as Claude Code's rules do ("Bash: `npm test`", "Bash: `git commit`");
   - **for Edit and Write:** "files in this folder";
   - **for WebFetch:** the site.

   Rules are kept per folder (its real path) in `<home>/permissions.json` (mode 0600), and passed to Claude Code as
   `--allowedTools` rules when an agent starts there.
6. **The folder for a task:**
   - a **Folder** picker sits next to the model and account pickers: **No folder** (the agent's own scratch folder,
     `<home>/app/agents/<id>/work`, the default), recent folders, or **Choose…**;
   - in the Electron app, Choose… opens the system's folder dialog (a new preload action); without Electron, the user
     types a path;
   - the agent's row and drawer show the folder;
   - the chosen folder is the agent's working folder (`cwd`), and Claude Code's own rules keep edits inside it;
   - refused folders: `/`, the home folder itself, `~/Library`, system folders, `~/.claude` (and the environment's
     `CLAUDE_CONFIG_DIR` folders), and `~/.ai-browser`.
7. **Trusting a folder:**
   - the first time a folder is used, AI Browser asks "Trust this folder?";
   - **trusted:** `--setting-sources local,project`, so its `CLAUDE.md`, its `.claude` agents and its settings load,
     as in Claude Code;
   - **not trusted:** `--setting-sources local` only, so the folder's own hooks, MCP servers and tool rules never run;
   - trust is kept per folder in the same file, and Settings → Permissions shows it with **Remove**.
8. **Sub-agents:**
   - Claude Code's built-in sub-agent tool. Sub-agents share the agent's folder, account and model, and ask through
     the same cards;
   - they can't start sub-agents of their own (Claude Code's rule);
   - Stop on the agent stops its sub-agents;
   - the agent's row says how many sub-agents are working, and its drawer lists each one: its task, its current
     action, and done ✓ or working ●.
9. **The to-do list:**
   - TodoWrite updates are read from the stream and shown live in the drawer: done ✓, current ● (its `activeForm`),
     pending ○, and "3 / 5 steps · 60%";
   - an agent without a list shows its actions instead;
   - the list is kept with the agent's events, so a page that opens later sees it.
10. **The action feed:**
    - every tool use is one line with a badge (**Bash**, **Edit**, **Write**, **Read**, **Web Search**, **Web Fetch**,
      **Browser Agent**, **Sub-agent**, **Skill**) and its time;
    - these lines are the data the new look's step cards, Current Task and Recent Activity show.
11. **The command sandbox (if it works headless):**
    - the plan's first task probes Claude Code's built-in Bash sandbox on macOS in `-p` mode with stream-json;
    - **if it works,** commands run sandboxed by default (no network, no writes outside the folder), and a command
      that needs more asks to run outside it, with its own card;
    - **if not,** the cards are the guard, and the plan records that as a ruling.
12. **The agents' instructions** (`BRAVE_PROMPT`) gain short lines:
    - use Web Search and Web Fetch for quick lookups, and Brave for pages that need the user's login or clicks;
    - commands run in the task's folder;
    - keep a to-do list for work of several steps;
    - use sub-agents for independent parts.

    The browsing rules stand: bot checks go to the user, nothing is disguised, `curl` never goes around a block, and
    passwords are never typed.
13. **Workflows** keep running in a scratch folder for now. Projects (project 3) gives them folders.

## Safety

- **Nothing runs on the user's Mac without their click,** except Decision 3's list. Every card is the user's own
  click: never the Brain, voice or the watcher.
- **No "Always allow" for dangerous commands** (Decision 4), and no wildcard rule that allows every command.
- **Untrusted folders can't run their own hooks or settings** (Decision 7).
- **Refused folders** (Decision 6) keep agents away from the system, AI Browser's own state and Claude Code's logins.
- **Unchanged:**
  - no API keys, never `--bare`;
  - page text is data, and pages use `textContent` only;
  - Hand over and Take back are clicks;
  - skills run in the sealed Docker box;
  - downloads need the user's OK.

## Interfaces

- **`src/ai_browser/app/powers.py` (new):**
  - `classify(tool, input, folder) -> "allow" | "ask" | "ask_always"` (Decisions 3 and 4);
  - `rule_for(tool, input) -> str | None` ("Bash(npm test:*)", "Edit", "WebFetch(domain:example.com)");
  - `card(tool, input, folder) -> dict` (what the card shows: command, diff lines, path or site);
  - `Rules(home)`: rules and trusted folders in `<home>/permissions.json`, with `allowed(folder)`,
    `add(folder, rule)`, `remove(folder, rule)`, `trusted(folder)`, `trust(folder)` and `untrust(folder)`;
  - `check_folder(path) -> str | None` (the reason a folder is refused).
- **`app/bridge.py`:**
  - `_command()` lists the built-in tools, the folder's rules, and `--setting-sources` by trust;
  - `cwd` is the task's folder;
  - the event loop reads TodoWrite and `parent_tool_use_id`.
- **`app/agents.py`:**
  - `create(..., folder=None)`;
  - an agent's `folder`, `todos` and `subagents`;
  - `answer_permission(..., always=False, note="")`.
- **`app/server.py`:**
  - `new_task` takes `folder`;
  - new app-only messages `folder_choose`, `folder_trust`, `permission_rules` and `permission_rule_remove`, each a
    `MESSAGE_RULES` row with its copy in `tests/test_watcher_rules.py`.
- **The pages:**
  - the Folder picker, the trust question and the extended card in AI Home, Mission Control and the floating chat;
  - Settings → Permissions.
- **`desktop/preload.js`:** a `chooseFolder` action, answered only to AI Browser's own top-level pages.

## Testing

- **The fake `claude`** gains:
  - `can_use_tool` requests for Bash, Edit (with old and new strings), Write, Read, WebFetch and WebSearch;
  - TodoWrite tool uses;
  - sub-agent events with `parent_tool_use_id`.
- **Tests:**
  - `classify` and `rule_for` over safe, dangerous and outside-the-folder inputs;
  - the card's diff, as text;
  - rules saved per folder and passed as `--allowedTools`;
  - trust deciding `--setting-sources`;
  - refused folders;
  - Deny with a note;
  - Stop ending sub-agents;
  - the to-do list and sub-agents in the drawer;
  - every new message app-only.
- **Real commands:** tests never run against the user's folders. They use throwaway folders, and the fake `claude`.
- **The first task is a probe** in a throwaway folder: does Claude Code's Bash sandbox work in `-p` stream-json on
  macOS, and how does it ask to run outside it? The result is a ruling, and the plan holds both outcomes.
- **The user's hand check:**
  - start a task in a real project folder and see the trust question;
  - allow a command once and always;
  - deny an edit with a note;
  - watch a sub-agent and a to-do list.

## Review Focus

1. **A command built to dodge the rules:** `git status; rm -rf x`, `$(…)`, backticks, `&&`, a newline, or an alias.
   Only the whole command can be "harmless" or match a rule. Anything with a second command, a substitution or a
   redirect outside the folder asks.
2. **A symlink or `..` path** that looks inside the folder but points outside. Paths are checked after resolving.
3. **A sub-agent's request when its parent was stopped,** or a card answered after the agent ended. Nothing runs,
   and the card closes.
4. **A folder deleted, renamed or unplugged** between tasks. The agent says so plainly, and its rules stay until
   removed.
5. **An edit diff that is huge or binary.** The card shows a clipped diff with its size and never freezes the page.
