"""QA's manners: one request at a time per host, robots.txt, Retry-After and the big sites it leaves alone."""

import asyncio
import email.utils
import time

import pytest

from ai_browser.qa.polite import (MAX_CRAWL_DELAY, ROBOTS_FOLLOWED, HostGate, HostStopped, Robots, big_site,
                                  cool_reason, pause, retry_after, short_reason, stop_reason)


async def test_one_host_takes_turns_while_two_hosts_run_together():
    gate = HostGate(delay=0.2)
    spans = {}

    async def request(name, host):
        async with gate.turn(host):
            began = time.monotonic()
            await asyncio.sleep(0.1)
            spans[name] = (began, time.monotonic())

    await asyncio.gather(request("a1", "a.example"), request("a2", "a.example"), request("b1", "b.example"))
    assert spans["a2"][0] >= spans["a1"][1] + 0.2 - 0.01  # one after the other, the delay apart
    assert spans["b1"][0] < spans["a1"][1]  # another host goes at the same time


async def test_turns_on_one_host_are_given_in_the_order_asked():
    gate = HostGate(delay=0.01)
    order = []

    async def request(number):
        async with gate.turn("shop.example.com"):
            order.append(number)
            await asyncio.sleep(0.01)

    await asyncio.gather(*(request(number) for number in range(3)))
    assert order == [0, 1, 2]


async def test_a_stopped_host_is_sent_nothing_more():
    gate = HostGate(delay=0.01)
    gate.stop("Shop.example.com", "answered 429 Too Many Requests on /pricing", 120)
    with pytest.raises(HostStopped) as stopped:
        async with gate.turn("shop.example.com"):
            raise AssertionError("a turn on a stopped host")
    assert (stopped.value.host, stopped.value.why) == ("shop.example.com", "answered 429 Too Many Requests on /pricing")
    assert gate.stopped("shop.example.com") == stopped.value.why and gate.waits["shop.example.com"] == 120
    gate.stop("shop.example.com", "answered 403 Forbidden on /x")  # the first reason stays
    assert gate.stopped("shop.example.com").startswith("answered 429") and gate.stopped("other.example") is None


async def test_requests_waiting_for_a_host_that_stops_are_turned_away():
    gate = HostGate(delay=0.01)
    seen = []

    async def first():
        async with gate.turn("a.example"):
            await asyncio.sleep(0.05)
            gate.stop("a.example", "answered 403 Forbidden on /")

    async def second():
        try:
            async with gate.turn("a.example"):
                seen.append("sent")
        except HostStopped:
            seen.append("stopped")

    await asyncio.gather(first(), second())
    assert seen == ["stopped"]


async def test_a_host_stopped_while_its_request_waits_for_a_free_slot_is_sent_nothing():
    gate = HostGate(delay=0.01, total=1)
    seen = []

    async def busy():
        async with gate.turn("b.example"):
            await asyncio.sleep(0.05)
            gate.stop("a.example", "answered 403 Forbidden on /")

    async def waiting():
        await asyncio.sleep(0.01)  # b.example holds the only slot by now
        try:
            async with gate.turn("a.example"):
                seen.append("sent")
        except HostStopped:
            seen.append("stopped")

    await asyncio.gather(busy(), waiting())
    assert seen == ["stopped"]


def test_crawl_delay_replaces_the_pause_when_longer_up_to_ten_seconds():
    gate = HostGate(delay=1.0)
    gate.set_delay("shop.example.com", 30)
    gate.set_delay("calm.example.com", 0.2)
    assert gate.delay_for("shop.example.com") == MAX_CRAWL_DELAY
    assert gate.delay_for("calm.example.com") == 1.0 and gate.delay_for("other.example") == 1.0


def test_retry_after_in_seconds_or_as_a_date():
    now = 1_800_000_000.0
    assert retry_after("120", now) == 120.0
    assert retry_after(email.utils.formatdate(now + 90, usegmt=True), now) == 90.0
    assert retry_after(email.utils.formatdate(now - 90, usegmt=True), now) == 0.0  # a date already past
    assert retry_after("soon", now) is None and retry_after("", now) is None and retry_after(None, now) is None


@pytest.mark.parametrize("host", ["google.com", "www.google.com", "google.com.ph", "maps.google.com", "youtu.be",
                                  "wa.me", "WWW.LinkedIn.com", "goo.gl"])
def test_big_sites(host):
    assert big_site(host)


@pytest.mark.parametrize("host", ["google.example.com", "notgoogle.com", "example.com", "notx.com"])
def test_sites_that_are_not_big(host):
    assert not big_site(host)


def test_robots_rules_follow_the_reply():
    robots = Robots.from_reply(200, "User-agent: *\r\nDisallow: /private/\r\nCrawl-delay: 30\r\n")
    assert robots.allowed("https://s.example/public.html") and not robots.allowed("https://s.example/private/x.html")
    assert robots.crawl_delay == MAX_CRAWL_DELAY and robots.note == ROBOTS_FOLLOWED
    assert not robots.closed and not robots.stops
    ours = Robots.from_reply(200, "User-agent: ai-browser\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
    assert not ours.allowed("https://s.example/")  # the group for our own name applies
    missing = Robots.from_reply(404, "")
    assert missing.allowed("https://s.example/private/x.html") and missing.crawl_delay is None
    for status in (500, 503, None):
        closed = Robots.from_reply(status, "")
        assert closed.closed and not closed.allowed("https://s.example/") and "closed to crawlers" in closed.note
    for status in (403, 429):
        assert Robots.from_reply(status, "").stops
    assert Robots.from_reply(200, "", challenge=True).stops


def test_reasons_read_plainly():
    assert (pause(120), pause(60), pause(30), pause(1)) == ("2 minutes", "1 minute", "30 seconds", "1 second")
    why = stop_reason(429, "/pricing", 120)
    assert why == "answered 429 Too Many Requests on /pricing (it asked for a 2-minute pause)"
    assert stop_reason(403, "/members") == "answered 403 Forbidden on /members"
    assert stop_reason(403, "/", challenge=True) == "answered with a bot check on /"
    assert [short_reason(text) for text in (why, stop_reason(503, "/", 600), stop_reason(None, "/", challenge=True))] \
        == ["429", "503", "bot check"]
    assert cool_reason(why, 120) == "429, it asked for 2 minutes"
    assert cool_reason(stop_reason(403, "/"), None) == "403"
