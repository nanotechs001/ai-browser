# The new look: Mission Control as the mockup's AI office, and one theme for the app

Date: 2026-10-05.

## Status

The user approved the design's four sections in chat. Sections 1 and 2 were agreed before the user widened the work
to "agent powers"; Sections 3 and 4 were answered "good". This spec writes them down. The user reviews it before the
plan is written.

**The user's request**, verbatim: "Next part let's replicate this UI and features. Let's make the AI working same in
that, you can remove the brain graphics just replicate what's in the image UI and feature and colors". It came with a
mockup: a dark navy and neon-blue "Mission Control - AI Browser" window.

**Their answers:**
- **How missions work:** "Just a new look". Today's agents stay one task each. Then: "You taking in consideration
  already the AI worker agent working will be same in screenshot right?"; the answer was each agent's own to-do list,
  shown live (agent powers, Decision 9).
- **New items:** "Workspaces, Usage meter (for AI Credits), Calendar view". Deep Research was left out.
- **The office scene:** "Drawn live in code (Recommended)".
- **The theme:** "The whole app (Recommended)".
- **The order of work:** "Powers → Look → Projects → Artifacts (Recommended)". This look is built after agent powers
  (`2026-10-05-agent-powers-design.md`) and designed around it: sub-agents, to-do lists and action badges.

## Facts this rests on

- **Mission Control today** (`app/ui/mission.html`, `mission.js`, `mission.css`):
  - a CSS-3D room (`scene.js`) with one station per agent, each a desk, a monitor and an SVG chibi (`chibi.js`);
  - the particle Brain in the middle (`blob.js`, `brainshape.js`);
  - an agent list, a drawer per agent, the Brain's talk panel (`talk.js`), and a task bar with the model and account
    pickers and the microphone.
- **The app is one window** with a tab menu (`app.html`: AI Home · Mission Control · Settings, plus closable tabs), in
  the Electron shell, with the floating chat (`chat.html`).
- **What the new pages reuse:**
  - workflows (`brain/workflows.py`: name, instructions, trigger manual/message/schedule, tools, skills, model;
    `workflows.js` `mountWorkflows`);
  - skills (`train.js` `mountTrain`, AI Home's skills list);
  - the Tools page (`tools.js` `mountTools`);
  - AI accounts (statuses, limits and reset times; `accountui.js`).
- **Usage numbers are not documented.** Claude Code's status line gets `rate_limits.five_hour.used_percentage`; the
  stream's `rate_limit_event` is undocumented. AI accounts logs unknown events' keys, so the real shape is known after
  a live run.

## Decisions

1. **One theme for the whole app** (`app/ui/theme.css`, shared by every page):
   - **Colours:** a deep navy background, slightly lighter navy panels with thin blue borders, and neon-blue
     highlights (buttons, selected items, progress bars, desk rims) with a soft glow;
   - **status colours:** green done, blue working, grey waiting, amber needs you, red failed;
   - **type:** a clean sans-serif, with small spaced capitals for labels ("MISSION CONTROL");
   - it applies to the tab bar, AI Home, Mission Control, Settings, the setup page and the floating chat. AI Home,
     Settings and the chat keep their layouts.
2. **Mission Control's layout,** as in the mockup:
   - **Left menu:**
     - the counts ("1 active task · 3 completed");
     - **New Mission ⌘K**;
     - Dashboard, My Missions, Templates, Knowledge, Integrations and History;
     - **Workspaces** with counts, and **New Workspace**;
     - the **Usage** card.
   - **Centre:**
     - the "MISSION CONTROL / Your AI Workforce" heading and its line;
     - the **Flow · List · Calendar** switch;
     - the composer.
   - **Right column:** Mission Progress, Current Task and Recent Activity.
   - **Narrow windows:** the right column folds under the centre first, then the left menu shrinks to icons.
   - **The tab bar** stays AI Browser's own (AI Home · Mission Control · Settings, and closable tabs), restyled. The
     mockup's Search, List and avatar buttons are left out.
3. **The office scene (Flow), drawn live in code:** today's CSS-3D room, rebuilt in the mockup's style.
   - **The room:**
     - a dark navy floor;
     - round desks with neon-blue rims;
     - chibis in hoodies and headphones at laptops;
     - a glowing globe in the centre, which replaces the Brain;
     - a hanging lamp, plants, and a neon "AI OFFICE" sign.
   - **One desk per agent.** A chibi's pose follows its agent: typing while working, waiting, needs you, done or
     failed.
   - **Sub-agents** are smaller chibis at their parent's desk.
   - **Above each desk, a step card:**
     - the agent's current step ("2. Analyze"), its timer, and its badge (Bash, Edit, Write, Read, Web Search, Web
       Fetch, Browser Agent, Sub-agent, Skill);
     - ✓ and the time taken when the step is done;
     - dotted lines link the cards to the globe.
   - **Clicking** a desk or card selects that agent for the right column.
   - **Many agents:** desks arrange in rings around the globe, and the room zooms out. Past 12 agents, the oldest
     finished ones leave the room (they stay in My Missions).
   - **Empty:** a quiet room, and the line "Start a mission below".
4. **The right column:**
   - **Mission Progress**, for the selected agent (or the one working):
     - "3 / 5 steps complete", the bar and the percentage, from its to-do list;
     - under it, your agents as chibi avatars: **Completed**, **In Progress** and **Pending** (waiting in line or
       needing you).
   - **Current Task:** the current step, its timer and its badge, the "Running…" checklist from the to-do list (done ✓,
     current ●, pending ○), and **Stop**, **Chat** and **Hand over**.
   - **Recent Activity:** started, step done, needs you and finished, each with a chibi, a coloured dot and "2m ago".
     **See all** opens History.
   - **An agent without a to-do list** shows its actions as the checklist, all ✓ and ●, with no percentage.
5. **The menu pages:**
   - **My Missions:** every agent as a row (chibi, task, folder, account, current step, time), filtered by All ·
     Working · Needs you · Done. Clicking one opens its drawer.
   - **Templates:** the workflows (Run, Edit, New template), restyled `mountWorkflows`.
   - **Knowledge:** the skills (what each one teaches, Train from a page, Remove).
   - **Integrations:** the Tools page, with each server on or off per account.
   - **History:** finished agents, newest first, with the task, result, time taken, account and the files changed.
     It has search, and **Open** shows the full chat and actions. Resuming comes with Projects.
6. **Workspaces:**
   - named groups of agents and templates, kept in `<home>/workspaces.json` (mode 0600);
   - each shows its counts in the menu, and clicking it filters the Dashboard, My Missions and Templates;
   - **New Workspace**, rename and delete. Deleting removes the grouping only;
   - pick a workspace in the composer, or move an agent from its menu;
   - Projects (project 3) lets a workspace also hold a project folder.
7. **The Usage card:**
   - per account: "Personal · 64% used · resets 9:00 pm", with the ring;
   - when no percentage is known: "Within limits", or "At its limit until …" from AI accounts;
   - clicking it opens Settings → Accounts;
   - the plan's first task records which usage fields the live stream reports (AI accounts' logged event keys). The
     percentage shows only if Claude Code reports one.
8. **The Calendar view:** a month or week grid with the scheduled templates' next runs and the finished agents' run
   times. Clicking one opens it.
9. **The composer:**
   - **Modes:** **Ask AI** (the Brain: it answers and proposes, and nothing runs without a click), **Build a Mission**
     (start an agent), **Use a Template** (pick a workflow, fill in its blank, run it);
   - the box "Describe what you want to accomplish…", with ⌘↵ to start and ⌘K to jump there;
   - **Attach:** images reach the agent as pictures; other files are copied into the agent's folder and named in the
     task. At most 10 files, 20 MB each;
   - **Web ▾:** Web + Brave (the default), Brave only, or No web. That's the agent's web tools: Web Search and Web Fetch
     on or off, Brave's tools on or off;
   - **Model ▾:** "Opus · most capable", "Sonnet · balanced", "Haiku · fastest";
   - **Account ▾:** with each account's limit status;
   - **Folder ▾** and **Workspace ▾;**
   - **🎤:** voice, as today, filling the box;
   - **the button:** Start Mission, Run Template or Ask, by mode;
   - on narrow windows the pickers fold into **⋯ Options**.
10. **What goes:**
    - the particle Brain (`blob.js`, `brainshape.js`) and the old room's look;
    - the Brain's talk moves into **Ask AI** and keeps its cards and numbers.
11. **"Upgrade Plan" is left out:** AI Browser handles no billing.

## Safety

- **Unchanged:**
  - every page sets text with `textContent` only, and the static guard forbids HTML writers;
  - the composer's Ask AI keeps the Brain's rule: nothing runs without the user's Start, Send or a plain yes;
  - Hand over is a click.
- **Attachments:** they go only into the agent's own folder, or the task's chosen folder, under an `attachments/`
  folder, never overwriting. Their names are cleaned.
- **Workspaces and usage add no new right:** every new message is app-only in `MESSAGE_RULES`.

## Testing

- **In throwaway headless Chrome:**
  - the layout at three widths;
  - the scene with 0, 1, 5 and 15 agents;
  - a sub-agent's chibi;
  - the step card and its badge;
  - the to-do checklist and the percentage;
  - Recent Activity;
  - each menu page;
  - workspaces' create, rename, delete and filter;
  - the Usage card with a percentage, without one, and at a limit;
  - the Calendar with scheduled and finished items;
  - each composer mode, with its pickers and attachments.
- **The theme on every page,** and a static check that the old Brain's files are gone.
- **The user's hand check:** compare against the mockup; see a mission run with its checklist and a sub-agent; resize
  the window.

## Review Focus

1. **Long text everywhere** (a 2,000-character task, a 300-character step, a long folder path). Cards clip with an
   ellipsis and a tooltip; nothing breaks the layout.
2. **Many agents at once** (20 or more, with sub-agents). The room stays readable and fast, and finished ones leave
   first.
3. **No usage numbers from Claude Code.** The card says "Within limits" or "At its limit until …", never a made-up
   number.
4. **A workspace deleted while its agents run.** They keep running, ungrouped.
5. **An attachment that's huge, a duplicate name, or a strange name** (`../x`, control characters). It's refused or
   renamed, and never written outside the agent's folder.
