// Settings → Brain: the switch that lets AI Browser read the user's Gmail, Slack and Asana tabs (off until they turn
// it on), what the Brain listens to (a checkbox per source, each on until the user unchecks it), whether it hands tasks
// to working agents by itself (15 s to cancel), how reading goes for each site, the parts of pages they watch, and
// Pick the part to watch. The picker runs in one of the user's open tabs in Brave, only on their click here, and only
// while the switch is on. Every name, title and sample is set as text.
"use strict";

const SITES = new Set(["gmail", "slack", "asana"]);
const STATES = { on: "Reading your open tabs in Brave.",
                 waiting: "Waiting for Brave: connect it at the top of Mission Control.",
                 off: "Off: AI Browser reads none of your tabs." };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function host(url) {
  try {
    return new URL(url).host;
  } catch {
    return "";
  }
}

export function mountBrainSettings(parts, send) {
  // parts: {toggle, sources, autoHand, state, sites, watched, pickTab, pickStart, pickNote}
  let on = false;
  let sources = {}; // the saved checkboxes: a refused change puts them back
  let autoHand = true;
  let reading = "off";
  let tabs = [];
  let picking = false;

  parts.toggle.addEventListener("change", () => {
    send({ type: "settings_set", key: "read_tabs", value: parts.toggle.checked, request: "read_tabs" });
  });
  parts.sources.addEventListener("change", () => { // every checkbox, as it now reads
    const value = Object.fromEntries([...parts.sources.querySelectorAll("input[data-source]")]
      .map((box) => [box.dataset.source, box.checked]));
    send({ type: "settings_set", key: "brain_sources", value, request: "brain_sources" });
  });
  parts.autoHand.addEventListener("change", () => {
    send({ type: "settings_set", key: "auto_hand", value: parts.autoHand.checked, request: "auto_hand" });
  });
  parts.pickStart.addEventListener("click", () => {
    const target = parts.pickTab.value;
    if (!on || picking || !target) return;
    picking = true;
    parts.pickNote.textContent = "In Brave: point at the part to watch and click it. Escape cancels.";
    renderPick();
    send({ type: "watch_pick", target, request: "pick" });
  });

  function renderPick() {
    const choices = tabs.filter((tab) => tab.owner?.kind === "you" && /^https?:\/\//.test(tab.url));
    const before = parts.pickTab.value;
    parts.pickTab.replaceChildren(...choices.map((tab) => {
      const option = el("option", "", `${tab.title || host(tab.url)} · ${host(tab.url)}`);
      option.value = tab.target;
      return option;
    }));
    if (choices.some((tab) => tab.target === before)) parts.pickTab.value = before;
    parts.sites.hidden = !on; // off: no empty site headings and no empty picker; the note says why
    parts.pickTab.closest(".brain-pick").hidden = !on && !picking;
    parts.pickTab.disabled = !on || picking || !choices.length;
    parts.pickStart.disabled = !on || picking || !choices.length;
    if (!on && !picking) parts.pickNote.textContent = "Turn on Read my Gmail, Slack and Asana tabs first.";
    else if (!choices.length && !picking) parts.pickNote.textContent = "Open the page in Brave first.";
  }

  function renderWatch(list) {
    parts.sites.replaceChildren();
    parts.watched.replaceChildren();
    for (const entry of list) {
      const line = el("div", "brain-site");
      line.dataset.site = entry.site;
      line.append(el("strong", "", entry.label || entry.site));
      if (SITES.has(entry.site)) {
        const note = reading !== "on" ? "" : entry.status || "reading";
        line.append(el("span", "muted", note ? ` · ${note}` : ""));
        parts.sites.append(line);
        continue;
      }
      line.append(el("span", "muted", ` · ${host(entry.url_match.replace(/\*$/, ""))}`));
      if (entry.enabled && entry.status && reading === "on") line.append(el("span", "muted", ` · ${entry.status}`));
      const toggle = el("button", "ghost", entry.enabled ? "Turn off" : "Turn on");
      toggle.addEventListener("click", () => send({ type: "watch_set", site: entry.site, enabled: !entry.enabled }));
      const remove = el("button", "ghost", "Remove");
      remove.addEventListener("click", () => send({ type: "watch_remove", site: entry.site }));
      line.append(toggle, remove);
      parts.watched.append(line);
    }
    if (!parts.watched.children.length) parts.watched.append(el("p", "muted", "No parts of pages yet."));
  }

  function showChoices() {
    for (const box of parts.sources.querySelectorAll("input[data-source]")) {
      box.checked = sources[box.dataset.source] !== false;
    }
    parts.autoHand.checked = autoHand;
  }

  function settings(values) { // the app's settings: read_tabs, brain_sources and auto_hand
    if (!values) return;
    on = values.read_tabs === true;
    parts.toggle.checked = on;
    sources = values.brain_sources || {};
    autoHand = values.auto_hand !== false;
    showChoices();
    renderPick();
  }

  function onMessage(message) {
    if (message.type === "snapshot") {
      settings(message.settings);
      tabs = message.tabs || [];
      renderPick();
      send({ type: "brain" }); // the watch list and how reading goes
    } else if (message.type === "settings") {
      settings(message);
    } else if (message.type === "tabs") {
      tabs = message.tabs || [];
      renderPick();
    } else if (message.type === "brain_snapshot" || message.type === "brain_state") {
      reading = message.reading || "off";
      parts.state.textContent = STATES[reading] || "";
      renderWatch(message.watch_list || []);
    } else if (message.type === "watch_picked") {
      picking = false;
      parts.pickNote.textContent = message.error ? message.error
        : message.cancelled ? "Nothing was picked."
          : `Watching it now${message.sample ? `: ${message.sample.slice(0, 120)}` : "."}`;
      renderPick();
    } else if (message.type === "error" && message.request === "read_tabs") {
      parts.state.textContent = message.text || "";
      parts.toggle.checked = on; // the saved value stays
    } else if (message.type === "error" && ["brain_sources", "auto_hand"].includes(message.request)) {
      parts.state.textContent = message.text || "";
      showChoices(); // the saved values stay
    }
  }

  renderPick();
  return { onMessage };
}
