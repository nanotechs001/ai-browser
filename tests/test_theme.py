"""One theme for the whole app (the new look, Decision 1): theme.css's tokens, linked first by every page, and none of
the old light palette left anywhere. Read as files, then drawn in a throwaway headless Chrome against a real app server
(the `stack` fixture)."""

import re
from pathlib import Path

import pytest

from ai_browser.chrome import chrome_binary
from test_home import open_page, stack, until  # noqa: F401  (fixture)

ROOT = Path(__file__).parents[1]
UI = ROOT / "src" / "ai_browser" / "app" / "ui"
CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
PAGES = ("app.html", "mission.html", "settings.html", "setup.html", "chat.html")
OLD = ("#faf9f5", "#c96442", "#d97757", "#f2f0e8", "#e6e3da", "#1f1e1d", "#262624", "#30302d", "#3a3936",
       "#ecebe6", "#a3a29c", "#6b6a66")  # the old palette: its backgrounds, accents, lines and words
TOKENS = ("--bg", "--bg-deep", "--bar", "--card", "--panel", "--code", "--soft", "--field", "--selected", "--line",
          "--line-strong", "--text", "--text-2", "--muted", "--dim", "--eyebrow", "--accent", "--accent-2",
          "--accent-bright", "--accent-fg", "--glow", "--rim", "--ok", "--work", "--wait", "--needs", "--fail",
          "--done", "--font", "--mono", "--radius", "--radius-sm", "--shadow")
LINK = re.compile(r'<link rel="stylesheet" href="([^"]+)">')


def test_every_page_links_the_theme_first():
    for name in PAGES:
        sheets = LINK.findall((UI / name).read_text(encoding="utf-8"))
        assert sheets and sheets[0] == "theme.css", name


def test_the_theme_defines_every_token():
    text = (UI / "theme.css").read_text(encoding="utf-8")
    for token in TOKENS:
        assert re.search(rf"{token}:\s*[^;]+;", text), token
    assert "color-scheme: dark" in text


def test_no_page_keeps_the_old_palette():
    files = [*UI.glob("*.css"), *UI.glob("*.html"), *UI.glob("*.js"),
             ROOT / "src" / "ai_browser" / "desktop" / "electron" / "main.js"]
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        assert not [colour for colour in OLD if colour in text], path.name
    for path in UI.glob("*.css"):
        if path.name != "theme.css":
            assert ":root" not in path.read_text(encoding="utf-8"), path.name  # one palette: the theme's


def test_every_variable_a_sheet_uses_is_defined():
    theme = set(re.findall(r"(--[a-z0-9-]+):", (UI / "theme.css").read_text(encoding="utf-8")))
    scripts = " ".join(path.read_text(encoding="utf-8") for path in UI.glob("*.js"))
    from_scripts = set(re.findall(r"""setProperty\(\s*["'](--[a-z0-9-]+)""", scripts))
    for path in UI.glob("*.css"):
        text = path.read_text(encoding="utf-8")
        own = set(re.findall(r"(--[a-z0-9-]+):", text))
        missing = set(re.findall(r"var\((--[a-z0-9-]+)", text)) - theme - own - from_scripts
        assert not missing, (path.name, sorted(missing))


def test_the_theme_opens_anywhere_like_the_setup_page():
    from ai_browser.app.server import OPEN_ANYWHERE

    assert "theme.css" in OPEN_ANYWHERE  # the setup page opens in Brave too, without the window's cookie


@CHROME
async def test_every_page_is_drawn_in_the_theme(stack):
    for path in ("/app", "/mission", "/settings", "/chat", "/setup"):
        _, js = await open_page(stack["cdp"], stack["url"] + path)
        assert await until(js, "document.readyState === 'complete'"), path
        assert await js("getComputedStyle(document.body).backgroundColor") == "rgb(7, 15, 35)", path  # --bg
        assert await js("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()") \
            == "#2a5cff", path
        assert await js("getComputedStyle(document.documentElement).colorScheme") == "dark", path
