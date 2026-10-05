"""Which site a tab's address belongs to (brain/sites.py), and the fake sites' own addresses (testpages)."""

import httpx

from fake_sites import inbox_sites  # noqa: F401  (a fixture)


def test_the_three_sites_are_fixed_and_matched_exactly():
    from ai_browser.brain.sites import INBOX, inbox_site

    assert INBOX == {"gmail": "https://mail.google.com/*", "slack": "https://app.slack.com/*",
                     "asana": "https://app.asana.com/*"}
    assert inbox_site("https://mail.google.com/mail/u/0/#inbox") == "gmail"
    assert inbox_site("https://mail.google.com") == "gmail"
    assert inbox_site("https://app.slack.com/client/T1/C1") == "slack"
    assert inbox_site("https://app.asana.com/0/inbox/1") == "asana"
    for other in ("https://mail.google.com.evil.example/", "http://mail.google.com/", "https://docs.google.com/",
                  "https://evil.example/mail.google.com/", "https://mail.google.com@evil.example/",
                  "https://xapp.slack.com/", "https://app.slack.com.evil/", "chrome://settings", "javascript:1", "",
                  None, 7, "https://[::1"):
        assert inbox_site(other) is None, other


def test_match_patterns_read_as_chrome_reads_them():
    from ai_browser.brain.sites import matches

    assert matches("http://localhost:8000/brain/gmail*", "http://localhost:8000/brain/gmail.html#all/t1")
    assert not matches("http://localhost:8000/brain/gmail*", "http://localhost:8001/brain/gmail.html")
    assert not matches("http://localhost:8000/brain/gmail*", "http://localhost:8000/brain/slack.html")
    assert matches("https://*.example.com/*", "https://shop.example.com/x")
    assert matches("https://*.example.com/*", "https://example.com/")
    assert not matches("https://*.example.com/*", "https://badexample.com/")
    assert matches("*://shop.example/*", "http://shop.example/") and matches("*://shop.example/*",
                                                                            "https://shop.example/a?b=1")
    for pattern, url in (("bad", "https://x/"), ("https://x/*", "not a url"), (None, "https://x/"),
                         ("https://x/*", None), ("https://x/*", "file:///x")):
        assert not matches(pattern, url), (pattern, url)


def test_a_picked_part_is_read_where_it_was_picked_and_below():
    from ai_browser.brain.sites import matches, watch_pattern

    assert watch_pattern("https://shop.example/orders?x=1#top") == "https://shop.example/orders*"
    assert watch_pattern("https://shop.example") == "https://shop.example/*"
    pattern = watch_pattern("http://localhost:8000/brain/orders.html")
    assert pattern == "http://localhost:8000/brain/orders.html*" and matches(pattern,
                                                                             "http://localhost:8000/brain/orders.html")


async def test_each_fake_site_has_its_own_address(inbox_sites):
    from ai_browser.brain.sites import inbox_site

    assert len({base for base in inbox_sites.values()}) == 3
    async with httpx.AsyncClient() as client:
        for site, base in inbox_sites.items():
            answer = await client.get(base + f"brain/{site}.html")
            assert answer.status_code == 200 and "<!doctype html>" in answer.text
            assert inbox_site(base + f"brain/{site}.html") == site  # INBOX points at the fakes in this test
    assert inbox_site(inbox_sites["gmail"] + "brain/slack.html") == "gmail"  # by address, never by the page
