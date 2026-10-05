"""The Brain's inbox and watch list on disk: they survive restarts and hold only what matters."""

import json

from conftest import file_mode


def item(raw_id, kind, **fields):
    from ai_browser.brain.store import Item

    return Item(id=f"gmail:{raw_id}", site="gmail", raw_id=raw_id, sender="Maria", subject="Launch",
                snippet="Monday?", url=f"https://mail.google.com/mail/u/0/#inbox/{raw_id}", time="10:02", kind=kind,
                **fields)


def test_the_store_survives_a_restart_and_keeps_only_what_matters(tmp_path):
    from ai_browser.brain.store import BrainStore, WatchEntry

    clock = [1000.0]
    store = BrainStore(tmp_path, clock=lambda: clock[0])
    store.put(item("t1", "needs_reply", summary="Move the launch?"))
    store.put(item("t2", "new", summary="A receipt"))
    store.put(item("t1", "needs_reply", summary="Move the launch to Monday?"))  # an update keeps its place
    store.mark_seen(["gmail:t1", "gmail:t2", "gmail:t3"])
    store.add_others(1)
    store.set_watch(WatchEntry(site="gmail", label="Gmail", url_match="https://mail.google.com/*",
                               instructions="Always tell me about clients", enabled=True))
    again = BrainStore(tmp_path, clock=lambda: clock[0])
    assert [i.id for i in again.items()] == ["gmail:t2", "gmail:t1"]
    assert again.get("gmail:t1").summary == "Move the launch to Monday?" and again.seen("gmail:t3")
    assert again.others == 1
    assert [e.site for e in again.watch()] == ["gmail", "slack", "asana"]
    assert again.entry("gmail").instructions == "Always tell me about clients" and again.entry("gmail").enabled
    for name in ("inbox.json", "watch.json"):
        assert file_mode(tmp_path / "brain" / name) in (0o600, None)
    clock[0] += 25 * 3600
    again.expire()
    assert [i.id for i in again.items()] == ["gmail:t1"]  # "new" goes after a day; "needs your reply" stays
    assert again.others == 0


def test_seen_ids_are_capped(tmp_path):
    from ai_browser.brain.store import BrainStore

    store = BrainStore(tmp_path)
    store.mark_seen([f"gmail:{n}" for n in range(6000)])
    assert not store.seen("gmail:0") and store.seen("gmail:5999")
    assert len(json.loads((tmp_path / "brain" / "inbox.json").read_text(encoding="utf-8"))["seen"]) == 5000


def test_a_damaged_file_starts_fresh_and_is_kept(tmp_path):
    from ai_browser.brain.store import BrainStore

    (tmp_path / "brain").mkdir()
    (tmp_path / "brain" / "inbox.json").write_text("not json", encoding="utf-8")
    store = BrainStore(tmp_path)
    assert store.items() == [] and (tmp_path / "brain" / "inbox.json.bad").read_text(encoding="utf-8") == "not json"
    store.remove_watch("gmail")
    assert store.entry("gmail") is not None and store.entry("gmail").enabled  # the three sites stay on


def test_added_sites_and_settings(tmp_path):
    from ai_browser.brain.store import BrainStore, WatchEntry

    store = BrainStore(tmp_path)
    assert store.style == ""
    store.set_watch(WatchEntry(site="custom:shop.example", label="shop.example", url_match="https://shop.example/*",
                               selector="#orders tbody", instructions="Summarize new orders", enabled=True))
    store.set_style("Short and friendly, sign as Alex")
    again = BrainStore(tmp_path)
    assert again.entry("custom:shop.example").selector == "#orders tbody"
    assert again.style == "Short and friendly, sign as Alex"
    again.remove_watch("custom:shop.example")
    assert again.entry("custom:shop.example") is None
    assert BrainStore(tmp_path).entry("custom:shop.example") is None


def test_a_damaged_file_is_set_aside_even_while_windows_holds_it(tmp_path, monkeypatch):
    from ai_browser import platforms
    from ai_browser.brain.store import BrainStore

    folder = tmp_path / "brain"
    folder.mkdir()
    (folder / "inbox.json").write_text("not json", encoding="utf-8")
    real, held = platforms.os.replace, []

    def busy_once(src, dst):
        if str(dst).endswith(".bad") and not held:  # only the rename that sets the damaged file aside
            held.append(src)
            raise PermissionError(13, "being scanned")
        real(src, dst)

    monkeypatch.setattr(platforms.os, "replace", busy_once)
    monkeypatch.setattr(platforms.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(platforms, "WINDOWS", True)  # only the retry loop changes: no Win32 call is made
    BrainStore(tmp_path)
    assert (folder / "inbox.json.bad").read_text(encoding="utf-8") == "not json"


def test_an_older_watch_file_loads_and_the_watchers_flags_go(tmp_path):
    from ai_browser.brain.store import BrainStore

    (tmp_path / "brain").mkdir()
    (tmp_path / "brain" / "watch.json").write_text(json.dumps({
        "watch": [], "style": "Short", "watcher_seen": True, "watcher_prompted": True}), encoding="utf-8")
    store = BrainStore(tmp_path)
    assert store.style == "Short" and not hasattr(store, "watcher_seen") and not hasattr(store, "watcher_prompted")
    store.set_style("Shorter")
    saved = json.loads((tmp_path / "brain" / "watch.json").read_text(encoding="utf-8"))
    assert saved["style"] == "Shorter" and "watcher_seen" not in saved and "watcher_prompted" not in saved


def test_the_three_sites_are_always_on_whatever_an_older_file_says(tmp_path):
    from ai_browser.brain.store import BrainStore

    assert all(entry.enabled for entry in BrainStore(tmp_path).watch())
    (tmp_path / "brain").mkdir()
    (tmp_path / "brain" / "watch.json").write_text(json.dumps({"watch": [
        {"site": "gmail", "label": "Gmail", "url_match": "https://mail.google.com/*", "instructions": "mine",
         "enabled": False}], "paused": True}), encoding="utf-8")  # the watcher's Pause and Gmail switched off
    store = BrainStore(tmp_path)
    assert store.entry("gmail").enabled and store.entry("gmail").instructions == "mine"
    assert not hasattr(store, "paused")  # Settings → Brain's switch took Pause's place
    store.set_style("Short")
    assert "paused" not in json.loads((tmp_path / "brain" / "watch.json").read_text(encoding="utf-8"))


def test_what_the_readers_keep_survives_a_restart(tmp_path):
    from ai_browser.brain.store import MEMORY_LIMIT, BrainStore, WatchEntry

    store = BrainStore(tmp_path)
    assert store.memory("slack") == {} and not store.baselined("custom:shop.example", "#orders")
    store.set_watch(WatchEntry(site="custom:shop.example", label="shop.example", url_match="https://shop.example/*",
                               selector="#orders", enabled=True))
    store.set_memory("slack", {f"C{n}": {"id": "abc", "read": False} for n in range(MEMORY_LIMIT + 10)})
    store.mark_baselined("custom:shop.example", "#orders")
    store.set_memory("slack", "not a dict")  # ignored
    again = BrainStore(tmp_path)
    assert len(again.memory("slack")) == MEMORY_LIMIT and "C0" not in again.memory("slack")  # the oldest go first
    assert again.baselined("custom:shop.example", "#orders") and not again.baselined("custom:shop.example", "#x")
    again.remove_watch("custom:shop.example")
    again.set_watch(WatchEntry(site="custom:other.example", label="other.example", url_match="https://other.example/*",
                               selector="ul", enabled=True))
    again.mark_baselined("custom:other.example", "ul")
    assert not again.baselined("custom:shop.example", "#orders")  # a removed part's mark goes with the next one
    assert file_mode(tmp_path / "brain" / "readers.json") in (0o600, None)
    (tmp_path / "brain" / "readers.json").write_text("not json", encoding="utf-8")
    assert BrainStore(tmp_path).memory("slack") == {}  # damaged: set aside, and that part starts empty
