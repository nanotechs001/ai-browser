"""The floating chat's "This page" matched to the tab list (app/pagematch.py): by address, then by title; else the
user picks. Never a guess."""

from ai_browser.app.pagematch import TITLE_LIMIT, URL_LIMIT, address, match, seen, title


def tab(target, url, name, kind="you"):
    return {"target": target, "url": url, "title": name, "owner": {"kind": kind}}


CART = tab("U1", "https://shop.example/cart", "Cart")
NEWS = tab("U2", "https://news.example/", "News")


def test_the_one_tab_at_the_address_is_the_one():
    tabs = [CART, NEWS, tab("A1", "https://flights.example/", "Flights", kind="agent")]
    assert match({"url": "https://shop.example/cart", "title": "Cart"}, tabs) == "U1"
    assert match({"url": "shop.example/cart", "title": "Cart"}, tabs) == "U1"  # Windows' address bar: no scheme
    assert match({"url": "https://www.shop.example/cart/", "title": "Something else"}, tabs) == "U1"
    assert match({"url": "https://flights.example/", "title": "Flights"}, tabs) == "A1"  # the AI's tabs are listed too
    assert match({"url": "https://bank.example/", "title": "Cart"}, tabs) is None  # not listed: another profile
    settings = tab("X", "brave://settings", "Settings")
    assert match({"url": "brave://settings", "title": "Settings"}, [*tabs, settings]) is None  # web pages only


def test_two_tabs_at_one_address_are_told_apart_by_title_or_picked():  # Review Focus 4
    plan = tab("U1", "https://docs.example/d/1", "Plan - Docs")
    budget = tab("U2", "https://docs.example/d/1", "Budget - Docs")
    twin = tab("U3", "https://docs.example/d/1", "Budget - Docs")
    assert match({"url": "https://docs.example/d/1", "title": "Plan - Docs"}, [plan, budget]) == "U1"
    assert match({"url": "https://docs.example/d/1", "title": "Plan - Docs - Work"}, [plan, budget]) == "U1"  # Windows
    assert match({"url": "https://docs.example/d/1", "title": "Budget - Docs"}, [plan, budget, twin]) is None
    assert match({"url": "https://docs.example/d/1", "title": "Other"}, [plan, budget]) is None


def test_with_no_address_the_title_alone_must_name_one_tab():
    tabs = [CART, NEWS, tab("U3", "https://other.example/", "News")]
    assert match({"url": "", "title": "Cart"}, tabs) == "U1"
    assert match({"url": "", "title": "News"}, tabs) is None  # two tabs called News: the user picks
    assert match({"url": "", "title": ""}, tabs) is None


def test_titles_and_addresses_are_compared_as_text():  # Review Focus 5
    hostile = '<img src=x onerror="alert(1)">\t"},{"state":"ok"} ‮ evil'
    tabs = [tab("U1", "https://shop.example/a%20b?q=1#top", hostile),
            tab("U2", "https://shop.example/a%20b?q=1#top", "Plain")]
    assert match({"url": "shop.example/a b?q=1#top", "title": hostile.replace("\t", " ")}, tabs) == "U1"
    assert title("  A\x07 title\n\twith   spaces ") == "A title with spaces"
    assert address("https://www.Shop.example/a%20b/") == address("shop.example/a b") == "shop.example/a b"
    assert address("HTTP://shop.example/?q=1") == "shop.example?q=1"
    odd = [{"target": 7, "url": "https://shop.example/"}, "junk", None, {"target": "U9", "url": None}]
    assert match({"url": "https://shop.example/", "title": "x"}, odd) is None


def test_what_the_chat_says_it_read_is_kept_to_two_strings():
    assert seen({"url": " https://shop.example/ ", "title": "Cart", "extra": 1}) == {
        "url": "https://shop.example/", "title": "Cart"}
    assert seen({"url": "x" * 5000, "title": "y" * 5000}) == {"url": "x" * URL_LIMIT, "title": "y" * TITLE_LIMIT}
    assert seen({"url": 7, "title": "Cart"}) is None and seen({"title": "Cart"}) is None
