// What a Brave notification says about a batch of new items (a pure function, so it can be tested on its own). One
// item gets its own notification, with Draft reply or Hand to agent, and Open; an item a workflow has already started
// on says so, with Open only (no second agent from here); several items get one summary that opens the Brain.
export function notificationFor(items) {
  if (items.length === 1) {
    const [item] = items;
    const title = `${item.sender || item.site}: ${item.subject || ""}`.slice(0, 120);
    const target = { id: item.id, url: item.url };
    if (item.state === "agent") {
      return { options: { title, message: [item.note, item.summary].filter(Boolean).join(": ").slice(0, 300),
                          buttons: [{ title: "Open" }] },
               note: { item: target, first: "open" } };
    }
    const first = item.suggest === "agent" ? "hand" : "draft";
    return { options: { title, message: (item.summary || item.snippet || "").slice(0, 300),
                        buttons: [{ title: first === "hand" ? "Hand to agent" : "Draft reply" }, { title: "Open" }] },
             note: { item: target, first } };
  }
  const needs = items.filter((item) => item.kind === "needs_reply").length;
  const fresh = items.length - needs;
  const line = (item) => `${item.sender}: ${item.state === "agent" ? item.note : item.summary}`;
  return { options: { title: [needs && `${needs} need you`, fresh && `${fresh} new`].filter(Boolean).join(", "),
                      message: items.slice(0, 3).map(line).join("\n").slice(0, 300),
                      buttons: [{ title: "Open the Brain" }] },
           note: {} };
}

const LIVE = /^http:\/\/127\.0\.0\.1:\d{1,5}\/live\?token=[A-Za-z0-9_-]{1,64}$/; // an engine's live view, nothing else

// An agent stopped at a bot check: the notification says who and where (plain text), and its buttons can only bring
// the tab forward (or open the live view that shows it) and tell the agent to carry on. Nothing here closes a tab.
export function checkNotification(request) {
  const live = LIVE.test(String(request.live || "")) ? String(request.live) : "";
  return {
    options: { title: `${request.name || "An agent"}: a bot check on ${request.site || "a site"}`.slice(0, 120),
               message: "Solve it in the tab, then press Continue.",
               buttons: [{ title: "Show me" }, { title: "Continue" }] },
    note: { check: { agent: String(request.agent || ""), target: String(request.target || ""), live } },
  };
}

// What a click on the notification does: Continue (button 1) tells the agent; Show me (button 0, or the notification
// itself) opens the live view when there is one, else asks the app to bring the agent's tab forward.
export function checkAction(note, index) {
  const check = note.check || {};
  if (index === 1) return { send: { type: "check_continue", id: check.agent } };
  if (check.live) return { open: check.live };
  return { send: { type: "watch", target: check.target } };
}
