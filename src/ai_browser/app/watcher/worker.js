// The watcher's worker, in the user's everyday browser (Brave). It keeps the line to `ai-browser app` (the Brain),
// registers a reader (a content script) for each site the user watches, shows the Brain's notifications, and does
// the only two things it ever does in a page: open a thread when the user asks for a draft, and put the reply the
// user approved into that thread's reply box. It never sends anything.
import { BUILD } from "./build.js";
import { connect } from "./link.js";
import { notificationFor } from "./notify.js";

const BRAIN = chrome.runtime.getURL("brain.html");
const READERS = new Set(["gmail", "slack", "asana"]); // added sites use the region reader
const UNSENT_LIMIT = 200; // reports kept while the app is off (beyond that, the oldest go first)
const RELOAD_EVERY = 60_000;
let storing = Promise.resolve();
let syncing = Promise.resolve(); // one watch list at a time: two close together don't race
let noting = Promise.resolve(); // one write at a time to the notifications' notes
let reporting = Promise.resolve(); // one write at a time to the readers' reports
let checking = null;
const threadTabs = new Map(); // a thread's address -> the tab opened for it

const link = connect({
  view: "watcher",
  onMessage: (message) => { handle(message).catch(() => {}); },
  onState: (state) => {
    chrome.action.setBadgeText({ text: state === "connected" ? "" : "off" }).catch(() => {});
    chrome.action.setBadgeBackgroundColor({ color: "#6b6a66" }).catch(() => {});
    if (state === "connected") flush();
  },
});

function readerOf(site) {
  return READERS.has(site) ? site : "region";
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---- the line to the Brain ------------------------------------------------------------------------------------

function send(message) { // a report that matters later: kept while the app is off
  if (!link.send(message)) remember(message);
}

function remember(message) {
  storing = storing.then(async () => {
    const { unsent = [] } = await chrome.storage.session.get("unsent");
    unsent.push(message);
    await chrome.storage.session.set({ unsent: unsent.slice(-UNSENT_LIMIT) });
  }).catch(() => {});
}

function flush() {
  storing = storing.then(async () => {
    const { unsent = [] } = await chrome.storage.session.get("unsent");
    let sent = 0;
    while (sent < unsent.length && link.send(unsent[sent])) sent += 1;
    await chrome.storage.session.set({ unsent: unsent.slice(sent) });
  }).catch(() => {});
}

async function handle(message) {
  if (message.type === "watcher_hello") await checkBuild(message.build);
  else if (message.type === "watch_list") {
    const list = { sites: Array.isArray(message.sites) ? message.sites : [], paused: Boolean(message.paused),
                   reader_timeout: message.reader_timeout || 120 };
    syncing = syncing.then(async () => {
      await chrome.storage.local.set({ watchList: list });
      await sync();
    }).catch(() => {});
    await syncing;
  } else if (message.type === "notify") await notify(message);
  else if (message.type === "permission_request") await askPermission(message);
  else if (message.type === "open_thread") await openThread(message);
  else if (message.type === "fill_reply") await fillReply(message);
}

async function checkBuild(build) { // the app has newer watcher files on disk: load them
  if (!build || build === BUILD) return;
  const { reloadedAt = 0 } = await chrome.storage.session.get("reloadedAt");
  if (Date.now() - reloadedAt < RELOAD_EVERY) return;
  await chrome.storage.session.set({ reloadedAt: Date.now() });
  chrome.runtime.reload();
}

// ---- the readers ----------------------------------------------------------------------------------------------

async function watchList() {
  const { watchList: list } = await chrome.storage.local.get("watchList");
  return list || { sites: [], paused: false, reader_timeout: 120 };
}

function matches(pattern, url) {
  const parts = /^(\*|https?):\/\/([^/]+)(\/.*)$/.exec(pattern);
  let address;
  try {
    address = new URL(url);
  } catch {
    return false;
  }
  if (!parts || (parts[1] !== "*" && address.protocol !== `${parts[1]}:`)) return false;
  const [host, port] = parts[2].split(":");
  const escape = (value) => value.replace(/[.+?^${}()|[\]\\]/g, "\\$&");
  const hostPattern = host.startsWith("*.") ? `^(?:[^.]+\\.)*${escape(host.slice(2))}$` : `^${escape(host)}$`;
  if (!new RegExp(hostPattern).test(address.hostname) || (port && address.port !== port)) return false;
  return new RegExp(`^${parts[3].split("*").map(escape).join(".*")}$`).test(address.pathname + address.search);
}

function baselineOf(site, selector) { // an added site starts from what is there, again for each part of it picked
  return `${site}|${selector || ""}`;
}

async function readerConfig(kind, url) {
  const list = await watchList();
  const site = list.sites.find((entry) => (kind === "region" ? readerOf(entry.site) === "region" &&
                                           matches(entry.url_match, url) : entry.site === kind));
  if (!site) return null;
  const { baselined = [] } = await chrome.storage.local.get("baselined");
  return { site: site.site, kind, selector: site.selector || "", url_match: site.url_match, paused: list.paused,
           reader_timeout: list.reader_timeout,
           baseline: kind === "region" && !baselined.includes(baselineOf(site.site, site.selector)) };
}

async function markBaselined(site, selector) {
  const { baselined = [] } = await chrome.storage.local.get("baselined");
  const key = baselineOf(site, selector);
  if (!baselined.includes(key)) await chrome.storage.local.set({ baselined: [...baselined, key] });
}

async function forgetBaselines(sites) { // a site removed, or another part of its page picked: it starts afresh
  const kept = new Set(sites.map((site) => baselineOf(site.site, site.selector)));
  const { baselined = [] } = await chrome.storage.local.get("baselined");
  const still = baselined.filter((key) => kept.has(key));
  if (still.length !== baselined.length) await chrome.storage.local.set({ baselined: still });
}

function status(site, ok, note) {
  link.send({ type: "reader_status", site, ok, note });
}

// Each tab's reader says how it reads; a site reads fine if any of its tabs does (a tab on Settings or a board is no
// alarm), and "reader needs an update" outranks "open the inbox". Kept in session storage: the worker may sleep.
function tell(site, states) {
  if (!states.length) return; // no reader has spoken yet (no tab at all: checkTabs says so)
  const best = states.find((state) => state.ok) || states.find((state) => !state.elsewhere) || states[0];
  status(site, best.ok, best.note);
}

function report(site, tabId, state) {
  reporting = reporting.then(async () => {
    const { readers = {} } = await chrome.storage.session.get("readers");
    const tabs = { ...(readers[site] || {}), [tabId]: state };
    await chrome.storage.session.set({ readers: { ...readers, [site]: tabs } });
    tell(site, Object.values(tabs));
  }).catch(() => {});
}

async function sync() {
  const list = await watchList();
  const wanted = list.paused ? [] : list.sites;
  const registered = await chrome.scripting.getRegisteredContentScripts().catch(() => []);
  const keep = new Set(wanted.map((site) => site.site));
  const stale = registered.filter((script) => !keep.has(script.id));
  if (stale.length) {
    await chrome.scripting.unregisterContentScripts({ ids: stale.map((script) => script.id) }).catch(() => {});
  }
  for (const script of stale) { // a site switched off or removed: its readers in open tabs stop reading too
    for (const tab of await chrome.tabs.query({ url: script.matches }).catch(() => [])) {
      chrome.tabs.sendMessage(tab.id, { type: "pause" }).catch(() => {});
    }
  }
  await forgetBaselines(list.sites);
  for (const site of wanted) {
    const files = ["readers/common.js", `readers/${readerOf(site.site)}.js`];
    if (!(await chrome.permissions.contains({ origins: [site.url_match] }).catch(() => false))) {
      status(site.site, false, "Brave hasn't allowed this site: add it again from the Brain page");
      continue;
    }
    const script = { id: site.site, matches: [site.url_match], js: files, runAt: "document_idle" };
    try {
      if (registered.some((known) => known.id === site.site)) await chrome.scripting.updateContentScripts([script]);
      else await chrome.scripting.registerContentScripts([script]);
    } catch (error) {
      status(site.site, false, `Can't watch this site: ${error.message}`);
      continue;
    }
    for (const tab of await chrome.tabs.query({ url: site.url_match }).catch(() => [])) { // pages already open
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files }).catch(() => {});
      chrome.tabs.sendMessage(tab.id, { type: "rescan" }).catch(() => {});
    }
  }
  if (list.paused) {
    for (const tab of await chrome.tabs.query({}).catch(() => [])) {
      chrome.tabs.sendMessage(tab.id, { type: "pause" }).catch(() => {});
    }
  }
  await checkTabs();
}

async function checkTabs() { // a watched site with no open tab can't be read: the watch list says so
  const list = await watchList();
  if (list.paused) return;
  reporting = reporting.then(async () => {
    const { readers = {} } = await chrome.storage.session.get("readers");
    const now = {};
    for (const site of list.sites) {
      const open = new Set((await chrome.tabs.query({ url: site.url_match }).catch(() => [])).map((tab) => `${tab.id}`));
      now[site.site] = Object.fromEntries(Object.entries(readers[site.site] || {}).filter(([tab]) => open.has(tab)));
      if (!open.size) status(site.site, false, "no open tab");
      else tell(site.site, Object.values(now[site.site]));
    }
    await chrome.storage.session.set({ readers: now });
  }).catch(() => {});
  await reporting;
}

function checkTabsSoon() {
  clearTimeout(checking);
  checking = setTimeout(() => { checkTabs().catch(() => {}); }, 1000);
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id || !message) return false;
  if (message.type === "reader_config") {
    readerConfig(message.kind, sender.tab?.url || sender.url || "").then(sendResponse, () => sendResponse(null));
    return true;
  }
  if (!sender.tab || typeof message.site !== "string") return false; // the rest come from readers in pages
  if (message.type === "items") {
    send({ type: "items", site: message.site, items: message.items, ...(message.baseline ? { baseline: true } : {}) });
    if (message.baseline) markBaselined(message.site, message.selector).catch(() => {});
  } else if (message.type === "replied") {
    send({ type: "replied", site: message.site, id: message.id });
  } else if (message.type === "status") {
    report(message.site, sender.tab.id, { ok: Boolean(message.ok), note: String(message.note || ""),
                                          elsewhere: Boolean(message.elsewhere) });
  }
  return false;
});

chrome.tabs.onRemoved.addListener(checkTabsSoon);
chrome.tabs.onUpdated.addListener((tabId, change) => { if (change.status === "complete") checkTabsSoon(); });

// ---- notifications --------------------------------------------------------------------------------------------

function keepNote(id, note) { // what a notification's buttons do, kept while the worker sleeps
  noting = noting.then(async () => {
    const { notes = {} } = await chrome.storage.session.get("notes");
    await chrome.storage.session.set({ notes: { ...notes, [id]: note } });
  }).catch(() => {});
  return noting;
}

async function notify({ items }) {
  if (!Array.isArray(items) || !items.length) return;
  const id = `n${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  const { options, note } = notificationFor(items);
  await keepNote(id, note);
  await chrome.notifications.create(id, { type: "basic", iconUrl: "icon.png", priority: 1, ...options });
}

// An agent waits for the user's yes to a tool. The notification can only deny: allowing happens on a card that shows
// the tool's exact input (the Brain page, AI Home or the chat panel).
async function askPermission(request) {
  const id = `p${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  const tool = String(request.tool || "").split("__").slice(2).join("__") || String(request.tool || "a tool");
  await keepNote(id, { permission: { agent: request.agent, request: request.request } });
  await chrome.notifications.create(id, {
    type: "basic", iconUrl: "icon.png", priority: 2, requireInteraction: true,
    title: `An agent wants ${request.server}: ${tool}`.slice(0, 120),
    message: "It waits for your answer. Review shows exactly what it would send.",
    buttons: [{ title: "Review" }, { title: "Deny" }],
  });
}

async function noteOf(id) {
  const { notes = {} } = await chrome.storage.session.get("notes");
  return notes[id] || {};
}

async function openBrain(itemId) {
  const url = BRAIN + (itemId ? `#item=${encodeURIComponent(itemId)}` : "");
  const tabs = await chrome.tabs.query({}).catch(() => []);
  const open = tabs.find((tab) => (tab.url || "").startsWith(BRAIN));
  if (open) {
    await chrome.tabs.update(open.id, { url, active: true });
    await chrome.windows.update(open.windowId, { focused: true }).catch(() => {});
  } else {
    await chrome.tabs.create({ url });
  }
}

chrome.notifications.onButtonClicked.addListener(async (id, index) => {
  const note = await noteOf(id);
  chrome.notifications.clear(id);
  if (note.permission) {
    if (index === 1) link.send({ type: "permission", ...note.permission, answer: "deny" });
    else await openBrain();
    return;
  }
  if (!note.item) return openBrain();
  if (index === (note.first === "open" ? 0 : 1)) { // Open: the message itself
    if (/^https?:\/\//.test(note.item.url || "")) await chrome.tabs.create({ url: note.item.url });
    else await openBrain(note.item.id);
  } else if (note.first === "draft") send({ type: "draft", id: note.item.id });
  else await openBrain(note.item.id); // Hand to agent: the user writes what to do there
});

chrome.notifications.onClicked.addListener(async (id) => {
  const note = await noteOf(id);
  chrome.notifications.clear(id);
  await openBrain(note.item?.id);
});

chrome.action.onClicked.addListener(() => { openBrain().catch(() => {}); });

// ---- the two things the watcher does in a page ----------------------------------------------------------------

async function loaded(tabId, ms = 20000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    const tab = await chrome.tabs.get(tabId).catch(() => null);
    if (!tab) return false;
    if (tab.status === "complete") return true;
    await sleep(200);
  }
  return false;
}

async function ask(tabId, message, ms, accept) { // the tab's reader may not be listening yet: try again until then
  const end = Date.now() + ms;
  while (Date.now() < end) {
    const answer = await chrome.tabs.sendMessage(tabId, message).catch(() => undefined);
    if (answer !== undefined && accept(answer)) return answer;
    await sleep(500);
  }
  return null;
}

async function openThread({ request, url }) {
  if (!/^https?:\/\//.test(url || "")) {
    link.send({ type: "thread", request, error: "this message has no web address" });
    return;
  }
  try {
    const tab = await chrome.tabs.create({ url, active: true });
    threadTabs.set(url, tab.id);
    await loaded(tab.id, 12000);
    const answer = await ask(tab.id, { type: "thread" }, 15000, (reply) => Boolean(reply?.text));
    link.send(answer ? { type: "thread", request, text: answer.text }
                     : { type: "thread", request, error: "the thread didn't show in time" });
  } catch (error) {
    link.send({ type: "thread", request, error: String(error?.message || error) });
  }
}

async function fillReply({ request, url, text }) {
  try {
    let tab = threadTabs.has(url) ? await chrome.tabs.get(threadTabs.get(url)).catch(() => null) : null;
    if (!tab || tab.url !== url) {
      tab = (await chrome.tabs.query({}).catch(() => [])).find((other) => other.url === url) || null;
    }
    if (!tab) {
      if (!/^https?:\/\//.test(url || "")) throw new Error("this message has no web address");
      tab = await chrome.tabs.create({ url, active: true });
      threadTabs.set(url, tab.id);
      await loaded(tab.id, 15000);
    }
    await chrome.tabs.update(tab.id, { active: true });
    await chrome.windows.update(tab.windowId, { focused: true }).catch(() => {});
    const answer = await ask(tab.id, { type: "fill", text: String(text || "") }, 15000,
                             (reply) => typeof reply?.ok === "boolean");
    link.send({ type: "filled", request, ok: Boolean(answer?.ok),
                reason: answer ? answer.reason || "" : "the page's reader didn't answer" });
  } catch (error) {
    link.send({ type: "filled", request, ok: false, reason: String(error?.message || error) });
  }
}

// ---- waking up ------------------------------------------------------------------------------------------------

// A sleeping worker has no line to the app: an alarm wakes it every 30 s, and waking up connects again.
chrome.alarms.create("reconnect", { periodInMinutes: 0.5 }).catch(() => {});
chrome.alarms.onAlarm.addListener(() => {});
chrome.runtime.onStartup.addListener(() => { sync().catch(() => {}); });
