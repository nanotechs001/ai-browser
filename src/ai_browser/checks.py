"""Bot checks: what the page reader's signals amount to, and the session's hold while the user deals with one.

The reader (reader.js, in its own isolated world) collects a few facts about the top page, its signals; the small
rules here decide, and the first matching rule wins. Detection only ever stops the agent: nothing here clicks, solves
or gets around a check, and the reader never looks inside a check frame."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from .render import render_check

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


# ---- the hold: while a check waits, the whole session waits for the user ---------------------------------------------

ALLOWED_WHILE_HELD = frozenset({"observe", "sandbox_status", "page_log", "read_file", "write_file", "find_skills",
                                "load_skill", "read_skill_file"})
SITE_TOOLS = frozenset({"open", "tabs", "act", "qa"})  # the tools that take an address: a skipped site is refused


@dataclass
class Held:
    tab_key: str
    target: str
    check: Check
    adopted: bool  # the user's own tab: the app never closes it
    where: str = "session"  # "session" (this session's browser) or "qa" (QA's own browser: the everyday-Brave spec)


class CheckGate:
    """The session's hold at a bot check, the sites the user skipped, and the hosts QA leaves alone for a while. It
    lives in the Engine, so it outlasts a reconnect, a sandbox_stop and a new sandbox_start."""

    def __init__(self, clock=time.time):
        self.held: Held | None = None
        self.skipped: set[str] = set()  # site keys: hosts without www.
        self.qa_stopped: dict[str, tuple[float, str]] = {}  # host -> (until, why)
        self._clock = clock

    def hold(self, tab_key: str, target: str, check: Check, adopted: bool, where: str = "session") -> Held:
        self.held = Held(tab_key, target, check, adopted, where)
        return self.held

    def solved(self) -> Held | None:
        """A read found the check gone: the hold ends."""
        held, self.held = self.held, None
        return held

    def closed(self) -> str | None:
        """The held tab was closed: the hold ends and its site is off-limits for the rest of the session."""
        held, self.held = self.held, None
        if held is None:
            return None
        key = site_key(held.check.site)
        if key:
            self.skipped.add(key)
        return key

    def refusal(self, tool: str, action: str | None = None, url: str | None = None,
                tab: str | None = None) -> str | None:
        """The text for a call that must not run, or None."""
        held = self.held
        if held is not None:
            if tool in ALLOWED_WHILE_HELD:
                return None
            if tool == "tabs" and (action == "list" or (action == "close" and tab == held.tab_key)):
                return None
            return self.waiting()
        if url and tool in SITE_TOOLS:
            skipped = self.skipped_for(url)
            if skipped is not None:
                return skipped
        if url and tool == "qa":
            from .qa.polite import big_site  # here, not at the top: qa/polite imports this module

            host = _host(url)
            if big_site(host):
                return (f"⛔ {host} is a big site, and qa never crawls one (they refuse or rate-limit automated "
                        "checks); open single pages with open")
            return self.cooling(host)
        return None

    def skipped_for(self, url: str) -> str | None:
        """The refusal for an address on a skipped site, or None."""
        key = next((key for key in sorted(self.skipped) if on_site(url, key)), None)
        return None if key is None else self.skipped_text(key)

    def qa_stop(self, host: str, until: float, why: str) -> None:
        """QA stopped on a host (a 429, a 403 or a bot check): a new qa there waits until `until`."""
        when = time.strftime("%H:%M", time.localtime(self._clock()))
        self.qa_stopped[host.lower()] = (until, f"at {when} ({why})")

    def cooling(self, host: str) -> str | None:
        entry = self.qa_stopped.get(host)
        if entry is None:
            return None
        until, why = entry
        if until <= self._clock():
            del self.qa_stopped[host]
            return None
        again = time.strftime("%H:%M", time.localtime(until))
        return f"QA stopped on {host} {why}: qa can run there again from {again}."

    @staticmethod
    def handoff(check: Check, tab_key: str, live_url: str | None = None) -> str:
        return render_check(check, tab_key, live_url)

    def waiting(self) -> str:
        held = self.held
        where = f"tab {held.tab_key} ({held.check.site})" if held is not None else "a tab"
        return (f"⏸ waiting for the user: {where} shows a bot check. Nothing runs until they've dealt with it. "
                "Tell the user and stop; when they say it's done, call observe.")

    @staticmethod
    def skipped_text(site: str) -> str:
        return (f"⛔ {site} is off-limits in this task: the user skipped it after a bot check. Ask the user if you "
                "need it.")
