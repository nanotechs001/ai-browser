import pytest

from ai_browser.config import RISKY_WORDS
from ai_browser.render import diff_rows, is_risky, render_diff, render_page, render_row


def row(**kw):
    base = {"id": "e3", "role": "button", "name": "Publish"}
    base.update(kw)
    return base


def state(**kw):
    base = {
        "url": "https://acme.test/wp-admin/post.php?post=12",
        "title": "Edit Page",
        "w": 1440,
        "h": 900,
        "scrollY": 0,
        "scrollH": 2300,
        "above": 4,
        "below": 38,
        "frames": [],
        "rows": [row()],
        "text": "About us",
        "doc": "d1",
        "truncated": 0,
        "find": None,
    }
    base.update(kw)
    return base


def test_row_basic():
    assert render_row(row()) == 'e3   button   "Publish"'


def test_row_risky_marker():
    assert render_row(row(risky=True)) == 'e3   button   "Publish" ⚠'


def test_row_frame_and_value():
    r = row(id="e4", role="textbox", name="Add title", value="About us", frame="canvas")
    assert render_row(r) == 'e4   textbox  [canvas] "Add title" = "About us"'


def test_row_empty_value_is_shown():
    assert render_row(row(role="textbox", name="Name", value="")).endswith('"Name" = ""')


def test_row_select_options():
    r = row(id="e9", role="select", name="Size", value="Medium", options=["Small", "Medium", "Large"])
    assert render_row(r) == 'e9   select   "Size" = "Medium" (Small|Medium|Large)'


def test_row_select_more_options():
    r = row(role="select", name="Country", value="", options=["A", "B"], more=40)
    assert render_row(r).endswith("(A|B|+40 more)")


def test_row_link_href():
    assert render_row(row(id="e12", role="link", name="Privacy", href="/privacy/")) == (
        'e12  link     "Privacy" → /privacy/'
    )


@pytest.mark.parametrize(
    "extra,suffix",
    [
        ({"checked": True}, " [checked]"),
        ({"checked": "mixed"}, " [mixed]"),
        ({"expanded": True}, " [expanded]"),
        ({"expanded": False}, " [collapsed]"),
        ({"selected": True}, " [selected]"),
        ({"disabled": True}, " [disabled]"),
        ({"editable": True}, " [editable]"),
    ],
)
def test_row_states(extra, suffix):
    assert render_row(row(**extra)).endswith(suffix)


def test_row_unchecked_shows_nothing():
    assert render_row(row(role="checkbox", name="Agree", checked=False)) == 'e3   checkbox "Agree"'


def test_page_header_and_rows():
    out = render_page(state(), ms=61)
    lines = out.splitlines()
    assert lines[0] == 'page  "Edit Page"  https://acme.test/wp-admin/post.php?post=12'
    assert lines[1] == "view  1440×900 · y 0/2300 · 4 above · 38 below"
    assert lines[2] == 'e3   button   "Publish"'
    assert "text:\nAbout us" in out
    assert lines[-1] == "⏱ 61 ms"


def test_page_lists_frames():
    out = render_page(state(frames=[{"label": "canvas", "url": "x", "cross": False},
                                    {"label": "map", "url": "y", "cross": True}]))
    assert "frames: [canvas] [map (cross-site, not readable)]" in out.splitlines()[1]


def test_page_truncation_hint():
    out = render_page(state(truncated=37))
    assert '… 37 more rows (use observe find="…")' in out


def test_page_without_rows_gives_a_hint():
    out = render_page(state(rows=[]))
    assert "(no interactive elements in view" in out


def test_page_find_header():
    out = render_page(state(find="pricing"))
    assert 'find  "pricing" · 1 match' in out


def test_diff_added_removed_changed():
    old = [row(id="e1", name="A"), row(id="e2", role="textbox", name="B", value="x")]
    new = [row(id="e2", role="textbox", name="B", value="xy"), row(id="e3", name="C")]
    d = diff_rows(old, new)
    assert [r["id"] for r in d["added"]] == ["e3"]
    assert [r["id"] for r in d["removed"]] == ["e1"]
    assert [r["id"] for r in d["changed"]] == ["e2"]


def test_diff_ignores_unchanged_rows():
    rows = [row(id="e1")]
    assert diff_rows(rows, [dict(r) for r in rows]) == {"added": [], "removed": [], "changed": []}


def test_render_diff_lines():
    d = {"added": [row(id="e51", role="option", name="London")], "removed": [row(id="e12", name="Old")],
         "changed": [row(id="e4", role="textbox", name="Where to?", value="Lon")]}
    out = render_diff(d, state(), ms=40)
    assert '+ e51  option   "London"' in out
    assert '- e12  button   "Old"' in out
    assert '~ e4   textbox  "Where to?" = "Lon"' in out
    assert out.splitlines()[-1] == "⏱ 40 ms"


def test_render_diff_no_change():
    out = render_diff({"added": [], "removed": [], "changed": []}, state())
    assert "(no visible change)" in out


def test_render_diff_includes_text_only_when_changed():
    d = {"added": [], "removed": [], "changed": []}
    assert "text:" not in render_diff(d, state(text="same"), old_text="same")
    assert "text:\nSaved!" in render_diff(d, state(text="Saved!"), old_text="Saving…")


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Publish", True),
        ("Update", True),
        ("Updates feed", False),
        ("Sign up now", True),
        ("Sign-up", True),
        ("signup", False),
        ("DELETE PAGE", True),
        ("Save draft", False),
        ("Move to trash", True),
    ],
)
def test_is_risky(name, expected):
    assert is_risky(name, RISKY_WORDS) is expected


def test_a_bot_check_box_is_the_users_to_tick():
    box = {"label": "a-1", "url": "https://www.google.com/recaptcha/api2/anchor?size=normal", "cross": True,
           "box": True}
    out = render_page(state(frames=[box]))
    assert "frames: [bot check box: the user ticks it]" in out.splitlines()[1]


def test_the_hand_off_has_nothing_to_click():
    from ai_browser.checks import Check
    from ai_browser.render import render_check

    text = render_check(Check("google", "www.google.com"), "t2", system="darwin")
    assert text.splitlines() == [
        "⛔ bot check in tab t2 (www.google.com): Google's \"unusual traffic\" check (\"I'm not a robot\").",
        "It is for the user to solve, never you. Stop and tell the user. Don't reload, retry, wait it out, or reach "
        "the site another way (another tab, browser, profile, tool or the shell).",
        "The tab is now in front.",
        "When the user says it's done, call observe. If they'd rather skip this site, they close the tab, or ask you "
        "to (tabs close t2): the site is then off-limits for the rest of this task.",
    ]
    live = render_check(Check("captcha", "shop.example.com"), "t3", "http://127.0.0.1:8770/live?token=abc",
                        system="darwin")
    assert live.splitlines()[2] == ("The tab is now in front. The user can solve it in the live view: "
                                    "http://127.0.0.1:8770/live?token=abc")
