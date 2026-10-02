# ai-browser — Engine design (project 1 of 3)

Date: 2026-10-01 · Status: approved in chat, building MVP

## 1. Goal

A general browser agent where **Claude is the worker** (no LLM API keys). The agent works
in **its own sandboxed browser** (Docker), uses a **catalog of all installed Claude skills**
that it searches and loads selectively, and is driven through a small set of fast tools.

The full system is three projects, built in order:

| # | Project | What it delivers |
|---|---------|------------------|
| 1 | **Engine** (this spec) | Docker sandbox + browser/shell/file/skill tools as an MCP server. Usable from Claude Code. |
| 2 | Skills | Our webdev skills (WordPress block editor, Elementor, website QA, page-from-reference) + local test WordPress. |
| 3 | Dashboard | Local web app: tasks, chat, live view, Allow/Deny, skills page. Worker = headless Claude Code in `--restricted` mode with `--disable-slash-commands`, `--strict-mcp-config`. |

Projects 2 and 3 get their own specs. This spec only fixes the interfaces they depend on.

## 2. Decisions (from the brainstorm)

- **Brain:** Claude (this Claude Code chat now; a locked-down background Claude Code worker in project 3). No API keys.
- **Sandbox:** one Docker container per login profile, running Chromium + a shell. It never sees the user's files, Chrome, or Claude login.
- **Logins:** the user logs in through the live view; sessions persist in a named profile volume. The agent never types passwords.
- **Skills:** nothing auto-loads. The agent calls `find_skills` / `load_skill`; the user can block skills (`~/.ai-browser/config.json`). Skill scripts run inside the sandbox.
- **Page model:** jev-ultrafast style — a numbered table of visible controls; actions target numbers; every action re-checks its target first.
- **Speed first:** batch steps, return diffs, one CDP call per read, event-based waits, screenshots only on demand. Budgets in §7.
- **Safety:** risky controls are marked ⚠ and need `confirmed=true`; page text is data, not instructions; everything is logged.

## 3. Architecture

```
Claude Code ──MCP (stdio)──▶ ai-browser engine (Python, on the Mac)
                               ├─ sandbox.py  docker run/exec/stop, profiles, ports
                               ├─ cdp.py      one websocket to Chromium, sessions, events
                               ├─ browser.py  tabs, open, observe, act, screenshot, logs
                               ├─ reader.js   in-page reader: table, guards, hit-tests
                               ├─ skills.py   catalog of installed Claude skills
                               ├─ live.py     live view (screencast + input) on 127.0.0.1
                               └─ tasklog.py  per-session log.jsonl + screenshots
                                     │ CDP (127.0.0.1:<random port>)
                               Docker "aib-<profile>"
                                 Chromium (headless, 1440×900) · bash, python3, node, curl
                                 /profile  ← volume aib-profile-<profile> (logins)
                                 /work     ← ~/.ai-browser/sandboxes/<profile>/work (rw)
                                 /skills   ← skill sources (read-only)
```

### 3.1 Sandbox (`docker/Dockerfile`, `sandbox.py`)

- Image `ai-browser-sandbox:0.1`: Debian bookworm-slim, `chromium`, fonts (Noto incl. CJK
  + emoji), `python3`, `nodejs`, `curl`, `jq`, `socat`, `tini`. Non-root user `agent` (uid 1000).
- Chromium listens on 127.0.0.1:9222 inside the container; `socat` exposes it on 9223,
  published to the host as `127.0.0.1::9223` (random host port read via `docker port`).
- Flags: `--headless=new --user-data-dir=/profile --window-size=1440,900 --no-first-run
  --no-default-browser-check --disable-extensions --disable-background-timer-throttling
  --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --mute-audio
  --password-store=basic`.
- Container flags: `--shm-size=1g --memory=2g --cpus=2 --cap-drop=ALL
  --security-opt=no-new-privileges --init`. Chromium's own sandbox needs kernel features
  the default Docker profile blocks, so the MVP runs Chromium with `--no-sandbox` and the
  container is the isolation boundary (known limitation; a seccomp profile can lift it later).
- Lifecycle: `start(profile)` reuses a running `aib-<profile>` container (warm start) or
  creates it; `fresh=True` uses a throwaway container `aib-fresh-<id>` with a tmpfs profile,
  removed on stop. `stop(profile)`; health check via `GET /json/version`.
- Each MCP session gets a task id; its working dir is `/work/<task-id>` (downloads go to
  `/work/<task-id>/downloads`).

### 3.2 CDP client (`cdp.py`)

Async websocket client (`websockets`): `send(method, params, session_id, timeout)`,
event subscription, one background reader task, auto-reconnect on drop. Flattened
sessions (`Target.attachToTarget flatten=true`).

### 3.3 Browser (`browser.py`)

- Owns the tabs it creates. On attach: enable `Page`, `Runtime`, `Network`, `Log`,
  lifecycle events, focus emulation; register `reader.js` with
  `Page.addScriptToEvaluateOnNewDocument` (reader preloaded → one small call per read).
- Buffers console errors/warnings, uncaught exceptions, failed requests and HTTP ≥ 400
  per tab for `page_log`.
- `open`: navigate → wait for `DOMContentLoaded` (cap 15 s) → settle → if no controls
  yet, wait for network idle (cap 3 s) → observe.
- Settle after input: two animation frames or 50 ms; editable comboboxes wait for
  visible options, cap 200 ms. URL/document change → wait for `DOMContentLoaded`.

### 3.4 Reader (`reader.js`)

Based on jev-ultrafast `snapshot.js` (MIT), extended:

- **Stable ids:** each element gets `e<n>` from a per-document WeakMap counter, kept for
  the element's lifetime (enables diffs). New document → new numbering.
- **Scope:** top document + same-origin iframes (recursive, coordinates offset, rows tagged
  `[frame-label]`) + open shadow roots. Cross-origin frames: listed as a frame row in MVP
  (OOPIF sessions are a later step).
- **Rows:** id, role, accessible name, value, states (checked/expanded/selected/disabled),
  frame tag, href for links, options for native selects (≤ 8 shown), `upload` role for file
  inputs, `editable` for contenteditable. Password fields: listed, value never shown.
- **Default view:** controls inside the viewport + counts of controls above/below + up to
  1,500 chars of visible text. `find="text"` searches the whole document instead.
- **Risky (⚠):** button/link/menuitem/submit whose name matches the risky word list
  (publish, update, delete, remove, trash, submit, send, pay, buy, purchase, order,
  checkout, confirm, sign up, register, subscribe, post, share, invite, transfer,
  unpublish, schedule, deactivate). List lives in config and is user-editable.
- **Guards & targeting:** `target(id)` re-resolves the live node, checks connected,
  visible, enabled, unchanged signature, scrolls into view if needed, recomputes the
  center point and hit-tests it (through same-origin frames). Returns `{x, y}` or a reason.

### 3.5 Skills catalog (`skills.py`)

Sources (namespace → host root → sandbox mount):

| Namespace | Host source | Sandbox path |
|-----------|-------------|--------------|
| `personal` | `~/.claude/skills/*/SKILL.md` | `/skills/personal` |
| `<plugin>` (ecc, superpowers, vercel, …) | `installPath` of each enabled plugin in `~/.claude/plugins/installed_plugins.json` → `skills/*/SKILL.md` | `/skills/plugins/<plugin>` |
| `anthropic-skills` | newest `~/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/*/*/skills` | `/skills/claude-ai` |
| `ai-browser` | `<project>/skills/*/SKILL.md` | `/skills/ai-browser` |

- Frontmatter parsed with PyYAML; name defaults to folder name; ~440 skills today.
- `find_skills(query)`: keyword score (name ×3, description ×1), top 10 with one-line
  descriptions and a `scripts` flag. Empty query → compact list of all names by namespace.
- `load_skill(name)`: SKILL.md body with a header giving its sandbox folder and file list;
  `${CLAUDE_PLUGIN_ROOT}` rewritten to the sandbox plugin root. Logged.
- `read_skill_file(name, path)`: text file inside that skill folder (no `..`, size-capped).
- Blocked skills (config) never appear in results and cannot be loaded.

### 3.6 Live view (`live.py`, `static/live.html`)

Starlette app on `127.0.0.1:8770` (next free port if taken), URL carries a random token.
`/live` page + `/live/ws` websocket: streams `Page.startScreencast` JPEG frames of the
current tab (only while a viewer is connected) and forwards mouse, wheel, key and text
input to `Input.*`. Viewer input is never logged.

### 3.7 Logging (`tasklog.py`)

`~/.ai-browser/tasks/<task-id>/log.jsonl`: one line per tool call (tool, args, ms,
outcome, short result). Screenshots saved to `shots/`. Text typed into fields is logged
(passwords are never typed by the agent).

## 4. Tools (MCP)

Every result ends with a timing line (`⏱ 84 ms`). Browser tools auto-start the `default`
sandbox if none is running.

| Tool | Purpose |
|------|---------|
| `sandbox_start(profile="default", fresh=false)` | Start/reuse sandbox; returns live-view URL. |
| `sandbox_stop()` · `sandbox_status()` | Stop / report sandbox, tabs, live URL. |
| `open(url, new_tab=false)` | Navigate and return the page table. |
| `observe(find=None)` | Page table (viewport) or whole-page search. |
| `act(steps, confirmed=false)` | Run steps in order; stop at first failure; return diff or table. |
| `screenshot(size="desktop", full_page=false, element=None)` | JPEG, ≤1280 px wide; `size="all"` → desktop 1440×900, tablet 768×1024, mobile 390×844. |
| `tabs(action="list", tab=None)` | list / switch / close / new. |
| `page_log()` | Console errors, exceptions, failed requests since last call. |
| `extract(kind)` | `links`, `tables` (CSV files in work dir), `meta` (title, description, headings, canonical, OG, images without alt). |
| `js(code)` | Run JS in the page (escape hatch), JSON result, logged. |
| `shell(command, timeout=60)` | Bash in the sandbox, cwd = task dir; output capped at 10 KB (full copy saved). |
| `read_file(path)` · `write_file(path, content)` | Files under `/work` only. |
| `find_skills(query="")` · `load_skill(name)` · `read_skill_file(name, path)` | Skill catalog. |

### 4.1 `act` step grammar

```
click e5 | dblclick e5 | hover e5
type e4 "text"        (replace content)   | append e4 "text" | type "text" (focused element)
key Enter | key Meta+A | key Shift+Tab
select e9 "Large"     (option label or value)
check e8 | uncheck e8
drag e7 e12
upload e5 file.png    (path relative to task dir, or /work/...)
scroll down|up [px] | scroll top|bottom | scroll e40
wait 500 | wait "Saved"   (text, max 10 s)
goto https://… | back | forward | reload
```

- Typing inserts the whole string at once (`Input.insertText`); `key` sends real key events.
- Replace = select only the target element's own content (not page-wide select-all), then insert.
- Drag uses CDP drag interception (`Input.setInterceptDrags` + `Input.dispatchDragEvent`)
  for HTML5 drag-and-drop, and falls back to pressed/moved/released mouse events.
- Upload uses `DOM.setFileInputFiles` with the sandbox path.
- Risky target (⚠) without `confirmed=true` → step is `blocked`, nothing executes.
- Result per step: `ok | stale | blocked | error` + ms. After the batch: if the document is
  unchanged, a **diff** (`+` added, `-` removed, `~` changed rows); otherwise the full table.

## 5. Output format (observe)

```
page  "Edit Page ‹ Acme — WordPress"  https://acme.com/wp-admin/post.php?post=12
view  1440×900 · y 0/2300 · 4 above · 38 below · frames: [canvas]
e1   button   "Toggle block inserter"
e3   button   "Publish" ⚠
e4   textbox  [canvas] "Add title" = "About us"
e9   select   "Size" = "Medium" (Small|Medium|Large)
e12  link     "Privacy" → /privacy/
text: About us — Our story …
⏱ 61 ms
```

## 6. Error handling

- Tools never raise into the session: they return `error: <plain English>` plus the
  current page summary when useful.
- Stale/covered targets → `stale` + fresh table; no retry of mutations.
- Dead container → restarted with the same profile on next call, reported in the result.
- CDP disconnect → reconnect once, then report.
- Shell timeout (default 60 s) → process killed, partial output returned.
- JS exceptions → returned as `error` with the message.

## 7. Speed rules and budgets

Rules: steps batch in one `act`; `open`/`act` return the page so no extra `observe`;
diffs after same-document actions; reader preloaded, one `Runtime.evaluate` per read;
event-based waits; whole-string typing; warm sandbox reuse; screenshots never automatic,
JPEG q70, viewport-only and ≤1280 px wide by default; screencast only while watched.

Budgets (median on local fixture pages, measured by `ai-browser bench`):

| Operation | Budget |
|-----------|--------|
| `observe` | < 100 ms (< 300 ms heavy editor page) |
| one click/type step incl. guards + settle | < 150 ms |
| `open` local page | < 500 ms |
| viewport screenshot | < 300 ms |
| observe output | < ~2,500 tokens (~10 KB) by default |

## 8. Testing

- **Unit (no Docker):** step parser, risky matcher, table/diff rendering, skills catalog
  (temp-dir fixtures), work-path sandboxing.
- **Integration (Docker, `-m docker`):** fixture pages served inside the sandbox
  (`python3 -m http.server` on two ports for cross-origin): form, login, frames, shadow DOM,
  drag-and-drop, upload, covered button, risky buttons, long page, delayed SPA content,
  autocomplete. Covers every step type, stale/covered/blocked paths, screenshots,
  `page_log`, shell/files, skills load + run a script.
- **MCP end-to-end:** stdio client lists tools and runs open → act → screenshot.
- **Benchmark:** `ai-browser bench` reports medians against §7.
- `ai-browser doctor`: Docker up, image present, sandbox starts, CDP answers, read +
  screenshot work, skill counts.

## 9. MVP acceptance (run from Claude Code)

1. Collect data from a public site into a CSV in the work dir.
2. Fill a form; `act` blocks the ⚠ Submit until confirmed.
3. Drag, upload and act inside a same-origin frame on fixture pages.
4. Hand a login to the user through the live view.
5. `find_skills` → `load_skill` → run one of the skill's scripts via `shell`.
6. Benchmark medians within §7 budgets.

## 10. Out of scope for the engine MVP

Dashboard, task queue, background worker, approvals UI (project 3); our webdev skills and
WordPress test site (project 2); cross-origin frame contents (OOPIF sessions); headful mode;
Chromium seccomp sandbox; parallel sandboxes per profile; attaching to the user's own Chrome.
