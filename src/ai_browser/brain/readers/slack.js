// Slack's reader: direct messages and @mentions, from the sidebar's unread entries and badges (Slack shows them
// whichever conversation is open). Each unread spell of a conversation is one item: the engine keeps the spells
// (config.memory, given back as `memory`), so a spell is the same item across reads and restarts. The open
// conversation's messages give the text, and the user's own message there means they have answered.
"use strict";
(() => {
  if (globalThis.AIB.readers.slack) return;
  const S = {
    entry: "[data-qa-channel-sidebar-channel-id]", channelId: "data-qa-channel-sidebar-channel-id",
    type: "data-qa-channel-sidebar-channel-type", unread: "p-channel_sidebar__channel--unread",
    badge: ".p-channel_sidebar__badge", name: ".p-channel_sidebar__name",
    message: '[data-qa="message_container"]', sender: "[data-message-sender]", body: '[data-qa="message-text"]',
    composer: '[data-qa="message_input"] [contenteditable="true"]',
  };
  const DIRECT = new Set(["im", "mpim"]);
  const { text, typeInto } = globalThis.AIB;
  let episodes = {}; // channel -> {id, read}: one item per unread spell

  function place() { // /client/<team>/<channel> (Slack's address)
    const found = /\/client\/([^/?#]+)\/([^/?#]+)/.exec(location.pathname + location.hash);
    return found ? { team: found[1], channel: found[2] } : null;
  }

  function self(team) {
    try {
      return JSON.parse(localStorage.getItem("localConfig_v2") || "{}").teams?.[team]?.user_id || "";
    } catch {
      return "";
    }
  }

  function messages() {
    let sender = "";
    let name = "";
    return [...document.querySelectorAll(S.message)].map((node) => {
      const by = node.querySelector(S.sender);
      if (by) {
        sender = by.getAttribute("data-message-sender") || "";
        name = text(by);
      }
      return { sender, name, text: text(node.querySelector(S.body)) };
    });
  }

  function remembered(memory) { // the engine's copy of the spells: only well-formed entries
    const out = {};
    for (const [channel, episode] of Object.entries(memory && typeof memory === "object" ? memory : {})) {
      if (typeof episode?.id === "string" && /^[a-z0-9]{1,20}$/.test(episode.id)) {
        out[channel] = { id: episode.id, read: episode.read === true };
      }
    }
    return out;
  }

  globalThis.AIB.readers.slack = {
    check: () => Boolean(document.querySelector(S.entry)),
    items(config) {
      episodes = remembered(config.memory);
      const here = place();
      const me = here ? self(here.team) : "";
      const conversation = here ? messages() : [];
      const last = conversation[conversation.length - 1];
      const out = [];
      for (const entry of document.querySelectorAll(S.entry)) {
        const channel = entry.getAttribute(S.channelId);
        const direct = DIRECT.has(entry.getAttribute(S.type));
        const badge = entry.querySelector(S.badge);
        const unread = entry.classList.contains(S.unread) && (direct || Boolean(badge));
        const episode = episodes[channel];
        if (unread && (!episode || episode.read)) {
          episodes[channel] = { id: Date.now().toString(36), read: false };
        } else if (!unread && episode && !episode.read) {
          episode.read = true;
        }
        const open = Boolean(here && here.channel === channel);
        if (open && me && last && last.sender === me) {
          out.push({ id: `${channel}:*`, from_me: true }); // the user answered there
          continue;
        }
        if (!unread) continue;
        const name = text(entry.querySelector(S.name));
        const theirs = open ? [...conversation].reverse().find((message) => message.sender !== me) : null;
        out.push({
          id: `${channel}:${episodes[channel].id}`,
          from: theirs?.name || name,
          subject: direct ? name : `#${name}`,
          snippet: theirs?.text || (badge ? `${text(badge)} unread` : "unread"),
          url: here ? `${location.origin}/client/${here.team}/${channel}` : location.href,
          time: "",
        });
      }
      return out;
    },
    memory: () => episodes,
    thread() {
      return messages().slice(-30).map((message) => `${message.name}: ${message.text}`).join("\n");
    },
    fill(value) {
      const box = document.querySelector(S.composer);
      if (!box) return { ok: false, reason: "no message box on this page" };
      const line = value.split("\n").map((part) => part.trim()).filter(Boolean).join(" "); // Enter sends in Slack
      typeInto(box, line);
      return { ok: true, reason: line === value.trim() ? "" : "on one line, since Enter sends in Slack" };
    },
  };
})();
