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
