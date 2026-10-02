// AI Browser's worker: AI Home as the pinned first tab, each agent's tabs in a Chrome tab group of its own, the
// toolbar badge (agents working), and the address bar keyword: type "ai", a space and a task.
import { connect, tabOfTarget } from "./link.js";

const HOME = chrome.runtime.getURL("home.html");
const agents = new Map(); // id -> the agent as the app describes it
const grouped = new Set(); // targets grouped once: a tab the user takes out of its group stays out
const groups = new Map(); // agent id -> its tab group
const targetsOf = new Map(); // agent id -> its targets, to ungroup the user's own tabs when the agent is closed

// Clicking the toolbar icon (or pressing ⌘⇧Y) opens the chat in the side panel.
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

async function homeTab() {
  const tabs = await chrome.tabs.query({}).catch(() => []);
  return tabs.find((tab) => (tab.url || tab.pendingUrl || "").startsWith(HOME));
}

// Exactly one pinned AI Home, first in each window and in front (a restored session may bring a second one back).
async function ensureHome() {
  const tabs = await chrome.tabs.query({}).catch(() => []);
  const windows = await chrome.windows.getAll({ windowTypes: ["normal"] }).catch(() => []);
  for (const window of windows) {
    const homes = tabs.filter((tab) => tab.windowId === window.id && (tab.url || tab.pendingUrl || "").startsWith(HOME));
    let keep = homes.find((tab) => tab.pinned) || homes[0];
    for (const extra of homes) {
      if (extra !== keep && extra.pinned) await chrome.tabs.remove(extra.id).catch(() => {});
    }
    if (!keep) {
      await chrome.tabs.create({ windowId: window.id, url: HOME, pinned: true, index: 0, active: true }).catch(() => {});
      continue;
    }
    if (!keep.pinned) await chrome.tabs.update(keep.id, { pinned: true }).catch(() => {});
    await chrome.tabs.move(keep.id, { index: 0 }).catch(() => {});
    await chrome.tabs.update(keep.id, { active: true }).catch(() => {});
  }
}
globalThis.ensureHome = ensureHome;

chrome.runtime.onInstalled.addListener(() => ensureHome());
chrome.runtime.onStartup.addListener(() => ensureHome());

function updateBadge() {
  const working = [...agents.values()].filter((agent) => agent.state === "working").length;
  chrome.action.setBadgeText({ text: working ? String(working) : "" }).catch(() => {});
  chrome.action.setBadgeBackgroundColor({ color: "#c96442" }).catch(() => {});
}

async function groupFor(agent, tab) {
  const known = groups.get(agent.id);
  if (known !== undefined) {
    try {
      const group = await chrome.tabGroups.get(known);
      if (group.windowId === tab.windowId) return known;
    } catch {
      groups.delete(agent.id); // the user closed or dissolved it
    }
  }
  return undefined;
}

async function groupTabs(agent) {
  const mine = targetsOf.get(agent.id) || new Set();
  targetsOf.set(agent.id, mine);
  for (const target of [...(agent.tabs || []), ...(agent.adopted || [])]) {
    mine.add(target);
    if (grouped.has(target)) continue;
    grouped.add(target); // before any await: two updates must not group the same tab twice
    const tabId = await tabOfTarget(target);
    if (tabId === null) {
      grouped.delete(target); // not a tab Chrome knows yet: the next update tries again
      continue;
    }
    try {
      const tab = await chrome.tabs.get(tabId);
      if (tab.pinned) continue; // pinned tabs can't be grouped (AI Home is one)
      let groupId = await groupFor(agent, tab);
      if (groupId === undefined) {
        groupId = await chrome.tabs.group({ tabIds: [tabId], createProperties: { windowId: tab.windowId } });
        groups.set(agent.id, groupId);
      } else {
        await chrome.tabs.group({ tabIds: [tabId], groupId });
      }
      await chrome.tabGroups.update(groupId, { title: agent.name, color: agent.color, collapsed: false });
    } catch {
      // the tab closed meanwhile
    }
  }
}

async function ungroupTabs(agentId) {
  for (const target of targetsOf.get(agentId) || []) {
    grouped.delete(target);
    const tabId = await tabOfTarget(target);
    if (tabId !== null) await chrome.tabs.ungroup(tabId).catch(() => {}); // the user's own tabs stay, ungrouped
  }
  targetsOf.delete(agentId);
  groups.delete(agentId);
}

const workflows = new Map(); // a workflow's name in lower case -> its slug: "ai <name> …" runs it

function onMessage(message) {
  if (message.type === "workflows_snapshot") {
    workflows.clear();
    for (const workflow of message.workflows || []) workflows.set(String(workflow.name).toLowerCase(), workflow.slug);
    return;
  }
  if (message.type === "snapshot") {
    agents.clear();
    for (const agent of message.agents) {
      agents.set(agent.id, agent);
      groupTabs(agent);
    }
  } else if (message.type === "agent") {
    agents.set(message.agent.id, message.agent);
    groupTabs(message.agent);
  } else if (message.type === "agent_closed") {
    agents.delete(message.id);
    ungroupTabs(message.id);
  } else {
    return;
  }
  updateBadge();
}

const link = connect({
  view: "worker",
  onMessage,
  onState: (state) => { if (state === "connected") link.send({ type: "workflows" }); },
});

function workflowFor(task) { // the longest workflow name the text starts with (then a space, or nothing more)
  const lower = task.toLowerCase();
  let found = null;
  for (const [name, slug] of workflows) {
    if ((lower === name || lower.startsWith(`${name} `)) && (!found || name.length > found.name.length)) {
      found = { name, slug };
    }
  }
  return found;
}

// "ai" + space + a task in the address bar: a new agent (or that workflow), and AI Home in front to watch it.
async function startTask(text) {
  const task = String(text || "").trim();
  if (!task) return;
  const stored = await chrome.storage.local.get("model").catch(() => ({}));
  await link.whenOpen();
  const workflow = workflowFor(task);
  if (workflow) {
    link.send({ type: "workflow_run", slug: workflow.slug, text: task.slice(workflow.name.length).trim(),
                request: `ai-${Date.now()}` });
  } else {
    link.send({ type: "new_task", text: task, skills: [], model: stored.model || "sonnet", request: `ai-${Date.now()}` });
  }
  const home = await homeTab();
  if (home) chrome.tabs.update(home.id, { active: true }).catch(() => {});
  else chrome.tabs.create({ url: HOME }).catch(() => {});
}
globalThis.startTask = startTask;

chrome.omnibox.setDefaultSuggestion({ description: "Start an AI Browser agent: %s" });
chrome.omnibox.onInputEntered.addListener((text) => startTask(text));
