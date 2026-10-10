// Settings → Where agents browse: the Brave profiles browser detection found, by name and colour (never an email),
// and the one agents work in (unless a saved agent picks its own). Mission Control's Tabs page lists that profile's
// tabs and only counts the others. Brave can't be told a profile, so AI Browser learns it while the user uses it; this
// section says plainly when it can't yet, and nothing here makes Brave ask anything. Every name is set as text.
"use strict";

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function mountPlaceSettings(parts, send) {
  // parts: {choices, state}
  let profiles = [];
  let chosen = null;
  let scope = null; // the tab list's {profile: "chosen" | "not_open" | "last_used" | "none", elsewhere}
  let brave = ""; // Brave's state: connected, off, ready, asking, refused, lost

  function name(folder, missing = "That profile") { // missing: the words when Brave no longer lists it
    return profiles.find((profile) => profile.folder === folder)?.name || missing;
  }

  function renderChoices() {
    const key = JSON.stringify(profiles);
    if (parts.choices.dataset.profiles !== key) { // rebuilt only when the profiles change
      parts.choices.replaceChildren();
      for (const profile of [{ folder: "", name: "The profile you used last in Brave", color: null }, ...profiles]) {
        const label = el("label", "place-choice");
        const input = document.createElement("input");
        input.type = "radio";
        input.name = "agents_profile";
        input.value = profile.folder;
        input.addEventListener("change", () => {
          if (input.checked) {
            send({ type: "settings_set", key: "agents_profile", value: profile.folder || null, request: "place" });
          }
        });
        const swatch = el("span", "swatch");
        if (profile.color) swatch.style.background = profile.color; // "#rrggbb", from browser detection
        else swatch.hidden = true;
        label.append(input, swatch, document.createTextNode(profile.name));
        parts.choices.append(label);
      }
      parts.choices.dataset.profiles = key;
    }
    for (const input of parts.choices.querySelectorAll("input")) input.checked = input.value === (chosen || "");
  }

  function renderState() {
    if (brave && brave !== "connected") {
      parts.state.textContent = "Brave isn't connected: connect it at the top of Mission Control.";
    } else if (!scope) {
      parts.state.textContent = "";
    } else if (scope.profile === "chosen") {
      parts.state.textContent = `Agents browse in ${name(chosen, "the profile you picked (not found in Brave)")}.`;
    } else if (scope.profile === "not_open") {
      parts.state.textContent = `${name(chosen)} isn't open in Brave yet: open a window of it, and click in it once.`;
    } else if (scope.profile === "last_used") {
      parts.state.textContent = "Agents browse in the profile you used last in Brave.";
    } else {
      parts.state.textContent = "AI Browser can't tell which Brave profile you use yet.";
    }
  }

  function settings(values) {
    if (!values) return;
    profiles = Array.isArray(values.profiles) ? values.profiles : [];
    chosen = values.agents_profile || null;
    renderChoices();
    renderState();
  }

  function onMessage(message) {
    if (message.type === "snapshot") {
      scope = message.tab_scope || null;
      brave = message.browser?.state || "";
      settings(message.settings);
    } else if (message.type === "settings") {
      settings(message);
    } else if (message.type === "tabs") {
      scope = message.tab_scope || null;
      renderState();
    } else if (message.type === "browser") {
      brave = message.state || "";
      renderState();
    } else if (message.type === "error" && message.request === "place") {
      parts.state.textContent = message.text || "";
      renderChoices(); // the saved one is checked again
    }
  }

  return { onMessage };
}
