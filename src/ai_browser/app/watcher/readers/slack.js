// Slack's reader: direct messages and @mentions, from the sidebar's unread entries and badges (Slack shows them
// whichever conversation is open). Each unread spell of a conversation is one item, kept across reloads; the open
// conversation's messages give the text, and the user's own message there means they have answered.
"use strict";
(() => {
  const S = {
    entry: "[data-qa-channel-sidebar-channel-id]", channelId: "data-qa-channel-sidebar-channel-id",
    type: "data-qa-channel-sidebar-channel-type", unread: "p-channel_sidebar__channel--unread",
    badge: ".p-channel_sidebar__badge", name: ".p-channel_sidebar__name",
    message: '[data-qa="message_container"]', sender: "[data-message-sender]", body: '[data-qa="message-text"]',
    composer: '[data-qa="message_input"] [contenteditable="true"]',
  };
  const DIRECT = new Set(["im", "mpim"]);
  const KEY = "slackEpisodes";
  const { start, text, typeInto } = globalThis.AIB_WATCH;
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

  start({
    kind: "slack",
    async init() {
      episodes = (await chrome.storage.local.get(KEY))[KEY] || {};
    },
    check: () => Boolean(document.querySelector(S.entry)),
    items() {
      const here = place();
      const me = here ? self(here.team) : "";
      const conversation = here ? messages() : [];
      const last = conversation[conversation.length - 1];
      const out = [];
      let changed = false;
      for (const entry of document.querySelectorAll(S.entry)) {
        const channel = entry.getAttribute(S.channelId);
        const direct = DIRECT.has(entry.getAttribute(S.type));
        const badge = entry.querySelector(S.badge);
        const unread = entry.classList.contains(S.unread) && (direct || Boolean(badge));
        const episode = episodes[channel];
        if (unread && (!episode || episode.read)) {
          episodes[channel] = { id: Date.now().toString(36), read: false };
          changed = true;
        } else if (!unread && episode && !episode.read) {
          episode.read = true;
          changed = true;
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
      if (changed) chrome.storage.local.set({ [KEY]: episodes }).catch(() => {});
      return out;
    },
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
  });
})();
