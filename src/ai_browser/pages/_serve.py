"""Static server for the test pages that forbids caching, so edited pages are always fresh.

It also answers the few routes the tests need: a download that takes a few seconds (/downloads/bigfile) and, for the
bot-check tests, a site's own "Just a moment..." page (403), the inside of a check frame, and a redirect to another
test page. The host-side test server (testpages.py) loads this same handler."""

import http.server
import sys
import time
from urllib.parse import parse_qs, urlsplit

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
        if path == "/downloads/bigfile":  # a download that takes a few seconds
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
        if path in ("/checks/cf", "/checks/cf-auto"):  # a site's own "Just a moment..." (cf-auto moves on by itself)
            script = MOVES_ON if path == "/checks/cf-auto" else ""
            self._send(403, JUST_A_MOMENT.format(script=script).encode())
            return True
        if path in CHECK_FRAMES:  # the inside of a check frame: the reader never looks in here
            if "slow=1" in self.path:  # a box from afar, still loading while the page is read
                time.sleep(2)
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
