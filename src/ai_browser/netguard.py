"""Without Docker (the no-Docker spec) the sandbox's browser runs on this computer, so it could reach this computer's own
services and its network's, which Docker's browser couldn't: its loopback was the container's own. So it never opens
them: loopback, private, link-local, shared (100.64.0.0/10, tailnets) and unspecified addresses, the names
localhost, *.localhost and *.local, and this computer's own public addresses (any it can bind, and the /64 of its IPv6
one: a page served over IPv6 learns the visitor's address).
- An address is judged as written (Chrome writes every address in one form first, so 2130706433 and 0x7f.1 reach it
  as 127.0.0.1).
- A name an agent opens, and every navigation's, is also looked up: a public name that points here (localtest.me) is
  refused too, and so is a name whose lookup is too slow to say (a page can make lookups hang).
The browser applies it to every request it makes (browser.py: CDP Fetch with PATTERNS), and open, act goto and qa
say so before anything loads."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

REFUSED = ("{host} is on this computer or its network, and the sandbox never opens those. QA a site on this computer "
           "in your own browser (ask the user first)")
# The ranges are listed, not taken from ipaddress's is_private and is_reserved: those also hold 198.18.0.0/15 (fake-IP
# proxies answer it for every site) and 64:ff9b::/96 (DNS64 answers it for every IPv4-only site), and their meaning
# changed in Python 3.12.4. 0/8 is "this host" (0.0.0.0 reaches this computer), 100.64/10 carrier-grade NAT and
# tailnets (Tailscale), 240/4 holds 255.255.255.255, fc00::/7 is IPv6's private range, fec0::/10 its old one.
PRIVATE_V4 = [ipaddress.ip_network(net) for net in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16",
    "240.0.0.0/4")]
PRIVATE_V6 = [ipaddress.ip_network(net) for net in ("::/128", "::1/128", "fc00::/7", "fe80::/10", "fec0::/10")]
NAT64 = ipaddress.ip_network("64:ff9b::/96")
# This computer's own addresses that are public (a page served over IPv6 sees the visitor's global address, and can
# send the browser to it: services listening on :: answer there) are found by asking the system, not by a list.
OWN_FOR = 60.0  # seconds this computer's own IPv6 network is remembered (temporary addresses change now and then)
_own: tuple[float, ipaddress.IPv6Network | None] | None = None  # (remembered until, the network)
LOOKUP_WAIT = 3.0  # seconds a name's lookup may take; past it, it is refused (a page can make lookups hang)
# Lookups run on threads of their own, not the loop's shared pool: a page that opens many names whose DNS never answers
# can only fill these four (then every lookup is refused, until they are free), and never stalls agentlink or the
# sandbox start. ponytail: a lookup stuck in the OS holds its thread until the OS gives up.
LOOKUPS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="netguard")
# The requests Chrome pauses for a look (CDP Fetch patterns: * and ? only, matched against the whole address). Every
# navigation (Document) pauses, so its name is looked up; any other request pauses only when its address may be private
# as written. The look decides: a pause that turns out public costs a round trip, a request that never paused is never
# judged, so these may match too much, never too little. Chrome keeps a user name in an address (http://u@127.0.0.1/),
# so each form that starts the host has a twin after "*@". A name ending in .local or .localhost has its end matched
# (a path that ends .local pauses too), not "*.local*", which paused every en.locale.json.
# Known edge: this computer's own public IPv4 address, or a name that points at it, is judged for a navigation only; as
# a picture or script it never pauses (every IPv6 address does, "[*"). Behind a router the address a page sees is the
# router's, not this computer's; only a computer directly on the internet has the case.
STARTS = ("localhost*", "0.*", "10.*", "127.*", "100.*", "169.254.*", "172.1?.*", "172.2?.*", "172.3?.*", "192.168.*",
          "24?.*", "25?.*", "[*")
ENDS = tuple(f"*{name}{after}" for name in (".local", ".localhost") for after in ("/*", ":*", "", "./*", ".:*", "."))
PATTERNS = [{"urlPattern": "*", "resourceType": "Document", "requestStage": "Request"},
            *({"urlPattern": f"*://{form}", "requestStage": "Request"}
              for form in (*STARTS, *(f"*@{start}" for start in STARTS), *ENDS))]


def exempt(url: str) -> bool:
    """Never, outside the test suite. The tests serve their pages on this computer, and let only those through by
    replacing this function."""
    return False


def carried(address: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """The IPv4 address an IPv6 one carries: mapped (::ffff:a.b.c.d), compatible (::a.b.c.d, but not :: or ::1), 6to4
    (2002:a.b.c.d::) or NAT64 (64:ff9b::a.b.c.d)."""
    for found in (address.ipv4_mapped, address.sixtofour):
        if found is not None:
            return found
    if address in NAT64 or 1 < int(address) < 1 << 32:
        return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    return None


def private_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if address.version == 6:  # an IPv4 address carried in an IPv6 one is judged as itself
        inside = carried(address)
        if inside is not None:
            address = inside
    if any(address in net for net in (PRIVATE_V4 if address.version == 4 else PRIVATE_V6)):
        return True
    if can_bind(address):  # this computer's own address, though a public one
        return True
    network = own_network() if address.version == 6 else None  # IPv4: the private ranges already cover the networks
    return network is not None and address in network


def can_bind(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Whether this computer has the address: a UDP socket binds only to an address of its own (nothing is sent)."""
    try:
        with socket.socket(socket.AF_INET6 if address.version == 6 else socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind((str(address), 0))
        return True
    except OSError:
        return False


def source_v6() -> ipaddress.IPv6Address | None:
    """The IPv6 address this computer uses to reach the internet, or None without IPv6. A UDP connect only picks the
    route and the address: nothing is sent."""
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as probe:
            probe.connect(("2001:4860:4860::8888", 53))
            return ipaddress.IPv6Address(probe.getsockname()[0].split("%", 1)[0])
    except (OSError, ValueError):
        return None


def own_network() -> ipaddress.IPv6Network | None:
    """The /64 of this computer's own global IPv6 address (its network), or None. Remembered for OWN_FOR seconds."""
    global _own
    if _own is None or _own[0] < time.monotonic():
        source = source_v6()
        if source is not None and any(source in net for net in PRIVATE_V6):
            source = None  # a private source: its network is already refused
        _own = (time.monotonic() + OWN_FOR, ipaddress.ip_network((source, 64), strict=False) if source else None)
    return _own[1]


def private_host(host: str) -> bool:
    """Whether a host, as written, is this computer or its network."""
    name = (host or "").strip().strip("[]").rstrip(".").lower()
    if not name:
        return False
    if name == "localhost" or name.endswith((".localhost", ".local")):
        return True
    try:
        return private_address(ipaddress.ip_address(name.split("%", 1)[0]))  # fe80::1%en0: the zone isn't the address
    except ValueError:
        return False  # a name: only a lookup can say


def host_of(url: str) -> str:
    try:
        return urlsplit(str(url).strip()).hostname or ""
    except ValueError:
        return ""


def private_url(url: str) -> bool:
    """Whether an address names this computer or its network, as written (no lookup). Exact only for an address as
    Chrome writes it, every address in one form (127.0.0.1 for 2130706433 or 0x7f.1): a raw string someone typed can
    hold forms this misses (0177.0.0.1). So a caller never treats a raw string as checked: the browser's pause
    (PATTERNS, judged by this) is the guard."""
    return not exempt(url) and private_host(host_of(url))


async def refused(url: str) -> str | None:
    """The refusal for an address the sandbox's browser never opens, or None: as written, then its name looked up.
    Early, plain-worded news for open, act goto and qa, not the guard (see private_url): on a raw string it can miss
    what Chrome would read differently, and a name can answer differently when the browser asks."""
    if exempt(url):
        return None
    host = host_of(url)
    if not host:
        return None  # data:, about:blank, a file in the work folder: no network
    if private_host(host):
        return REFUSED.format(host=host)
    try:
        ipaddress.ip_address(host)
        return None  # a public address, as written
    except ValueError:
        pass
    try:
        found = await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(LOOKUPS, socket.getaddrinfo, host, None), LOOKUP_WAIT)
    except TimeoutError:  # before OSError: it is one. Too slow to say, so no: a page can make a lookup hang
        return REFUSED.format(host=host)
    except (OSError, UnicodeError):
        return None  # not found: the browser can't open it either
    for *_, address in found:
        try:
            if private_address(ipaddress.ip_address(str(address[0]).split("%", 1)[0])):
                return REFUSED.format(host=host)
        except ValueError:
            continue
    return None
