"""AI Browser's window, as the app server sees it, for tests that need it without a browser: the window's cookie
(aib_ui_<port>, set by swapping a one-time code), and from Task 9 a socket with that cookie and our exact Origin."""


def ui_cookie(server) -> dict:
    """The Cookie header AI Browser's window sends on every request (httpx takes it as a header)."""
    return {"Cookie": f"aib_ui_{server.port}={server.ui_secret}"}
