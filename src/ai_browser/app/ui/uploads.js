// The composer's Attach (the new look, Decision 9): at most 10 files, 20 MB each. Each file goes to the app in pieces
// over the page's line (the pages' CSP allows no other way), shown as a chip with its name, its size and how far it
// got, and × to drop it. The app stages them until the task starts; Start waits until each one is whole. The name shown
// is the app's cleaned one, set as text.
"use strict";

import { el } from "./chat.js";
import { bytes } from "./permission.js";

export const MAX_FILES = 10;
export const MAX_BYTES = 20_000_000; // 20 MB, as the app counts it
const PIECE = 786_432; // bytes in one piece: 1,048,576 characters of base64, the app's limit
let made = 0;

function base64(view) {
  let binary = "";
  for (let start = 0; start < view.length; start += 0x8000) {
    binary += String.fromCharCode(...view.subarray(start, start + 0x8000));
  }
  return btoa(binary);
}

export function mountUploads({ list, send, note }) {
  const files = new Map(); // the page's id for a file -> {file, state, sent, why, chip, parts}

  function render(entry) {
    entry.parts.progress.textContent = entry.state === "done" ? "✓" : entry.state === "failed" ? entry.why
      : `${Math.floor((entry.sent / Math.max(1, entry.file.size)) * 100)}%`;
    entry.chip.dataset.state = entry.state;
  }

  function fail(id, why) {
    const entry = files.get(id);
    if (!entry || entry.state === "failed") return;
    entry.state = "failed";
    entry.why = why;
    render(entry);
  }

  function drop(id) {
    const entry = files.get(id);
    if (!entry) return;
    files.delete(id);
    entry.chip.remove();
    send({ type: "attach_drop", upload: id });
    list.hidden = files.size === 0;
  }

  async function pump(id) { // the pieces, one after another, once the app is ready for them
    const entry = files.get(id);
    let seq = 0;
    for (let start = 0; start < entry.file.size; start += PIECE) {
      if (files.get(id) !== entry || entry.state !== "sending") return; // dropped or refused meanwhile
      const piece = new Uint8Array(await entry.file.slice(start, start + PIECE).arrayBuffer());
      if (!send({ type: "attach_chunk", upload: id, seq, data: base64(piece) })) {
        fail(id, "Not sent: attach it again");
        return;
      }
      seq += 1;
      entry.sent = Math.min(entry.file.size, start + PIECE);
      render(entry);
    }
  }

  function chip(id, entry) {
    const node = el("li", "attached-file");
    node.dataset.id = id;
    entry.parts = { name: el("span", "name clip", entry.file.name), size: el("span", "size muted",
                                                                                bytes(entry.file.size)),
                    progress: el("span", "progress muted") };
    entry.parts.name.title = entry.file.name;
    const remove = el("button", "drop", "×");
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${entry.file.name}`);
    remove.addEventListener("click", () => drop(id));
    node.append(entry.parts.name, entry.parts.size, entry.parts.progress, remove);
    return node;
  }

  function add(chosen) {
    for (const file of chosen) {
      if (files.size >= MAX_FILES) {
        note(`At most ${MAX_FILES} files at once`);
        break;
      }
      if (file.size > MAX_BYTES) {
        note(`${file.name} is over 20 MB`);
        continue;
      }
      made += 1;
      const id = `u${Date.now().toString(36)}-${made}`;
      const entry = { file, state: "sending", sent: 0, why: "" };
      entry.chip = chip(id, entry);
      files.set(id, entry);
      list.append(entry.chip);
      render(entry);
      if (!send({ type: "attach_start", upload: id, name: file.name, size: file.size })) {
        fail(id, "Not sent: attach it again");
      }
    }
    list.hidden = files.size === 0;
  }

  return {
    add,
    count: () => files.size,
    ids: () => [...files.entries()].filter(([, entry]) => entry.state === "done").map(([id]) => id),
    why() { // "" when Start may go
      const states = [...files.values()].map((entry) => entry.state);
      if (states.includes("sending")) return "Wait for the attached files to finish";
      if (states.includes("failed")) return "Remove the files that didn't arrive (×), or attach them again";
      return "";
    },
    clear() { // a task took them: the app moved them into the agent's folder
      for (const entry of files.values()) entry.chip.remove();
      files.clear();
      list.hidden = true;
    },
    onMessage(message) {
      const id = message.upload ?? message.request;
      if (typeof id !== "string" || !files.has(id)) return;
      const entry = files.get(id);
      if (message.type === "attach_ready") {
        entry.parts.name.textContent = String(message.name || entry.file.name); // the app's cleaned name
        entry.parts.name.title = entry.parts.name.textContent;
        pump(id);
      } else if (message.type === "attach_done") {
        entry.state = "done";
        entry.sent = entry.file.size;
        render(entry);
      } else if (message.type === "error") {
        fail(id, String(message.text || "Not sent: attach it again"));
      }
    },
  };
}
