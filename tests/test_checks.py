"""Bot-check rules on the reader's signals (no browser): a check is seen by a specific sign, never by words alone."""

import pytest

from ai_browser.checks import KINDS, Check, box_frames, detect, google_host, on_site, site_key

LONG = "An article about bot checks. " * 400  # well over SHORT_PAGE characters
BFRAME = "https://www.google.com/recaptcha/api2/bframe?hl=en&v=abc&k=key"
ANCHOR = "https://www.google.com/recaptcha/api2/anchor?ar=1&k=key&co=x&hl=en&v=abc&size={size}&cb=1"


def page(title="", text="Hello", status=200, ids=(), frames=()):
    return {"title": title, "text": text[:2000], "textLength": len(text), "status": status, "ids": list(ids),
            "frames": list(frames)}


def frame(src, w=400, h=580, on_screen=True, visible=True):
    return {"src": src, "w": w, "h": h, "onScreen": on_screen, "visible": visible}


@pytest.mark.parametrize("url", ["https://www.google.com/sorry/index?continue=https://www.google.com/search",
                                 "https://google.com.ph/sorry/", "https://www.google.co.uk/sorry/",
                                 "https://ipv4.google.com/sorry/index"])
def test_googles_sorry_page_is_a_google_check(url):
    assert detect(url, page()) == Check("google", url.split("/")[2])


@pytest.mark.parametrize("url", ["https://www.google.com/search?q=sorry", "https://sorry.example.com/sorry/"])
def test_the_word_sorry_alone_is_not_a_check(url):
    assert detect(url, page()) is None


def test_unusual_traffic_counts_on_short_pages_only():
    words = "Our systems have detected unusual traffic from your computer network."
    assert detect("https://www.google.de/search?q=x", page(text=words)) == Check("google", "www.google.de")
    assert detect("https://shop.example.com/", page(text=words)) == Check("traffic", "shop.example.com")
    assert detect("https://news.example.com/a", page(text=words + LONG)) is None


def test_picture_challenges_need_a_frame_someone_can_see():
    shop = "https://shop.example.com/"
    assert detect(shop, page(frames=[frame(BFRAME)])) == Check("captcha", "shop.example.com")
    assert detect(shop, page(frames=[frame(BFRAME, visible=False)])) is None
    assert detect(shop, page(frames=[frame(BFRAME, w=0, h=0)])) is None
    assert detect(shop, page(frames=[frame(BFRAME, on_screen=False)])) is None
    hcaptcha = frame("https://newassets.hcaptcha.com/captcha/v1/abc/static/hcaptcha.html#frame=challenge&id=1")
    assert detect(shop, page(frames=[hcaptcha])) == Check("captcha", "shop.example.com")


def test_checkboxes_are_form_fields_never_checks():
    invisible = frame(ANCHOR.format(size="invisible"), w=256, h=60)
    normal = frame(ANCHOR.format(size="normal"), w=304, h=78)
    hcaptcha = frame("https://newassets.hcaptcha.com/captcha/v1/abc/static/hcaptcha.html#frame=checkbox&id=1",
                     w=302, h=76)
    turnstile = frame("https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/if/ov2/av0/x",
                      w=300, h=65)
    signals = page(title="Contact us", frames=[invisible, normal, hcaptcha, turnstile])
    assert detect("https://shop.example.com/contact", signals) is None
    assert box_frames(signals) == [normal, hcaptcha, turnstile]
    assert box_frames(page(frames=[{**normal, "visible": False}])) == []


def test_cloudflare_needs_its_page_and_a_block_or_its_frame():
    shop, moment = "https://shop.example.com/", "Just a moment..."
    assert detect(shop, page(title=moment, status=503)) == Check("cloudflare", "shop.example.com")
    assert detect(shop, page(title="Attention Required! | Cloudflare", status=403)).kind == "cloudflare"
    assert detect(shop, page(ids=["challenge-stage"], status=403)).kind == "cloudflare"
    challenge = frame("https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/orchestrate/x", w=300, h=65)
    assert detect(shop, page(title=moment, frames=[challenge])).kind == "cloudflare"
    assert detect(shop, page(title=moment, status=200)) is None
    background = frame("https://shop.example.com/cdn-cgi/challenge-platform/scripts/jsd/main.js", 0, 0, False, False)
    assert detect(shop, page(title="Shop", text="Welcome to the shop", frames=[background])) is None


def test_perimeterx_and_akamai():
    assert detect("https://shop.example.com/", page(ids=["px-captcha"])) == Check("perimeterx", "shop.example.com")
    suspicious = "Something seems suspicious about this request. Please try again later."
    assert detect("https://air.example.com/", page(text=suspicious)) == Check("akamai", "air.example.com")
    assert detect("https://air.example.com/", page(text=suspicious + LONG)) is None
    denied = page(title="Access Denied", text="You don't have permission to access this page. Reference #18.1a2b3c")
    assert detect("https://air.example.com/", denied) == Check("akamai", "air.example.com")


def test_only_web_pages_and_every_kind_has_plain_words():
    assert detect("data:text/html,unusual traffic", page(text="unusual traffic")) is None
    assert detect("about:blank", page()) is None
    assert set(KINDS) == {"google", "traffic", "captcha", "cloudflare", "perimeterx", "akamai"}
    assert Check("google", "www.google.com").what == KINDS["google"]


@pytest.mark.parametrize("host", ["google.com", "www.google.de", "google.com.ph", "maps.google.co.uk"])
def test_google_hosts(host):
    assert google_host(host)


@pytest.mark.parametrize("host", ["google.example.com", "notgoogle.com", "google.community"])
def test_hosts_that_only_look_like_google(host):
    assert not google_host(host)


def test_site_keys_and_matching():
    assert site_key("www.google.com") == site_key("https://www.google.com/search?q=x") == "google.com"
    assert on_site("https://mail.google.com/mail/", "google.com") and on_site("google.com", "google.com")
    assert on_site("HTTPS://WWW.GOOGLE.COM.:443/x", "google.com")
    assert not on_site("https://notgoogle.com/", "google.com")
    assert not on_site("https://google.com.evil.example/", "google.com")
    assert on_site("http://localhost:8123/checks/counter.html", "localhost")
    assert not on_site("", "google.com") and not on_site("https://google.com/", "")


import time  # noqa: E402  (the hold's tests)

from ai_browser.checks import CheckGate  # noqa: E402

GOOGLE = Check("google", "www.google.com")
WAITING = "⏸ waiting for the user: tab t2 (www.google.com) shows a bot check."


def test_while_held_only_reading_and_the_held_tab_go_through():
    gate = CheckGate()
    assert gate.refusal("open", url="https://example.com") is None
    gate.hold("t2", "TARGET", GOOGLE, adopted=False)
    for tool in ("open", "act", "screenshot", "extract", "js", "qa", "shell", "sandbox_start", "sandbox_stop"):
        assert gate.refusal(tool).startswith(WAITING), tool
    for action, tab in (("new", None), ("switch", "t1"), ("close", "t1")):
        assert gate.refusal("tabs", action=action, tab=tab).startswith(WAITING), action
    for tool in ("observe", "sandbox_status", "page_log", "read_file", "write_file", "find_skills", "load_skill",
                 "read_skill_file"):
        assert gate.refusal(tool) is None, tool
    assert gate.refusal("tabs", action="list") is None and gate.refusal("tabs", action="close", tab="t2") is None
    assert gate.waiting() == (WAITING + " Nothing runs until they've dealt with it. Tell the user and stop; when they "
                              "say it's done, call observe.")
    assert gate.solved().tab_key == "t2" and gate.held is None and gate.skipped == set()
    assert gate.refusal("js") is None


def test_a_closed_check_tab_skips_its_site_everywhere():
    gate = CheckGate()
    gate.hold("t2", "TARGET", GOOGLE, adopted=False)
    assert gate.closed() == "google.com" and gate.held is None and gate.skipped == {"google.com"}
    refused = ("⛔ google.com is off-limits in this task: the user skipped it after a bot check. Ask the user if you "
               "need it.")
    for tool, action in (("open", None), ("act", None), ("qa", None), ("tabs", "new")):
        assert gate.refusal(tool, action=action, url="https://maps.google.com/x") == refused, tool
    assert gate.skipped_for("https://www.google.com/") == refused
    assert gate.refusal("open", url="https://notgoogle.com/") is None
    assert gate.refusal("open", url="https://www.bing.com/") is None


def test_qa_cools_down_on_a_host_it_stopped_on():
    now = [1_800_000_000.0]
    gate = CheckGate(clock=lambda: now[0])
    gate.qa_stop("shop.example.com", now[0] + 120, "429, it asked for 2 minutes")
    at = time.strftime("%H:%M", time.localtime(now[0]))
    again = time.strftime("%H:%M", time.localtime(now[0] + 120))
    assert gate.refusal("qa", url="https://shop.example.com/pricing") == (
        f"QA stopped on shop.example.com at {at} (429, it asked for 2 minutes): qa can run there again from {again}.")
    assert gate.refusal("open", url="https://shop.example.com/pricing") is None  # single pages stay allowed
    now[0] += 121
    assert gate.refusal("qa", url="https://shop.example.com/") is None and gate.qa_stopped == {}


def test_qa_never_starts_on_a_big_site():
    gate = CheckGate()
    refused = gate.refusal("qa", url="https://www.youtube.com/@someone")
    assert refused.startswith("⛔ www.youtube.com is a big site, and qa never crawls one")
    assert gate.refusal("open", url="https://www.youtube.com/@someone") is None  # single pages stay allowed
    assert gate.refusal("qa", url="https://shop.example.com/") is None
