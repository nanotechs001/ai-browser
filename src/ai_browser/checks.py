"""Bot checks: what the page reader's signals amount to (and, from Task 2 on, the session's hold).

The reader (reader.js, in its own isolated world) collects a few facts about the top page, its signals; the small
rules here decide, and the first matching rule wins. Detection only ever stops the agent: nothing here clicks, solves
or gets around a check, and the reader never looks inside a check frame."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

KINDS: dict[str, str] = {
    "google": "Google's \"unusual traffic\" check (\"I'm not a robot\")",
    "traffic": "an \"unusual traffic\" block page",
    "captcha": "a CAPTCHA picture check",
    "cloudflare": "Cloudflare's \"verify you are human\" check",
    "perimeterx": "a \"Press & Hold\" check (PerimeterX)",
    "akamai": "an Akamai block page (\"Something seems suspicious\" or \"Access Denied\")",
}
SHORT_PAGE = 3000  # characters of visible text: the text rules only look at pages shorter than this
MIN_CHALLENGE = 100  # px: a picture-challenge frame smaller than this either way is shown to no one
_GOOGLE = re.compile(r"(?:^|\.)google\.(?:com|[a-z]{2}|com\.[a-z]{2}|co\.[a-z]{2})$")
_CF_TITLES = ("just a moment", "attention required")
_CF_IDS = frozenset({"challenge-stage", "challenge-form", "challenge-running"})


@dataclass(frozen=True)
class Check:
    kind: str  # a key of KINDS
    site: str  # the page's host, for example www.google.com

    @property
    def what(self) -> str:
        """The check in plain words, from our own table (never from the page)."""
        return KINDS[self.kind]


def _host(value: str) -> str:
    """The lower-case host of a URL, or of a bare host name with or without a port."""
    text = (value or "").strip().lower()
    if "://" not in text:
        text = "http://" + text
    try:
        return (urlsplit(text).hostname or "").rstrip(".")
    except ValueError:
        return ""


def google_host(host: str) -> bool:
    """google.com, google.<cc>, google.com.<cc>, google.co.<cc>, or any host under one of them."""
    return bool(_GOOGLE.search(_host(host)))


def site_key(url_or_host: str) -> str:
    """The site a skip applies to: the host without www."""
    host = _host(url_or_host)
    return host[4:] if host.startswith("www.") else host


def on_site(url: str, key: str) -> bool:
    """Whether a URL (or a bare host) is the site `key` or under it: notgoogle.com is not on google.com."""
    host, key = _host(url), (key or "").strip().lower()
    return bool(host and key) and (host == key or host.endswith("." + key))


def _on(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def _parts(frame: dict) -> tuple[str, str, str]:
    """(host, path, the whole address) of a frame the reader listed."""
    src = str(frame.get("src") or "")
    try:
        parts = urlsplit(src)
        return (parts.hostname or "").lower(), parts.path, src
    except ValueError:
        return "", "", src


def _challenge_frame(frame: dict) -> bool:
    """A picture challenge someone is looking at: visible, on screen and at least MIN_CHALLENGE px both ways."""
    if not (frame.get("visible") and frame.get("onScreen")):
        return False
    if (frame.get("w") or 0) < MIN_CHALLENGE or (frame.get("h") or 0) < MIN_CHALLENGE:
        return False
    host, path, src = _parts(frame)
    if "/recaptcha/api2/bframe" in path or "/recaptcha/enterprise/bframe" in path:
        return True  # matched by path: Google serves these from www.google.com and www.recaptcha.net
    return _on(host, "hcaptcha.com") and "frame=challenge" in src


def _cloudflare_frame(frame: dict) -> bool:
    host, path, _ = _parts(frame)
    return host == "challenges.cloudflare.com" or "/cdn-cgi/challenge-platform/" in path


def box_frames(signals: dict) -> list[dict]:
    """The visible checkbox frames (reCAPTCHA, hCaptcha, Turnstile): form fields the user ticks, never a hold."""
    boxes = []
    for frame in (signals or {}).get("frames") or []:
        if not frame.get("visible"):
            continue
        host, path, src = _parts(frame)
        recaptcha = ("/recaptcha/api2/anchor" in path or "/recaptcha/enterprise/anchor" in path) \
            and "size=invisible" not in src
        hcaptcha = _on(host, "hcaptcha.com") and "frame=checkbox" in src
        turnstile = host == "challenges.cloudflare.com" and "/turnstile/" in path
        if recaptcha or hcaptcha or turnstile:
            boxes.append(frame)
    return boxes


def detect(url: str, signals: dict) -> Check | None:
    """The bot check this page is, or None. Only web pages can be one; the first matching rule wins."""
    try:
        parts = urlsplit(url or "")
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    signals = signals or {}
    host = (parts.hostname or "").lower()
    title = str(signals.get("title") or "")
    text = str(signals.get("text") or "")
    length = signals.get("textLength")
    short = (length if isinstance(length, int) else len(text)) < SHORT_PAGE
    words = f"{title}\n{text}".lower()
    frames = [frame for frame in signals.get("frames") or [] if isinstance(frame, dict)]
    ids = {str(name) for name in signals.get("ids") or []}
    if google_host(host) and (parts.path.startswith("/sorry/") or (short and "unusual traffic" in words)):
        return Check("google", host)
    if short and "unusual traffic" in words:
        return Check("traffic", host)
    if any(_challenge_frame(frame) for frame in frames):
        return Check("captcha", host)
    cloudflare_page = title.strip().lower().startswith(_CF_TITLES) or bool(ids & _CF_IDS)
    if cloudflare_page and (signals.get("status") in (403, 503) or any(_cloudflare_frame(f) for f in frames)):
        return Check("cloudflare", host)
    if "px-captcha" in ids:
        return Check("perimeterx", host)
    if short and "something seems suspicious" in words:
        return Check("akamai", host)
    if title.strip().lower() == "access denied" and "reference #" in text.lower():
        return Check("akamai", host)
    return None
