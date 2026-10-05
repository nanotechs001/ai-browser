"""The sites the Brain reads in the user's Brave, and which one a tab's address belongs to.

Gmail, Slack and Asana are read while Settings → Brain → "Read my Gmail, Slack and Asana tabs" is on. Their addresses
are fixed here, never taken from a page or a message. A part of a page the user picked to watch is read on the page
it was picked on, and the pages under that address (watch_pattern). Patterns are Chrome's match patterns:
scheme://host/path, where * matches anything (in the host, only a leading "*." does)."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

INBOX = {"gmail": "https://mail.google.com/*", "slack": "https://app.slack.com/*", "asana": "https://app.asana.com/*"}
_PATTERN = re.compile(r"^(\*|https?)://([^/]+)(/.*)$")


def matches(pattern: str, url: str) -> bool:
    """Whether `url` is one of the addresses `pattern` names (its path and query count; its fragment doesn't)."""
    found = _PATTERN.match(pattern) if isinstance(pattern, str) else None
    if found is None or not isinstance(url, str):
        return False
    try:
        address = urlsplit(url)
        port = address.port
    except ValueError:
        return False
    scheme, host_part, path = found.groups()
    if address.scheme not in ("http", "https") or (scheme != "*" and address.scheme != scheme):
        return False
    host, _, wanted_port = host_part.partition(":")
    name = (address.hostname or "").lower()
    if host.startswith("*."):
        if not (name == host[2:].lower() or name.endswith("." + host[2:].lower())):
            return False
    elif name != host.lower():
        return False
    if wanted_port and str(port) != wanted_port:
        return False
    tail = address.path + (f"?{address.query}" if address.query else "")
    return re.fullmatch(".*".join(re.escape(part) for part in path.split("*")), tail or "/") is not None


def inbox_site(url: str) -> str | None:
    """"gmail", "slack" or "asana" for an address of that site; None for any other."""
    return next((site for site, pattern in INBOX.items() if matches(pattern, url)), None)


def watch_pattern(address: str) -> str:
    """Where a picked part is read: the page it was picked on, and the pages under its address, not the whole site."""
    parts = urlsplit(address)
    path = parts.path.replace("*", "") or "/"
    return f"{parts.scheme}://{parts.netloc}{path}*"
