"""The watcher in a throwaway headless Chrome (installed over the pipe), a real app server with the Brain (fake
claude: items come back as "new" unless a test scripts verdicts), and the sample pages in pages/brain/."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from test_home import evaluate, open_page, until

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


class Rig:
    def __init__(self, server, brain, app, cdp, base, log, script, worker_js, home, runner):
        self.server, self.brain, self.app, self.cdp, self.base = server, brain, app, cdp, base
        self.log, self.script, self.worker_js, self.home, self.runner = log, script, worker_js, home, runner

    async def until(self, predicate, seconds=10):
        for _ in range(int(seconds * 10)):
            if predicate():
                return True
            await asyncio.sleep(0.1)
        return predicate()

    async def watch(self, site, page, open_at=None, **fields):
        """Watch the sample page as `site`; returns (target, js) for the page, opened once its reader is set up."""
        error = self.brain.set_watch({"site": site, "enabled": True, "url_match": f"http://localhost/{page}*",
                                      **fields})
        assert error == ""
        registered = ("chrome.scripting.getRegisteredContentScripts()"
                      f".then(scripts => scripts.some(script => script.id === {json.dumps(site)}))")
        assert await until(self.worker_js, registered)
        return await open_page(self.cdp, self.base + (open_at or page))

    def raw_ids(self, site="gmail"):
        return {item["raw_id"] for item in self.brain.snapshot()["items"] if item["site"] == site}

    def sorted_calls(self):
        if not self.log.exists():
            return 0
        return sum(1 for line in self.log.read_text().splitlines() if line.startswith('{"oneshot"'))


async def start_server(home, agents, brain):
    from ai_browser.app.server import AppServer
    from ai_browser.brain.watcher import prepare_watcher

    server = AppServer(home, agents, brain=brain)
    url = await server.start()
    folder, server.watcher_build = prepare_watcher(home, url, server.token)
    return server, folder


@pytest.fixture
async def watcher(fake_claude, tmp_path):
    from ai_browser import testpages
    from ai_browser.app.agents import AgentManager
    from ai_browser.appbrowser import launch_app_browser
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore
    from ai_browser.cdp import CDP

    runner, log, script = fake_claude
    script.write_text(json.dumps([{"result": "[]"}]))
    base, _, stop_pages = testpages.serve_host()
    home = tmp_path / "home"
    agents = AgentManager(home, claude=str(runner))
    brain = BrainService(BrainStore(home), agents, claude=str(runner), batch_wait=0.2, reader_timeout=2)
    server, folder = await start_server(home, agents, brain)
    app = launch_app_browser(tmp_path / "profile", folder, headless=True)
    server.allow_origin(f"chrome-extension://{app.extension_id}", watcher=True)
    cdp = await CDP.connect(app.ws_url)
    worker = None
    for _ in range(50):
        workers = [t for t in (await cdp.send("Target.getTargets"))["targetInfos"]
                   if t["type"] == "service_worker" and app.extension_id in t["url"]]
        if workers:
            worker = (await cdp.send("Target.attachToTarget", {"targetId": workers[0]["targetId"],
                                                               "flatten": True}))["sessionId"]
            break
        await asyncio.sleep(0.1)
    assert worker, "the watcher's worker is not running"

    async def worker_js(expression):
        return await evaluate(cdp, worker, expression)

    rig = Rig(server, brain, app, cdp, base, log, script, worker_js, home, runner)
    assert await rig.until(lambda: rig.brain.watcher), "the watcher did not connect"
    yield rig
    await cdp.close()
    await rig.server.stop()
    app.close()
    stop_pages()


@CHROME
async def test_gmail_rows_are_reported_once_and_a_reply_clears_them(watcher):
    _, page = await watcher.watch("gmail", "brain/gmail.html")
    assert await watcher.until(lambda: watcher.raw_ids() == {"t1", "t2"})
    assert await until(watcher.worker_js, "chrome.notifications.getAll().then(all => Object.keys(all).length === 1)")
    await page("markReplied('t1'); true")
    assert await watcher.until(lambda: watcher.raw_ids() == {"t2"})
    await page("addRow({id: 't3', from: 'Ana', email: 'ana@client.example', subject: 'Quote', "
               "snippet: 'What would the new page cost?'}); true")
    assert await watcher.until(lambda: watcher.raw_ids() == {"t2", "t3"})
    await asyncio.sleep(1)
    assert watcher.sorted_calls() == 2  # t1 and t2, then t3: nothing is reported twice
    item = next(item for item in watcher.brain.snapshot()["items"] if item["raw_id"] == "t3")
    assert item["sender"] == "Ana" and item["subject"] == "Quote" and item["snippet"] == "What would the new page cost?"
    assert item["url"].startswith(watcher.base + "brain/gmail.html#")


@CHROME
async def test_spanish_gmail_reads_the_same(watcher):
    _, page = await watcher.watch("gmail", "brain/gmail-es.html")
    assert await watcher.until(lambda: watcher.raw_ids() == {"t1", "t2"})
    await page("markReplied('t2'); true")
    assert await watcher.until(lambda: watcher.raw_ids() == {"t1"})


@CHROME
async def test_an_unknown_layout_marks_the_reader(watcher):
    await watcher.watch("gmail", "brain/empty.html")
    assert await watcher.until(lambda: watcher.brain.store.entry("gmail").status == "reader needs an update", 8)


@CHROME
async def test_slack_dms_and_mentions_and_asana_tasks(watcher):
    _, page = await watcher.watch("slack", "brain/slack.html", open_at="brain/slack.html#/client/T1/C1")
    assert await watcher.until(lambda: {raw.split(":")[0] for raw in watcher.raw_ids("slack")} == {"D1", "C2"})
    calls = watcher.sorted_calls()
    await page("location.reload(); true")
    await asyncio.sleep(2.5)
    assert watcher.sorted_calls() == calls  # the same unread messages after a reload: nothing new
    await watcher.watch("asana", "brain/asana.html")
    assert await watcher.until(lambda: len(watcher.raw_ids("asana")) == 1)
    [task] = [item for item in watcher.brain.snapshot()["items"] if item["site"] == "asana"]
    assert task["raw_id"].startswith("333:") and task["subject"] == "Fix the footer"


@CHROME
async def test_a_picked_region_reports_new_rows(watcher):
    _, page = await watcher.watch("custom:localhost", "brain/orders.html", selector="#orders tbody",
                                  instructions="Summarize new orders")
    await asyncio.sleep(2)
    assert watcher.raw_ids("custom:localhost") == set()  # the rows already there are where watching starts
    await page("addOrder('#1002', 'Ben', '$75'); true")
    assert await watcher.until(lambda: len(watcher.raw_ids("custom:localhost")) == 1)
    [order] = [item for item in watcher.brain.snapshot()["items"] if item["site"] == "custom:localhost"]
    assert "#1002" in order["snippet"] and "Ben" in order["snippet"]


@CHROME
async def test_the_picker_gives_a_selector_for_one_element(watcher):
    _, page = await watcher.watch("custom:localhost", "brain/orders.html", selector="#orders tbody")
    await watcher.worker_js("globalThis.picked = null; chrome.runtime.onMessage.addListener(message => {"
                            " if (message.type === 'picked') globalThis.picked = message; }); true")
    tab = await watcher.worker_js("chrome.tabs.query({}).then(tabs => tabs.find(tab => "
                                  "tab.url.includes('orders.html')).id)")
    await watcher.worker_js(f"chrome.scripting.executeScript({{target: {{tabId: {tab}}}, files: ['picker.js']}})"
                            ".then(() => true)")
    await page("const cell = document.querySelector('#orders tbody td');"
               "cell.dispatchEvent(new MouseEvent('mousemove', {bubbles: true}));"
               "cell.closest('tbody').dispatchEvent(new MouseEvent('click', {bubbles: true})); true")
    assert await until(watcher.worker_js, "globalThis.picked !== null")
    picked = await watcher.worker_js("globalThis.picked")
    count = await page(f"document.querySelectorAll({json.dumps(picked['selector'])}).length")
    same = await page(f"document.querySelector({json.dumps(picked['selector'])}) === "
                      "document.querySelector('#orders tbody')")
    assert count == 1 and same and "#1001" in picked["sample"]


@CHROME
async def test_draft_fills_the_box_and_clicks_nothing(watcher):
    verdicts = [{"id": "gmail:t1", "kind": "needs_reply", "summary": "Maria asks to move the launch",
                 "why": "a client", "suggest": "draft"}]
    watcher.script.write_text(json.dumps({"default": [{"result": "[]"}],
                                          "You sort new messages": [{"result": json.dumps(verdicts)}],
                                          "You draft a reply": [{"result": "Monday works for us."}]}))
    await watcher.watch("gmail", "brain/gmail.html")
    assert await watcher.until(lambda: "t1" in watcher.raw_ids())
    await watcher.brain.draft("gmail:t1")
    item = watcher.brain.store.get("gmail:t1")
    assert item.state == "draft_ready" and item.draft == "Monday works for us.", item.note
    prompt = [json.loads(line) for line in watcher.log.read_text().splitlines()
              if line.startswith('{"oneshot"') and "You draft a reply" in line][0]["oneshot"]
    assert "Can we move the launch to Monday?" in prompt  # the thread, read from the opened page
    await watcher.brain.approve("gmail:t1", "Monday works.\nThanks, Kurl", 1)
    assert await watcher.until(lambda: watcher.brain.store.get("gmail:t1").state == "filled")
    targets = (await watcher.cdp.send("Target.getTargets"))["targetInfos"]
    thread = next(t for t in targets if t["type"] == "page" and "gmail.html#" in t["url"])
    session = (await watcher.cdp.send("Target.attachToTarget", {"targetId": thread["targetId"],
                                                                 "flatten": True}))["sessionId"]
    box = await evaluate(watcher.cdp, session, "document.getElementById('box').innerText")
    reply, signature = box.split("-- Kurl, Web team")  # the reply above the user's signature, which stays
    assert reply.replace("\n\n", "\n").strip() == "Monday works.\nThanks, Kurl" and signature.strip() == ""
    assert await evaluate(watcher.cdp, session, "window.sendClicks") == 0


@CHROME
async def test_items_wait_while_the_app_is_off(watcher):
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore

    target, page = await watcher.watch("gmail", "brain/gmail.html")
    assert await watcher.until(lambda: watcher.raw_ids() == {"t1", "t2"})
    await watcher.server.stop()
    await page("addRow({id: 't3', from: 'Ana', email: 'ana@client.example', subject: 'Quote', "
               "snippet: 'Price?'}); true")
    await asyncio.sleep(1.5)  # read while the app is off: kept by the watcher
    await watcher.cdp.send("Target.closeTarget", {"targetId": target})  # and the page is gone before it is back
    brain = BrainService(BrainStore(watcher.home), watcher.server.agents, claude=str(watcher.runner), batch_wait=0.2,
                         reader_timeout=2)
    server, _ = await start_server(watcher.home, watcher.server.agents, brain)
    server.allow_origin(f"chrome-extension://{watcher.app.extension_id}", watcher=True)
    watcher.server, watcher.brain = server, brain
    assert await watcher.until(lambda: watcher.raw_ids() == {"t1", "t2", "t3"}, 15)
    await asyncio.sleep(1)
    assert watcher.sorted_calls() == 2  # t3 arrived once


@CHROME
async def test_pause_unregisters_the_readers(watcher):
    _, page = await watcher.watch("gmail", "brain/gmail.html")
    assert await watcher.until(lambda: watcher.raw_ids() == {"t1", "t2"})
    watcher.brain.set_paused(True)
    assert await until(watcher.worker_js, "chrome.scripting.getRegisteredContentScripts()"
                                          ".then(scripts => scripts.length === 0)")
    await page("addRow({id: 't3', from: 'Ana', email: 'ana@client.example', subject: 'Quote', "
               "snippet: 'Price?'}); true")
    await asyncio.sleep(1.5)
    assert watcher.raw_ids() == {"t1", "t2"} and watcher.sorted_calls() == 1


async def tab_of(watcher, part):
    return await watcher.worker_js(f"chrome.tabs.query({{}}).then(tabs => tabs.find(tab => tab.url.includes({json.dumps(part)})).id)")


async def fill(watcher, tab, text):
    """The watcher's fill message to a tab's reader, as fillReply sends it; the reader's answer."""
    return await watcher.worker_js(f"chrome.tabs.sendMessage({tab}, {{type: 'fill', text: {json.dumps(text)}}})")


def status(watcher, site):
    return watcher.brain.store.entry(site).status


@CHROME
async def test_gmail_reads_only_the_inbox(watcher):
    _, page = await watcher.watch("gmail", "brain/gmail.html", open_at="brain/gmail.html#spam")
    assert await watcher.until(lambda: status(watcher, "gmail").startswith("open the inbox"), 8)
    assert watcher.raw_ids() == set()  # unread spam (or a label, or a search) is never read
    await page("location.hash = '#inbox'; true")
    assert await watcher.until(lambda: watcher.raw_ids() == {"t1", "t2"})
    assert await watcher.until(lambda: status(watcher, "gmail") == "")


@CHROME
async def test_an_empty_inbox_or_a_second_tab_raises_no_alarm(watcher):
    await watcher.watch("gmail", "brain/gmail", open_at="brain/gmail-empty.html")
    await asyncio.sleep(3.5)  # past the reader's 2 s timeout
    assert status(watcher, "gmail") == ""  # Inbox Zero is not a broken reader
    await open_page(watcher.cdp, watcher.base + "brain/gmail.html?broken")  # this tab's layout is unknown
    await asyncio.sleep(3.5)
    assert status(watcher, "gmail") == ""  # another tab reads the inbox fine


@CHROME
async def test_gmail_fill_goes_above_the_signature_and_replaces_its_own_text(watcher):
    _, page = await watcher.watch("gmail", "brain/gmail.html", open_at="brain/gmail.html#all/t1")
    tab = await tab_of(watcher, "#all/t1")
    box = "document.getElementById('box')"
    assert (await fill(watcher, tab, "Monday works.\nThanks, Kurl"))["ok"]
    first = await page(f"{box}.innerText")
    assert first.index("Monday works.") < first.index("Thanks, Kurl") < first.index("-- Kurl, Web team")
    html = await page(f"{box}.innerHTML")
    assert (await fill(watcher, tab, "Monday works.\nThanks, Kurl"))["ok"]
    assert await page(f"{box}.innerHTML") == html  # the same text again changes nothing
    assert (await fill(watcher, tab, "Tuesday works better."))["ok"]
    now = await page(f"{box}.innerText")
    assert "Monday" not in now and now.index("Tuesday works better.") < now.index("-- Kurl, Web team")
    assert now.count("-- Kurl, Web team") == 1 and await page("window.sendClicks") == 0


@CHROME
async def test_slack_gets_one_line_once(watcher):
    _, page = await watcher.watch("slack", "brain/slack.html", open_at="brain/slack.html#/client/T1/C1")
    tab = await tab_of(watcher, "slack.html")
    composer = "document.getElementById('composer').innerText.trim()"
    answer = await fill(watcher, tab, "Monday works.\nThanks, Kurl")
    assert answer["ok"] and "one line" in answer["reason"]  # Enter sends in Slack: no line breaks typed
    assert await page(composer) == "Monday works. Thanks, Kurl"
    await fill(watcher, tab, "Monday works.\nThanks, Kurl")
    assert await page(composer) == "Monday works. Thanks, Kurl"  # once
    await fill(watcher, tab, "Tuesday then.")
    assert await page(composer) == "Tuesday then."  # only the watcher's text was there: replaced


@CHROME
async def test_rows_keep_their_ids_when_their_times_change(watcher):
    _, page = await watcher.watch("custom:localhost", "brain/orders.html", selector="#orders tbody")
    await asyncio.sleep(2)
    await page("tickTimes(); true")  # "just now" becomes "1 minute ago"
    await asyncio.sleep(2.5)
    assert watcher.raw_ids("custom:localhost") == set()
    await page("addOrder('#1002', 'Ben', '$75'); true")
    assert await watcher.until(lambda: len(watcher.raw_ids("custom:localhost")) == 1)
    await page("tickTimes(); true")
    await asyncio.sleep(2.5)
    assert len(watcher.raw_ids("custom:localhost")) == 1 and watcher.sorted_calls() == 1
    _, asana = await watcher.watch("asana", "brain/asana.html")
    assert await watcher.until(lambda: len(watcher.raw_ids("asana")) == 1)
    await asana("tick(); true")  # "5 minutes ago" becomes "6 minutes ago"
    await asyncio.sleep(2.5)
    assert len(watcher.raw_ids("asana")) == 1 and watcher.sorted_calls() == 2


@CHROME
async def test_asana_pages_other_than_the_inbox_raise_no_alarm(watcher):
    await watcher.watch("asana", "brain/asana.html", open_at="brain/asana.html?elsewhere")
    assert await watcher.until(lambda: status(watcher, "asana").startswith("open the Inbox"), 8)


@CHROME
async def test_a_site_switched_off_stops_reading_its_open_tabs(watcher):
    _, page = await watcher.watch("gmail", "brain/gmail.html")
    assert await watcher.until(lambda: watcher.raw_ids() == {"t1", "t2"})
    await watcher.worker_js("globalThis.heard = 0; chrome.runtime.onMessage.addListener((message) => {"
                            " if (message.type === 'items') globalThis.heard += 1; }); true")
    watcher.brain.set_watch({"site": "gmail", "enabled": False})
    assert await until(watcher.worker_js, "chrome.scripting.getRegisteredContentScripts()"
                                          ".then(scripts => scripts.length === 0)")
    await page("addRow({id: 't3', from: 'Ana', email: 'ana@client.example', subject: 'Quote', "
               "snippet: 'Price?'}); true")
    await asyncio.sleep(2.5)
    assert await watcher.worker_js("globalThis.heard") == 0


@CHROME
async def test_another_region_on_the_same_site_starts_from_what_is_there(watcher):
    await watcher.watch("custom:localhost", "brain/orders.html", selector="#orders tbody")
    await asyncio.sleep(2)
    assert watcher.brain.set_watch({"site": "custom:localhost", "selector": "#notes"}) == ""
    await asyncio.sleep(3)
    assert watcher.raw_ids("custom:localhost") == set()  # the notes already there aren't news


@CHROME
async def test_a_notification_and_a_permission_request_at_once_keep_both(watcher):
    item = {"id": "gmail:t9", "site": "gmail", "sender": "Ana", "subject": "Hi", "summary": "Hello", "kind": "new",
            "state": "open", "suggest": "tell", "url": ""}
    watcher.brain.send_watcher({"type": "notify", "items": [item], "count": 1})
    watcher.brain.send_watcher({"type": "permission_request", "agent": "a1", "server": "clickup",
                                "tool": "mcp__clickup__create_task", "request": "r1"})
    assert await until(watcher.worker_js, "chrome.storage.session.get('notes')"
                                          ".then(({notes = {}}) => Object.keys(notes).length === 2)")


@CHROME
async def test_notifications_say_what_started_and_added_sites_watch_their_page(watcher):
    _, js = await open_page(watcher.cdp, f"chrome-extension://{watcher.app.extension_id}/brain.html")
    notify = "import('./notify.js').then(({notificationFor}) => notificationFor([{item}]))"
    started = await js(notify.replace("{item}", json.dumps({
        "id": "asana:3", "site": "asana", "sender": "Ana", "subject": "Task 3", "summary": "Fix the footer",
        "state": "agent", "note": "Started Site fix", "suggest": "agent", "kind": "new", "url": "https://x.example/3"})))
    assert started["options"]["message"].startswith("Started Site fix")
    assert [button["title"] for button in started["options"]["buttons"]] == ["Open"]  # no second agent from here
    plain = await js(notify.replace("{item}", json.dumps({
        "id": "gmail:t1", "site": "gmail", "sender": "Maria", "subject": "Launch", "summary": "Maria asks",
        "state": "open", "suggest": "draft", "kind": "needs_reply", "url": ""})))
    assert [button["title"] for button in plain["options"]["buttons"]] == ["Draft reply", "Open"]
    patterns = await js("import('./sites.js').then(({watchPattern}) => [watchPattern("
                        "'https://shop.example.com/admin/orders?status=new'), watchPattern('https://shop.example.com/')])")
    assert patterns == ["https://shop.example.com/admin/orders*", "https://shop.example.com/*"]
