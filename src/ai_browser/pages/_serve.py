"""Static server for the test pages that forbids caching, so edited pages are always fresh.

It also answers the few routes the QA test site needs: a two-hop redirect chain, a 403, a request that stays open
and an HTML page sent as a download. The host-side test server (testpages.py) loads this same handler."""

import http.server
import sys
import time

REDIRECTS = {"/qa/old": "/qa/older", "/qa/older": "/qa/about.html"}
_FLAKY = {"requests": 0}


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
        return False


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), NoStore).serve_forever()
