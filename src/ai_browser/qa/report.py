"""Write the QA report (report.html as one shareable file, issues.csv, full-page screenshots) and its summary."""

from __future__ import annotations

import base64
import csv
import html
import io
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..checks import site_key
from ..workfs import WorkDir
from .model import SITE_STOPPED, Issue, PageResult, QARun
from .polite import BIG_SITE_NOTE, ROBOTS_FOLLOWED, ROBOTS_NOTE, SKIPPED_NOTE
from .urls import slug

TOP = 10  # issues listed in the summary
_FORMULA = ("=", "+", "-", "@", "\t", "\r")  # spreadsheet apps would run these as formulas


@dataclass
class ReportPaths:
    folder_sandbox: str
    folder_host: str
    html: str
    csv: str
    shots: str


def folder_for(site: str, started: float) -> str:
    """The run's folder in the work folder: qa/<host>[-<port>]-<YYYYmmdd-HHMMSS>."""
    parts = urlsplit(site)
    name = (parts.hostname or "site") + (f"-{parts.port}" if parts.port else "")
    return f"qa/{name}-{time.strftime('%Y%m%d-%H%M%S', time.localtime(started))}"


def _shot_name(number: int, page: PageResult, size: str) -> str:
    return f"shots/{number:02d}-{slug(page.final_url or page.url)}-{size}.jpg"


def save_shots(work: WorkDir, folder: str, number: int, page: PageResult) -> None:
    """Write a page's full-page screenshots and drop them from memory (a long run would hold hundreds of MB)."""
    for size, result in page.sizes.items():
        if result.shot:
            work.write_bytes(f"{folder}/{_shot_name(number, page, size)}", result.shot)
            result.shot = b""


def write_report(work: WorkDir, run: QARun) -> ReportPaths:
    """Save any screenshots still in memory, report.html and issues.csv in the run's folder."""
    folder = folder_for(run.site, run.started)
    shots: dict[tuple[int, str], str] = {}
    for number, page in enumerate(run.pages, 1):
        save_shots(work, folder, number, page)
        for size in page.sizes:
            shots[(number, size)] = _shot_name(number, page, size)
    html_path = work.write_text(f"{folder}/report.html", _html(run, shots))
    csv_path = work.write_text(f"{folder}/issues.csv", _csv(run))
    folder_sandbox = work.to_sandbox(folder)
    return ReportPaths(folder_sandbox, str(work.to_host(folder)), html_path, csv_path, folder_sandbox + "/shots")


def summary(run: QARun, paths: ReportPaths) -> str:
    """What the tool returns: counts, the top issues and where the report is."""
    first = f"qa {run.start_url} — {_count(len(run.pages), 'page')} in {run.seconds:.1f} s"
    if run.stopped == "max_pages":
        first += f" (stopped at max_pages: {run.more_found} more pages found)" if run.more_found else \
            " (stopped at max_pages)"
    elif run.stopped == SITE_STOPPED:
        first += " (stopped early)"
    elif run.stopped:
        first += f" (stopped: {run.stopped})"
    counts = _severities(run.issues)
    lines = [first, f"issues: {counts['high']} high · {counts['medium']} medium · {counts['low']} low · "
                    f"{_count(len(run.unchecked), 'link')} couldn't be checked · "
                    f"{_count(len(run.not_followed), 'action link')} not followed"]
    for number, issue in enumerate(run.issues[:TOP], 1):
        lines.append(f"{number}. {issue.severity:<7} {issue.kind:<18} {issue.detail}{_where(issue)}")
    if len(run.issues) > TOP:
        lines.append(f"… {len(run.issues) - TOP} more in the report")
    shots = sum(len(page.sizes) for page in run.pages)
    lines.append(f"report: {paths.html} (on this Mac: {paths.folder_host}/report.html)")
    lines.append(f"csv: {paths.csv} · screenshots: {paths.shots} ({shots})")
    lines += _notes(run)
    return "\n".join(lines)


def _notes(run: QARun) -> list[str]:
    """After the usual lines: robots.txt unless simply followed, where QA stopped early, what it didn't check."""
    lines = []
    if run.robots and run.robots != ROBOTS_FOLLOWED:
        lines.append(run.robots)
    host = urlsplit(run.site).hostname or ""
    why = run.stopped_hosts.get(host)
    if why:
        lines.append(f"stopped early: {host} {why}, so QA stopped after {_count(len(run.pages), 'page')}")
    parts = _not_checked(run.unchecked)
    if parts:
        lines.append("not checked: " + ", ".join(parts))
    return lines


def _not_checked(unchecked: list[tuple[str, str]]) -> list[str]:
    skipped = [url for url, why in unchecked if why == SKIPPED_NOTE]
    big = [url for url, why in unchecked if why == BIG_SITE_NOTE]
    robots = [url for url, why in unchecked if why == ROBOTS_NOTE]
    refused = [why.removeprefix("not checked: ") for _, why in unchecked
               if why.startswith("not checked: ") and " refused (" in why]
    parts = []
    if skipped:
        sites = list(dict.fromkeys(site_key(url) for url in skipped))
        parts.append(f"{_count(len(skipped), 'link')} to sites the user skipped ({', '.join(sites)})")
    if big:
        sites = list(dict.fromkeys(site_key(url) for url in big))
        more = "…" if len(sites) > 2 else ""
        parts.append(f"{_count(len(big), 'link')} to big sites ({', '.join(sites[:2])}{more})")
    if robots:
        parts.append(f"{_count(len(robots), 'page')} robots.txt asks crawlers to skip")
    if refused:
        hosts = dict.fromkeys(text.replace(" refused (", ": ").rstrip(")") for text in refused)
        parts.append(f"{_count(len(refused), 'link')} on hosts that refused ({', '.join(hosts)})")
    return parts


def _reason(why: str) -> str:
    if why.startswith("not checked: "):
        return why.removeprefix("not checked: ")
    return f"the site turned the check away, or the browser blocked it ({why})"


def _grouped(unchecked: list[tuple[str, str]]) -> str:
    """The "Not checked" list, grouped by reason."""
    groups: dict[str, list[str]] = {}
    for url, why in unchecked:
        groups.setdefault(_reason(why), []).append(url)
    if not groups:
        return '<ul class="plain"><li class="none">None.</li></ul>'
    return "".join(f"<h3>{_e(reason)}</h3><ul class=\"plain\">{''.join(f'<li>{_link(url)}</li>' for url in urls)}</ul>"
                   for reason, urls in groups.items())


def _count(number: int, word: str) -> str:
    return f"{number} {word}{'' if number == 1 else 's'}"


def _severities(issues: list[Issue]) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for issue in issues:
        counts[issue.severity] += 1
    return counts


def _short(url: str) -> str:
    parts = urlsplit(url)
    return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


def _where(issue: Issue) -> str:
    bits = []
    if issue.sizes:
        bits.append("on " + "/".join(issue.sizes))
    if issue.pages:
        first = _short(issue.pages[0])
        bits.append(f"at {first}" if len(issue.pages) == 1 else f"on {len(issue.pages)} pages, e.g. {first}")
    if issue.extra:
        bits.append(issue.extra.rsplit("/", 1)[-1] if issue.extra.startswith("http") else f'"{issue.extra}"')
    return " — " + ", ".join(bits) if bits else ""


def _csv(run: QARun) -> str:
    def cell(value) -> str:
        text = str(value)
        return "'" + text if text.startswith(_FORMULA) else text

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["severity", "kind", "detail", "pages_count", "pages", "sizes", "extra"])
    for issue in run.issues:
        writer.writerow([cell(issue.severity), cell(issue.kind), cell(issue.detail), len(issue.pages),
                         cell(" | ".join(issue.pages)), cell(" ".join(issue.sizes)), cell(issue.extra)])
    return buffer.getvalue()


# ---- report.html ------------------------------------------------------------------------------------------

def _e(text) -> str:
    return html.escape(str(text), quote=True)


def _link(url: str, text: str | None = None) -> str:
    """A link only for web addresses; anything else is shown as plain text."""
    label = _e(text if text is not None else url)
    return f'<a href="{_e(url)}">{label}</a>' if url.startswith(("http://", "https://")) else label


def _issue_row(issue: Issue) -> str:
    pages = ", ".join(_link(page, _short(page)) for page in issue.pages[:3])
    if len(issue.pages) > 3:
        pages += f" and {len(issue.pages) - 3} more"
    extra = f'<div class="pages">{_e(issue.extra)}</div>' if issue.extra else ""
    sizes = f'<div class="pages">{_e(" / ".join(issue.sizes))}</div>' if issue.sizes else ""
    return (f'<tr><td><span class="sev {_e(issue.severity)}">{_e(issue.severity)}</span></td>'
            f"<td>{_e(issue.kind)}</td><td class=\"detail\">{_e(issue.detail)}{extra}</td>"
            f'<td class="pages">{pages}{sizes}</td></tr>')


def _page_card(number: int, page, issues: list[Issue], shots: dict[tuple[int, str], str]) -> str:
    url = page.final_url or page.url
    figures = []
    for size, result in page.sizes.items():
        thumb = base64.b64encode(result.thumb).decode() if result.thumb else ""
        image = f'<img src="data:image/jpeg;base64,{thumb}" alt="{_e(size)} view">' if thumb else ""
        figures.append(f'<figure><a href="{_e(shots[(number, size)])}">{image}</a>'
                       f"<figcaption>{_e(size)} · full page</figcaption></figure>")
    found = [issue for issue in issues if url in issue.pages]
    listed = "".join(f'<li><span class="sev {_e(i.severity)}">{_e(i.severity)}</span> {_e(i.kind)}: {_e(i.detail)}</li>'
                     for i in found) or '<li class="none">No problems found on this page.</li>'
    status = f" · HTTP {page.status}" if page.status else ""
    return (f'<section class="card"><h3>{number}. {_e(page.title or _short(url))}</h3>'
            f'<div class="pages">{_link(url)}{_e(status)} · checked in {page.seconds:.1f} s</div>'
            f'<div class="thumbs">{"".join(figures)}</div><ul class="plain">{listed}</ul></section>')


def _html(run: QARun, shots: dict[tuple[int, str], str]) -> str:
    counts = _severities(run.issues)
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(run.started))
    stopped = " · stopped early" if run.stopped == SITE_STOPPED else \
        f" · stopped early ({_e(run.stopped)})" if run.stopped else ""
    notes = "".join(f'<p class="meta">{_e(line)}</p>' for line in _notes(run))
    rows = "".join(_issue_row(issue) for issue in run.issues) or \
        '<tr><td colspan="4" class="none">No issues found.</td></tr>'
    skipped = "".join(f"<li>{_link(url)}</li>" for url in run.not_followed)
    cards = "".join(_page_card(number, page, run.issues, shots) for number, page in enumerate(run.pages, 1))
    chips = "".join(f'<div class="chip"><b>{value}</b>{_e(label)}</div>' for label, value in (
        ("pages checked", len(run.pages)), ("high", counts["high"]), ("medium", counts["medium"]),
        ("low", counts["low"]), ("links not checkable", len(run.unchecked))))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Website QA — {_e(urlsplit(run.site).netloc)}</title>
<style>
:root {{ --fg: #1d2330; --muted: #5f6b7a; --line: #e3e7ee; --card: #f7f9fc; --high: #c62828; --medium: #a35f00;
  --low: #3f6597; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: var(--fg);
  background: #fff; }}
main {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 64px; }}
h1 {{ font-size: 24px; margin: 0 0 4px; }}
h2 {{ font-size: 18px; margin: 32px 0 12px; }}
a {{ color: #1f5fbf; }}
.meta, .pages, .none {{ color: var(--muted); }}
.pages {{ font-size: 13px; }}
.chips {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 20px 0; }}
.chip {{ border: 1px solid var(--line); border-radius: 8px; padding: 8px 14px; background: var(--card); }}
.chip b {{ display: block; font-size: 20px; }}
.sev {{ display: inline-block; min-width: 64px; padding: 1px 6px; border-radius: 4px; color: #fff; font-size: 12px;
  font-weight: 600; text-align: center; text-transform: uppercase; }}
.sev.high {{ background: var(--high); }} .sev.medium {{ background: var(--medium); }} .sev.low {{ background: var(--low); }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
td.detail {{ word-break: break-word; }}
.card {{ margin: 0 0 16px; padding: 16px; border: 1px solid var(--line); border-radius: 10px; background: var(--card); }}
.card h3 {{ margin: 0; font-size: 16px; }}
.card .pages {{ word-break: break-all; }}
.thumbs {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; margin: 12px 0; }}
.thumbs figure {{ margin: 0; }}
.thumbs img {{ display: block; max-width: 320px; border: 1px solid var(--line); border-radius: 4px; }}
.thumbs figcaption {{ color: var(--muted); font-size: 12px; }}
ul.plain {{ margin: 0; padding-left: 18px; }}
@media print {{ .card {{ break-inside: avoid; }} }}
</style>
</head>
<body>
<main>
<h1>Website QA report</h1>
<p class="meta">{_link(run.start_url)} · {_e(when)} · {_e(run.browser)} · {len(run.pages)} pages in {run.seconds:.0f} s{stopped}</p>
{notes}
<div class="chips">{chips}</div>
<h2>Issues, most important first</h2>
<table><thead><tr><th>Severity</th><th>Problem</th><th>Details</th><th>Where</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Not checked</h2>
<p class="pages">Big sites QA leaves alone, pages robots.txt asks crawlers to skip, hosts that refused, and sites that turned the check away. Open them by hand if they matter.</p>
{_grouped(run.unchecked)}
<h2>Links not followed</h2>
<p class="pages">These look like actions (log out, delete, add to cart…), so the check never opened them.</p>
<ul class="plain">{skipped or '<li class="none">None.</li>'}</ul>
<h2>Pages checked</h2>
<p class="pages">Each page at desktop (1440 px), tablet (768 px) and mobile (390 px). Click a picture for the full page.</p>
{cards}
</main>
</body>
</html>
"""
