import pytest

from ai_browser.qa.urls import action_link, is_file, normalize, origin, slug


@pytest.mark.parametrize("raw,expected", [
    ("HTTPS://Example.COM:443/a?b=1#top", "https://example.com/a?b=1"),
    ("http://example.com", "http://example.com/"),
    ("http://example.com:8080/x", "http://example.com:8080/x"),
    ("mailto:a@b.c", None), ("javascript:void(0)", None), ("tel:123", None), ("", None),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_origin():
    assert origin("https://example.com/a/b?c") == "https://example.com"
    assert origin("http://localhost:8000/qa/") == "http://localhost:8000"


@pytest.mark.parametrize("url,text", [
    ("https://s.com/wp-login.php?action=logout&_wpnonce=1", ""), ("https://s.com/logout", ""),
    ("https://s.com/account/sign-out/", ""), ("https://s.com/?add-to-cart=12", ""),
    ("https://s.com/wp-admin/post.php?post=1", ""), ("https://s.com/cart/?remove_item=ab", ""),
    ("https://s.com/x", "Log out"), ("https://s.com/x", "Delete account"), ("https://s.com/u?token=abc", ""),
])
def test_action_links_are_recognised(url, text):
    assert action_link(url, text)


@pytest.mark.parametrize("url,text", [
    ("https://s.com/blog/how-we-removed-clutter/", "Read more"), ("https://s.com/checkout/", "Checkout"),
    ("https://s.com/posts/", "Latest posts"), ("https://s.com/updates/", "Updates"), ("https://s.com/", "Home"),
])
def test_ordinary_pages_are_not_action_links(url, text):
    assert not action_link(url, text)


def test_files_and_slugs():
    assert is_file("https://s.com/files/brochure.ZIP") and is_file("https://s.com/a.pdf?x=1")
    assert not is_file("https://s.com/about/") and not is_file("https://s.com/page.html")
    assert slug("https://s.com/") == "home" and slug("https://s.com/Blog/My Post/?a=1") == "blog-my-post"


@pytest.mark.parametrize("url", ["https://s.com/DeleteUser.aspx?id=4", "https://s.com/doLogout", "https://s.com/removeItem?id=3",
                                 "https://s.com/cart/empty", "https://s.com/cart/add?id=1",
                                 "https://s.com/admin/posts/5/publish", "https://s.com/admin/", "https://s.com/orders/7/cancel"])
def test_more_action_links_are_recognised(url):
    assert action_link(url)


@pytest.mark.parametrize("url", ["https://s.com/publishing-guide/", "https://s.com/cancellation-policy/",
                                 "https://s.com/administration/", "https://s.com/cartoons/"])
def test_words_that_merely_start_like_actions_are_pages(url):
    assert not action_link(url)
