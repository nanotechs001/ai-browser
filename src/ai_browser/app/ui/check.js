// A bot check waiting for the user: which agent stopped, on which site, and what kind of check, all set as text.
// Show me brings the agent's tab forward (or shows the live view of the browser that shows it, through the caller's
// openLive: in AI Browser's window, a tab of its own), Continue tells the agent the user dealt with it, and Skip this
// site closes the agent's own tab with the check. The agent never touches the check, and nothing a page says can press
// these buttons. This file imports nothing, so Brave's watcher can share it.
"use strict";

const LIVE = /^http:\/\/127\.0\.0\.1:\d{1,5}\/live\?token=[A-Za-z0-9_-]{1,64}$/; // an engine's live view, nothing else

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function checkCard(agent, send, { openLive = null } = {}) {
  const check = agent.check || {};
  const live = LIVE.test(String(check.live || "")) ? String(check.live) : "";
  const own = !check.adopted && !check.live; // only the agent's own tab can be closed from here
  const card = el("div", "bot-check card");
  card.dataset.since = String(check.since ?? "");
  card.append(el("div", "bot-check-head", `${agent.name || "An agent"} stopped at a bot check`));
  card.append(el("div", "bot-check-what", `${check.site || "a site"} · ${check.what || "a bot check"}`));
  const where = check.adopted ? "It's in your own tab. Solve it there yourself"
    : check.live ? "Solve it in the live view (Show me)" : "Solve it in the tab yourself";
  card.append(el("p", "bot-check-how", `${where}, then click Continue. The agent never touches it.`));
  if (!own) card.append(el("p", "bot-check-skip muted", "To skip it, tell the agent: skip it"));
  const buttons = el("div", "row bot-check-buttons");
  const done = el("span", "muted");
  const show = el("button", "show-me", "Show me");
  show.addEventListener("click", () => {
    if (live) openLive?.(live, agent);
    else if (!check.live && check.target) send({ type: "watch", target: String(check.target) });
  });
  buttons.append(show);
  const answer = (className, label, type, said) => {
    const button = el("button", className, label);
    button.addEventListener("click", () => {
      if (!send({ type, id: agent.id })) return;
      for (const other of buttons.querySelectorAll(".continue, .skip-site")) other.disabled = true;
      done.textContent = said;
    });
    buttons.append(button);
  };
  answer("continue primary", "Continue", "check_continue", "Told the agent to carry on");
  if (own) answer("skip-site", "Skip this site", "check_skip", "Closed its tab and told the agent");
  buttons.append(done);
  card.append(buttons);
  return card;
}
