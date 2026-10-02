---
name: website-qa
description: Whole-website QA with ai-browser — crawl a site, check layout on desktop, tablet and mobile, page errors and broken links, then verify the findings and write them up for a client. Use when asked to QA, test, check or audit a website (before launch, after changes, for a client), or to find broken links, broken images, console errors or mobile layout problems.
---

# Website QA

One `qa` call checks a whole site. This playbook turns its findings into a report you can trust.

## 1. Pick the browser

qa crawls in the Docker sandbox by default, even when the session browses in the user's Brave: its tabs and link
checks stay out of the user's signed-in profile. Its result starts "checked in the Docker sandbox".

- **Sandbox (default):** neutral results, no extensions, no personal logins. QA's own sandbox (profile `qa`) stays up
  between runs; `uv run ai-browser stop qa` stops it.
- **Staging behind a login:** ask the user to log in once with `uv run ai-browser live --profile qa` (QA uses that
  login from then on), or `sandbox_start(profile="client-acme")` for a session of its own. Never type passwords
  yourself.
- **The user's own browser:** only when the user asks for their own browser (for their logins, or a site on this
  computer the sandbox can't reach): `sandbox_start(chrome=true)` first, then `qa`. Say in the report that ad and
  tracker blocking (Brave Shields, extensions) can hide third-party problems.
- **Bot checks:** if qa or open stops at a bot check, stop and tell the user. Never switch browsers, profiles or
  tools to get past it: the user solves it, or skips the site.
- **In the AI Browser app:** just run `qa`. Agents that browse in the user's Brave run it in the sandbox; with
  `ai-browser app --browser app` it uses AI Browser itself.

## 2. Run it

`qa(url="https://client-site.com", max_pages=30)`

- 30 pages take about three minutes, because qa is polite (below). A run stops visiting pages after five minutes
  and says so. A site with many links takes longer while the links qa didn't visit are checked, about six minutes
  at most. For bigger sites, run section by section (start at /blog/, /shop/…).
- It never clicks, types or submits, and never requests log-out, delete or add-to-cart style links (they are listed
  as "not followed").
- It returns counts, the top 10 issues, and the paths of `report.html` (one shareable file), `issues.csv` and the
  screenshots.

## Be polite

- `qa` goes one request at a time per site, follows robots.txt and Retry-After, and stops a site after a 429, 403 or
  bot check. The summary says where it stopped and what it didn't check.
- Never crawl from the shell: no curl loops, no `xargs -P`, no faked user agents.
- `ignore_robots=true` only when the user says the site is theirs (staging sites often tell every crawler to stay
  out). The report then says robots.txt was ignored at their request.

## 3. Verify before you report

The checks are careful, but confirm every high and medium issue yourself before telling anyone:

- **Broken link or page:** `open` the URL and see what a visitor sees. The summary names the pages that link to it
  and the link text.
- **Sideways scroll:** `open` the page, then `screenshot(size="mobile", full_page=true)`. The culprit names
  (e.g. `div.wide-table "…" — 242 px past the edge`) say which element to look at; `observe(find="…")` locates it.
- **Script and console errors:** `open` the page and read `page_log()`. Decide whether visitors notice: a broken menu
  matters, a failed analytics call usually doesn't. Errors from other sites' scripts are already ranked lower.
- **Broken images:** `open` the image URL.
- Drop anything you can't reproduce, and say that you dropped it.

## 4. Known false positives

- Sites that refuse automated checks appear under "Not checked", not as broken. So do links to big sites (Google,
  YouTube, LinkedIn…), which qa never requests, pages robots.txt asks crawlers to skip, and links on hosts that
  stopped answering (429, 403 or a bot check). Open them by hand if they matter.
- Pages behind a login look broken unless the session is logged in.
- In the user's own browser, extensions can change pages or block requests.

## 5. Write it up for the client

Use this shape; keep it short and concrete:

> **Website QA — client-site.com (2 Oct 2026)**
> Checked 30 pages on desktop, tablet and mobile, and every link.
> **Fix first (high):** 1. … — page, screen size, what happens, how to fix it.
> **Should fix (medium):** …
> **Nice to fix (low):** …
> **Not checked:** links to big sites (Google, YouTube…), pages robots.txt asks crawlers to skip, hosts that stopped
> answering; anything behind a login; forms.
> Full report with screenshots: report.html (attached).

- Lead with what visitors experience, not technical detail.
- One line per issue: where, which screen, what's wrong, the fix.
- Send `report.html`: the summary, issues and thumbnails are inside the file. Zip the whole report folder to include
  the full-page screenshots. `issues.csv` imports into Sheets or ClickUp.

## 6. After fixes

Run `qa` again on the same URL and compare the counts. Say what is fixed and what is left.

## Limits

- Tablet and mobile use the desktop browser at those screen sizes (no mobile user agent).
- Forms and checkouts aren't tested, because QA never submits. Test them with the user.
- No SEO checks: use the seo skills for that.
- Frames from other sites, canvas content, and content that needs clicks to appear aren't inspected.
