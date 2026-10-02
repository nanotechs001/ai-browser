# Own Chrome Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `sandbox_start(chrome=true)` drives the user's real Chrome with the existing engine.
**Architecture:** read `DevToolsActivePort`, connect one CDP websocket, reuse `Browser` with `mode="chrome"`
(background tabs, no settings changes, host-path uploads); shell stays in a Docker shell container.
**Tech Stack:** existing engine (Python, websockets, MCP); installed Google Chrome for tests.
**Spec:** `docs/superpowers/specs/2026-10-02-own-chrome-mode-design.md`

## Global Constraints

- Never modify the user's default Chrome settings or profile; tests use a throwaway `--user-data-dir`.
- Only tabs the session opened (plus tabs those tabs opened) are read, acted on, or closed.
- Connection wait ≤ 60 s; errors are one plain-English line with the fix.
- Same speed budgets as the engine (`ai-browser bench` numbers must not regress).

## Review Focus

1. Chrome not running / remote debugging not allowed / stale `DevToolsActivePort` → clear fix message.
2. The user closes Chrome mid-session → next call reconnects or explains; no traceback.
3. The user's own tabs are never touched (list, act, close) — even after popups and session end.
4. `screenshot(size="all")` in chrome mode returns the tab to the real window size.
5. Uploads in chrome mode resolve to host paths inside the work folder only.

### Task C1: `chrome.py`
Files: `src/ai_browser/chrome.py`, `tests/test_chrome.py`.
- [ ] Tests: missing folder/file → `ChromeError` naming `chrome://inspect/#remote-debugging`; stale port → "isn't running";
  real throwaway Chrome (`launch`) → `find_ws_url` → CDP `Browser.getVersion` answers.
- [ ] Implement `ChromeError`, `default_chrome_dir`, `find_ws_url`, `launch`, `chrome_binary`.

### Task C2: Browser chrome mode
Files: `src/ai_browser/browser.py`, `tests/test_chrome.py`, host page server helper in `src/ai_browser/testpages.py`.
- [ ] Tests (throwaway Chrome + host server): open/act/observe work; tabs opened are background tabs and
  closing the session leaves pre-existing tabs open; `screenshot("all")` clears the viewport override;
  upload uses a host path.
- [ ] Implement `mode`, background tabs, no download/viewport override in chrome mode, host upload paths.

### Task C3: Engine + shell
Files: `src/ai_browser/engine.py`, `src/ai_browser/sandbox.py`, `tests/test_chrome.py`.
- [ ] Tests: `sandbox_start(chrome=True)` → status names "your Chrome"; open + act; `shell` runs in
  `aib-chrome-sh` (docker); Chrome killed → next call reconnects to a relaunched Chrome or reports clearly.
- [ ] Implement `Sandboxes.start_shell`, `Engine` chrome mode (connect, lazy shell, registry, reconnect).

### Task C4: MCP, CLI, docs
Files: `src/ai_browser/server.py`, `src/ai_browser/cli.py`, `README.md`, tests.
- [ ] Tests: `sandbox_start` tool schema has `chrome`; `doctor --chrome` with a throwaway Chrome passes.
- [ ] Implement; README "Use your own Chrome" section.

### Task C5: Real-world check
- [ ] Visible throwaway Chrome → Cebu Pacific one-way search, Cagayan de Oro → Manila, 1 adult, about two
  weeks out; stop at the results; stop immediately on any block or challenge. Record timings.

### Task C6: Final review and fix pass
- [ ] Fresh reviewer on the changed files; Critical/Important fixed test-first; report.
