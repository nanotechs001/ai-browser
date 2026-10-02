# Website QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `qa(url, max_pages=30)` tool that crawls a site in the session's browser and does three things:
- checks layout on 3 sizes, page errors and every link;
- writes `report.html`, `issues.csv` and screenshots;
- returns a short summary.

It ships with an `ai-browser:website-qa` skill.

**Architecture:**
- **Package:** a new `ai_browser/qa/` package, made of small units: URL rules, an issue model, a link checker, a page
  visitor with an in-page probe, a report writer and a runner.
- **Tabs:** the runner opens its own tabs through `Browser.open_worker()`. A *home* tab parks on the start page and
  checks links with `Network.loadNetworkResource`; two worker tabs visit pages.
- **Engine and MCP:** both expose it as `qa`.

**Tech stack:** Python 3.12, asyncio, the existing CDP client, Chrome DevTools Protocol, pytest + pytest-asyncio,
and a throwaway headless Chrome for tests (`chrome.launch`). Docker is used for one sandbox test.

**Spec:** `docs/superpowers/specs/2026-10-02-website-qa-design.md`

## Global Constraints

- QA never clicks, types or submits. It only navigates, scrolls by script, reads the page, emulates sizes and takes
  screenshots.
- Internal action links (log out/sign out, delete, remove, trash, unsubscribe, add-to-cart, `wp-admin`,
  `wp-login.php`, query keys `action`/`_wpnonce`/`nonce`/`token`) are neither followed nor requested.
- Only HTML internal pages are opened, after the home tab has checked their status and headers. There's no
  download override, because a per-page deny leaks to the whole browser.
- Link checks: at most 2 per host and 8 in total; 12 s timeout. Internal links send credentials; external ones don't.
- `max_pages` is clamped to 1–200; the crawl budget is 180 s and the link budget 60 s. A run cut short says so.
- Screenshots:
  - sizes desktop 1440×900, tablet 768×1024, mobile 390×844 (`config.SIZES`);
  - full page up to 8000 CSS px tall, width at most 1280 px, JPEG quality 60;
  - a viewport thumbnail about 320 px wide.
- Everything taken from pages is untrusted. The report escapes all of it, and the tool returns text only (no images).
- The working tab (`browser.current`) is untouched, and every QA tab and popup is closed at the end.
- The repo has no git, so wherever a step says "commit", append a line to the ledger
  `.superpowers/sdd/2026-10-02-website-qa/progress.md` instead.

## Review Focus

1. **Huge pages** (thousands of elements, very tall): the probe must stay fast (it scans at most 20,000 elements) and
   shots must be capped. Test: visit `heavy.html` in under 6 s (Task 4).
2. **Pages that never go quiet** (beacons, long polling): the visit must not hang. Test: `pending.html` keeps a
   request open for 20 s and the visit still ends in under 10 s (Task 4).
3. **Crawl traps** (calendars, faceted filters): the frontier crawls at most 5 query variants per path. Test: a pure
   `Frontier` unit test (Task 6).
4. **Pages that open alerts or popups:** the visit must not stall, and popups are closed at the end. Test: visit
   `dialogs.html`, then a full run leaves no extra tabs (Tasks 4 and 6).
5. **A response that lies about being a page** (HTML sent as an attachment, or files): the page is never opened, and
   only its status is recorded. Test: the `/qa/attachment` route plus the `.zip` link (Task 3, then the Task 6 run).

---

### Task 1: Planted test site and shared test-server routes

**Files:**
- Modify: `src/ai_browser/pages/_serve.py`. It holds the handler `NoStore` with a route table; the server starts
  only under `__main__`.
- Modify: `src/ai_browser/testpages.py`. `serve_host` loads `NoStore` from `pages/_serve.py` with `importlib`.
- Create: `src/ai_browser/pages/qa/`:
  - pages `index.html`, `about.html`, `products.html`, `contact.html`, `team.html`, `blog/index.html`,
    `logout.html`, `pending.html`;
  - files `files/brochure.zip` and `images/photo.png`.
- Test: `tests/test_testpages.py`

**Interfaces:**
- **Produces routes:** `/qa/old` 301 → `/qa/older` 301 → `/qa/about.html`; `/qa/forbidden` 403;
  `/qa/slow` (sleeps 20 s, then 200); `/qa/attachment` (`text/html` with `Content-Disposition: attachment`).
- **Planted findings**, exactly as listed in the spec's Testing section:

  | Where | Finding |
  |---|---|
  | `index.html` | links: `about.html`, `products.html`, `contact.html`, `team.html`, `blog`; `missing.html` ("Old offers"); `files/brochure.zip`; `logout.html` ("Log out"); `/qa/attachment` ("Terms (download)"). Plus a script that adds external links `http://127.0.0.1:<port>/qa/missing.html` ("Partner site") and `http://127.0.0.1:<port>/qa/forbidden` ("Members area") |
  | `about.html` (title "About us") | clean; 6 tall sections with `loading="lazy"` images of `images/photo.png`; a link to `/qa/old` ("Our story") |
  | `products.html` | `<div class="wide-table">` 600 px wide (sticks out at 390 only); a 900 px table inside `<div style="overflow-x:auto">` (fine) |
  | `contact.html` | `console.error("Contact form failed to load")`; `setTimeout(() => { throw new Error("map widget crashed") })` |
  | `team.html` | `<img src="images/missing-photo.jpg" alt="Our office">` (404) plus one valid image |
  | `blog/index.html` | clean |
  | `pending.html` | `fetch("/qa/slow")`; not linked from anywhere |

  Every page has `<meta name="viewport" content="width=device-width, initial-scale=1">`.

- [ ] **Step 1: Write the failing test** (`tests/test_testpages.py`)

```python
import http.client
from urllib.parse import urlsplit

from ai_browser import testpages


def _get(url: str) -> http.client.HTTPResponse:
    parts = urlsplit(url)
    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=5)
    conn.request("GET", parts.path)
    return conn.getresponse()


def test_host_server_has_the_qa_routes():
    base, _, stop = testpages.serve_host()
    try:
        first = _get(base + "qa/old")
        assert first.status == 301 and first.getheader("Location") == "/qa/older"
        second = _get(base + "qa/older")
        assert second.status == 301 and second.getheader("Location") == "/qa/about.html"
        assert _get(base + "qa/forbidden").status == 403
        attachment = _get(base + "qa/attachment")
        assert attachment.status == 200 and "attachment" in attachment.getheader("Content-Disposition")
        assert _get(base + "qa/index.html").status == 200
        assert _get(base + "qa/missing.html").status == 404
    finally:
        stop()
```

- [ ] **Step 2: Run it.** `uv run pytest tests/test_testpages.py -q`. Expected: FAIL (`qa/old` is a 404).
- [ ] **Step 3: Implement**
  - In `_serve.py`, `NoStore` overrides `do_GET` and `do_HEAD` through `_route()`:

    ```python
    REDIRECTS = {"/qa/old": "/qa/older", "/qa/older": "/qa/about.html"}

    def _route(self) -> bool:
        path = self.path.split("?", 1)[0]
        if path in REDIRECTS:
            self.send_response(301); self.send_header("Location", REDIRECTS[path]); self.end_headers(); return True
        if path == "/qa/forbidden":
            self.send_error(403); return True
        if path == "/qa/slow":
            time.sleep(20); self.send_response(200); self.end_headers(); return True
        if path == "/qa/attachment":
            body = b"<title>Terms</title>"
            self.send_response(200); self.send_header("Content-Type", "text/html")
            self.send_header("Content-Disposition", 'attachment; filename="terms.html"')
            self.send_header("Content-Length", str(len(body))); self.end_headers()
            if self.command == "GET": self.wfile.write(body)
            return True
        return False
    ```

  - Run the server only under `__main__`.
  - In `testpages.serve_host`, use `functools.partial(_handler(), directory=...)`. `_handler()` loads
    `PAGES / "_serve.py"` through `importlib.util.spec_from_file_location`.
  - Write the planted pages.
- [ ] **Step 4: Run it again.** Expected: PASS. Also run `uv run pytest tests/test_chrome.py -q` to confirm
  `serve_host` still works.
- [ ] **Step 5: Ledger.** Add "Task 1: complete".

### Task 2: URL rules and the issue model (pure Python)

**Files:**
- Create: `src/ai_browser/qa/__init__.py` (empty for now), `src/ai_browser/qa/urls.py`, `src/ai_browser/qa/model.py`,
  `src/ai_browser/qa/issues.py`
- Test: `tests/test_qa_urls.py`, `tests/test_qa_issues.py`

**Interfaces (produced):**
- `urls.normalize(url: str) -> str | None`. It:
  - accepts http(s) only, lowercases the scheme and host, drops the default port and the fragment;
  - turns an empty path into `/` and keeps the query;
  - returns None for anything else.
- `urls.origin(url) -> str` returns `scheme://host[:port]`.
- `urls.action_link(url, text="") -> bool` matches token-bounded patterns in the path or query:
  - `log[-_]?out`, `sign[-_]?out`, `log[-_]?off`;
  - `delete`, `remove`, `trash`, `unsubscribe`;
  - `add[-_]to[-_]cart`, `empty[-_]cart`;
  - `wp-admin`, `wp-login.php`.

  It also matches the query keys `action`, `_wpnonce`, `nonce`, `token`, `add-to-cart`, `remove_item`, and link text
  matching `\b(log ?out|sign ?out|log ?off|delete|remove|unsubscribe|trash)\b`.
- `urls.is_file(url) -> bool`: the path ends in a known non-page extension (pdf, zip, rar, 7z, gz, tar, dmg, exe, msi,
  apk, doc(x), xls(x), ppt(x), csv, xml, json, jpg, jpeg, png, gif, webp, svg, ico, mp3, mp4, mov, avi, webm, wav,
  woff, woff2, ttf, css, js).
- `urls.slug(url) -> str`: the path as a file name, `[a-z0-9-]`, at most 40 characters, `home` for `/`.
- `model.Issue` (dataclass): `severity: str` (`high`/`medium`/`low`), `kind: str`, `detail: str`,
  `pages: list[str]`, `sizes: list[str] = []`, `extra: str = ""`. Property `rank -> tuple`.
- `model.LinkResult` (dataclass): `url`, `status: int | None`, `error: str | None`, `content_type: str = ""`,
  `attachment: bool = False`, `challenge: bool = False`, and property `page -> bool` (HTML and not an attachment).
- `issues.link_verdict(result: LinkResult) -> str` returns one of `ok`, `broken`, `server error`, `timeout`,
  `unchecked`:

  | Result | Verdict |
  |---|---|
  | 200–399 | `ok` |
  | 404, 410 | `broken` |
  | 401, 403, 429, 999 | `unchecked` |
  | 503 with `challenge` | `unchecked` |
  | other 5xx | `server error` |
  | other 4xx | `unchecked` |
  | error `timeout`, `net::ERR_TIMED_OUT`, `net::ERR_CONNECTION_TIMED_OUT` | `timeout` |
  | errors `NAME_NOT_RESOLVED`, `CONNECTION_REFUSED`, `CONNECTION_RESET`, `CONNECTION_CLOSED`, `ADDRESS_UNREACHABLE`, `EMPTY_RESPONSE`, `TOO_MANY_REDIRECTS`, `INVALID_RESPONSE`, `CERT_*`, `SSL_*` | `broken` |
  | anything else (`BLOCKED_BY_CLIENT`, `ABORTED`, `UNSAFE_PORT`…) | `unchecked` |

- `issues.link_issue(result, internal: bool, referrers: list[tuple[str, str]]) -> Issue | None`:

  | Verdict | Internal link | External link |
  |---|---|---|
  | `broken` | high `broken link` | medium `broken link (external)` |
  | `server error` | high `server error` | medium `server error` |
  | `timeout` | low `link timed out` | low `link timed out` |
  | `ok`, `unchecked` | None | None |

  The detail is `url (404)` or `url (net::ERR_…)`, pages are the referrer pages, and extra is the first link text.
- `issues.lower(severity) -> str` steps a severity down: high → medium → low → low.
- `issues.merge(issues: list[Issue]) -> list[Issue]` merges on `(kind, detail)`:
  - it unions pages and sizes (keeping order) and keeps the highest severity;
  - it sorts by severity (high, medium, low), then number of pages descending, then kind.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_qa_urls.py
import pytest

from ai_browser.qa.urls import action_link, is_file, normalize, origin, slug


@pytest.mark.parametrize("raw,expected", [
    ("HTTPS://Example.COM:443/a?b=1#top", "https://example.com/a?b=1"),
    ("http://example.com", "http://example.com/"),
    ("http://example.com:8080/x", "http://example.com:8080/x"),
    ("mailto:a@b.c", None), ("javascript:void(0)", None), ("tel:123", None), ("", None),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_origin():
    assert origin("https://example.com/a/b?c") == "https://example.com"
    assert origin("http://localhost:8000/qa/") == "http://localhost:8000"


@pytest.mark.parametrize("url,text", [
    ("https://s.com/wp-login.php?action=logout&_wpnonce=1", ""), ("https://s.com/logout", ""),
    ("https://s.com/account/sign-out/", ""), ("https://s.com/?add-to-cart=12", ""),
    ("https://s.com/wp-admin/post.php?post=1", ""), ("https://s.com/cart/?remove_item=ab", ""),
    ("https://s.com/x", "Log out"), ("https://s.com/x", "Delete account"), ("https://s.com/u?token=abc", ""),
])
def test_action_links_are_recognised(url, text):
    assert action_link(url, text)


@pytest.mark.parametrize("url,text", [
    ("https://s.com/blog/how-we-removed-clutter/", "Read more"), ("https://s.com/checkout/", "Checkout"),
    ("https://s.com/posts/", "Latest posts"), ("https://s.com/updates/", "Updates"), ("https://s.com/", "Home"),
])
def test_ordinary_pages_are_not_action_links(url, text):
    assert not action_link(url, text)


def test_files_and_slugs():
    assert is_file("https://s.com/files/brochure.ZIP") and is_file("https://s.com/a.pdf?x=1")
    assert not is_file("https://s.com/about/") and not is_file("https://s.com/page.html")
    assert slug("https://s.com/") == "home" and slug("https://s.com/Blog/My Post/?a=1") == "blog-my-post"
```

```python
# tests/test_qa_issues.py
from ai_browser.qa.issues import link_issue, link_verdict, merge
from ai_browser.qa.model import Issue, LinkResult


def verdict(status=None, error=None, challenge=False):
    return link_verdict(LinkResult("https://x.com/", status, error, challenge=challenge))


def test_link_verdicts():
    assert verdict(200) == verdict(301) == "ok"
    assert verdict(404) == verdict(410) == "broken"
    assert verdict(500) == verdict(502) == "server error"
    assert verdict(503, challenge=True) == verdict(403) == verdict(429) == verdict(999) == "unchecked"
    assert verdict(405) == "unchecked"
    assert verdict(error="net::ERR_NAME_NOT_RESOLVED") == verdict(error="net::ERR_CERT_DATE_INVALID") == "broken"
    assert verdict(error="timeout") == verdict(error="net::ERR_TIMED_OUT") == "timeout"
    assert verdict(error="net::ERR_BLOCKED_BY_CLIENT") == verdict(error="net::ERR_UNSAFE_PORT") == "unchecked"


def test_link_issues_by_place():
    refs = [("https://s.com/", "Old offers")]
    internal = link_issue(LinkResult("https://s.com/missing", 404, None), True, refs)
    assert (internal.severity, internal.kind) == ("high", "broken link")
    assert internal.detail == "https://s.com/missing (404)" and internal.pages == ["https://s.com/"]
    assert internal.extra == "Old offers"
    external = link_issue(LinkResult("https://o.com/x", 404, None), False, refs)
    assert (external.severity, external.kind) == ("medium", "broken link (external)")
    assert link_issue(LinkResult("https://o.com/x", 403, None), False, refs) is None


def test_merge_unions_pages_and_ranks():
    a = Issue("medium", "broken image", "https://s.com/f.jpg (404)", ["/a"])
    b = Issue("medium", "broken image", "https://s.com/f.jpg (404)", ["/b"])
    c = Issue("high", "script error", "Error: boom", ["/c"])
    d = Issue("low", "link timed out", "https://o.com/ (timeout)", ["/a"])
    merged = merge([d, a, c, b])
    assert [i.kind for i in merged] == ["script error", "broken image", "link timed out"]
    assert merged[1].pages == ["/a", "/b"]
```

- [ ] **Step 2: Run them.** `uv run pytest tests/test_qa_urls.py tests/test_qa_issues.py -q`. Expected: FAIL
  (`ModuleNotFoundError: ai_browser.qa`).
- [ ] **Step 3: Implement** the four modules exactly as specified above. `Issue.rank` is
  `(SEVERITY_ORDER[severity], -len(pages), kind, detail)`.
- [ ] **Step 4: Run them again.** Expected: PASS.
- [ ] **Step 5: Ledger.** Add "Task 2: complete".

### Task 3: Link checker inside the browser

**Files:**
- Create: `src/ai_browser/qa/checker.py`
- Modify: `tests/conftest.py`. Move the `throwaway_chrome` and `chrome_browser` fixtures here from
  `tests/test_chrome.py`, unchanged, so the QA tests can use them.
- Test: `tests/test_qa_browser.py`

**Interfaces:**
- **Consumes:** `model.LinkResult`; `Browser.owned`/`Tab` (`tab.session`, `tab.frame`); `CDP.send`.
- **Produces:**
  - `LinkChecker(cdp: CDP, tab: Tab, per_host: int = 2, total: int = 8, timeout: float = 12.0)`;
  - `await check(url, credentials: bool) -> LinkResult`.

  The check calls `Network.loadNetworkResource` with `{"frameId": tab.frame, "url": url, "options":
  {"disableCache": True, "includeCredentials": credentials}}` on `tab.session`.
  - **Result:** status = `httpStatusCode`; error = `netErrorName` (None when the call succeeded, or when it is
    `ERR_HTTP_RESPONSE_CODE_FAILURE` and there's a status).
  - **Headers** are read case-insensitively:
    - content type: the lowercase value before `;`;
    - attachment: `content-disposition` starts with `attachment`;
    - challenge: header `cf-mitigated: challenge`.
  - **Clean-up:** the stream is closed with `IO.close`.
  - **Failures:** a timeout gives error `timeout`; any other `CDPError` gives error `str(exc)`.
  - **Concurrency:** one `asyncio.Semaphore(total)` plus one semaphore of `per_host` per hostname.

- [ ] **Step 1: Write the failing test** (`tests/test_qa_browser.py`)

```python
import asyncio
import time

import pytest

from ai_browser.chrome import chrome_binary

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


@CHROME
async def test_link_checker_reports_status_files_and_errors(chrome_browser):
    from ai_browser.qa.checker import LinkChecker
    from ai_browser.qa.issues import link_verdict

    browser, base, _ = chrome_browser
    await browser.open(base + "qa/index.html")
    other = base.replace("localhost", "127.0.0.1")
    checker = LinkChecker(browser.cdp, browser.current)
    results = await asyncio.gather(*[checker.check(url, credentials) for url, credentials in [
        (base + "qa/about.html", True), (base + "qa/missing.html", True), (other + "qa/forbidden", False),
        (base + "qa/old", True), (base + "qa/files/brochure.zip", True), (base + "qa/attachment", True),
        ("http://no-such-host.invalid/", False)]])
    about, missing, forbidden, old, zip_file, attachment, nowhere = results
    assert about.status == 200 and about.page
    assert link_verdict(missing) == "broken" and missing.status == 404
    assert link_verdict(forbidden) == "unchecked"
    assert old.status == 200 and old.page  # redirects are followed
    assert link_verdict(zip_file) == "ok" and not zip_file.page
    assert attachment.status == 200 and attachment.attachment and not attachment.page
    assert link_verdict(nowhere) == "broken" and nowhere.error == "net::ERR_NAME_NOT_RESOLVED"
```

- [ ] **Step 2: Run it.** Expected: FAIL (no module `checker`).
- [ ] **Step 3: Implement** `checker.py` as specified, and move the fixtures to conftest.
- [ ] **Step 4: Run it**, plus `tests/test_chrome.py`. Expected: PASS.
- [ ] **Step 5: Ledger.** Add "Task 3: complete".

### Task 4: Page visitor and in-page probe

**Files:**
- Create: `src/ai_browser/qa/probe.js`, `src/ai_browser/qa/page.py`
- Modify: `src/ai_browser/browser.py`
  - `open_worker() -> Tab` creates a background tab (in chrome mode) and sets it up as owned but not current. On a
    failed setup it closes the target.
  - `close_tab(tab)` forgets the tab and closes it, ignoring `CDPError`.
  - `_new_tab` is rewritten to use `open_worker` plus `_switch`.
- Test: `tests/test_qa_browser.py`

**Interfaces:**
- **Consumes:** `Browser.open_worker`, `Tab`, `config.SIZES`, `config.SHOT_MAX_WIDTH`.
- **Produces:**
  - `model.SizeResult(name, scrolls: bool, overflow_px: int, offenders: list[str], shot: bytes, thumb: bytes,
    width: int, height: int)`.
  - `model.PageResult(url, final_url="", status=None, title="", hops: list[tuple[str, int]] = [],
    links: list[tuple[str, str]] = [], sizes: dict[str, SizeResult] = {}, console: list[tuple[str, str]] = [],
    exceptions: list[tuple[str, str]] = [], failed: list[tuple[str, str, str]] = [],
    insecure: list[tuple[str, str]] = [], error: str = "", seconds: float = 0.0)`.
    - In `failed`, each entry is `(url, resource type, "404" | net error | "blocked: csp")`.
    - In `insecure`, each entry is `(url, "blockable" | "optionally-blockable")`.
  - `PageVisitor(browser: Browser, tab: Tab)`, with `await visit(url) -> PageResult` and `close()`, which
    unregisters its CDP handlers.
  - `page_issues(page: PageResult, site: str) -> list[Issue]`. Third-party means the origin of the resource, or of
    the `where` URL, differs from `site`; such issues are one severity lower.
    - `page didn't load` (high): from `error`.
    - `script error` (high): from exceptions.
    - `console error` (medium): from console entries.
    - Failed resources, by resource type:
      - Script → `broken script` (high);
      - Stylesheet → `broken stylesheet` (high);
      - Image → `broken image` (medium);
      - Font → `broken font` (medium);
      - XHR/Fetch → `failed request` (medium);
      - anything else → `broken resource` (medium);
      - `blocked: csp` → `blocked by CSP` (medium).
    - Insecure content:
      - blockable → `insecure content blocked` (high);
      - optionally-blockable → `insecure content` (medium).
    - `sideways scroll`: one issue per page. Sizes are the sizes that scroll. Severity is high when mobile is among
      them, otherwise medium. Detail lists the offenders at the smallest size that scrolls.
- **`probe.js`** defines `window.__aibqa`, only if it's missing, with:
  - `links()`: `[href, text]` for `a[href]`/`area[href]` with an http(s) `href`, the first text per href, at most
    2000 links.
  - `wake()` (async):
    - makes every `img[loading=lazy]` eager;
    - scrolls in steps of `innerHeight` to the bottom (at most 12 steps, 60 ms apart), then back to the top;
    - returns the number of steps.
  - `layout()`: returns `{scrolls, overflow, offenders}`.
    - Scrolling is tested directly: `scrollTo(1e6, y)`, then `scrollX > 0`, then the scroll is restored.
    - Offenders are visible elements whose right edge is past the viewport edge (`clientWidth + 1`). They are kept
      only if they aren't `position: fixed`, and no ancestor below `<body>` has `overflow-x` hidden/clip/auto/scroll.
    - Only the outermost offenders are kept, at most 3, named `tag#id.class1.class2 "text…"` with the px past the
      edge.
    - At most 20,000 elements are scanned.
  - `title()`.
- **Visit order:**
  1. Desktop emulation (`Emulation.setDeviceMetricsOverride`, `deviceScaleFactor` 1).
  2. Arm a `Page.loadEventFired` wait, then `Page.navigate`. An `errorText` ends the visit with `error`.
  3. Wait for load (at most 15 s), then a quiet network: no request open for 500 ms, at most 3 s.
  4. `wake()`, then a quiet network for at most 2 s.
  5. Read the title and links.
  6. For each size: emulate it, settle for two animation frames (at most 300 ms), run `layout()`, take a full shot
     and a thumbnail.

  **Collectors**, keyed by `tab.session`:
  - `Network.requestWillBeSent`:
    - open requests;
    - resource type by request id;
    - document redirect hops, from a `redirectResponse` on a `Document` request (`(url, status)`);
    - `mixedContentType`.
  - `Network.responseReceived`: the main Document's status; subresources with status ≥ 400.
  - `Network.loadingFinished` closes open requests.
  - `Network.loadingFailed`: a failure, unless it was canceled or the error is `net::ERR_ABORTED` or
    `net::ERR_BLOCKED_BY_CLIENT`; `blockedReason == "csp"` records `blocked: csp`.
  - `Runtime.consoleAPICalled`, types error and assert.
  - `Runtime.exceptionThrown`.
  - `Log.entryAdded` with level error and a source other than network.

- [ ] **Step 1: Write the failing tests**

```python
@CHROME
async def test_visit_finds_planted_page_problems(chrome_browser):
    from ai_browser.qa.page import PageVisitor, page_issues

    browser, base, _ = chrome_browser
    site = base.rstrip("/")
    tab = await browser.open_worker()
    visitor = PageVisitor(browser, tab)
    try:
        contact = await visitor.visit(base + "qa/contact.html")
        kinds = {(i.severity, i.kind) for i in page_issues(contact, site)}
        assert kinds == {("medium", "console error"), ("high", "script error")}
        products = await visitor.visit(base + "qa/products.html")
        assert products.sizes["mobile"].scrolls and not products.sizes["tablet"].scrolls
        assert not products.sizes["desktop"].scrolls
        assert products.sizes["mobile"].offenders[0].startswith('div.wide-table "')
        [sideways] = page_issues(products, site)
        assert (sideways.severity, sideways.kind, sideways.sizes) == ("high", "sideways scroll", ["mobile"])
        team = await visitor.visit(base + "qa/team.html")
        [image] = page_issues(team, site)
        assert (image.severity, image.kind) == ("medium", "broken image") and "missing-photo.jpg" in image.detail
        about = await visitor.visit(base + "qa/about.html")
        assert page_issues(about, site) == [] and about.title == "About us"
        old = await visitor.visit(base + "qa/old")
        assert [status for _, status in old.hops] == [301, 301] and old.final_url == base + "qa/about.html"
        for size in ("desktop", "tablet", "mobile"):
            shot = about.sizes[size]
            assert shot.shot[:2] == b"\xff\xd8" and shot.thumb[:2] == b"\xff\xd8" and shot.width <= 1280
    finally:
        visitor.close()
        await browser.close_tab(tab)
    assert tab.key not in browser.owned


@CHROME
async def test_visit_stays_quick_on_heavy_noisy_and_dialog_pages(chrome_browser):
    from ai_browser.qa.page import PageVisitor

    browser, base, _ = chrome_browser
    tab = await browser.open_worker()
    visitor = PageVisitor(browser, tab)
    try:
        for page, limit in (("heavy.html", 6), ("qa/pending.html", 10), ("dialogs.html", 6)):
            started = time.monotonic()
            result = await visitor.visit(base + page)
            assert not result.error and time.monotonic() - started < limit, page
    finally:
        visitor.close()
        await browser.close_tab(tab)


@CHROME
async def test_worker_tabs_never_become_the_working_tab(chrome_browser):
    browser, base, _ = chrome_browser
    working = browser.current
    tab = await browser.open_worker()
    assert browser.current is working and tab.key in browser.owned
    await browser.close_tab(tab)
    assert tab.key not in browser.owned
```

- [ ] **Step 2: Run them.** Expected: FAIL (no `open_worker` and no `ai_browser.qa.page`).
- [ ] **Step 3: Implement** `Browser.open_worker`/`close_tab`, `probe.js` and `page.py` as specified.
- [ ] **Step 4: Run them**, plus `uv run pytest tests/test_chrome.py tests/test_browser_misc.py -q`. Expected: PASS.
- [ ] **Step 5: Ledger.** Add "Task 4: complete".

### Task 5: Report writer

**Files:**
- Create: `src/ai_browser/qa/report.py`
- Modify: `src/ai_browser/workfs.py`. `write_bytes(path, data: bytes) -> str` does the same no-follow write as
  `write_text`.
- Test: `tests/test_qa_report.py`, `tests/test_workfs.py`

**Interfaces:**
- **Consumes:** `model.Issue`, `PageResult`, `SizeResult`; `WorkDir.write_text`/`write_bytes`.
- **Produces:**
  - `model.QARun` (dataclass):
    - run details: `start_url`, `site`, `browser: str` ("sandbox" | "your own browser"), `started: float` (epoch),
      `seconds: float`;
    - results: `pages: list[PageResult]`, `issues: list[Issue]` (already merged), `unchecked: list[tuple[str, str]]`
      (url and reason), `not_followed: list[str]`, `more_found: int`;
    - `stopped: str = ""` (`"max_pages"`, `"time budget"` or `""`).
  - `ReportPaths(folder_sandbox, folder_host, html, csv, shots)`, all strings with `/work` paths except
    `folder_host`.
  - `write_report(work: WorkDir, run: QARun) -> ReportPaths`:
    - folder `qa/<host>[-<port>]-<YYYYmmdd-HHMMSS>/`;
    - full shots go to `shots/NN-<slug>-<size>.jpg` and are then dropped from memory (`SizeResult.shot = b""`).
  - `summary(run, paths) -> str`, in this shape:

    ```
    qa <start> — N pages in S s
    issues: H high · M medium · L low · U links couldn't be checked · F action links not followed
    1. high    broken link        https://… (404) — on 1 page, e.g. /qa/ "Old offers"
    …at most 10 numbered lines…
    report: /work/…/report.html (on this Mac: …)
    csv: /work/…/issues.csv · screenshots: /work/…/shots (N)
    ```

    Counts use the singular for 1 ("1 page", "1 link couldn't be checked"). The first line adds a note when the run
    stopped early: `(stopped at max_pages: X more pages found)` or `(stopped: time budget)`.
- **`report.html`:**
  - a single file with inline CSS;
  - the header (site, date, browser, pages, duration);
  - summary chips with the counts;
  - an issues table (severity badge, kind, detail, pages, sizes, extra);
  - "Couldn't check" and "Not followed" lists;
  - per-page cards: URL, status, seconds, three thumbnails as `data:image/jpeg;base64,…` each linking to
    `shots/…jpg`, and the page's issues.

  Every page-derived string goes through `html.escape(…, quote=True)`. Hrefs are only `http(s)` URLs (escaped) or
  relative `shots/` paths.
- **`issues.csv`:** header `severity,kind,detail,pages_count,pages,sizes,extra`, with pages joined by `" | "`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_qa_report.py
import csv
import io

from ai_browser.qa.model import Issue, PageResult, QARun, SizeResult
from ai_browser.qa.report import summary, write_report
from ai_browser.workfs import WorkDir

JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 20 + b"\xff\xd9"


def sample_run() -> QARun:
    sizes = {name: SizeResult(name, name == "mobile", 210 if name == "mobile" else 0,
                              ['div.wide-table "Wide"'] if name == "mobile" else [], JPEG, JPEG, 390, 900)
             for name in ("desktop", "tablet", "mobile")}
    page = PageResult("https://s.com/", final_url="https://s.com/", status=200,
                      title='<script>alert("x")</script> & co', sizes=sizes, seconds=1.2)
    issues = [Issue("high", "broken link", "https://s.com/missing (404)", ["https://s.com/"], extra="Old <b>offers</b>"),
              Issue("medium", "console error", 'Failed: "quoted" & <tag>', ["https://s.com/"])]
    issues += [Issue("low", "link timed out", f"https://o{n}.com/ (timeout)", ["https://s.com/"]) for n in range(12)]
    return QARun("https://s.com/", "https://s.com", "sandbox", 1_790_000_000.0, 3.4, [page], issues,
                 [("https://o.com/x", "403")], ["https://s.com/logout"], 0)


def test_report_files_escape_page_text(tmp_path):
    work = WorkDir(tmp_path / "work", "t1")
    paths = write_report(work, sample_run())
    html = work.to_host(paths.html).read_text()
    assert "<script>alert" not in html and "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; co" in html
    assert "Old &lt;b&gt;offers&lt;/b&gt;" in html and "data:image/jpeg;base64," in html
    assert 'href="shots/01-home-mobile.jpg"' in html
    rows = list(csv.reader(io.StringIO(work.to_host(paths.csv).read_text())))
    assert rows[0] == ["severity", "kind", "detail", "pages_count", "pages", "sizes", "extra"]
    assert len(rows) == 1 + 14 and rows[1][:2] == ["high", "broken link"]
    assert work.to_host(paths.shots + "/01-home-desktop.jpg").read_bytes() == JPEG


def test_summary_lists_counts_and_at_most_ten_issues(tmp_path):
    work = WorkDir(tmp_path / "work", "t1")
    run = sample_run()
    text = summary(run, write_report(work, run))
    lines = text.splitlines()
    assert lines[0].startswith("qa https://s.com/ — 1 page in 3.4 s")
    assert lines[1] == ("issues: 1 high · 1 medium · 12 low · 1 link couldn't be checked · "
                        "1 action link not followed")
    assert sum(1 for line in lines if line[:3].strip().rstrip(".").isdigit()) == 10
    assert any(line.startswith("report: /work/t1/qa/s.com-") for line in lines)
```

  In `tests/test_workfs.py`, add:

```python
def test_write_bytes_never_follows_links(work, tmp_path, monkeypatch):
    target = tmp_path / "victim"
    target.write_bytes(b"original")
    os.symlink(target, work.host_task / "shot.jpg")
    _checks_pass(monkeypatch)
    with pytest.raises(PathError, match="symbolic link"):
        work.write_bytes("shot.jpg", b"new")
    assert target.read_bytes() == b"original"
    assert work.write_bytes("shots/a.jpg", b"\xff\xd8") == "/work/t1/shots/a.jpg"
```

- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** `write_bytes`, the `QARun` dataclass in `model.py`, and `report.py`.
- [ ] **Step 4: Run them.** Expected: PASS.
- [ ] **Step 5: Ledger.** Add "Task 5: complete".

### Task 6: Runner (crawl and link-check orchestration)

**Files:**
- Create: `src/ai_browser/qa/run.py`
- Modify: `src/ai_browser/qa/__init__.py` (export `run_qa`)
- Test: `tests/test_qa_run.py` (pure `Frontier`), `tests/test_qa_browser.py` (full run)

**Interfaces:**
- **Consumes:** everything above, plus `browser.url_problem`.
- **Produces:**
  - `Frontier(site: str, max_variants: int = 5)`:
    - `mark(url)` records a URL as visited, so it is never queued.
    - `add(url, page, text) -> str`, returning `"new"`, `"seen"`, `"external"`, `"action"` or `"variant"`. Every
      call records `(page, text)` as a referrer of `url`.
    - `pop() -> str | None` returns new internal URLs in breadth-first order.
    - `links: dict[str, Link]`, where `Link(url, internal: bool, referrers: list, result: LinkResult | None = None,
      visited: bool = False)`. Action links are kept out of `links`.
    - `action: list[str]` and `variants: list[str]`.
  - `await run_qa(browser, work, url, max_pages=30, progress=None, on_tabs=None, crawl_budget=180.0,
    link_budget=60.0) -> str`.
- **Algorithm:**
  1. Validate:
     - `url_problem(url, browser.mode)` → `BrowserError`;
     - `normalize(url)` → `BrowserError("qa needs a full http(s) address")`;
     - clamp `max_pages`.
  2. Record `before = set(browser.owned)`. Open the home tab, then call `on_tabs()`. Visit the start URL with the
     home tab's visitor. If the start page fails to load, raise `BrowserError(f"could not open {url}: {error}")`
     and close the tabs. Set `site = origin(final_url)`. Report progress for page 1.
  3. Set up the frontier and add the start page's links:
     - `Frontier(site)`, with `mark` called on the start URL and its `final_url`;
     - the start page's hops, if any, become a redirect chain.
  4. Open 2 worker tabs, each with its own visitor, then call `on_tabs()`. Run the scheduler loop while there are
     URLs to visit or work in flight, `done + in_flight < max_pages`, and there is time left in the crawl budget.
     For each free worker, pop a URL and process it:
     - **Check first:** `checker.check(url, True)` on the home tab. Store the result on the link.
     - **Not a page:** if the verdict isn't `ok` or `result.page` is false, stop there.
     - **Visit:** otherwise visit the URL in the worker tab.
     - **Redirect chain:** if `len(hops) >= 2`, add `Issue("low", "redirect chain",
       f"{url} → {final_url} ({len(hops)} redirects)", referrer pages)`.
     - **Already checked:** if `final_url` was already visited, drop the page.
     - **New page:** otherwise mark it, add it to the pages, add its links to the frontier, and call
       `progress(done, max_pages, f"checked {done} of up to {max_pages} pages")`. Exceptions from `progress` are
       swallowed.
  5. Check the remaining links for at most `link_budget`:
     - unvisited internal links: `check(url, True)`;
     - external links: `check(url, False)`;
     - links left over when the budget runs out go to `unchecked` with reason `"time limit"`.
  6. Build the issues:
     - `page_issues` for each page;
     - `link_issue` for each checked link;
     - redirect chains;
     - unchecked links → `run.unchecked`, as `(url, status or error)`;
     - `merge`.
  7. Write the report and return `summary(run, paths)`.
  8. `finally`, close every owned tab not in `before` (the QA tabs and popups pages opened), drop them from
     `browser._opened`, and call `on_tabs()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_qa_run.py
from ai_browser.qa.run import Frontier


def test_frontier_order_variants_actions_and_referrers():
    frontier = Frontier("https://s.com", max_variants=2)
    assert frontier.add("https://s.com/a", "https://s.com/", "A") == "new"
    assert frontier.add("https://s.com/a#x", "https://s.com/b", "A again") == "seen"
    assert frontier.add("https://o.com/", "https://s.com/", "Partner") == "external"
    assert frontier.add("https://s.com/logout", "https://s.com/", "Log out") == "action"
    assert [frontier.add(f"https://s.com/cal?m={n}", "https://s.com/", "") for n in range(4)] == \
        ["new", "new", "variant", "variant"]
    assert [frontier.pop() for _ in range(4)] == ["https://s.com/a", "https://s.com/cal?m=0", "https://s.com/cal?m=1", None]
    assert frontier.links["https://s.com/a"].referrers == [("https://s.com/", "A"), ("https://s.com/b", "A again")]
    assert frontier.action == ["https://s.com/logout"] and not frontier.links["https://o.com/"].internal
    frontier.mark("https://s.com/b")
    assert frontier.add("https://s.com/b", "https://s.com/", "B") == "seen"
```

```python
# tests/test_qa_browser.py (add)
EXPECTED = {("high", "broken link", "qa/missing.html (404)"), ("medium", "broken link (external)", "qa/missing.html (404)"),
            ("high", "sideways scroll", "products.html"), ("medium", "console error", "Contact form failed to load"),
            ("high", "script error", "map widget crashed"), ("medium", "broken image", "missing-photo.jpg"),
            ("low", "redirect chain", "qa/old")}


def matches(issues, expected):
    """Each expected (severity, kind, text) matches exactly one issue, and nothing else is reported."""
    remaining = list(issues)
    for severity, kind, text in expected:
        hits = [i for i in remaining if (i.severity, i.kind) == (severity, kind)
                and (text in i.detail or any(text in page for page in i.pages))]
        assert len(hits) == 1, (severity, kind, text, issues)
        remaining.remove(hits[0])
    assert remaining == [], remaining


@CHROME
async def test_qa_run_finds_exactly_the_planted_problems(chrome_browser, monkeypatch):
    from ai_browser.qa import run as run_module

    browser, base, _ = chrome_browser
    captured = {}
    real_write = run_module.write_report

    def keep(work, run):
        captured["run"] = run
        return real_write(work, run)

    monkeypatch.setattr(run_module, "write_report", keep)
    working, before = browser.current, set(browser.owned)
    progress = []

    async def note(done, total, message):
        progress.append(done)

    started = time.monotonic()
    text = await run_module.run_qa(browser, browser.work, base + "qa/index.html", progress=note)
    took = time.monotonic() - started
    run = captured["run"]
    matches(run.issues, EXPECTED)
    assert [url for url, _ in run.unchecked] == [base.replace("localhost", "127.0.0.1") + "qa/forbidden"]
    assert run.not_followed == [base + "qa/logout.html"]
    opened = {page.final_url for page in run.pages}
    assert base + "qa/files/brochure.zip" not in opened and base + "qa/attachment" not in opened
    assert base + "qa/logout.html" not in opened and len(run.pages) == 6
    assert progress == list(range(1, 7)) and took < 20
    assert browser.current is working and set(browser.owned) == before
    assert text.splitlines()[1].startswith("issues: 3 high · 3 medium · 1 low")
    html = browser.work.to_host(next(line for line in text.splitlines() if line.startswith("report: "))
                                .split()[1]).read_text()
    assert "products.html" in html


@CHROME
async def test_qa_run_respects_max_pages(chrome_browser):
    from ai_browser.qa import run_qa

    browser, base, _ = chrome_browser
    text = await run_qa(browser, browser.work, base + "qa/index.html", max_pages=2)
    assert "2 pages" in text.splitlines()[0] and "stopped at max_pages" in text.splitlines()[0]


@CHROME
async def test_qa_refuses_local_files_in_the_users_own_browser(chrome_browser):
    from ai_browser.browser import BrowserError
    from ai_browser.qa import run_qa

    browser, _, _ = chrome_browser
    with pytest.raises(BrowserError, match="only web pages"):
        await run_qa(browser, browser.work, "file:///etc/hosts")
```

- [ ] **Step 2: Run them.** Expected: FAIL (no `run.py`).
- [ ] **Step 3: Implement** `run.py` as specified.
- [ ] **Step 4: Run them.** Expected: PASS. If an expected finding is missed or an extra one appears, fix the
  visitor or classification rules, never the expectation list.
- [ ] **Step 5: Ledger.** Add "Task 6: complete", with the run time of the planted site.

### Task 7: Engine, MCP tool and sandbox run

**Files:**
- Modify: `src/ai_browser/engine.py`. `async def qa(self, url, max_pages=30, progress=None) -> ToolResult` uses
  `_with_browser("qa", {"url": url, "max_pages": max_pages}, …)` and calls
  `run_qa(browser, self.work, url, max_pages, progress=progress, on_tabs=self._register)`.
- Modify: `src/ai_browser/server.py`.
  - Add a `qa(url: str, max_pages: int = 30, ctx: Context)` tool. It reports progress through
    `ctx.report_progress`, guarded so that a client without progress support is fine.
  - Add an INSTRUCTIONS line: "To QA a whole site, call qa(url) and load ai-browser:website-qa for how to verify
    and report."
- Test: `tests/test_server.py`, `tests/test_qa_sandbox.py` (marked docker)

**Interfaces:**
- **Consumes:** `run_qa`.
- **Produces:** the MCP tool `qa` (params `url`, `max_pages`). The `ctx` parameter is injected and is not part of
  the schema.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server.py (add)
async def test_qa_tool_is_listed_with_its_parameters():
    async with Client(build_server(FakeEngine)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert set(tools["qa"].input_schema["properties"]) == {"url", "max_pages"}
```

  `FakeEngine` gains `async def qa(self, url, max_pages=30, progress=None)`, returning `ToolResult("qa ok")`.

```python
# tests/test_qa_sandbox.py
import pytest

from ai_browser import testpages
from ai_browser.engine import Engine
from ai_browser.skills import Catalog

pytestmark = pytest.mark.docker


async def test_qa_runs_in_the_sandbox(tmp_path):
    engine = Engine(home=tmp_path, catalog=Catalog([], set()))
    try:
        assert "ready" in (await engine.sandbox_start(fresh=True)).text
        base, _ = testpages.serve(engine.sandboxes, engine.info)
        result = await engine.qa(base + "qa/index.html")
        lines = result.text.splitlines()
        assert lines[0].startswith("qa http://localhost:8000/qa/index.html — 6 pages")
        assert lines[1].startswith("issues: 3 high · 3 medium · 1 low · 1 link couldn't be checked")
    finally:
        await engine.close()
```

- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** `Engine.qa`, the MCP tool and the INSTRUCTIONS line. Before writing the tool,
  read how `MCPServer` injects `Context`: `mcp/server/mcpserver/tools/base.py`.
- [ ] **Step 4: Run them.** Expected: PASS.
- [ ] **Step 5: Ledger.** Add "Task 7: complete".

### Task 8: Skill, docs, real-world check, final review

**Files:**
- Create: `skills/website-qa/SKILL.md`
- Modify: `README.md` (a `qa` row in the Tools table, a "Website QA" section, a Speed row)
- Test: `tests/test_skills.py` (the project skill is found and loads)

**Interfaces:** the skill reference `ai-browser:website-qa`.

- [ ] **Step 1: Write the failing test**

```python
def test_the_website_qa_skill_ships_with_the_project():
    from ai_browser.config import project_root
    from ai_browser.skills import Catalog

    catalog = Catalog.discover(project_root() / "no-claude-home", project_root() / "no-app-support",
                               project_root() / "skills", set())
    loaded = catalog.load("ai-browser:website-qa")
    assert "qa(" in loaded and "verify" in loaded.lower()
```

- [ ] **Step 2: Run it.** Expected: FAIL (no skill).
- [ ] **Step 3: Write `SKILL.md`.**
  - Front matter: `name: website-qa`, plus a description with trigger words (QA, test, check, audit a website,
    broken links, mobile layout).
  - Sections:
    - **When to use.**
    - **Pick the browser:** the sandbox by default; `sandbox_start(profile=…)` for staging logins;
      `sandbox_start(chrome=true)` for bot-protected sites, keeping in mind that Brave Shields hides trackers.
    - **Run:** `qa(url, max_pages)` (30 by default; up to 200 for big sites; split them by section).
    - **Read the summary.**
    - **Verify before reporting:** for each high or medium issue, `open` the page; `observe(find=…)`, or
      `screenshot(size="mobile", element=…)`, for layout; open links again; drop false positives.
    - **Known false positives:** another site's scripts, links that refuse checks, pages behind a login.
    - **Client write-up template:** a summary, then issues by severity with page, size, steps and a screenshot path;
      then what was checked and what couldn't be.
    - **Fix and re-run.**
    - **Limits:** desktop user agent on mobile; no form testing; no SEO (use the seo skills for that).
- [ ] **Step 4: Run it.** Expected: PASS. Update the README.
- [ ] **Step 5: Real-world check.**
  - Run a scratch driver: `qa("https://books.toscrape.com/", max_pages=30)` in a fresh sandbox.
  - Target: 30 pages in under 2 minutes.
  - Record the time, the counts and anything surprising in the ledger. Check every high issue by hand with
    `open`/`screenshot` before calling it real.
- [ ] **Step 6: Final review.**
  - A fresh reviewer (opus) reviews `ai_browser/qa/`, the `Browser` and `WorkDir` additions, the Engine/MCP tool and
    the tests, against this plan's Review Focus and Global Constraints.
  - Fix Critical and Important findings test-first, and record Minor ones in the ledger.
  - Run the full suite and `uv run ai-browser bench`, then record "Website QA plan: COMPLETE."
