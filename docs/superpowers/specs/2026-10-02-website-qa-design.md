# ai-browser — Website QA (project 2, first skill)

Date: 2026-10-02 · Status: design approved in chat; the user approved going from spec to plan to build in one go
("yeah do the thing to proceed, you have my permission").

## Goal

One tool call checks a whole website the way a careful QA person would, and leaves a report a client can read:

- **layout** on desktop, tablet and mobile;
- **errors** in the page;
- **broken links**.

A skill holds the playbook for running it, checking findings and writing them up.

What the user chose:
- website QA first;
- the whole site, crawled automatically;
- checks: layout on 3 screens, plus errors and broken links;
- output: HTML report plus CSV (no PDF, Sheets or ClickUp).

## Decisions

- **Tool:** `qa(url, max_pages=30)` (MCP and `Engine.qa`).
  - It runs in whichever browser the session uses: a sandbox profile, a throwaway sandbox, or the user's own
    browser. Staging sites behind a login therefore work.
  - It returns a short text summary, never images, to keep tokens down.
- **Its own tabs:**
  - a *home* tab opens the start page and then stays there to run link checks;
  - two *worker* tabs crawl the other pages in parallel.
  - The working tab (`browser.current`) is never touched. QA tabs, and any popups pages open from them, are
    closed when the run ends.
  - In the user's own browser all QA tabs are background tabs.
- **Crawl:**
  - **Order and scope:** breadth-first from the start URL. Internal means the same origin as the start page
    after its redirects.
  - **Limits:** `max_pages` is clamped to 1–200. The time budget is 240 s; when it runs out, the report covers
    what was done and says so.
  - **Page count:** `max_pages` counts distinct pages opened and checked, by final URL after redirects. A redirect
    that lands on an already-checked page doesn't count again.
  - **URLs:** fragments are dropped. At most 5 query variants per path are crawled; further variants are only
    status-checked.
  - **Nothing on the site is changed:** QA never clicks, types or submits.
  - **Action links** are neither followed nor requested, and the report lists them as "not followed". These are
    internal links whose path, query or text looks like an action: log out / sign out, delete, remove, trash,
    unsubscribe, add-to-cart, `wp-admin`, `wp-login.php`, or query keys `action`, `_wpnonce`, `nonce`, `token`.
- **No downloads:**
  - Before opening an internal page (other than the start URL), the home tab requests it and reads its status
    and headers. Only HTML that isn't an attachment is opened; files are only status-checked.
  - Measured on 2026-10-02: Chrome's per-page download "deny" also blocks other tabs, so it would change the
    user's own browser. It is not used.
- **Link checks run in the browser:** `Network.loadNetworkResource` from the home tab. Measured, it:
  - reaches what the pages reach, including sandbox-local and Mac-local sites, cross-origin too;
  - follows redirects and returns the status or a network error name;
  - stops a big file after the headers (a 300 MB file took 0.5 s).

  Rules:
  - internal links send cookies; external links don't;
  - at most 2 requests per host and 8 overall at a time;
  - 12 s timeout each.
- **Per page:**
  1. Open the page; wait for `load` (at most 15 s) and then a quiet network (at most 3 s).
  2. Wake lazy content: lazy images become eager, and a short scroll runs down the page and back.
  3. For each size, desktop 1440×900, tablet 768×1024 and mobile 390×844:
     - emulate the size;
     - check whether the page scrolls sideways, and name up to 3 outermost elements that stick out;
     - take a full-page JPEG (up to 8000 CSS px tall, at most 1280 px wide) and a viewport thumbnail of about
       320 px.
- **Errors come from the page's own events:**
  - console errors and uncaught exceptions;
  - subresources that fail or return ≥400, sorted by type (script, stylesheet, image, font, API request, other);
  - mixed content (`http://` on an `https://` page) and requests blocked by mixed content or CSP.

  Not reported, as noise: warnings, and requests that were canceled or blocked by the browser's own ad or
  tracker blocking (`ERR_ABORTED`, `ERR_BLOCKED_BY_CLIENT`; Brave Shields does this).
- **Redirect chains:** measured on pages that are opened, where every hop is visible. Other links report only
  their final status.
- **One problem, one issue:** the same problem on many pages becomes one issue with a page list, for example a
  broken footer image.
- **Report:** saved under `qa/<host>-<YYYYmmdd-HHMMSS>/` in the task's work folder.
  - `report.html` is self-contained and shareable as one file. It has:
    - a summary;
    - issues ranked by severity;
    - "couldn't check" and "not followed" lists;
    - per-page cards with embedded thumbnails that link to the full shots.

    All text taken from pages is HTML-escaped.
  - `issues.csv` has one row per issue.
  - `shots/` holds the full-page JPEGs.
- **Progress:** an MCP progress notification after each page.
- **Skill** `ai-browser:website-qa` (`skills/website-qa/SKILL.md`) covers:
  - when to run `qa`, and with which browser;
  - checking findings with `open`, `observe` and `screenshot` before reporting them;
  - a write-up template for clients;
  - re-running after fixes.

## Severity

| Finding | Severity |
|---|---|
| Internal link or page returning 404/410 or unreachable; uncaught exception; script or stylesheet failing; page scrolls sideways on mobile; insecure content blocked | high |
| Broken image; console error; API request or other resource failing; broken external link; external link with a server error; sideways scroll on tablet or desktop; insecure (`http://`) content allowed on an `https://` page; request blocked by CSP | medium |
| Redirect chain (2+ hops) on an opened page; link timed out; errors from another site's scripts (one step lower than the same error from the site itself) | low |
| External link refused by its site (401/403/429/999, bot challenge), other unexpected 4xx, blocked by the browser, unsafe port | not an issue: listed under "couldn't check" |

## Interfaces

- `ai_browser/qa/` package:
  - **`urls.py`:** `normalize(url) -> str | None`, `origin(url)`, `action_link(url, text) -> bool`,
    `is_file(url) -> bool`, `slug(url) -> str`.
  - **`issues.py`:**
    - `Issue(severity, kind, detail, pages, sizes, extra)`;
    - `link_verdict(status, net_error) -> verdict`;
    - `merge(issues) -> list[Issue]` (merged and ranked).
  - **`checker.py`:** `LinkChecker(cdp, session, frame)`, with `await check(url, credentials) -> LinkResult`.
  - **`probe.js` + `page.py`:** `PageVisitor(browser, tab)`, with `await visit(url) -> PageResult`, holding:
    - status and redirect hops;
    - links (href, text);
    - per-size layout and shots;
    - errors.
  - **`report.py`:** `write_report(work, run) -> ReportPaths`, `summary(run, paths) -> str`.
  - **`run.py`:** `await run_qa(browser, work, url, max_pages, progress=None, on_tabs=None) -> str`.
- **Changes elsewhere:**
  - `Browser.open_worker() -> Tab`: a background tab, owned and registered, but not made current;
  - `Browser.close_tab(tab)`;
  - `WorkDir.write_bytes(path, data)`: a no-follow write, like `write_text`;
  - `Engine.qa(url, max_pages=30, progress=None)`;
  - MCP tool `qa(url, max_pages=30)`, which reports progress through the request context.
- **Test servers:** the test page servers (host-side `testpages` and in-sandbox `pages/_serve.py`) share one
  handler with three extra routes:
  - `/qa/old` → `/qa/older` → `/qa/about.html`, a 2-hop redirect chain;
  - `/qa/forbidden` → 403.

## Testing

- **Unit tests:**
  - URL rules, the action-link filter and link verdicts;
  - merging and ranking;
  - report escaping (page text is untrusted), the CSV and the summary.
- **Planted test site** `pages/qa/`, served on `localhost`. Its "external" site is the same server reached as
  `127.0.0.1`, which is a different origin. It holds exactly these findings:
  - **high:** broken internal link (`missing.html`, 404);
  - **medium:** broken external link (404);
  - **high:** mobile sideways scroll on `products.html`, naming `div.wide-table`;
  - **medium:** console error, and **high:** uncaught exception, both on `contact.html`;
  - **medium:** broken image on `team.html`;
  - **low:** redirect chain `old → older → about.html`;
  - **couldn't check:** one external 403;
  - **not followed:** one action link ("Log out").

  Traps that must stay silent:
  - a 1-hop directory redirect (`blog` → `blog/`);
  - lazy images;
  - a wide table inside a scrolling box;
  - a `.zip` link, which is status-checked but never opened.

  A QA run must report exactly the planted findings.
- **Integration runs:**
  - your own browser's mode, with a throwaway headless Chrome: findings, report files, summary, no tabs left open;
  - sandbox mode (Docker): the same site served inside the sandbox.
- **Speed:**
  - the planted site in under 20 s;
  - a real-world run on `books.toscrape.com`, a site made for crawler practice: 30 pages in under 2 minutes.
