"""AI Browser's window, as the app server sees it, for tests that need it without a browser: the window's cookie
(aib_ui_<port>, set by swapping a one-time code), and from Task 9 a socket with that cookie and our exact Origin."""

from websockets.asyncio.client import connect


def ui_cookie(server) -> dict:
    """The Cookie header AI Browser's window sends on every request (httpx takes it as a header)."""
    return {"Cookie": f"aib_ui_{server.port}={server.ui_secret}"}


def ui_socket(server, url, cookie=True, origin="", secret=None):
    """A socket on /ws as AI Browser's window opens it: the cookie, our exact Origin (origin="" means url's own; None
    sends none), and the Host websockets takes from the address. Use it as `async with ui_socket(...) as ws`."""
    headers = {"Cookie": f"aib_ui_{server.port}={secret or server.ui_secret}"} if cookie else {}
    return connect(url.replace("http://", "ws://", 1) + "/ws", origin=url if origin == "" else origin,
                   additional_headers=headers, proxy=None)
