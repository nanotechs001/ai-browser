from ai_browser.qa.run import Frontier


def test_frontier_order_variants_actions_and_referrers():
    frontier = Frontier("https://s.com", max_variants=2)
    assert frontier.add("https://s.com/a", "https://s.com/", "A") == "new"
    assert frontier.add("https://s.com/a#x", "https://s.com/b", "A again") == "seen"
    assert frontier.add("https://o.com/", "https://s.com/", "Partner") == "external"
    assert frontier.add("https://s.com/logout", "https://s.com/", "Log out") == "action"
    assert [frontier.add(f"https://s.com/cal?m={n}", "https://s.com/", "") for n in range(4)] == \
        ["new", "new", "variant", "variant"]
    assert [frontier.pop() for _ in range(4)] == ["https://s.com/a", "https://s.com/cal?m=0", "https://s.com/cal?m=1", None]
    assert frontier.links["https://s.com/a"].referrers == [("https://s.com/", "A"), ("https://s.com/b", "A again")]
    assert frontier.action == ["https://s.com/logout"] and not frontier.links["https://o.com/"].internal
    frontier.mark("https://s.com/b")
    assert frontier.add("https://s.com/b", "https://s.com/", "B") == "seen"



def test_a_link_seen_as_an_action_anywhere_is_never_visited():
    frontier = Frontier("https://s.com")
    assert frontier.add("https://s.com/account/x", "https://s.com/", "") == "new"  # an icon-only link first...
    assert frontier.add("https://s.com/account/x", "https://s.com/b", "Log out") == "action"  # ...then its text
    assert frontier.pop() is None and "https://s.com/account/x" not in frontier.links
    assert frontier.add("https://s.com/account/x", "https://s.com/c", "") == "action"
    assert frontier.action == ["https://s.com/account/x"]
