// A stand-in for Gmail's inbox and thread pages, built with the same classes and attributes the Brain's reader
// looks for: rows tr.zA (unread .zE), senders .yW [email], subject .bog, snippet .y2, time .xW span[title], thread
// ids, the open thread's .gD senders and .a3s messages, the Reply button .ams.bkH, the reply box and the Send button
// .aoO (whose clicks are counted: the reader must never press it), the main region (role="main") and, in a reply box
// Reply opens, the user's signature (.gmail_signature). The words come from window.SAMPLE; ?broken shows a layout no
// reader knows.
"use strict";
const ME = "me@example.com";
window.sendClicks = 0;
const threads = new Map();

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  node.append(...children);
  return node;
}

function row(thread) {
  const senders = el("div", { class: "yW" },
                     el("span", { class: "yP", email: thread.email, name: thread.from, text: thread.from }));
  const subject = el("span", { class: "bog" },
                     el("span", { "data-thread-id": `#thread-f:${thread.id}`, "data-legacy-thread-id": thread.id,
                                  text: thread.subject }));
  const tr = el("tr", { class: "zA zE", "data-test": thread.id },
                el("td", {}, senders), el("td", {}, subject, el("span", { class: "y2", text: ` - ${thread.snippet}` })),
                el("td", { class: "xW" }, el("span", { title: "Thu, Oct 2, 2026, 10:02 AM", text: "10:02" })));
  tr.addEventListener("click", () => { location.hash = `#inbox/${thread.id}`; });
  return tr;
}

function addRow(thread) {
  threads.set(thread.id, { messages: [{ from: thread.from, email: thread.email, text: thread.snippet }], ...thread });
  document.getElementById("rows").prepend(row(threads.get(thread.id)));
}

function markReplied(id) {
  const tr = document.querySelector(`tr[data-test="${id}"]`);
  tr.classList.replace("zE", "yO");
  tr.querySelector(".yW").append(", ", el("span", { class: "yP", email: ME, name: SAMPLE.me, text: SAMPLE.me }));
}

function route() {
  const found = /^#(?:inbox|all)\/(.+)$/.exec(location.hash);
  const thread = found && threads.get(found[1]);
  document.getElementById("list").hidden = Boolean(thread);
  document.getElementById("thread").hidden = !thread;
  document.getElementById("compose").hidden = true;
  document.getElementById("box").textContent = "";
  if (!thread) return;
  document.querySelector("h2.hP").textContent = thread.subject;
  document.getElementById("messages").replaceChildren(...thread.messages.map((message) => el("div", { class: "gs" },
    el("span", { class: "gD", email: message.email, name: message.from, text: message.from }),
    el("div", { class: "a3s", text: message.text }))));
}

document.title = SAMPLE.title;
document.getElementById("reply").textContent = SAMPLE.reply;
document.getElementById("send").textContent = SAMPLE.send;
document.getElementById("reply").addEventListener("click", () => {
  document.getElementById("compose").hidden = false;
  const box = document.getElementById("box");
  if (!box.childNodes.length) { // Gmail starts a reply with the user's signature in the box
    box.replaceChildren(el("div", {}, el("br")),
                        el("div", { class: "gmail_signature", "data-smartmail": "gmail_signature", text: SAMPLE.signature }));
  }
});
document.getElementById("send").addEventListener("click", () => { window.sendClicks += 1; });
for (const thread of [...SAMPLE.threads].reverse()) addRow(thread);
const main = el("div", { role: "main" });
document.getElementById("list").before(main);
main.append(document.getElementById("list"), document.getElementById("thread"));
addEventListener("hashchange", route);
route();
if (new URLSearchParams(location.search).has("broken")) document.body.replaceChildren(el("p", { text: "Loading…" }));
