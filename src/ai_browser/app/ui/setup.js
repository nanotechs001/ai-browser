// The setup page's script. The page holds no secret: it is the one page of AI Browser's that opens anywhere (the
// watcher's "Set it up" link opens it in Brave). Copy, Show the folder, and the watcher's status, all set as text.
// Show the folder works only in AI Browser's own window, whose cookie the server checks.
"use strict";

const watcherStatus = document.getElementById("watcher-status");
const mismatch = document.getElementById("mismatch");

document.getElementById("copy").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  try {
    await navigator.clipboard.writeText(document.getElementById("watcher-folder").textContent);
    button.textContent = "Copied";
  } catch {
    button.textContent = "Select and copy it";
  }
});

document.getElementById("reveal-watcher").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const manager = button.dataset.manager; // the file manager's name, from the server
  try {
    const answer = await fetch("/setup/reveal", { method: "POST" });
    button.textContent = answer.status === 204 ? `Shown in ${manager}`
      : answer.status === 403 ? "This button works in AI Browser's own window" : `Couldn't open ${manager}`;
  } catch {
    button.textContent = "Can't reach ai-browser app";
  }
});

async function check() {
  try {
    const answer = await (await fetch("/setup/status", { cache: "no-store" })).json();
    if (answer.mismatch) {
      mismatch.textContent = `A watcher connected as ${answer.mismatch}, which this app didn't expect, so it was `
        + "refused: please report this.";
      mismatch.hidden = false;
    }
    if (answer.watcher) {
      watcherStatus.textContent = "The watcher is connected: the Brain is on.";
      watcherStatus.className = "done";
      return;
    }
  } catch {
    watcherStatus.textContent = "Can't reach ai-browser app: is it still running?";
  }
  setTimeout(check, 1000);
}
check();
