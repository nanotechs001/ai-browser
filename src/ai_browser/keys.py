"""Turn key combos like `Enter`, `Shift+Tab` or `Meta+A` into CDP key event parameters."""

from __future__ import annotations

MODIFIERS = {"alt": 1, "option": 1, "ctrl": 2, "control": 2, "meta": 4, "cmd": 4, "command": 4, "shift": 8}

# name -> (key, code, windowsVirtualKeyCode, text)
NAMED = {
    "enter": ("Enter", "Enter", 13, "\r"),
    "tab": ("Tab", "Tab", 9, None),
    "escape": ("Escape", "Escape", 27, None),
    "esc": ("Escape", "Escape", 27, None),
    "backspace": ("Backspace", "Backspace", 8, None),
    "delete": ("Delete", "Delete", 46, None),
    "space": (" ", "Space", 32, " "),
    "arrowup": ("ArrowUp", "ArrowUp", 38, None),
    "arrowdown": ("ArrowDown", "ArrowDown", 40, None),
    "arrowleft": ("ArrowLeft", "ArrowLeft", 37, None),
    "arrowright": ("ArrowRight", "ArrowRight", 39, None),
    "home": ("Home", "Home", 36, None),
    "end": ("End", "End", 35, None),
    "pageup": ("PageUp", "PageUp", 33, None),
    "pagedown": ("PageDown", "PageDown", 34, None),
}
PUNCTUATION = {
    "/": ("Slash", 191), ".": ("Period", 190), ",": ("Comma", 188), "-": ("Minus", 189), "=": ("Equal", 187),
    ";": ("Semicolon", 186), "'": ("Quote", 222), "[": ("BracketLeft", 219), "]": ("BracketRight", 221),
    "\\": ("Backslash", 220), "`": ("Backquote", 192),
}
# The sandbox runs Linux Chromium, where ⌘ shortcuts do nothing; send editing commands directly instead.
COMMANDS = {"a": "selectAll", "c": "copy", "v": "paste", "x": "cut", "z": "undo", "y": "redo"}


def key_event(combo: str) -> tuple[dict, int]:
    """Return (Input.dispatchKeyEvent params without `type`, modifier bitmask)."""
    if not combo:
        raise ValueError("empty key; use names like Enter, Tab, Escape, ArrowDown or a single character")
    if combo.endswith("++"):
        names, key = combo[:-2].split("+") if combo[:-2] else [], "+"
    else:
        *names, key = combo.split("+")
    if not key:
        raise ValueError(f"{combo!r}: missing the key after the modifiers")
    mask = 0
    for name in names:
        if name.lower() not in MODIFIERS:
            raise ValueError(f"{combo!r}: unknown modifier {name!r}; use Ctrl, Alt, Shift or Meta")
        mask |= MODIFIERS[name.lower()]

    if key.lower() in NAMED:
        key_value, code, vk, text = NAMED[key.lower()]
    elif len(key) == 1:
        lower = key.lower()
        if lower.isalpha() and lower.isascii():
            key_value, code, vk = lower if not mask & 8 else lower.upper(), f"Key{lower.upper()}", ord(lower.upper())
        elif key.isdigit():
            key_value, code, vk = key, f"Digit{key}", ord(key)
        elif key in PUNCTUATION:
            key_value, (code, vk) = key, PUNCTUATION[key]
        else:
            key_value, code, vk = key, "", 0
        text = key_value
    elif len(key) in (2, 3) and key[0] in "Ff" and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        key_value, code, vk, text = key.upper(), key.upper(), 111 + int(key[1:]), None
    else:
        raise ValueError(f"{combo!r}: unknown key {key!r}; use Enter, Tab, Escape, ArrowDown, F5 or one character")

    params = {"key": key_value, "code": code, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk,
              "modifiers": mask}
    if mask & (2 | 4) and key.lower() in COMMANDS:
        params["commands"] = [COMMANDS[key.lower()]]
    elif text and not mask & (1 | 2 | 4):
        params["text"] = text
        params["unmodifiedText"] = text
    return params, mask
