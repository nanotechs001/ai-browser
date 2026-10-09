// A question before a step that can't be undone (the saved-agents spec, 5): Delete agent, and Close on a run that is
// still working. The browser's own modal dialog: the rest of the page can't be reached while it is open, and focus
// stays in it. Keep has the focus (Enter keeps), Escape keeps, and only the button that does it says yes. Its words
// are set as text.
"use strict";

import { el } from "./chat.js";

let asked = 0;

// {title, lines, yes, no}: the question, what it does (one line each), and its two buttons' words
export function confirmAction({ title, lines = [], yes, no = "Keep" }) {
  return new Promise((resolve) => {
    asked += 1;
    const dialog = el("dialog", "confirm");
    const heading = el("h2", "confirm-title", title);
    heading.id = `confirm-${asked}`;
    dialog.setAttribute("aria-labelledby", heading.id);
    const keep = el("button", "keep", no);
    keep.type = "button";
    const go = el("button", "go danger", yes);
    go.type = "button";
    const buttons = el("div", "row confirm-buttons");
    buttons.append(keep, go);
    dialog.append(heading, ...lines.map((line) => el("p", "", line)), buttons);
    const done = (answer) => {
      if (!dialog.isConnected) return; // answered once
      dialog.close();
      dialog.remove();
      resolve(answer);
    };
    keep.addEventListener("click", () => done(false));
    go.addEventListener("click", () => done(true));
    dialog.addEventListener("cancel", (event) => { // Escape: kept
      event.preventDefault();
      done(false);
    });
    document.body.append(dialog);
    dialog.showModal();
    keep.focus();
  });
}
