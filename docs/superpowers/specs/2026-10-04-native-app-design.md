# AI Browser as a native app, with no extension

Date: 2026-10-04.

## Status

The user approved the design's three sections in chat: "yes proceed", "yeah" and "yes". This spec writes them down. The
user reviews it before the plans are written.

**The user's request**, verbatim: "then in app I want it built in, no need to install the extensions it is such a
hassle find a way to build it natively we can switch to standalone app if necessary".

**Their answers:**
- **The direction:** "Keep Brave, app does it all (Recommended)". Brave stays their browser, with their sign-ins, and
  nothing is installed in it.
- **The chat beside their pages:** "Floating window beside Brave (Recommended)".
- **Their inboxes:** "Open tabs, after one OK (Recommended)".
- **How to build it:** "Electron (Recommended)".
- **Earlier, the same day:** one window with a tab menu instead of popups ("Yes, build it next"). That's built and under
  review.

**What this replaces:**
- wave C (`browser-profile-choice`): its profile choice folds into Decision 6;
- wave D (`side-chat`): its chat becomes the floating chat window.

Their specs and plans stay in `docs/` as history.

**What it builds on:**
- wave B: the pages over http, the one-time code and cookie, and the strict headers;
- the tab menu;
- the relay, with allow-once: one connection to Brave, asked once;
- watcher safety's rights table;
- browser detection: profiles by name and colour;
- AI accounts, which is built before this.

## Facts this rests on

- **The user's machines:**
  - **the Mac:** macOS 26.5 on arm64, with Node.js 26.7, npm 11.19 and Homebrew;
  - **the Windows laptop:** unknown, and assumed to have no Node.js.
- **The extension today** (the watcher, version 0.2.0) does these jobs:
  - reads Gmail, Slack and Asana for the Brain, and fills reply drafts;
  - groups the AI's tabs (`tabGroups`);
  - shows notifications;
  - the `ai` keyword in the address bar;
  - the Brain page;
  - tells the app which Brave profile is the user's;
  - the Brain's "Pick the part to watch" picker, and checking watched parts of pages.
- **Electron** is Chromium, the same engine AI Browser's pages run on today. Its official builds come as zips with a
  `SHASUMS256.txt`. It provides always-on-top windows, global shortcuts, a menu-bar (tray) icon, native notifications,
  permission handlers, and guards on navigation and new windows.
- **The page you're on:**
  - **On macOS,** Brave answers AppleScript: `tell application "Brave Browser" to get {URL, title} of active tab of front
    window`. macOS asks the user once whether the asking app may control Brave.
  - **On Windows,** UI Automation can read the active tab's title and address from Brave's window.
- **Through the relay's one connection,** the app can attach to a tab and run a script in an isolated world
  (`Page.createIsolatedWorld`), where the page's own scripts can't see or change it. `Input.insertText` types into the
  focused field.
- **Tab placement isn't certain.** `Target.createTarget` with `newWindow` opens a tab in a new window. Whether later
  tabs can be placed in that same window is checked by a probe in part b.

## Decisions

1. **AI Browser is an Electron app over the Python engine.**
   - **Starting it:** `uv run ai-browser app` starts the engine as today (the server, the one Brave connection, agents,
     the Brain), then the Electron app, named "AI Browser", with its own Dock icon and a menu-bar icon. The menu-bar icon
     offers **Open AI Browser**, **Show chat** and **Quit**.
   - **The main window** is the tab menu (AI Home · Mission Control · Settings), with a title bar only. Its pages come
     from `http://127.0.0.1:<port>`, entered with wave B's one-time code and cookie.
   - **Closing and quitting:**
     - closing the main window hides it, and the app keeps running in the menu bar, so ⌥Space still works and agents
       keep working;
     - **Quit** (the menu-bar icon or ⌘Q) stops the app and its agents;
     - this changes today's rule, where closing the window stops everything.
   - **Before Electron is set up**, `ai-browser app` opens the Chrome app window as it does today, and AI Home offers the
     setup. The floating chat, the shortcut, the menu-bar icon and native notifications need Electron.
2. **Setting it up:**
   - `ai-browser doctor --setup` shows what it will download (the pinned Electron version, its size and its address)
     and asks first;
   - the download is checked against Electron's `SHASUMS256.txt`, and a mismatch keeps nothing;
   - it builds "AI Browser.app" (on Windows, an "AI Browser" folder) in `~/.ai-browser/desktop/`, with AI Browser's name
     and icon. On the Mac the app is signed locally (ad hoc), so macOS remembers its microphone and Brave permissions;
   - **running it needs no Node.js.** AI Browser's Electron code is plain JavaScript in the repo, with no npm packages at
     run time;
   - a double-click start (Electron starting the engine itself) comes later.
3. **Electron is locked down:**
   - `contextIsolation` and `sandbox` are on, `nodeIntegration` is off, and `webSecurity` is on;
   - windows load only `http://127.0.0.1:<port>` pages of AI Browser. Any other navigation is blocked, and no window can
     open another: a website link goes to Brave through the engine's existing `open_url`;
   - **the preload exposes a few named actions only:** show or hide the chat, notify, set the shortcut, and ask for the
     page you're on;
   - **permissions:** the microphone is allowed for AI Browser's own origin only, and everything else is denied;
   - **no debugging port** and no DevTools in the product. Tests drive Electron through a test-only switch, and a static
     guard proves the product never passes it.
4. **The floating chat:**
   - a small window that stays on top beside Brave, remembers its place and size, and can be resized;
   - **⌥Space** shows or hides it from anywhere. It can be changed in Settings, and a shortcut another app holds is
     reported there, never silently failed;
   - it loads a new page, `/chat`, with the Brain's talk, **New task**, and messages to an open agent (brain
     delegation's numbers and cards). The Brain only proposes, as everywhere;
   - **"This page"** shows the Brave tab you're on, found as Facts says (AppleScript on the Mac, UI Automation on
     Windows) while the chat is showing. It is matched to the relay's tab list by address and title. With no single
     match, or no answer, the chat shows a picker of your tabs;
   - **reading pages:** the chat reads a page's text only when you ask about that page in the chat, never in the
     background. An agent acts in your tab only after **Hand over**, as today;
   - **New task** replaces typing `ai` in Brave's address bar.
5. **The inboxes:**
   - Settings → Brain → **Read my Gmail, Slack and Asana tabs**, off until the user turns it on;
   - while it is on, the engine reads those tabs when they're open in Brave, through the relay's one connection;
   - the extension's readers move into the engine. They run in an isolated world in each of those tabs, and page text
     stays data;
   - a draft goes into the reply box only on the user's **Use draft** click, and AI Browser never clicks Send;
   - turning the switch off stops reading at once, and a read under way keeps nothing;
   - **the Brain's Watch** moves the same way:
     - **Pick the part to watch** runs the extension's picker in the user's tab, in an isolated world, only when they
       click it. The picker outlines the element under the mouse; a click picks it, and Escape cancels;
     - the Brain checks watched parts only in tabs that are open, as the extension did.
6. **Your Brave profile:**
   - Settings → **Where agents browse** lists the profiles browser detection found, by name and colour, never an email;
     the user picks one;
   - agents work in that profile;
   - AI Home lists its tabs, and counts tabs in other profiles without listing them (watcher safety's scope, now
     chosen rather than told).
7. **The AI's tabs:**
   - agents' tabs open in one Brave window of their own and never mix into the user's windows;
   - if the probe in part b shows Chromium can't place later tabs in that window, each agent's first tab opens a window
     for that agent instead (a ruling, with the cost said);
   - AI Home and Mission Control show which agent owns each tab.
8. **Notifications:**
   - Electron shows native notifications for a bot check, an agent waiting for the user, and the Brain's notes;
   - they say what needs the user ("An agent is waiting for you", "A bot check on example.com"), never message bodies
     or page text;
   - clicking one opens the right place: AI Home's row, or the agent's tab in Brave.
9. **What retires:**
   - **Chrome's app mode** (wave B's `AppWindow`, and the "window's browser" setting) retires once Electron is set up,
     and stays only as the fallback in Decision 1;
   - **the watcher extension** retires: its folder, the watcher's role in the rights table, the `ai` keyword and the
     Brain page;
   - AI Home tells the user that they can remove "AI Browser watcher" from `brave://extensions`. AI Browser never removes
     anything itself;
   - bot checks, Hand over and Take back, and Brave's one question are unchanged.

## Safety

- **No debugging** in Electron, and its pages are limited to AI Browser's own origin. The preload's few actions are the
  only bridge to the computer.
- **Downloads only with the user's OK:** Electron's download is checksum-verified, and nothing else is downloaded.
- **Inbox reading only after the switch.** It runs in an isolated world, page text is data, drafts go in on a click
  only, and nothing is ever sent.
- **The current page is read only when the user asks** about it in the chat. Agents act in a tab only after Hand over.
- **AppleScript and UI Automation only read** the active tab's address and title. They never type, click or open
  anything.
- **Notifications carry no message or page text.**
- **No passwords, no API keys**, and never `--bare`, as everywhere.

## Parts

Each part gets its own plan, a test-first build, a fresh review and a merge, in this order:
- **a. The Electron shell:**
  - the setup download;
  - the app itself: its name, icon, Dock and menu-bar icon, the main window with the tab menu, and closing versus Quit;
  - the locked-down windows, the shortcut and notifications;
  - Chrome's app mode as the fallback.
- **b. The extension's jobs:**
  - the inbox switch and readers through the relay;
  - Where agents browse;
  - the AI tabs window, with its probe;
  - the extension retires.
- **c. The floating chat:**
  - `/chat`;
  - the always-on-top window and ⌥Space;
  - "This page", through AppleScript, UI Automation or the picker;
  - reading a page only when asked.

## Testing

- **Electron:** driven in throwaway runs through a test-only switch (never in the product), with throwaway profiles. A
  static guard proves the product's command line and code never enable debugging.
- **The readers:** run through the relay against fake Gmail, Slack and Asana pages (`testpages`) in throwaway browsers.
- **AppleScript and UI Automation:** behind a small interface with fakes in the tests, and the exact command checked
  per platform.
- **The user's hand checks,** on the Mac and on Windows:
  - the app's look, Dock and menu bar;
  - ⌥Space anywhere;
  - the floating chat following the tab;
  - the inbox switch;
  - notifications;
  - Quit versus closing.

## Review Focus

1. **⌥Space already taken** by another app (Raycast, Alfred, a keyboard tool). Settings says so and offers another
   shortcut. Nothing crashes, and nothing silently doesn't work.
2. **Brave not running, or not connected, when the chat looks for "this page".** The chat says so, and nothing makes
   Brave ask a new question.
3. **The inbox switch turned off during a read.** Reading stops at once, and nothing from that read is kept.
4. **A website link inside an Electron page** (an agent's chat, a draft). It opens in Brave, never inside Electron.
5. **The Electron download interrupted, or not matching its checksum.** Nothing is kept, the Chrome app window still
   works, and Settings says what happened.
