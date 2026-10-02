"""Static server for the test pages that forbids caching, so edited pages are always fresh.

It also answers the few routes the tests need. For the QA test site: a two-hop redirect chain, a 403, a request that
stays open and an HTML page sent as a download, and a link-rich site (/qa3/). For the bot-check tests: a site's own
"Just a moment..." page (403), the inside of a check frame, and a redirect to another test page. The host-side test
server (testpages.py) loads this same handler."""

import http.server
import sys
import time
from urllib.parse import parse_qs, urlsplit

REDIRECTS = {"/qa/old": "/qa/older", "/qa/older": "/qa/about.html"}
_FLAKY = {"requests": 0}
_LATER = {"requests": 0}
CHECK_FRAMES = {"/checks/recaptcha/api2/bframe", "/checks/recaptcha/api2/anchor"}
JUST_A_MOMENT = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Just a moment...</title></head><body>'
    '<div id="challenge-stage"></div><p>This local test page stands in for a site\'s own check: it answers 403 and '
    "waits, the way such pages do while they look at the browser. There is nothing to solve here, and ai-browser's "
    "tests use it only to check that the agent waits a few seconds, then hands the page to the user.</p>{script}"
    "</body></html>")
MOVES_ON = '<script>setTimeout(() => location.replace("/checks/counter.html"), 1000);</script>'


class NoStore(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass

    def do_GET(self):
        if not self._route():
            super().do_GET()

    def do_HEAD(self):
        if not self._route():
            super().do_HEAD()

    def _send(self, status: int, body: bytes, headers=()) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        if self.command == "GET":
            self.wfile.write(body)

    def _route(self) -> bool:
        path = self.path.split("?", 1)[0]
        if path in REDIRECTS:
            self.send_response(301)
            self.send_header("Location", REDIRECTS[path])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        if path == "/qa/flaky":  # slow on every other request, like a server that hiccups
            _FLAKY["requests"] += 1
            if _FLAKY["requests"] % 2:
                time.sleep(3)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        if path == "/qa/elsewhere":  # a link on the site that leads to another site
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_address[1]}/qa/about.html")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        if path == "/qa/bigfile":  # a download that takes a few seconds
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="setup.dmg"')
            self.send_header("Content-Length", str(64 * 1024 * 300))
            self.end_headers()
            try:
                for _ in range(300):
                    self.wfile.write(b"x" * 64 * 1024)
                    time.sleep(0.01)
            except OSError:  # the browser cancelled it
                pass
            return True
        if path == "/qa/forbidden":  # a site that refuses automated checks
            self.send_error(403)
            return True
        if path == "/qa/slow":  # a request that stays open, like long polling
            time.sleep(20)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        if path == "/qa/attachment":  # an HTML page sent as a download
            body = b"<title>Terms</title>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Disposition", 'attachment; filename="terms.html"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command == "GET":
                self.wfile.write(body)
            return True
        if path == "/qa2/busy":  # a site that asks for a two-minute pause
            self._send(429, b"<!doctype html><title>Too many requests</title><p>Slow down, please.</p>",
                       headers=[("Retry-After", "120")])
            return True
        if path == "/qa2/later":  # unavailable for a second on its first request, fine after that
            _LATER["requests"] += 1
            if _LATER["requests"] == 1:
                self._send(503, b"<!doctype html><title>Back soon</title><p>Back in a second.</p>",
                           headers=[("Retry-After", "1")])
            else:
                self._send(200, b"<!doctype html><title>Later</title><p>Back again: this page loads fine now.</p>")
            return True
        if path.startswith("/qa3/"):  # a link-rich site: /qa3/<width>/<n>.html links <width> pages of its own
            parts = path.split("/")
            try:
                width, number = int(parts[2]), int(parts[3].removesuffix(".html"))
            except (IndexError, ValueError):
                width = number = -1
            if not (1 <= width <= 100 and 0 <= number < 1_000_000 and parts[3].endswith(".html")):
                self.send_error(404)
                return True
            links = "".join(f'<li><a href="{number * width + i}.html">Page {number * width + i}</a></li>'
                            for i in range(1, width + 1))
            self._send(200, (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Page {number}</title>'
                             f'</head><body><h1>Page {number}</h1><p><a href="0.html">Home</a></p><ul>{links}</ul>'
                             "</body></html>").encode())
            return True
        if path in ("/checks/cf", "/checks/cf-auto"):  # a site's own "Just a moment..." (cf-auto moves on by itself)
            script = MOVES_ON if path == "/checks/cf-auto" else ""
            self._send(403, JUST_A_MOMENT.format(script=script).encode())
            return True
        if path in CHECK_FRAMES:  # the inside of a check frame: the reader never looks in here
            self._send(200, b"<!doctype html><title>Check frame</title><p>A test frame.</p>")
            return True
        if path == "/checks/go":  # a redirect to another of the test pages (never anywhere else)
            target = parse_qs(urlsplit(self.path).query).get("to", [""])[0]
            try:  # by host, not prefix: http://127.0.0.1:80@evil.example/ starts the same and goes elsewhere
                parts = urlsplit(target)
                local = parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1") and bool(parts.port)
            except ValueError:
                local = False
            if not local:
                self.send_error(400)
                return True
            self.send_response(302)
            self.send_header("Location", target)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        return False


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), NoStore).serve_forever()
