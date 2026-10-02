# ai-browser — "Own Chrome" mode (engine addendum)

Date: 2026-10-02 · Status: approved in chat ("proceed to build")

## Goal

Let the engine drive the user's **real, running Google Chrome** — like Claude in Chrome — with the same
fast numbered reads, batched guarded actions, ⚠ confirmations, dialog rules and secret masking. Use it for
sites that refuse the sandboxed headless browser (airlines, banks, ticketing), or when the user's existing
logins are needed. The Docker sandbox stays the default.

## Decisions

- **Opt-in per session:** `sandbox_start(chrome=true)`; `AIB_BROWSER=chrome` makes it the session default.
- **Connection:** Chrome writes `DevToolsActivePort` into its user-data folder once remote debugging is
  allowed at `chrome://inspect/#remote-debugging`. The engine reads that file (folder from `AIB_CHROME_DIR`,
  default `~/Library/Application Support/Google/Chrome`) and connects to `ws://127.0.0.1:<port><path>`.
  Chrome then asks "Allow remote debugging?" — the user clicks Allow. The engine never automates that
  click nor changes Chrome settings. Connection wait: up to 60 s, then a plain-English error.
- **Only our tabs:** new tabs are opened in the background (`background: true`) and closed when the session
  ends; the user's own tabs are never read or touched. Tabs a page opens from our tabs are still followed.
- **No settings changes:** no download-behaviour override (downloads go to the user's normal folder);
  no fixed viewport override at start (the real window size is used); screenshot sizes still emulate and
  then clear the override.
- **Files:** work folder `~/.ai-browser/chrome/work/<task>`; uploads use host paths from there.
- **Shell and skill scripts** still run in the Docker shell container (`aib-chrome-sh`), started lazily on
  the first `shell` call; if Docker is unavailable, only `shell` reports that.
- **Recovery:** if Chrome closes, the next call reconnects (the user may need to click Allow again).
- **Session registry:** same dead-session tab cleanup as sandboxes, under `~/.ai-browser/sandboxes/chrome`.
- **Honesty:** nothing is spoofed or hidden; some sites may still detect automation.

## Interfaces

- `chrome.py`: `ChromeError`; `default_chrome_dir() -> Path`; `find_ws_url(user_data_dir) -> str`;
  `launch(user_data_dir, headless=True, extra_args=()) -> subprocess.Popen` (throwaway Chrome for tests,
  doctor and demos; never the default profile).
- `Browser(cdp, work, cfg, mode="sandbox"|"chrome")`.
- `Sandboxes.start_shell(profile, work_host) -> str` (shell container only).
- `Engine.sandbox_start(profile="default", fresh=False, chrome=False)`; MCP tool gains `chrome`.
- `ai-browser doctor --chrome`: checks the user's Chrome is reachable (asks for Allow once).

## Testing

Automated tests launch a throwaway Chrome (installed Google Chrome app, temp profile, headless,
`--remote-debugging-port=0`) and point `AIB_CHROME_DIR` at it; pages are served from a host-side test
server. A real-world check runs a Cebu Pacific search (Cagayan de Oro → Manila) in a visible throwaway
Chrome; if the site blocks or shows a challenge, the test stops and reports it.
