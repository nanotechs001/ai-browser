// The AI's tabs in tab groups, in the user's Brave. The app asks (group_tab) and the watcher answers (tab_grouped):
// it finds the one tab the request names (by a secret mark in its first address, by its address in the opener's
// window, or by its exact address for a tab the user handed over) and puts it in the group for that key, titled and
// coloured as asked. Grouping is a picture only: it moves the AI's tabs into, out of and between groups and windows,
// never a handed tab to another window, and it reads nothing inside pages, only the tab facts `tabs` already gives.
// Its one other act: when a link the AI clicked opened a tab in front, the user's tab gets the focus back.
"use strict";

export const COLORS = new Set(["grey", "blue", "red", "yellow", "green", "pink", "purple", "cyan", "orange"]);
const KEY = /^[a-z0-9-]{1,40}$/;
const MARKER = /^[0-9a-f]{16}$/;
const FIND_FOR = 1000; // ms to look for the tab
const NEW_FOR = 5000; // ms: a tab one of the AI's pages opened is that new
const NONE = -1; // chrome.tabGroups.TAB_GROUP_ID_NONE
let grouping = Promise.resolve(); // one at a time: two requests for one key must not make two groups
let noting = Promise.resolve();

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const shows = (tab, url) => tab.url === url || tab.pendingUrl === url;

export function groupsAvailable() {
  return typeof chrome.tabGroups === "object" && typeof chrome.tabs?.group === "function";
}

export function valid(message) { // only what the app may ask: a short key, Brave's colours, a short plain title
  const find = message?.find;
  if (!KEY.test(String(message?.key ?? "")) || !COLORS.has(message?.color)) return false;
  if (typeof message.title !== "string" || message.title.length > 40 || !find || typeof find !== "object") return false;
  if ("marker" in find) return MARKER.test(String(find.marker));
  if ("opener_tab" in find) return Number.isInteger(find.opener_tab) && typeof find.url === "string";
  return typeof find.url === "string" && /^https?:\/\//.test(find.url);
}

// Called once at the worker's top level: a tab a page opened is told apart from older ones by its age.
export function watchNewTabs() {
  chrome.tabs.onCreated.addListener((tab) => {
    noting = noting.then(async () => {
      const { born = {} } = await chrome.storage.session.get("born");
      const now = Date.now();
      const kept = Object.fromEntries(Object.entries(born).filter(([, at]) => now - at < 30_000));
      await chrome.storage.session.set({ born: { ...kept, [tab.id]: now } });
    }).catch(() => {});
  });
}

async function stored() {
  const { groups = {}, grouped = [] } = await chrome.storage.session.get(["groups", "grouped"]);
  return { groups, grouped };
}

async function candidates(find) {
  const tabs = await chrome.tabs.query({}).catch(() => []);
  if ("marker" in find) return tabs.filter((tab) => shows(tab, `about:blank#aib-${find.marker}`));
  if ("opener_tab" in find) {
    // Measured: a tab opened from a background tab gets the window's active tab as its openerTabId, so the tab is
    // found by its address, in the opener's window, new, and not grouped yet or already in its opener's group (Chrome
    // puts a tab a grouped tab opened in that group by itself).
    const opener = await chrome.tabs.get(find.opener_tab).catch(() => null);
    if (!opener) return [];
    await noting;
    const { born = {} } = await chrome.storage.session.get("born");
    const now = Date.now();
    return tabs.filter((tab) => tab.windowId === opener.windowId && tab.id !== opener.id
      && (tab.groupId === NONE || tab.groupId === opener.groupId)
      && now - (born[tab.id] || 0) < NEW_FOR && (!find.url || shows(tab, find.url)));
  }
  return tabs.filter((tab) => shows(tab, find.url));
}

async function findTab(find) {
  const end = Date.now() + FIND_FOR;
  for (;;) {
    const found = await candidates(find);
    if (found.length > 1) return { reason: "ambiguous" }; // never a guess
    if (found.length === 1) return { tab: found[0] };
    if (Date.now() >= end) return { reason: "not_found" };
    await sleep(100);
  }
}

async function live(groupId, windowId) { // a stored group the user closed or dissolved is replaced by a new one
  if (groupId === undefined) return undefined;
  try {
    const group = await chrome.tabGroups.get(groupId);
    return group.windowId === windowId ? groupId : undefined;
  } catch {
    return undefined;
  }
}

async function put(tab, key, title, color, mayMove) {
  const { groups } = await stored();
  const mine = groups[key] || {};
  let windowId = tab.windowId;
  let groupId = await live(mine[windowId], windowId);
  if (groupId === undefined && mayMove) { // the key's group in another window: the tab moves there first
    for (const [other, id] of Object.entries(mine)) {
      const found = await live(id, Number(other));
      if (found !== undefined) {
        await chrome.tabs.move(tab.id, { windowId: Number(other), index: -1 });
        windowId = Number(other);
        groupId = found;
        break;
      }
    }
  }
  groupId = groupId === undefined
    ? await chrome.tabs.group({ tabIds: [tab.id], createProperties: { windowId } })
    : await chrome.tabs.group({ tabIds: [tab.id], groupId });
  await chrome.tabGroups.update(groupId, { title, color, collapsed: false }); // a plain string: never markup
  const now = await stored();
  await chrome.storage.session.set({
    groups: { ...now.groups, [key]: { ...(now.groups[key] || {}), [windowId]: groupId } },
    grouped: [...new Set([...now.grouped, tab.id])],
  });
  return { tab: tab.id, window: windowId, group: groupId };
}

// Measured: a link clicked in the AI's background tab opens its new tab in front, in place of the tab the user was on
// (which Chrome names as the new tab's openerTabId). Only Watch or a bot check may bring the AI's tabs forward, so the
// user's tab gets the focus back. When the user was watching the AI's tab itself, the new tab stays in front.
async function giveFocusBack(tab, opener) {
  const now = await chrome.tabs.get(tab.id).catch(() => null);
  if (!now?.active || !Number.isInteger(now.openerTabId) || now.openerTabId === opener) return;
  await chrome.tabs.update(now.openerTabId, { active: true }).catch(() => {});
}

async function place(message) {
  const request = message?.request;
  if (!groupsAvailable() || !valid(message)) return { request, ok: false, reason: "not_found" };
  const { tab, reason } = await findTab(message.find);
  if (!tab) return { request, ok: false, reason };
  if (tab.pinned) return { request, ok: false, reason: "pinned" };
  if ("opener_tab" in message.find) await giveFocusBack(tab, message.find.opener_tab);
  const handed = !("marker" in message.find) && !("opener_tab" in message.find); // never moved to another window
  try {
    return { request, ok: true, ...(await put(tab, message.key, message.title, message.color, !handed)) };
  } catch {
    return { request, ok: false, reason: "not_found" }; // closed meanwhile, or in a popup window (no groups there)
  }
}

export function groupTab(message) {
  const answer = grouping.then(() => place(message));
  grouping = answer.catch(() => {});
  return answer;
}

export async function ungroupTabs(tabIds) { // only tabs the watcher grouped itself: never one of the user's groups
  const { grouped } = await stored();
  const ours = (Array.isArray(tabIds) ? tabIds : []).filter((id) => Number.isInteger(id) && grouped.includes(id));
  for (const id of ours) await chrome.tabs.ungroup(id).catch(() => {});
  if (ours.length) await chrome.storage.session.set({ grouped: grouped.filter((id) => !ours.includes(id)) });
}

export function groupBrainTab(tab) { // a thread the watcher opened itself: it knows the tab, no matching needed
  if (!groupsAvailable() || !tab?.id) return Promise.resolve();
  const done = grouping.then(() => put(tab, "brain", "Brain", "purple", false)).catch(() => {});
  grouping = done;
  return done;
}
