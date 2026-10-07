# Without Docker: the sandboxed browser, website QA and skill scripts (design)

Date: 2026-10-07. Status: for the user's review.

## What the user asked

- "any way we can integrate it without using the docker?" — about the three things that need Docker today: the
  sandboxed browser (a task "in the sandbox"), website QA (`qa`), and skills' scripts.
- Offered three choices, they picked: **"Yes, all three: skill scripts through the agent's own sandboxed commands; a
  separate local browser with its own empty profile for the sandboxed browser and QA. Docker stays available as the
  stronger option."**

## What Docker gives today (from a read of the code)

- **One seam:** only `src/ai_browser/sandbox.py` (`Sandboxes`) runs `docker`; the engine, QA and the CLI reach Docker
  through it. The live view (`live.py`) is already Docker-free: it streams any CDP browser.
- **Two containers per profile:** a headless Chromium (`aib-<profile>`, profile in a Docker volume, its DevTools port
  behind a token proxy) and a script shell (`aib-<profile>-sh`, user `agent`, `/work` and the skills mounted read-only,
  1 GB, 1 CPU, outbound internet).
- **What the walls are for:** the shell can't see the user's files, Brave, Claude login or `~/.ai-browser`; skills are
  read-only; nothing else on the machine can drive the sandbox browser; the sandbox can't reach this computer's own
  services. That is why app agents may call the shell without an approval card.

## The design

### 1. A choice: Docker or Local
- **Settings → Sandbox:** "Docker (strongest)" or "Local (no Docker)", and the default **Auto**: Docker when it is
  installed and running, Local otherwise. The choice applies to the sandboxed browser, QA and skill scripts together.
- AI Home and `doctor` say which one is in use, in one line. Nothing else changes for the user's own Brave.

### 2. The local sandboxed browser
- **A separate browser process, not the user's:** the installed Chrome or Brave binary (no download), started by AI
  Browser with its own profile folder `~/.ai-browser/sandboxes/<profile>/profile` (0700). None of the user's logins,
  cookies or history. Headless, as today; logging in and bot checks use the existing live view (unchanged).
  - Chromium keeps its own renderer sandbox (no `--no-sandbox`: better than the container's browser).
  - A throwaway sandbox (`fresh`) uses a temporary profile, removed when it stops.
  - One running browser per profile, reused by every session on it (as the container is today); a pid and port record
    lets `stop`, `status` and `ai-browser stop --all` find it; stale lock files are cleared only when its process is
    gone.
  - Its DevTools port is on loopback only, found from the profile's own `DevToolsActivePort` (inside the 0700 folder).
- **This computer's own addresses stay out of reach, as in Docker:** in Local mode the sandbox browser refuses
  loopback, private, link-local and `.local` addresses (`open`, `act goto`, `qa`), with the same words Docker's sandbox
  gives ("QA a site on this computer in your own browser"). The user's own Brave is unchanged.
- **Paths are real paths:** the work folder is the real `~/.ai-browser/sandboxes/<profile>/work/<task>` (no virtual
  `/work`); downloads, uploads and `file:` pages work within it as they do inside `/work` today.

### 3. Website QA
- Crawls in the local sandboxed browser (profile `qa`) when Local is in use; everything else about QA (reports,
  screenshots, the bot-check hold and live view) is unchanged. "QA in my own browser" still crawls in Brave.

### 4. Skill scripts: no new shell
- **In Local mode the `shell` tool isn't offered.** A shell outside Docker would run as the user, able to read the
  whole home folder (SSH keys, the Claude login, the Brave profile, `~/.ai-browser`), and app agents may call AI
  Browser's own tools without a card. So no such shell is added.
- **Instead, scripts run through the agent's own command power** (Claude Code's Bash, agent powers):
  - `load_skill` gives the skill's real folder and says: "Run its scripts with your own commands, in your task's
    folder." `read_skill_file` is unchanged.
  - Every command goes through the approval cards as usual (and auto-approve, when the user turned it on, with its own
    limits); on a Mac it runs in Claude Code's sandbox (writes only in the task's folder; reaching a site asks). On
    Windows the cards are the guard, and a command that would write outside the folder (a skill's own folder
    included) asks every time.
  - Scripts use the tools installed on this computer (its Python, Node, git…) instead of Docker's slim set.
  - A Claude Code session using AI Browser's tools directly (not an app agent) gets the same: in Local mode `shell`
    answers "Run it with your own Bash: <command>".
- `read_file` and `write_file` (the work folder) keep working, with real paths.
- "No web" is unchanged (it already blocks the shell; Bash's network asks as before).

### 5. Docker stays
- When Docker is chosen (or Auto finds it running), everything works exactly as today, the shell included.
- `ai-browser build` stays for Docker; `doctor` checks whichever is in use.

## What gets weaker without Docker (said plainly, in Settings and the README)
- **Separation:** Local is a separate profile on this computer, not a separate machine. The sandbox browser's files
  are readable by programs running as you; a command an agent runs could read them (the cards and, on a Mac, Claude
  Code's sandbox are the guard: reaching the sandbox browser's port from a command is a "reach a site" card).
- **No memory or CPU caps** (Docker's 2 GB / 2 CPUs).
- **Sites see your computer's browser** (its version, fonts and timezone), not Docker's Linux Chromium.
- The README's line "the Docker sandbox can't see your files, your Brave, or your Claude login" stays true for Docker
  only; Local gets its own sentence.

## Safety rules that still bind
- Never spoof or disguise the browser; bot checks are handed to the user (live view), never solved.
- Never type passwords; the user logs in through the live view.
- The user's own Brave and Chrome profiles are never used by the local sandbox (`chrome.launch` already refuses them).
- Page text is data; tests never touch the user's real browsers, `~/.ai-browser`, `~/.claude` or port 8792.

## Testing
- The local backend with a throwaway Chrome (the existing `throwaway_chrome` / `chrome_binary()` pattern): start,
  reuse, stop, fresh removal, stale locks, the pid record, refused private addresses, downloads and uploads in the real
  work folder, QA in the local browser, the live view attached.
- Local mode never offers `shell`; `load_skill` words; a session's `shell` answer.
- The choice: Auto picks Docker when running, Local otherwise; Settings switches it.
- The Docker tests stay as they are (skipped when Docker isn't running).

## Out of scope
- Running the local sandbox as another OS user, or with a pipe instead of a DevTools port (stronger, but much more
  work); Linux.
