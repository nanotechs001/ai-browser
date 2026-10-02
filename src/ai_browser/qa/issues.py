"""Turn link results and page findings into ranked issues, merging the same problem across pages."""

from __future__ import annotations

from .model import SEVERITY_ORDER, Issue, LinkResult

_REFUSED = {401, 403, 429, 999}  # the site turned the check away; that says nothing about the link
_TIMEOUTS = {"timeout", "net::ERR_TIMED_OUT", "net::ERR_CONNECTION_TIMED_OUT"}
_BROKEN = {"net::ERR_NAME_NOT_RESOLVED", "net::ERR_CONNECTION_REFUSED", "net::ERR_CONNECTION_RESET",
           "net::ERR_CONNECTION_CLOSED", "net::ERR_ADDRESS_UNREACHABLE", "net::ERR_EMPTY_RESPONSE",
           "net::ERR_TOO_MANY_REDIRECTS", "net::ERR_INVALID_RESPONSE"}
# verdict -> (severity, kind) for links within the site, then for links to other sites
_LINK_KINDS = {
    "broken": (("high", "broken link"), ("medium", "broken link (external)")),
    "server error": (("high", "server error"), ("medium", "server error")),
    "timeout": (("low", "link timed out"), ("low", "link timed out")),
}


def link_verdict(result: LinkResult) -> str:
    """ok · broken · server error · timeout · unchecked (the site refused the check, or the browser blocked it)."""
    error = result.error or ""
    if error in _TIMEOUTS:
        return "timeout"
    if result.status is not None:
        status = result.status
        if 200 <= status < 400:
            return "ok"
        if status in (404, 410):
            return "broken"
        if status in _REFUSED or (status == 503 and (result.challenge or result.retry_after is not None)):
            return "unchecked"  # refused, or "come back later": that says nothing about the link
        if 500 <= status < 600:
            return "server error"
        return "unchecked"
    if error in _BROKEN or error.startswith(("net::ERR_CERT_", "net::ERR_SSL_")):
        return "broken"
    return "unchecked"


def link_issue(result: LinkResult, internal: bool, referrers: list[tuple[str, str]]) -> Issue | None:
    """The issue a checked link amounts to, or None when it is fine or could not be judged."""
    verdict = link_verdict(result)
    if verdict not in _LINK_KINDS:
        return None
    severity, kind = _LINK_KINDS[verdict][0 if internal else 1]
    why = str(result.status) if result.status is not None and verdict != "timeout" else result.error or verdict
    pages = list(dict.fromkeys(page for page, _ in referrers))
    extra = next((text for _, text in referrers if text), "")
    return Issue(severity, kind, f"{result.url} ({why})", pages, extra=extra)


def lower(severity: str) -> str:
    """One step less severe (for problems caused by another site's code)."""
    return {"high": "medium", "medium": "low"}.get(severity, "low")


def merge(issues: list[Issue]) -> list[Issue]:
    """One issue per (kind, detail): pages and sizes united, the highest severity kept; most important first."""
    merged: dict[tuple[str, str], Issue] = {}
    for issue in issues:
        kept = merged.get((issue.kind, issue.detail))
        if kept is None:
            merged[(issue.kind, issue.detail)] = Issue(issue.severity, issue.kind, issue.detail, list(issue.pages),
                                                       list(issue.sizes), issue.extra)
            continue
        kept.pages += [page for page in issue.pages if page not in kept.pages]
        kept.sizes += [size for size in issue.sizes if size not in kept.sizes]
        if SEVERITY_ORDER[issue.severity] < SEVERITY_ORDER[kept.severity]:
            kept.severity = issue.severity
        kept.extra = kept.extra or issue.extra
    return sorted(merged.values(), key=lambda issue: issue.rank)
