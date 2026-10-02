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
