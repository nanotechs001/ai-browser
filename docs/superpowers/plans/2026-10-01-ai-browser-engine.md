# ai-browser Engine MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Docker-sandboxed browser + shell + skill-catalog toolset, exposed as an MCP server, that Claude drives through fast, guarded, numbered-element actions.

**Architecture:** Python engine on the Mac talks to a per-profile Docker container (Chromium + bash) over one CDP websocket. An in-page reader (`reader.js`, derived from jev-ultrafast) produces a compact numbered table and re-validates targets before every input. A skills catalog scans all installed Claude skills and serves them on demand; skill scripts run inside the sandbox.

**Tech Stack:** Python ≥3.12, uv, `mcp` (FastMCP, stdio), `websockets`, `pyyaml`, Starlette + uvicorn (live view), pytest; Docker (Debian bookworm, Chromium).

**Spec:** `docs/superpowers/specs/2026-10-01-ai-browser-engine-design.md`

**Note on code in this plan:** to avoid writing the codebase twice, this plan fixes every file, interface, behavior, and test case precisely; the implementation code is written directly into the files in each task's "implement" step, against those tests.

## Global Constraints

- Python `>=3.12`; packaging and runs via `uv`; package `ai_browser` in `src/`; console script `ai-browser`.
- Home dir: `AIB_HOME` env var, default `~/.ai-browser` (config `config.json`, `tasks/`, `sandboxes/<profile>/work/`).
- Image tag `ai-browser-sandbox:0.1`; container name `aib-<profile>` (`aib-fresh-<id>` for fresh); profile volume `aib-profile-<profile>`; profile names match `^[a-z0-9][a-z0-9-]{0,30}$`.
- CDP inside container on 127.0.0.1:9222, socat on 9223, published `127.0.0.1::9223`. Live view on 127.0.0.1, port 8770 (next free up to 8790), random token.
- Container flags: `--shm-size=1g --memory=2g --cpus=2 --cap-drop=ALL --security-opt=no-new-privileges --init`; Chromium `--no-sandbox` (documented limitation).
- Viewports: desktop 1440×900, tablet 768×1024 (mobile=true), mobile 390×844 (mobile=true). Screenshots JPEG q70, ≤1280 px wide, full page capped at 10,000 px tall.
- Caps: observe ≤150 rows and ≤1,500 chars visible text (~10 KB output); shell output 10,000 chars (full copy saved); read_file 50,000 chars; js result 10,000 chars; select options shown ≤8; names ≤80 chars.
- Settle: 2 animation frames or 50 ms; editable combobox: visible `[role=option]` or 200 ms; `open` DOMContentLoaded cap 15 s, network-idle fallback cap 3 s; `wait "text"` cap 10 s; sandbox ready cap 20 s.
- Risky words (default, user-editable in config): publish, update, delete, remove, trash, submit, send, pay, buy, purchase, order, checkout, confirm, sign up, register, subscribe, post, share, invite, transfer, unpublish, schedule, deactivate. Match: case-insensitive, whole word.
- Budgets (medians, `ai-browser bench`): observe <100 ms (heavy page <300 ms); click/type step <150 ms; open local page <500 ms; viewport screenshot <300 ms.
- Everything binds to 127.0.0.1. No telemetry. Viewer (live view) input is never logged.

## Review Focus

1. **Docker not running / image not built** → every tool returns a one-line fix ("Start Docker Desktop" / "Run `ai-browser build`"), never a traceback. Test: Task 10 `test_docker_unavailable_message`.
2. **A step navigates mid-batch** (click a link, then `type e4 …`) → remaining id-targeted steps are skipped with "page changed", full table returned, nothing typed into the new page. Test: Task 8 `test_navigation_mid_batch_skips_id_steps`.
3. **Huge pages** (thousands of controls) → output stays within caps with "N more" hints and `observe` stays <300 ms. Test: Task 7 `test_heavy_page_capped_and_fast`.
4. **Non-ASCII text** ("Zürich – 東京 😀") → typed exactly and rendered back exactly. Test: Task 8 `test_type_unicode_roundtrip`.
5. **Two Claude sessions on one profile** → both reuse the same container, each gets its own tab, stopping one session's tab handling doesn't break the other. Test: Task 10 `test_two_engines_share_container`.

---

## File Structure

```
pyproject.toml                 deps, script entry, pytest markers
README.md                      setup + usage
.mcp.json                      project-scoped MCP registration (Task 14)
docker/Dockerfile              sandbox image
docker/entrypoint.sh           socat + chromium launcher
src/ai_browser/__init__.py
src/ai_browser/config.py       constants, paths, Config load
src/ai_browser/steps.py        act step grammar → Step
src/ai_browser/render.py       page table + diff rendering, risky matcher
src/ai_browser/skills.py       skill catalog
src/ai_browser/workfs.py       /work path mapping + file read/write
src/ai_browser/tasklog.py      task id, log.jsonl, screenshots
src/ai_browser/sandbox.py      docker lifecycle + exec
src/ai_browser/cdp.py          async CDP client
src/ai_browser/reader.js       in-page reader/guards/helpers
src/ai_browser/browser.py      tabs, open, observe, act, screenshot, logs, extract, js
src/ai_browser/keys.py         key-combo → CDP key event params
src/ai_browser/engine.py       tool facade: lazy sandbox, timing, errors, logging
src/ai_browser/live.py         live view server
src/ai_browser/static/live.html
src/ai_browser/server.py       MCP tool definitions
src/ai_browser/cli.py          mcp | build | doctor | bench | live | stop
tests/conftest.py              markers, docker fixtures, fixture web server
tests/fixtures/*.html          local test pages
tests/test_*.py                unit + docker tests
```

---

### Task 0: Scaffold + config

**Files:** Create `pyproject.toml`, `src/ai_browser/__init__.py`, `src/ai_browser/config.py`, `tests/conftest.py`, `tests/test_config.py`, `.gitignore`.

**Interfaces — Produces:**
- `config.home() -> Path` (reads `AIB_HOME`, expands `~`), `config.IMAGE: str`, `config.SIZES: dict[str, tuple[int,int,bool]]`, `config.RISKY_WORDS: list[str]`, cap constants (`MAX_ROWS=150`, `TEXT_LIMIT=1500`, `SHELL_LIMIT=10_000`, `READ_LIMIT=50_000`, `JS_LIMIT=10_000`).
- `@dataclass Config(blocked_skills: list[str], risky_words: list[str])`; `load_config(home: Path) -> Config` (missing/invalid file → defaults; unknown keys ignored).
- `project_root() -> Path` (repo root, for `docker/` and `skills/`).
- pytest marker `docker` (tests skipped unless Docker reachable and image present; `--docker` not required).

- [ ] Write `tests/test_config.py`: `test_home_env_override` (monkeypatch `AIB_HOME` → `home()` equals it), `test_load_config_defaults_when_missing`, `test_load_config_reads_blocked_and_risky`, `test_load_config_invalid_json_falls_back`.
- [ ] Run `uv run pytest tests/test_config.py -v` → FAIL (module missing).
- [ ] Implement `pyproject.toml` (deps: `mcp>=2,<3`, `websockets>=15`, `pyyaml>=6`, `starlette`, `uvicorn`; dev: `pytest`, `pytest-asyncio`; script `ai-browser = "ai_browser.cli:main"`; `asyncio_mode = "auto"`), `config.py`, `conftest.py` (marker + auto-skip logic).
- [ ] Run → PASS. Checkpoint.

### Task 1: Step grammar

**Files:** Create `src/ai_browser/steps.py`, `tests/test_steps.py`.

**Interfaces — Produces:**
```python
@dataclass(frozen=True)
class Step:
    op: str; target: str | None = None; target2: str | None = None
    value: str | None = None; amount: int | None = None; raw: str = ""
class StepError(ValueError)
def parse_step(text: str) -> Step
def parse_steps(items: list[str]) -> list[Step]   # error message names the 1-based step index
ID_OPS = {"click","dblclick","hover","type","append","select","check","uncheck","drag","upload"}
```
Ops and forms: `click|dblclick|hover|check|uncheck eN`; `type eN "t"`; `type "t"` (target None); `append eN "t"`; `key COMBO`; `select eN "opt"`; `drag eN eM`; `upload eN path`; `scroll down|up [px]`, `scroll top|bottom`, `scroll eN`; `wait MS`, `wait "text"`; `goto URL` (http/https/about/file); `back|forward|reload`. Ids match `^e\d+$`. Quotes via `shlex` (posix).

- [ ] Tests: one per form above asserting the exact `Step`; `test_unicode_text_preserved` ("Zürich – 東京 😀"); errors: bad id `x5`, unknown op, missing text, unterminated quote, `goto ftp://x`, `scroll sideways`, step index in message.
- [ ] Run → FAIL; implement; run → PASS. Checkpoint.

### Task 2: Rendering + risky matcher

**Files:** Create `src/ai_browser/render.py`, `tests/test_render.py`.

**Interfaces:**
- Consumes: page state dict produced by `reader.js` (Task 7):
  `{"url","title","w","h","scrollY","scrollH","above","below","frames":[{"label","url","cross"}],"rows":[Row],"text","doc","truncated","find"}`,
  `Row = {"id","role","name","value"?, "risky"?, "frame"?, "href"?, "options"?, "checked"?, "expanded"?, "selected"?, "disabled"?, "editable"?}`.
- Produces: `render_row(row) -> str`; `render_page(state, ms=None) -> str`; `diff_rows(old_rows, new_rows) -> dict[str, list]` (`added`, `removed`, `changed`); `render_diff(diff, state, ms=None) -> str`; `risky_regex(words) -> re.Pattern`; `is_risky(name, words) -> bool`.

Format (exact): `e3   button   "Publish" ⚠`; frame tag `[canvas] ` before the name; value ` = "About us"`; options ` (Small|Medium|Large)`; href ` → /privacy/`; states ` [checked]` ` [expanded]` ` [selected]` ` [disabled]` ` [editable]`. Header lines `page  "<title>"  <url>` and `view  1440×900 · y 0/2300 · 4 above · 38 below · frames: [canvas]`. `text: …`. `⏱ N ms` when ms given. Rows beyond `MAX_ROWS` → `… N more rows (use observe find="…")`. Diff: `+ e51 option "London"`, `- e12 …`, `~ e4 textbox … = "Lon"`; empty diff → `(no visible change)`.

- [ ] Tests: each row variant; header with/without frames; truncation line; diff added/removed/changed (changed when name/value/state differs); empty diff; `is_risky`: "Publish" yes, "Update" yes, "Updates feed" no, "Sign up now" yes, "signup" no, case-insensitive.
- [ ] FAIL → implement → PASS. Checkpoint.

### Task 3: Skills catalog

**Files:** Create `src/ai_browser/skills.py`, `tests/test_skills.py`.

**Interfaces — Produces:**
```python
@dataclass(frozen=True)
class Skill: ref: str; namespace: str; name: str; description: str; host_dir: Path; sandbox_dir: str; has_scripts: bool
@dataclass(frozen=True)
class SkillSource: namespace: str; host_root: Path; mount: str; pattern: str  # "*/SKILL.md" or "skills/*/SKILL.md"
class SkillNotFound(KeyError); class AmbiguousSkill(KeyError)
class Catalog:
    def __init__(self, sources: list[SkillSource], blocked: set[str])
    @classmethod
    def discover(cls, claude_home: Path, app_support: Path, project_skills: Path, blocked: set[str]) -> "Catalog"
    def all(self) -> list[Skill]
    def find(self, query: str, limit: int = 10) -> list[Skill]
    def summary(self) -> str            # empty query: "ecc (292): a, b, …" per namespace
    def get(self, name: str) -> Skill   # "ns:name" exact, or bare name if unique
    def load(self, name: str) -> str    # header + body, ${CLAUDE_PLUGIN_ROOT} → mount
    def read_file(self, name: str, rel: str) -> str
    def mounts(self) -> list[tuple[Path, str]]
```
Discovery: `personal` = `claude_home/skills` (`*/SKILL.md`, mount `/skills/personal`); each enabled plugin from `claude_home/plugins/installed_plugins.json` (`plugins[key][0].installPath`, namespace = key before `@`, enabled per `claude_home/settings.json` `enabledPlugins` when present) → `skills/*/SKILL.md`, mount `/skills/plugins/<ns>`; `anthropic-skills` = newest `app_support/local-agent-mode-sessions/skills-plugin/*/*/skills` (`*/SKILL.md`, mount `/skills/claude-ai`); `ai-browser` = `project_skills` (mount `/skills/ai-browser`). Frontmatter via `yaml.safe_load`; bad/missing → name = folder, description "". Duplicate refs: first wins. Search: query tokens (lowercase, ≥2 chars); score +3 per token in name, +1 per token in description; ties by ref; zero-score excluded. `load` header: `skill ecc:api-design · sandbox folder /skills/plugins/ecc/skills/api-design (read-only)` + `files: scripts/x.py, …` (≤30). `read_file`: rejects absolute paths and `..`, size cap `READ_LIMIT`.

- [ ] Tests (tmp dirs that mimic all four sources): discovery counts and refs; disabled plugin excluded; blocked excluded from `all/find/get`; name match outranks description match; `get` bare unique / ambiguous / missing; `load` header + rewritten root; `read_file` traversal rejected; malformed frontmatter tolerated; `mounts()` pairs; `summary()` groups.
- [ ] FAIL → implement → PASS. Run once against the real machine: `uv run python -c "from ai_browser.skills import Catalog; …"` prints ~440. Checkpoint.

### Task 4: Work dir + task log

**Files:** Create `src/ai_browser/workfs.py`, `src/ai_browser/tasklog.py`, `tests/test_workfs.py`, `tests/test_tasklog.py`.

**Interfaces — Produces:**
```python
class PathError(ValueError)
class WorkDir:
    def __init__(self, host_root: Path, task_id: str)   # host_root ↔ "/work"
    host_task: Path; sandbox_task: str                   # host_root/task_id ↔ /work/task_id
    def to_host(self, path: str) -> Path                 # relative→task dir; "/work/…" absolute; escape → PathError
    def to_sandbox(self, path: str) -> str
    def read_text(self, path: str, limit: int) -> str    # "[truncated: N more chars]" suffix
    def write_text(self, path: str, content: str) -> str # creates parents; returns sandbox path
def new_task_id() -> str                                  # "YYYYMMDD-HHMMSS-xxxx"
class TaskLog:
    def __init__(self, root: Path, task_id: str); dir: Path; shots: Path
    def record(self, tool: str, args: dict, ms: int, outcome: str, result: str) -> None  # JSON line, ts ISO-8601 UTC, result ≤500 chars
    def save_shot(self, data: bytes, label: str) -> Path   # shots/NNN-label.jpg
```
- [ ] Tests: relative/absolute mapping; `..` and symlink escape rejected; write creates dirs and returns `/work/...`; read truncation note; task id regex; log line fields + truncation; shot numbering.
- [ ] FAIL → implement → PASS. Checkpoint.

### Task 5: Sandbox image + manager

**Files:** Create `docker/Dockerfile`, `docker/entrypoint.sh`, `src/ai_browser/sandbox.py`, `tests/test_sandbox.py`.

**Interfaces — Produces:**
```python
class DockerError(RuntimeError)        # message is a one-line user fix
@dataclass
class SandboxInfo: name: str; profile: str; http: str; work_host: Path; fresh: bool; created: bool
@dataclass
class ExecResult: code: int; output: str; timed_out: bool
class Sandboxes:
    def __init__(self, home: Path, image: str = IMAGE, mounts: list[tuple[Path, str]] = ())
    def check(self) -> None                          # raises DockerError (docker down / image missing)
    def build(self, context: Path) -> None
    def start(self, profile: str = "default", fresh: bool = False) -> SandboxInfo
    def stop(self, name: str) -> None
    def is_running(self, name: str) -> bool
    def ws_url(self, info: SandboxInfo) -> str        # /json/version ws URL rewritten to 127.0.0.1:<host port>
    def exec(self, name: str, command: str, cwd: str = "/work", timeout: int = 60) -> ExecResult
```
Dockerfile: `debian:bookworm-slim`; apt `chromium fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji fonts-liberation python3 python3-pip python3-venv nodejs npm curl jq socat ca-certificates procps`; user `agent` uid 1000; dirs `/profile /work /skills`. Entrypoint: remove `Singleton*` locks, `socat TCP-LISTEN:9223,fork,reuseaddr TCP:127.0.0.1:9222 &`, `exec chromium` with spec flags + `--no-sandbox --remote-debugging-port=9222 about:blank`. `start`: validate profile; reuse running container (created=False); remove stopped one; `docker run -d` with flags, volume `aib-profile-<p>:/profile` (fresh: `--tmpfs /profile`), `-v <work_host>:/work`, read-only skill mounts, `-p 127.0.0.1::9223`; poll `GET http://127.0.0.1:<port>/json/version` until ready (≤20 s). `exec`: `docker exec -u agent -w <cwd> <name> timeout -s KILL <t>s bash -lc <cmd>`; exit 137 with elapsed≥t → `timed_out`. Output truncated to `SHELL_LIMIT`.

- [ ] Write docker tests: `test_start_creates_and_answers_cdp`, `test_start_reuses_running_container` (created False, <1.5 s), `test_fresh_container_removed_on_stop`, `test_exec_echo_and_cwd`, `test_exec_timeout_kills` (sleep 30 with timeout 1 → timed_out, <5 s), `test_invalid_profile_rejected` (unit), `test_check_reports_docker_down` (unit: `DOCKER_HOST=unix:///nonexistent` → DockerError mentioning Docker Desktop).
- [ ] Run unit ones → FAIL; implement; `uv run ai-browser build` equivalent (`docker build -t ai-browser-sandbox:0.1 docker/`); run all → PASS. Checkpoint.

### Task 6: CDP client

**Files:** Create `src/ai_browser/cdp.py`, `tests/test_cdp.py`.

**Interfaces — Produces:**
```python
class CDPError(RuntimeError): code: int; method: str
class CDP:
    @classmethod
    async def connect(cls, ws_url: str) -> "CDP"          # max_size=None, ping disabled
    async def send(self, method: str, params: dict | None = None, session_id: str | None = None, timeout: float = 30) -> dict
    def on(self, method: str, handler) -> None            # handler(params: dict, session_id: str | None)
    def off(self, method: str, handler) -> None
    async def wait_for(self, method: str, predicate=None, session_id: str | None = None, timeout: float = 10) -> dict
    async def close(self) -> None
    @property
    def closed(self) -> bool
```
Pending futures fail with `CDPError("connection closed")` on socket drop.
- [ ] Docker tests: `Browser.getVersion`; create+attach target, `Runtime.evaluate 1+1` in session = 2; unknown method → CDPError; navigate → `Page.loadEventFired` via `wait_for`; `wait_for` timeout → `asyncio.TimeoutError`; close fails pending sends.
- [ ] FAIL → implement → PASS. Checkpoint.

### Task 7: Reader + observe

**Files:** Create `src/ai_browser/reader.js`, `src/ai_browser/browser.py` (tab setup, `open`, `observe`), `tests/fixtures/{form,frames,frame_inner,shadow,long,heavy,spa,covered}.html`, `tests/test_observe.py`; fixture server helper in `tests/conftest.py`.

**Interfaces:**
- reader.js defines `window.__aib` once per document: `doc` (uuid), `observe({find, maxRows, textLimit, risky})` → state dict (Task 2 schema); `target(id, kind)` → `{ok:true,x,y,risky,name,role}` | `{ok:false,reason}` with reasons `gone|hidden|disabled|covered|readonly`; `node(id)` → element; `selectContents(id)`; `caretEnd(id)`; `selectOption(id, value)` → `{ok, value}`; `state(id)` → row; `scrollIntoView(id)`; `rect(id)` → page-coordinate rect; `waitText(text, ms)` → Promise<bool>; `settle(id)` → Promise; `extract(kind)`.
- Candidates: jev selector + roles `slider treeitem menuitemcheckbox`, `[draggable=true]`, `[onclick]`, `[tabindex]` ≥ 0, topmost `cursor:pointer` elements in viewport; file inputs included even when hidden (named by their label); password inputs listed with no value. Traverses same-origin iframes (label from `name`/`title`/`id`, coordinates offset) and open shadow roots. Ids stable per element per document.
- Browser (this task):
```python
class Browser:
    def __init__(self, cdp: CDP, work: WorkDir, cfg: Config)
    async def start(self) -> None          # own a new tab "t1", attach, enable Page/Runtime/Network/Log, lifecycle, focus emulation, desktop metrics, preload reader, downloads → /work/<task>/downloads
    async def open(self, url: str, new_tab: bool = False) -> str
    async def observe(self, find: str | None = None) -> str
    async def state(self, find: str | None = None) -> dict   # raw reader state
```
- [ ] Fixture server: conftest copies `tests/fixtures/*` into the sandbox work dir and runs `python3 -m http.server 8000` and `8001` (bound 127.0.0.1) via `exec` in background; base URLs `http://localhost:8000/` and `http://127.0.0.1:8001/`.
- [ ] Docker tests: form rows (textbox value, select options, checkbox state, ⚠ on "Submit order", password listed without value); frames (`[frame-label]` rows from same-origin frame; cross-origin frame listed in `frames` with `cross: true`); shadow DOM button found; long page `below` count > 0 and `find="Footer link 90"` finds an off-screen row; stable ids across two observes; spa page: `open` waits until delayed button appears (<3 s); `test_heavy_page_capped_and_fast` (3,000 controls → ≤150 rows, truncated note, median of 5 observes <300 ms); covered button still listed.
- [ ] FAIL → implement → PASS. Checkpoint.

### Task 8: Actions (`act`)

**Files:** Modify `src/ai_browser/browser.py` (add `act`); Create `src/ai_browser/keys.py`, `tests/fixtures/{dnd,upload,editor,autocomplete,nav}.html`, `tests/test_act.py`, `tests/test_keys.py`.

**Interfaces — Produces:**
- `keys.key_event(combo: str) -> tuple[dict, int]` → CDP params (`key`, `code`, `windowsVirtualKeyCode`, `text` for printable/Enter) and modifier bitmask (Alt 1, Ctrl 2, Meta 4, Shift 8).
- `Browser.act(steps: list[Step], confirmed: bool = False) -> str` — per-step lines (`✓ click e5 34 ms`, `✗ stale e7: covered`, `⛔ blocked e3 "Publish" ⚠ — ask the user, then repeat with confirmed=true`, `– skipped N steps (page changed)`), then diff (same `doc`) or full table.
Behavior: click = mouseMoved → pressed → released at guarded point; dblclick clickCount 2; hover = mouseMoved; type = click to focus → `selectContents` → `Input.insertText` (empty text → Backspace); append = click → `caretEnd` → insertText; type without id → insertText; key → keyDown/keyUp; select → `selectOption`; check/uncheck → click only if state differs; drag → `Input.setInterceptDrags` + press/move in 5 steps → if `Input.dragIntercepted` → `dispatchDragEvent` dragEnter/dragOver/drop at target, else mouse release at target; upload → host file must exist → `DOM.setFileInputFiles(objectId)`; scroll → mouseWheel at viewport center (default 0.8×h) / `scrollTo` top/bottom / `scrollIntoView`; wait → sleep ≤10 s or `waitText`; goto/back/forward/reload → navigate and wait DOMContentLoaded. After each step: if `doc` changed → wait DCL, ensure reader, mark navigated; else `settle`. On navigation with remaining id steps → skip them.

- [ ] Tests (`test_keys.py` unit): Enter, Meta+A, Shift+Tab, ArrowDown, "a", unknown key error.
- [ ] Docker tests: click toggles fixture counter; dblclick; hover reveals menu (diff shows `+` row); type replaces existing value; append; `test_type_unicode_roundtrip`; contenteditable replace touches only that block (editor.html sibling block unchanged); key Enter submits search form (page changes); select by label and by value; check/uncheck idempotent; drag reorders HTML5 list and JS-mouse list (two fixtures); upload to hidden file input shows filename; scroll down changes `y`; `wait "Loaded"` succeeds and times out with error after cap (use 1 s override); goto/back/forward; stale: DOM mutated between observe and act → `stale` reported, nothing clicked; covered → `stale e?: covered`; risky blocked without confirmed, runs with confirmed; `test_navigation_mid_batch_skips_id_steps`; batch of 5 steps returns a diff not a full table; autocomplete: type in combobox → options appear in the same result.
- [ ] FAIL → implement → PASS. Checkpoint.

### Task 9: Screenshot, page_log, extract, js, tabs

**Files:** Modify `src/ai_browser/browser.py`; Create `tests/fixtures/{errors,table}.html`, `tests/test_browser_misc.py`.

**Interfaces — Produces:**
```python
@dataclass
class Shot: label: str; data: bytes; width: int; height: int
Browser.screenshot(size: str = "desktop", full_page: bool = False, element: str | None = None) -> list[Shot]
Browser.page_log() -> str          # since last call; ≤50 newest entries shown; buffer ≤200
Browser.extract(kind: str) -> str  # links (also links.json) | tables (table-N.csv) | meta
Browser.js(code: str) -> str       # await promises; top-level return wrapped; JSON ≤ JS_LIMIT
Browser.tabs(action: str = "list", tab: str | None = None, url: str | None = None) -> str
```
- [ ] Docker tests: desktop shot is JPEG ≤1280 wide; `all` gives 3 labeled shots with mobile narrower layout (fixture shows "mobile" text under 600 px) and restores desktop metrics; full_page height > viewport; element crop size ≈ element size; page_log shows console.error text, uncaught exception, 404 resource, then empty on second call; extract links/tables(meta) write files and summarize; js returns value, handles `return`, reports exceptions; tabs new/list/switch/close only touch owned tabs.
- [ ] FAIL → implement → PASS. Checkpoint.

### Task 10: Engine facade

**Files:** Create `src/ai_browser/engine.py`, `tests/test_engine.py`.

**Interfaces — Produces:**
```python
@dataclass
class ToolResult: text: str; images: list[bytes] = field(default_factory=list)
class Engine:
    def __init__(self, home: Path | None = None)
    task_id: str
    async def sandbox_start(self, profile: str = "default", fresh: bool = False) -> ToolResult
    async def sandbox_stop(self) -> ToolResult
    async def sandbox_status(self) -> ToolResult
    async def open(self, url: str, new_tab: bool = False) -> ToolResult
    async def observe(self, find: str | None = None) -> ToolResult
    async def act(self, steps: list[str], confirmed: bool = False) -> ToolResult
    async def screenshot(self, size: str = "desktop", full_page: bool = False, element: str | None = None) -> ToolResult
    async def tabs(self, action: str = "list", tab: str | None = None, url: str | None = None) -> ToolResult
    async def page_log(self) -> ToolResult
    async def extract(self, kind: str) -> ToolResult
    async def js(self, code: str) -> ToolResult
    async def shell(self, command: str, timeout: int = 60) -> ToolResult
    async def read_file(self, path: str) -> ToolResult
    async def write_file(self, path: str, content: str) -> ToolResult
    async def find_skills(self, query: str = "", limit: int = 10) -> ToolResult
    async def load_skill(self, name: str) -> ToolResult
    async def read_skill_file(self, name: str, path: str) -> ToolResult
    async def close(self) -> None
```
Every method: time it, append `⏱ N ms`, log via `TaskLog`, convert any exception to `error: <message>` (DockerError/StepError/PathError/SkillNotFound/CDPError messages pass through; unknown → `error: <Type>: <msg>`). Browser tools lazily start `default`; if container died or CDP closed → restart + re-attach once and prefix `(sandbox restarted)`. Shell long output saved to `.shell/NNN.log` in the task dir. Screenshots saved via `TaskLog.save_shot`. Live view started on first sandbox start (Task 12 hooks in; until then status shows "live view: not started").
- [ ] Tests: unit `test_docker_unavailable_message` (env `DOCKER_HOST` bogus → `open` returns text starting `error:` mentioning Docker Desktop, no exception); docker: lazy start on `open`; restart after `docker kill` mid-session; shell output truncation + saved copy; read/write roundtrip + escape rejected; find/load skill via catalog built from tmp sources and `shell` runs the skill's script at its `/skills/...` path; log.jsonl has one line per call; `test_two_engines_share_container`.
- [ ] FAIL → implement → PASS. Checkpoint.

### Task 11: MCP server + `ai-browser mcp`

**Files:** Create `src/ai_browser/server.py`, `src/ai_browser/cli.py` (with `mcp` subcommand), `tests/test_server.py`.

**Interfaces:**
- Consumes: `Engine`.
- Produces: FastMCP server `ai-browser` exposing the 17 spec tools with short docstrings; `ToolResult` → text content + JPEG image contents. Engine created lazily on first tool call; closed on shutdown. Logs only to stderr.
- [ ] Tests: unit — tool list names equal spec set; docker e2e — `mcp` stdio client spawns `uv run ai-browser mcp`, calls `open` (fixture), `act`, `screenshot` → gets text and an image item.
- [ ] FAIL → implement (check the installed `mcp` 2.x FastMCP import path and image type first) → PASS. Checkpoint.

### Task 12: Live view

**Files:** Create `src/ai_browser/live.py`, `src/ai_browser/static/live.html`, `tests/test_live.py`; Modify `engine.py` (start on first sandbox start; URL in `sandbox_start`/`sandbox_status`).

**Interfaces — Produces:** `LiveView(browser_getter, host="127.0.0.1", ports=range(8770, 8791))`, `async start() -> str` (URL with `?token=`), `async stop()`. WS messages client→server: `{"t":"mouse","e":"down|up|move","x","y","b":"left|right"}`, `{"t":"wheel","x","y","dx","dy"}`, `{"t":"key","e":"down|up","key","code","kc","mod","text"}`, `{"t":"text","text"}`; server→client: `{"t":"frame","data":<base64 jpeg>,"w","h"}`. Screencast runs only while ≥1 viewer; restarts on tab switch. Wrong token → 403.
- [ ] Docker tests: page 200 with token, 403 without; websocket receives a frame within 3 s; mouse down/up at a button's center (scaled) toggles the fixture counter; screencast stops after disconnect (no frames buffered).
- [ ] FAIL → implement → PASS. Manual: open URL in your browser, click around. Checkpoint.

### Task 13: CLI — build, doctor, bench, live, stop

**Files:** Modify `src/ai_browser/cli.py`; Create `tests/test_cli.py`.

**Interfaces — Produces:** `ai-browser build` (docker build of `docker/`), `ai-browser doctor` (✓/✗ lines: Docker, image, sandbox start, CDP version, open+observe fixture, screenshot, skills count; exit 1 on any ✗), `ai-browser bench [--runs 15]` (serves fixtures in sandbox; medians for observe, heavy observe, click step, type step, open, screenshot; table with budget and PASS/OVER; exit 1 if any OVER), `ai-browser live [--profile P]` (prints live URL, runs until Ctrl-C), `ai-browser stop [PROFILE|--all]`.
- [ ] Tests: unit — argparse wiring and help text; docker — `doctor` exits 0; `bench --runs 3` prints all six rows.
- [ ] Implement; run `uv run ai-browser bench` and record medians in README. Tune until all PASS. Checkpoint.

### Task 14: Registration, README, acceptance

**Files:** Create `.mcp.json`, `README.md`.

- [ ] `.mcp.json`: `{"mcpServers":{"ai-browser":{"command":"uv","args":["run","--directory","<abs project path>","ai-browser","mcp"]}}}`.
- [ ] README: what it is, setup (`uv sync`, `uv run ai-browser build`, `uv run ai-browser doctor`), registering with Claude Code, tools list, profiles + live-view login, safety notes (⚠, `--no-sandbox` limitation), bench numbers.
- [ ] Full test run: `uv run pytest -q` (all pass) and `uv run ai-browser doctor`.
- [ ] Acceptance from a new Claude Code session (spec §9, items 1–6). Record results in README.
