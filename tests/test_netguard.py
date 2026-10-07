"""netguard.py (the no-Docker spec): the local sandbox's browser never opens this computer's own addresses or its
network's, as written or looked up. Docker's never could: its loopback was the container's own. Every name looked up
here is a fake: no test asks a real DNS server."""

import asyncio
import socket

import pytest

from ai_browser import netguard

PRIVATE = ["http://localhost:8792/home", "http://LOCALHOST./", "http://app.localhost/", "http://printer.local/",
           "http://127.0.0.1/", "http://127.9.9.9:3000/", "http://0.0.0.0:8000/", "http://10.0.0.1/",
           "http://172.16.0.1/", "http://172.31.255.255/", "http://192.168.1.1/admin", "http://169.254.169.254/",
           "http://100.64.0.1/", "http://100.127.255.1/", "http://[::1]:8080/",
           "http://[fe80::1]/", "http://[fd00::1]/", "http://[::ffff:127.0.0.1]/", "http://[::ffff:c0a8:101]/",
           "https://192.168.0.10:8443/", "ws://localhost:9222/devtools/browser/x"]
PUBLIC = ["https://example.com/", "http://93.184.216.34/", "http://172.32.0.1/", "http://100.128.0.1/",
          "http://10.example.com/", "https://localhost.example.com/", "http://[2606:4700::1111]/", "about:blank",
          "data:text/html,hi", "file:///tmp/x.html", "not a url", ""]


@pytest.mark.parametrize("url", PRIVATE)
def test_this_computers_and_its_networks_addresses_are_private_as_written(url):
    assert netguard.private_url(url), url


@pytest.mark.parametrize("url", PUBLIC)
def test_public_addresses_and_pages_without_a_host_are_not(url):
    assert not netguard.private_url(url), url


def fake_lookup(monkeypatch, answers: dict[str, list[str]]):
    """getaddrinfo for these names only; any other name isn't found, as on a computer with no network."""
    async def getaddrinfo(self, host, port, *args, **kwargs):
        if host not in answers:
            raise socket.gaierror(socket.EAI_NONAME, "not found")
        return [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))
                for address in answers[host]]

    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", getaddrinfo)


async def test_a_public_name_that_points_here_is_refused_once_looked_up(monkeypatch):
    fake_lookup(monkeypatch, {"localtest.me": ["127.0.0.1"], "router.example": ["fe80::1%en0"],
                              "example.com": ["93.184.216.34", "2606:2800:220:1::1"],
                              "mixed.example": ["93.184.216.34", "10.0.0.7"]})
    assert await netguard.refused("http://example.com/") is None
    for url in ("http://localtest.me:8792/home", "http://router.example/", "http://mixed.example/"):
        problem = await netguard.refused(url)
        assert problem is not None and problem.startswith(f"{netguard.host_of(url)} is on this computer or its "
                                                          "network"), url
        assert "QA a site on this computer in your own browser" in problem
    assert await netguard.refused("http://nowhere.example/") is None  # not found: the browser can't open it either
    assert await netguard.refused("http://127.0.0.1:3000/") is not None  # as written: no lookup needed
    assert await netguard.refused("data:text/html,hi") is None and await netguard.refused("about:blank") is None


async def test_a_slow_lookup_lets_the_browser_decide(monkeypatch):
    async def slow(self, host, port, *args, **kwargs):
        await asyncio.sleep(60)

    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", slow)
    monkeypatch.setattr(netguard, "LOOKUP_WAIT", 0.1)
    assert await netguard.refused("http://slow.example/") is None


async def test_only_the_tests_own_pages_are_ever_exempt(monkeypatch):
    assert netguard.exempt("http://localhost:8000/form.html") is False  # outside the tests: nothing
    monkeypatch.setattr(netguard, "exempt", lambda url: url.startswith("http://localhost:8000/"))
    assert not netguard.private_url("http://localhost:8000/form.html")
    assert await netguard.refused("http://localhost:8000/form.html") is None
    assert netguard.private_url("http://localhost:8001/form.html")


def test_the_patterns_pause_every_navigation_and_each_private_form():
    import fnmatch

    def paused(url, kind="Image"):
        return any(fnmatch.fnmatchcase(url, pattern["urlPattern"].replace("[", "[[]"))
                   and pattern.get("resourceType", kind) == kind for pattern in netguard.PATTERNS)

    assert all(pattern["requestStage"] == "Request" for pattern in netguard.PATTERNS)
    assert paused("https://example.com/", "Document")  # a navigation is always looked at, so a name is looked up
    assert not paused("https://example.com/logo.png")  # a public picture never waits
    for url in PRIVATE:
        if url.startswith("http"):
            assert paused(url.lower()), url  # every private form, as Chrome writes it (lower case), waits for a look
