"""Wave 2 (everyday Brave) builds on wave 1 (safe browsing) through a few named seams: this pins them."""

import inspect


def test_wave_one_seams_have_their_names():
    from ai_browser.agentlink import AgentLink
    from ai_browser.app.server import AppServer
    from ai_browser.checks import CheckGate, Held
    from ai_browser.engine import Engine

    report = inspect.signature(AgentLink.report).parameters.values()
    assert any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in report)
    assert inspect.iscoroutinefunction(Engine._hold) and inspect.iscoroutinefunction(Engine._on_check)
    assert list(inspect.signature(Engine._hold).parameters) == ["self", "browser", "tab", "check"]
    assert not inspect.iscoroutinefunction(Engine._release)  # wave 1's tab-closed callback calls it without await
    assert callable(Engine._wire) and callable(AppServer._agent_report)
    assert callable(CheckGate.hold) and "adopted" in Held.__dataclass_fields__
