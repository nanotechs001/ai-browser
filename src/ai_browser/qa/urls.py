"""URL rules for the QA crawl: canonical form, which links are files, and which look like actions."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}
# Words that make a link an action (log out, delete...) rather than a page; a crawl must never request them.
# Matched on whole words of the lower-cased path or query, after camelCase is split (doLogout → do logout).
_ACTION_PATH = re.compile(
    r"(?<![a-z0-9])(log[-_ ]?out|sign[-_ ]?out|log[-_ ]?off|delete|remove|trash|unsubscribe|add[-_ ]to[-_ ]cart|"
    r"empty[-_ ]cart|cart[-_ /](?:add|empty|remove|clear)|wp-admin|wp-login\.php|admin|publish|unpublish|approve|"
    r"cancel)(?![a-z0-9])")
_ACTION_KEYS = {"action", "_wpnonce", "nonce", "token", "add-to-cart", "remove_item"}
_ACTION_TEXT = re.compile(r"\b(log ?out|sign ?out|log ?off|delete|remove|unsubscribe|trash)\b", re.IGNORECASE)
_FILE_TYPES = {
    "pdf", "zip", "rar", "7z", "gz", "tgz", "tar", "dmg", "exe", "msi", "apk", "doc", "docx", "xls", "xlsx", "ppt",
    "pptx", "csv", "xml", "json", "jpg", "jpeg", "png", "gif", "webp", "avif", "svg", "ico", "mp3", "mp4", "m4a",
    "mov", "avi", "webm", "wav", "woff", "woff2", "ttf", "otf", "css", "js",
}


def normalize(url: str) -> str | None:
    """A canonical http(s) URL (lower-case scheme and host, no default port, no fragment), or None."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS or not parts.hostname:
        return None
    host = parts.hostname.lower()
    if ":" in host:  # IPv6
        host = f"[{host}]"
    netloc = host if port in (None, _DEFAULT_PORTS[scheme]) else f"{host}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _words(text: str) -> str:
    return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", unquote(text)).lower()


def action_link(url: str, text: str = "") -> bool:
    """True for links that do something (log out, delete, add to cart...) instead of showing a page."""
    parts = urlsplit(url)
    if _ACTION_PATH.search(_words(parts.path)) or _ACTION_PATH.search(_words(parts.query)):
        return True
    if any(key.lower() in _ACTION_KEYS for key, _ in parse_qsl(parts.query, keep_blank_values=True)):
        return True
    return bool(_ACTION_TEXT.search(text or ""))


def is_file(url: str) -> bool:
    name = urlsplit(url).path.rsplit("/", 1)[-1]
    return "." in name and name.rsplit(".", 1)[-1].lower() in _FILE_TYPES


def slug(url: str) -> str:
    """The URL's path as a short file-name part: /Blog/My Post/ → blog-my-post; / → home."""
    text = re.sub(r"[^a-z0-9]+", "-", unquote(urlsplit(url).path).lower()).strip("-")
    return text[:40].strip("-") or "home"
