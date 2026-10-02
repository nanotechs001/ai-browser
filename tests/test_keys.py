import pytest

from ai_browser.keys import key_event


def test_enter_sends_carriage_return_text():
    params, mask = key_event("Enter")
    assert (params["key"], params["code"], params["windowsVirtualKeyCode"], params["text"], mask) == (
        "Enter", "Enter", 13, "\r", 0)


def test_meta_a_becomes_select_all_command():
    params, mask = key_event("Meta+A")
    assert mask == 4
    assert (params["key"], params["code"], params["windowsVirtualKeyCode"]) == ("a", "KeyA", 65)
    assert params["commands"] == ["selectAll"]
    assert "text" not in params


def test_ctrl_z_becomes_undo_command():
    assert key_event("Ctrl+Z")[0]["commands"] == ["undo"]


def test_shift_tab():
    params, mask = key_event("Shift+Tab")
    assert (params["key"], params["windowsVirtualKeyCode"], mask) == ("Tab", 9, 8)


def test_arrow_down():
    assert key_event("ArrowDown")[0]["windowsVirtualKeyCode"] == 40


def test_printable_letter_has_text():
    params, mask = key_event("a")
    assert (params["key"], params["code"], params["text"], mask) == ("a", "KeyA", "a", 0)


def test_slash_for_block_editors():
    params, _ = key_event("/")
    assert (params["key"], params["code"], params["text"], params["windowsVirtualKeyCode"]) == ("/", "Slash", "/", 191)


def test_combined_modifiers():
    assert key_event("Ctrl+Shift+ArrowLeft")[1] == 10


def test_modifier_names_are_case_insensitive():
    assert key_event("cmd+a")[1] == 4


@pytest.mark.parametrize("combo", ["Hyper+x", "NotAKey", "", "Ctrl+"])
def test_unknown_keys_raise(combo):
    with pytest.raises(ValueError):
        key_event(combo)
