"""The fake Gmail, Slack and Asana pages (src/ai_browser/pages/brain/) on three addresses of their own, as the real
sites each have their own, with brain/sites.py's INBOX pointed at them for one test."""

import pytest


@pytest.fixture
def inbox_sites(monkeypatch):
    """{"gmail": base, "slack": base, "asana": base}: each base serves pages/, so the fake Gmail is at
    bases["gmail"] + "brain/gmail.html", and only Gmail's base counts as Gmail."""
    from ai_browser import testpages
    from ai_browser.brain import sites

    bases, stop = testpages.serve_sites()
    for site, base in bases.items():
        monkeypatch.setitem(sites.INBOX, site, base + "*")
    yield bases
    stop()
