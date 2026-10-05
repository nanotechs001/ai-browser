// The AI accounts' pieces that AI Home, Mission Control and Settings share: when a usage limit resets, what an
// account's status says, the Account picker, an agent's ask (Continue on, Wait for the reset), and the Brain's card.
// Every text is built here and set as text; none is an email or an organisation.
import { el } from "./chat.js";

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const IDLE = new Set(["your_turn", "stopped", "failed"]);

export function resetTime(seconds, now = new Date()) { // "3:00 pm", or "Tue 3:00 pm" on another day
  const when = new Date(seconds * 1000);
  const hours = when.getHours();
  const clock = `${hours % 12 || 12}:${String(when.getMinutes()).padStart(2, "0")} ${hours < 12 ? "am" : "pm"}`;
  return when.toDateString() === now.toDateString() ? clock : `${DAYS[when.getDay()]} ${clock}`;
}

export function statusText(row) { // what Settings → Accounts says of an account: signed in, and its plan, only
  if (!row.checked) return "Checking…";
  if (row.signed_in === true) return row.plan ? `Signed in · ${row.plan}` : "Signed in";
  if (row.signed_in === false) return "Not signed in";
  return "Couldn't check: is Claude Code installed?";
}

export function optionText(row) { // the Account picker's words for one account
  if (row.signed_in === false) return `${row.name} · Sign in first`;
  if (Number.isFinite(row.limit_until)) return `${row.name} · at its limit until ${resetTime(row.limit_until)}`;
  return row.name;
}

// The Account picker beside the model: set to the default; a signed-out account is listed, but can't be picked. It is
// rebuilt only when what it shows changes, so a pick stays; with one account there is nothing to pick.
export function fillPicker(select, rows) {
  const signature = JSON.stringify(rows.map((row) => [row.id, optionText(row), row.default]));
  if (select.dataset.rows !== signature) {
    const kept = select.dataset.rows ? select.value : "";
    select.textContent = "";
    for (const row of rows) {
      const option = el("option", "", optionText(row));
      option.value = row.id;
      option.disabled = row.signed_in === false;
      select.append(option);
    }
    const usable = rows.some((row) => row.id === kept && row.signed_in !== false);
    select.value = usable ? kept : rows.find((row) => row.default)?.id || rows[0]?.id || "";
    select.dataset.rows = signature;
  }
  select.hidden = rows.length < 2;
}

export function pickDefault(select, rows) { // after a Start: the default again, for the next task
  const chosen = rows.find((row) => row.default)?.id;
  if (chosen) select.value = chosen;
}

function others(agent, rows) { // where it may continue: the other accounts that are signed in
  const own = agent.account?.id || "default";
  return rows.filter((row) => row.id !== own && row.signed_in === true);
}

export function askKey(agent, rows) { // what an agent's ask is drawn from: it is rebuilt only when that changes
  return JSON.stringify([agent.id, agent.state, Boolean(agent.permission), Boolean(agent.check), agent.limit || null,
                         agent.account || null, others(agent, rows).map((row) => [row.id, optionText(row)])]);
}

// A Continue on that was clicked waits for the app: a move under way changes the agent's row, and a refused one comes
// back as an error naming the click's request, after which the button can be clicked again (askError).
const asking = new Map(); // request id -> the button that sent it
let asked = 0;

function ask(send, message, button) {
  asked += 1;
  const request = `ask-${asked}`;
  if (!send({ ...message, request })) return false;
  asking.set(request, button);
  return true;
}

export function askError(message) { // an error from the app: true when it answers a Continue on, now clickable again
  const button = message.type === "error" ? asking.get(message.request) : undefined;
  if (!button) return false;
  asking.delete(message.request);
  button.disabled = false;
  return true;
}

function continueOn(choices, onPick) { // "Continue on Work", with a picker when there is more than one to choose from
  const parts = [];
  let choice = choices[0];
  const go = el("button", "continue", `Continue on ${choice.name}`);
  go.type = "button";
  if (choices.length > 1) {
    const pick = el("select", "continue-on");
    pick.setAttribute("aria-label", "Continue on");
    for (const row of choices) {
      const option = el("option", "", optionText(row));
      option.value = row.id;
      pick.append(option);
    }
    pick.addEventListener("change", () => {
      choice = choices.find((row) => row.id === pick.value) || choices[0];
      go.textContent = `Continue on ${choice.name}`;
    });
    parts.push(pick);
  }
  go.addEventListener("click", () => { if (onPick(choice, go)) go.disabled = true; });
  parts.push(go);
  return parts;
}

// An agent's ask (AI accounts Decisions 8 and 11), or null. At a usage limit: "Personal hit its usage limit (resets
// 3:00 pm)." with Continue on and Wait for the reset. Idle, with another account signed in: Continue on, to move it
// there or back. Clicks only: account_move is a message only AI Browser's own pages may send.
export function askBox(agent, rows, send) {
  if (!IDLE.has(agent.state) || agent.permission || agent.check) return null;
  const choices = others(agent, rows);
  const limit = agent.limit;
  if (!limit && !choices.length) return null;
  const box = el("div", limit ? "account-ask card" : "account-move");
  const buttons = el("div", "row account-ask-buttons");
  if (choices.length) {
    buttons.append(...continueOn(choices, (choice, button) => ask(send, { type: "account_move", id: agent.id,
                                                                          account: choice.id }, button)));
  }
  if (limit) {
    const name = agent.account?.name || "Its account";
    const resets = Number.isFinite(limit.resets_at) ? ` (resets ${resetTime(limit.resets_at)})` : "";
    box.append(el("p", "account-ask-head", `${name} hit its usage limit${resets}.`));
    if (!choices.length) box.append(el("p", "muted add-account", "Add an account in Settings"));
    const wait = el("button", "wait ghost", "Wait for the reset");
    wait.type = "button";
    wait.addEventListener("click", () => { wait.hidden = true; }); // it stays paused, and Continue stays
    buttons.append(wait);
  }
  box.append(buttons);
  return box;
}

// The Brain's card in AI Home (Decision 10): "The Brain hit its limit on Personal. Continue on Work?". The click sets
// the Brain's account (account_brain), which Settings can change back; the card goes once the Brain is moved.
export function brainCard(node, limit, rows, send) {
  const brain = rows.find((row) => row.brain);
  node.textContent = "";
  node.hidden = !limit || !brain || brain.id !== limit.account;
  if (node.hidden) return;
  const name = rows.find((row) => row.id === limit.account)?.name || "its account";
  const choices = rows.filter((row) => row.id !== limit.account && row.signed_in === true);
  if (!choices.length) {
    node.append(el("p", "account-ask-head", `The Brain hit its limit on ${name}.`),
                el("p", "muted add-account", "Add an account in Settings"));
    return;
  }
  const question = (choice) => `The Brain hit its limit on ${name}. Continue on ${choice.name}?`;
  const head = el("p", "account-ask-head", question(choices[0]));
  const buttons = el("div", "row account-ask-buttons");
  buttons.append(...continueOn(choices, (choice, button) => ask(send, { type: "account_brain", id: choice.id },
                                                                button)));
  const pick = buttons.querySelector(".continue-on");
  pick?.addEventListener("change", () => {
    head.textContent = question(choices.find((row) => row.id === pick.value) || choices[0]);
  });
  node.append(head, buttons);
}
