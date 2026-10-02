import http.client
from urllib.parse import urlsplit

from ai_browser import testpages


def _get(url: str) -> http.client.HTTPResponse:
    parts = urlsplit(url)
    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=5)
    conn.request("GET", parts.path + (f"?{parts.query}" if parts.query else ""))
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


def test_host_server_has_the_bot_check_routes():
    from urllib.parse import quote

    base, _, stop = testpages.serve_host()
    try:
        page = _get(base + "checks/cf")
        assert page.status == 403 and b"Just a moment..." in page.read()
        assert b"location.replace" in _get(base + "checks/cf-auto").read()
        assert _get(base + "checks/recaptcha/api2/bframe?hl=en").status == 200
        go = _get(base + "checks/go?to=" + quote(base + "checks/counter.html", safe=""))
        assert go.status == 302 and go.getheader("Location") == base + "checks/counter.html"
        assert _get(base + "checks/go?to=" + quote("https://example.com/", safe="")).status == 400
        assert _get(base + "checks/go?to=" + quote("http://127.0.0.1:80@evil.example/", safe="")).status == 400
    finally:
        stop()
