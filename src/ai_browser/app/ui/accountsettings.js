// Settings → Accounts (AI accounts): the user's Claude logins, each with its status, Sign in and Remove; Add, or use a
// Claude Code folder the user already has; the default account for new agents, and the Brain's. Every text is set as
// text. No email or organisation is ever here: the app keeps only whether an account is signed in, and its plan.
import { el } from "./chat.js";
import { resetTime, statusText } from "./accountui.js";

const HOW = "Sign in there and in your browser. AI Browser never sees your password.";

export function mountAccounts(parts, send) {
  const { list, pickDefault, pickBrain, name, existing, folder, add, error } = parts;
  let rows = [];
  let drawn = ""; // what the list was drawn from: it is redrawn only when that changes, so a click isn't lost
  const open = new Set(); // accounts whose Sign in is unfolded
  const waiting = new Set(); // accounts the app watches for their sign-in
  const notes = new Map(); // account id -> one line under its Sign in ("Copied", …)
  let requests = 0;

  function ask(message) { // each message has a request id, so the app's error comes back to this section
    requests += 1;
    if (send({ ...message, request: `acct-${requests}` })) return true;
    error.textContent = "Not connected: is `ai-browser app` running?";
    return false;
  }

  function button(className, label, onClick) {
    const node = el("button", className, label);
    node.type = "button";
    node.addEventListener("click", onClick);
    return node;
  }

  function ways(row) { // Sign in, unfolded: Open Terminal, or Copy the command for the user's own terminal
    const box = el("div", "signin-ways");
    box.append(el("p", "muted", HOW));
    const buttons = el("div", "row");
    buttons.append(button("terminal", "Open Terminal", () => {
      if (ask({ type: "account_signin", id: row.id, how: "terminal" })) waiting.add(row.id);
      draw();
    }));
    const copy = button("copy", "Copy the command", () => {
      if (ask({ type: "account_signin", id: row.id, how: "copy" })) waiting.add(row.id);
      const copying = navigator.clipboard?.writeText(row.command) ?? Promise.reject(new Error("no clipboard"));
      copying.then(() => notes.set(row.id, "Copied"),
                   () => notes.set(row.id, "Couldn't copy: select the command below and copy it")).finally(draw);
    });
    copy.disabled = !row.command;
    buttons.append(copy);
    box.append(buttons, el("code", "command", row.command || ""));
    if (notes.has(row.id)) box.append(el("p", "muted note", notes.get(row.id)));
    if (waiting.has(row.id)) box.append(el("p", "muted waiting", "Waiting for you to sign in…"));
    return box;
  }

  function drawRow(row) {
    const box = el("div", "account card");
    box.dataset.id = row.id;
    const top = el("div", "top-line");
    top.append(el("strong", "name", row.name), el("span", "chip status", statusText(row)));
    if (row.default) top.append(el("span", "chip", "Used for new agents"));
    if (row.brain) top.append(el("span", "chip", "Used by the Brain"));
    box.append(top);
    if (Number.isFinite(row.limit_until)) {
      box.append(el("p", "muted limit", `At its limit until ${resetTime(row.limit_until)}`));
    }
    const buttons = el("div", "row");
    if (row.signed_in !== true) {
      buttons.append(button("signin", "Sign in", () => {
        if (open.has(row.id)) open.delete(row.id);
        else open.add(row.id);
        draw();
      }));
    }
    if (row.id !== "default") {
      const remove = button("remove ghost", "Remove", () => ask({ type: "account_remove", id: row.id }));
      remove.title = "AI Browser forgets it: its folder, conversations and sign-in stay";
      buttons.append(remove);
    }
    box.append(buttons);
    if (open.has(row.id) && row.signed_in !== true) box.append(ways(row));
    return box;
  }

  function fill(select, chosen) {
    if (document.activeElement === select) return; // never while it's open
    select.textContent = "";
    for (const row of rows) {
      const option = el("option", "", row.name);
      option.value = row.id;
      select.append(option);
    }
    select.value = chosen || "default";
  }

  function draw() {
    const signature = JSON.stringify([rows, [...open], [...waiting], [...notes]]);
    if (signature === drawn) return;
    drawn = signature;
    list.textContent = "";
    for (const row of rows) list.append(drawRow(row));
    fill(pickDefault, rows.find((row) => row.default)?.id);
    fill(pickBrain, rows.find((row) => row.brain)?.id);
  }

  function addAccount() {
    const label = name.value.trim();
    if (!label) {
      error.textContent = "Give the account a name";
      return;
    }
    const message = existing.checked ? { type: "account_add_existing", name: label, folder: folder.value.trim() }
      : { type: "account_add", name: label };
    if (ask(message)) error.textContent = "";
  }

  existing.addEventListener("change", () => { folder.hidden = !existing.checked; });
  add.addEventListener("click", addAccount);
  for (const input of [name, folder]) {
    input.addEventListener("keydown", (event) => { if (event.key === "Enter") addAccount(); });
  }
  pickDefault.addEventListener("change", () => ask({ type: "account_default", id: pickDefault.value }));
  pickBrain.addEventListener("change", () => ask({ type: "account_brain", id: pickBrain.value }));

  return {
    setRows(next) { // the app's list (the snapshot's, then each "accounts" message)
      rows = Array.isArray(next) ? next : [];
      for (const row of rows) {
        if (row.signed_in === true) { // signed in: its Sign in folds away
          open.delete(row.id);
          waiting.delete(row.id);
          notes.delete(row.id);
        }
      }
      draw();
    },
    onMessage(message) {
      if (message.type === "account_added") {
        name.value = "";
        folder.value = "";
        existing.checked = false;
        folder.hidden = true;
        error.textContent = "";
        open.add(message.id); // its Sign in, ready
        draw();
      } else if (message.type === "account_signin" && message.opened === false) {
        notes.set(message.id, "Couldn't open a terminal here: copy the command instead.");
        draw();
      } else if (message.type === "error") {
        error.textContent = message.text || "";
      }
    },
  };
}
