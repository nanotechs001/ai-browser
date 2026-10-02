"""Wave 2 (everyday Brave) builds on wave 1 (safe browsing) through a few named seams: this pins them."""

import inspect

import pytest

from ai_browser.chrome import chrome_binary

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


def test_wave_one_seams_have_their_names():
    from ai_browser.agentlink import AgentLink
    from ai_browser.app.server import AppServer
    from ai_browser.checks import CheckGate, Held
    from ai_browser.engine import Engine

    report = inspect.signature(AgentLink.report).parameters.values()
    assert any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in report)
    assert inspect.iscoroutinefunction(Engine._hold) and inspect.iscoroutinefunction(Engine._on_check)
    assert list(inspect.signature(Engine._hold).parameters) == ["self", "browser", "tab", "check", "where"]
    assert inspect.signature(Engine._hold).parameters["where"].default == "session"
    assert not inspect.iscoroutinefunction(Engine._release)  # wave 1's tab-closed callback calls it without await
    assert callable(Engine._wire) and callable(AppServer._agent_report)
    assert "where" in inspect.signature(CheckGate.hold).parameters and "where" in Held.__dataclass_fields__


async def test_a_hold_in_another_browser_brings_that_browser_forward(tmp_path):
    from types import SimpleNamespace

    from ai_browser.browser import Tab
    from ai_browser.checks import Check
    from ai_browser.engine import Engine
    from ai_browser.skills import Catalog

    engine = Engine(home=tmp_path / "home", catalog=Catalog([], set()))
    fronted = []

    async def bring_to_front(tab):
        fronted.append(tab.key)

    engine.live = SimpleNamespace(url="http://127.0.0.1:8770/live?token=abc")  # QA's sandbox view (Task 12)
    other = SimpleNamespace(bring_to_front=bring_to_front)
    text = await engine._hold(other, Tab("q3", "TARGET", "SESSION"), Check("traffic", "shop.example.com"), where="qa")
    assert fronted == ["q3"] and "http://127.0.0.1:8770/live?token=abc" in text
    assert (engine.gate.held.tab_key, engine.gate.held.where) == ("q3", "qa")


@CHROME
async def test_run_qa_awaits_on_check_and_returns_its_text(chrome_browser):
    from ai_browser.qa import run_qa

    browser, base, _ = chrome_browser
    seen = []

    async def on_check(tab, check):
        seen.append((tab.key, check.kind))
        return "HANDED OVER TO THE USER"

    result = await run_qa(browser, browser.work, base + "qa2/check.html", 5, delay=0.05, on_check=on_check)
    assert [kind for _, kind in seen] == ["traffic"]
    assert "HANDED OVER TO THE USER" in result
