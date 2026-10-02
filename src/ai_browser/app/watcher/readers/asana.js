// Asana's reader: the inbox's entries (tasks assigned to the user, comments on their tasks), by the task link in each
// entry and its words without times; an open task pane gives the text for a draft, and its comment box takes the
// approved reply. The user's own newest comment on an open task means they have answered. Other pages (My Tasks, a
// board) are no alarm.
"use strict";
(() => {
  const S = {
    item: '[data-testid="inbox-item"], .InboxFeedItem', task: 'a[href*="/task/"], a[href*="/0/"]',
    author: '.InboxFeedItem-author, [data-testid="inbox-item-author"]',
    pane: '.TaskPane, [data-testid="task-pane"]',
    comment: '.TaskStoryFeed-comment, [data-testid="comment"]', authorLink: 'a[href*="/profile/"]',
    me: '[data-testid="topbar-avatar"] a[href*="/profile/"], .TopbarPageHeaderGlobalActions a[href*="/profile/"]',
    box: '.ProseMirror[contenteditable="true"], [data-testid="comment-composer"] [contenteditable="true"]',
  };
  const { start, text, hash, stableText, typeInto } = globalThis.AIB_WATCH;

  function taskOf(address) {
    const found = /\/task\/(\d+)/.exec(address) || /\/0\/\d+\/(\d+)/.exec(address);
    return found ? found[1] : null;
  }

  function profile(link) {
    return /\/profile\/(\d+)/.exec(link?.getAttribute("href") || "")?.[1] || "";
  }

  start({
    kind: "asana",
    elsewhere: "open the Inbox: this tab shows another page",
    check() {
      if (document.querySelector(S.item) || document.querySelector(S.pane)) return true;
      return /\/inbox(?:[/?#]|$)/.test(location.pathname + location.hash) ? false : "elsewhere";
    },
    items() {
      const out = [];
      for (const node of document.querySelectorAll(S.item)) {
        const link = node.querySelector(S.task);
        const task = link && taskOf(link.getAttribute("href") || "");
        if (!task) continue;
        out.push({ id: `${task}:${hash(stableText(node))}`, from: text(node.querySelector(S.author)), subject: text(link),
                   snippet: text(node), url: link.href, time: "" });
      }
      const open = taskOf(location.href);
      const comments = [...document.querySelectorAll(`${S.pane} ${S.comment}`)];
      const newest = comments[comments.length - 1];
      const me = profile(document.querySelector(S.me));
      if (open && me && newest && profile(newest.querySelector(S.authorLink)) === me) {
        out.push({ id: `${open}:*`, from_me: true }); // the user answered on that task
      }
      return out;
    },
    thread() {
      const pane = document.querySelector(S.pane);
      return pane ? text(pane) : "";
    },
    fill(value) {
      const box = document.querySelector(S.box);
      if (!box) return { ok: false, reason: "open the task to reply in its comment box" };
      typeInto(box, value);
      return { ok: true };
    },
  });
})();
