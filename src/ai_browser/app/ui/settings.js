// Settings, in its tab of AI Browser's window: AI Browser's own app (its state, its shortcut, its setup),
// which browser draws that window, and the Accounts section (AI accounts; wave C adds where agents browse). The
// choices come from the app; a change is saved there, and the window's browser applies the next time AI Browser
// starts. Every name is set as text.
import { mountAccounts } from "./accountsettings.js";
import { connect } from "./link.js";
import { guardCloseKey, guardLinks, openTab } from "./nav.js";

const $ = (id) => document.getElementById(id);
let current = null; // the app's settings: {model, voice, window_browser, window: {using, name, note, choices}}

function setStatus(state) {
  $("status").dataset.state = state;
  $("status").title = { connected: "Connected to ai-browser app", connecting: "Connecting…",
                        refused: "This window wasn't opened by this run of ai-browser app: close it" }[state]
    || "Not connected: is `ai-browser app` running?";
}

function renderWindow() {
  if (!current) return;
  const info = current.window || {};
  const choices = info.choices || [];
  const box = $("window-choices");
  if (box.dataset.choices !== JSON.stringify(choices)) { // rebuilt only when the choices change
    box.textContent = "";
    for (const choice of choices) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "window_browser";
      input.value = choice.id;
      input.disabled = !choice.installed;
      input.addEventListener("change", () => {
        if (input.checked) link.send({ type: "settings_set", key: "window_browser", value: choice.id, request: "window" });
      });
      label.append(input, document.createTextNode(`${choice.name}${choice.installed ? "" : " · not installed"}`));
      box.append(label);
    }
    box.dataset.choices = JSON.stringify(choices);
  }
  for (const input of box.querySelectorAll("input")) input.checked = input.value === current.window_browser;
  $("window-using").textContent = info.name
    ? `This window: ${info.name}. A change applies the next time AI Browser starts.` : "";
  $("window-note").textContent = info.note || "";
  $("window-note").hidden = !info.note;
}

const SHORTCUT_NOTES = { // what Settings says about the saved shortcut, by its state (the app's word on it)
  ready: (label) => `${label} shows and hides AI Browser. Press it once to check: if another app answers instead, `
    + "pick another shortcut.",
  works: (label) => `${label} shows and hides AI Browser.`,
  taken: (label) => `${label} is used by another app, so it does nothing here. Pick another shortcut.`,
  off: () => "No shortcut.",
  unknown: () => "",
};

function appState(app) {
  if (app.running) return "AI Browser runs as its own app.";
  if (app.set_up) return "AI Browser's own app is set up, but this run uses a browser window.";
  if (app.supported) return "AI Browser runs in a browser window now.";
  return "AI Browser's own app runs on macOS and on Windows (x64).";
}

function renderShortcut(app) { // the offered shortcuts and Off, the saved one checked
  const options = [...(app.shortcuts || []), { value: null, label: "Off" }];
  const box = $("shortcut-choices");
  if (box.dataset.options !== JSON.stringify(options)) { // rebuilt only when the choices change
    box.textContent = "";
    for (const option of options) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "shortcut";
      input.value = option.value ?? "";
      input.addEventListener("change", () => {
        if (!input.checked) return;
        link.send({ type: "settings_set", key: "shortcut", value: option.value, request: "shortcut" });
      });
      label.append(input, document.createTextNode(option.label));
      box.append(label);
    }
    box.dataset.options = JSON.stringify(options);
  }
  const saved = app.shortcut?.value ?? "";
  for (const input of box.querySelectorAll("input")) input.checked = input.value === saved;
  const note = SHORTCUT_NOTES[app.shortcut?.state] || SHORTCUT_NOTES.unknown;
  $("shortcut-note").textContent = note(app.shortcut?.label || "");
}

function renderApp() { // AI Browser's own app: running, set up, or offered (its setup command and the last problem)
  const app = current?.desktop;
  if (!app) return;
  $("window-section").hidden = Boolean(app.running); // the window's browser matters only without the app
  $("app-state").textContent = appState(app);
  $("app-shortcut").hidden = !app.running;
  if (app.running) renderShortcut(app);
  $("app-setup").hidden = Boolean(app.running || app.set_up || !app.supported);
  $("app-adds").textContent = `Its own app adds ${app.platform === "mac" ? "a menu-bar icon" : "an icon by the clock"}`
    + ", a shortcut and notifications.";
  $("app-command").textContent = app.command || "";
  $("app-problem").textContent = app.problem ? `The last try didn't work: ${app.problem}` : "";
  $("app-problem").hidden = !app.problem;
}

function handle(message) {
  if (message.type === "snapshot") {
    current = message.settings || null;
    renderWindow();
    renderApp();
    accounts.setRows(message.accounts || []);
    link.send({ type: "accounts" }); // each account's status, now
  } else if (message.type === "settings") {
    current = message;
    $("window-error").textContent = "";
    renderWindow();
    renderApp();
  } else if (message.type === "accounts") {
    accounts.setRows(message.accounts || []);
  } else if (message.type === "account_added" || message.type === "account_signin") {
    accounts.onMessage(message);
  } else if (message.type === "error" && message.request === "shortcut") {
    renderApp(); // the saved one is checked again
    $("shortcut-note").textContent = message.text || "";
  } else if (message.type === "error" && message.request === "window") {
    $("window-error").textContent = message.text || "";
    renderWindow(); // the saved choice stays checked
  } else if (message.type === "error" && String(message.request || "").startsWith("acct-")) {
    accounts.onMessage(message);
  }
}

const accounts = mountAccounts({ // Settings → Accounts (AI accounts)
  list: $("accounts"), pickDefault: $("account-default"), pickBrain: $("account-brain"), name: $("account-name"),
  existing: $("account-existing"), folder: $("account-folder"), add: $("account-add"), error: $("accounts-error"),
}, (message) => link.send(message));

const link = connect({ view: "settings", onMessage: handle, onState: setStatus });
guardLinks(link);
$("app-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("app-command").textContent);
    $("app-copied").textContent = "Copied.";
  } catch {
    $("app-copied").textContent = "Copy didn't work: select the command and copy it yourself.";
  }
});
guardCloseKey(); // Command-W (Ctrl+W) never closes the window from here
// Shown again (its tab, or the window after the user signed in in a terminal): each account's status, now
window.addEventListener("focus", () => link.send({ type: "accounts" }));
$("home-link").addEventListener("click", () => openTab("/home"));
