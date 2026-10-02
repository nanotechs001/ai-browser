from dataclasses import replace

import pytest

from ai_browser.steps import ID_OPS, Step, StepError, parse_step, parse_steps


@pytest.mark.parametrize(
    "text,expected",
    [
        ("click e5", Step("click", target="e5")),
        ("dblclick e12", Step("dblclick", target="e12")),
        ("hover e2", Step("hover", target="e2")),
        ("check e8", Step("check", target="e8")),
        ("uncheck e8", Step("uncheck", target="e8")),
        ('type e4 "About us"', Step("type", target="e4", value="About us")),
        ('type "hello world"', Step("type", value="hello world")),
        ('type e4 ""', Step("type", target="e4", value="")),
        ('append e4 " more"', Step("append", target="e4", value=" more")),
        ("key Enter", Step("key", value="Enter")),
        ("key Meta+A", Step("key", value="Meta+A")),
        ("key /", Step("key", value="/")),
        ('select e9 "Large"', Step("select", target="e9", value="Large")),
        ("drag e7 e12", Step("drag", target="e7", target2="e12")),
        ("upload e5 logo.png", Step("upload", target="e5", value="logo.png")),
        ('upload e5 "/work/my file.png"', Step("upload", target="e5", value="/work/my file.png")),
        ("scroll down", Step("scroll", value="down")),
        ("scroll up 300", Step("scroll", value="up", amount=300)),
        ("scroll top", Step("scroll", value="top")),
        ("scroll bottom", Step("scroll", value="bottom")),
        ("scroll e40", Step("scroll", target="e40")),
        ("wait 500", Step("wait", amount=500)),
        ('wait "Saved"', Step("wait", value="Saved")),
        ('wait "500"', Step("wait", value="500")),
        ("goto https://example.com/a?b=1", Step("goto", value="https://example.com/a?b=1")),
        ("back", Step("back")),
        ("forward", Step("forward")),
        ("reload", Step("reload")),
        ("Click e5", Step("click", target="e5")),
    ],
)
def test_parse_step_forms(text, expected):
    assert parse_step(text) == replace(expected, raw=text)


def test_unicode_text_preserved():
    assert parse_step('type e4 "Zürich – 東京 😀"').value == "Zürich – 東京 😀"


def test_apostrophe_inside_double_quotes():
    assert parse_step("type e4 \"it's fine\"").value == "it's fine"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "click",
        "click x5",
        "click e5 extra",
        "fly e5",
        "type e4",
        'type e4 "unterminated',
        "select e9",
        "drag e1",
        "upload e5",
        "key",
        "wait",
        "wait soon",
        "scroll sideways",
        "goto ftp://example.com",
        "back now",
    ],
)
def test_parse_step_rejects(text):
    with pytest.raises(StepError):
        parse_step(text)


def test_parse_steps_returns_steps_in_order():
    steps = parse_steps(["click e1", 'type e2 "x"'])
    assert [s.op for s in steps] == ["click", "type"]


def test_parse_steps_error_names_the_step_number():
    with pytest.raises(StepError, match="step 2"):
        parse_steps(["click e1", "fly"])


def test_parse_steps_rejects_empty_list():
    with pytest.raises(StepError):
        parse_steps([])


def test_id_ops_lists_ops_that_need_an_element():
    assert {"click", "type", "drag", "upload"} <= ID_OPS
    assert "key" not in ID_OPS
