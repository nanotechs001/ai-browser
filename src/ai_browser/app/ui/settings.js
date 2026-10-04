// Settings, in a small window of its own: which browser draws AI Browser's window (wave C adds where agents browse).
// The choices come from the app; a change is saved there, and applies the next time AI Browser starts. Every name is
// set as text.
import { connect } from "./link.js";
import { focusHome, guardLinks } from "./nav.js";

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

function handle(message) {
  if (message.type === "snapshot") {
    current = message.settings || null;
    renderWindow();
  } else if (message.type === "settings") {
    current = message;
    $("window-error").textContent = "";
    renderWindow();
  } else if (message.type === "error" && message.request === "window") {
    $("window-error").textContent = message.text || "";
    renderWindow(); // the saved choice stays checked
  }
}

const link = connect({ view: "settings", onMessage: handle, onState: setStatus });
guardLinks(link);
$("home-link").addEventListener("click", () => focusHome());
