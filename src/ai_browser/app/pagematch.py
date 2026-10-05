"""The floating chat's "This page" (native-app Decision 4): the Brave tab the user is on, as AI Browser's own app read
it from Brave's front window (an address and a title, nothing else: desktop/electron/thispage.js), matched to the tab
list (BraveLink.tabs(): the profile where agents browse, and the AI's own tabs).
- One listed web tab at that address is the one.
- Several are told apart by the title. On Windows, the window's title may go on with " - " and a profile's name.
- With no address (an address bar the user is typing in), the title alone must name one tab.
- Anything else is the user's to pick: never a guess.
Addresses are compared as Brave's address bar may show them: without "https://" or "www.", %-escapes decoded, no
trailing slash. Titles are compared as text: control characters out, spaces collapsed. Pure: nothing here reads
Brave, the network or the disk."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import unquote

URL_LIMIT = 2000  # characters of an address the chat may send
TITLE_LIMIT = 300  # characters of a title
WEB = ("http://", "https://")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def seen(message: dict) -> dict | None:
    """What the chat says the app read, as {"url", "title"} (strings, cut to length); None when it isn't that."""
    url, name = message.get("url"), message.get("title")
    if not isinstance(url, str) or not isinstance(name, str):
        return None
    return {"url": url.strip()[:URL_LIMIT], "title": name[:TITLE_LIMIT]}


def address(url) -> str:
    """An address as Brave's address bar may show it: "https://www.Shop.example/a%20b/" and "shop.example/a b" are
    both "shop.example/a b"."""
    text = _SCHEME.sub("", unquote(str(url or "").strip()), count=1)
    cut = re.search(r"[/?#]", text)
    host, rest = (text[:cut.start()], text[cut.start():]) if cut else (text, "")
    host = host.lower().removeprefix("www.")
    if rest.startswith("/"):
        end = re.search(r"[?#]", rest)
        path, tail = (rest[:end.start()], rest[end.start():]) if end else (rest, "")
        rest = path.rstrip("/") + tail
    return host + rest


def title(text) -> str:
    """A title as compared: control characters out, spaces collapsed, one Unicode form."""
    return " ".join(unicodedata.normalize("NFC", _CONTROL.sub(" ", str(text or ""))).split())


def _titled(found: str, listed: str) -> bool:
    return bool(listed) and (found == listed or found.startswith(listed + " - "))


def match(found: dict, tabs) -> str | None:
    """The target of the one listed web tab the user is on, or None: the user picks."""
    rows = [tab for tab in tabs or [] if isinstance(tab, dict) and isinstance(tab.get("target"), str)
            and isinstance(tab.get("url"), str) and tab["url"].startswith(WEB)]
    named = title(found.get("title"))
    if found.get("url"):
        wanted = address(found["url"])
        rows = [tab for tab in rows if address(tab["url"]) == wanted]
        if len(rows) == 1:
            return rows[0]["target"]
    elif not named:
        return None
    titled = [tab for tab in rows if _titled(named, title(tab.get("title")))]
    return titled[0]["target"] if len(titled) == 1 else None
