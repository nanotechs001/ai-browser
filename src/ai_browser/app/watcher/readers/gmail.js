// Gmail's reader: unread inbox rows found by their structure (classes and attributes, never English words, so any
// language works), the open thread for a draft, and the reply box. It reads the inbox and its category tabs only (the
// view is in the address): never Spam, Sent, a label or a search. To place an approved reply it may click Reply, which
// only opens the box, and puts the reply at the top, above the user's signature; it never touches Send.
"use strict";
(() => {
  const S = {
    row: "tr.zA", unread: "zE", sender: ".yW [email]", subject: ".bog", snippet: ".y2", time: ".xW span[title]",
    threadId: "[data-legacy-thread-id]", threadIdAlt: "[data-thread-id]",
    message: ".a3s", messageHolder: ".gs", messageSender: ".gD[email]", threadSubject: "h2.hP",
    replyBox: 'div[contenteditable="true"][role="textbox"]', reply: ".ams.bkH", main: '[role="main"]',
  };
  const INBOX = new Set(["", "inbox", "category"]);
  const { start, text, waitFor, ownEmail } = globalThis.AIB_WATCH;
  let own = null; // the block the watcher put in the reply box, and its text

  function view() { // "inbox", "category", "spam", "label"…, from the address: the same in every language
    return location.hash.replace(/^#/, "").split(/[/?]/)[0];
  }

  function shown(node) {
    return Boolean(node && node.getClientRects().length);
  }

  function replyBox() {
    return [...document.querySelectorAll(S.replyBox)].find(shown) || null;
  }

  // The approved reply goes in a block of its own at the top of the reply box, above the signature and the quoted
  // text. A newer approved draft replaces that block; the same text again changes nothing.
  function place(box, value) {
    if (own && own.block.isConnected && box.contains(own.block)) {
      if (own.value === value) return;
    } else {
      own = { block: document.createElement("div"), value: "" };
      box.prepend(own.block);
    }
    own.block.replaceChildren(...value.split("\n").map((line) => {
      const row = document.createElement("div");
      if (line) row.textContent = line;
      else row.append(document.createElement("br"));
      return row;
    }));
    own.value = value;
    box.focus();
    box.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
  }

  function threadOf(row) {
    const legacy = row.querySelector(S.threadId);
    if (legacy) return legacy.getAttribute("data-legacy-thread-id");
    const other = row.querySelector(S.threadIdAlt)?.getAttribute("data-thread-id") || "";
    return other.replace(/^#?thread-[a-z]:/, "") || null;
  }

  function name(node) {
    return node ? node.getAttribute("name") || text(node) : "";
  }

  start({
    kind: "gmail",
    elsewhere: "open the inbox: this tab shows another view",
    check() {
      const where = view();
      if (!INBOX.has(where)) return "elsewhere"; // Spam, Sent, a label, a search, Settings…
      if (document.querySelector(S.row) || document.querySelector(S.message)) return true;
      // an empty inbox: Gmail's main region, with nothing unread in the tab title ("Inbox (3) - …")
      return Boolean(document.querySelector(S.main)) && (where === "category" || !/\(\d/.test(document.title.split(" - ")[0]));
    },
    items() {
      const me = ownEmail();
      return [...document.querySelectorAll(S.row)].map((row) => {
        const id = threadOf(row);
        if (!id) return null;
        const senders = [...row.querySelectorAll(S.sender)];
        const last = senders[senders.length - 1];
        const time = row.querySelector(S.time);
        return {
          id,
          from: name(senders[0]),
          subject: text(row.querySelector(S.subject)),
          snippet: text(row.querySelector(S.snippet)).replace(/^[\s\-–—]+/, ""),
          time: time ? time.getAttribute("title") || text(time) : "",
          url: `${location.origin}${location.pathname}#all/${id}`,
          unread: row.classList.contains(S.unread),
          from_me: Boolean(me && last && (last.getAttribute("email") || "").toLowerCase() === me),
        };
      }).filter(Boolean);
    },
    thread() {
      const parts = [...document.querySelectorAll(S.message)].map((body) => {
        const holder = body.closest(S.messageHolder) || body.parentElement;
        return `${name(holder?.querySelector(S.messageSender))}: ${text(body)}`;
      });
      return [text(document.querySelector(S.threadSubject)), ...parts].filter(Boolean).join("\n\n");
    },
    async fill(value) {
      let box = replyBox();
      if (!box) {
        const buttons = [...document.querySelectorAll(S.reply)];
        const reply = buttons.filter(shown).pop() || buttons.pop();
        if (!reply) return { ok: false, reason: "no Reply button on this page" };
        reply.click(); // opens the reply box; nothing is sent
        box = await waitFor(replyBox, 5000);
      }
      if (!box) return { ok: false, reason: "the reply box didn't open" };
      place(box, value);
      return { ok: true };
    },
  });
})();
