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
