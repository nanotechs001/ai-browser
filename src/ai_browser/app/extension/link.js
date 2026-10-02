// The extension's line to `ai-browser app`. config.json (server address and token) is read again before every
// attempt, so a restarted app, on a new port with a new token, is found again. Pings from the server keep the
// service worker, and its socket, alive. Also: Chrome tab ids <-> DevTools target ids (the app speaks targets).
"use strict";

export function connect({ view, onMessage = () => {}, onState = () => {} }) {
  let socket = null;
  let retries = 0;
  const waiters = [];

  function retry() {
    setTimeout(open, Math.min(5000, 250 * 2 ** retries++));
  }

  async function open() {
    onState("connecting");
    let config;
    try {
      config = await (await fetch(chrome.runtime.getURL("config.json"), { cache: "no-store" })).json();
    } catch {
      onState("disconnected");
      retry();
      return;
    }
    let ws;
    try {
      ws = new WebSocket(`${config.server.replace(/^http/, "ws")}/ws?token=${encodeURIComponent(config.token)}`);
    } catch {
      onState("disconnected");
      retry();
      return;
    }
    ws.onopen = () => {
      retries = 0;
      socket = ws;
      ws.send(JSON.stringify({ type: "hello", view }));
      onState("connected");
      for (const resolve of waiters.splice(0)) resolve();
    };
    ws.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message && message.type !== "ping") onMessage(message);
    };
    ws.onclose = () => {
      if (socket === ws) socket = null;
      onState("disconnected");
      retry();
    };
  }

  open();
  return {
    send(message) {
      if (!socket || socket.readyState !== WebSocket.OPEN) return false;
      socket.send(JSON.stringify(message));
      return true;
    },
    whenOpen() {
      if (socket && socket.readyState === WebSocket.OPEN) return Promise.resolve();
      return new Promise((resolve) => waiters.push(resolve));
    },
  };
}

async function targets() {
  try {
    return await chrome.debugger.getTargets(); // only lists them: nothing is attached
  } catch {
    return [];
  }
}

export async function targetOfTab(tabId) {
  return (await targets()).find((target) => target.tabId === tabId)?.id ?? null;
}

export async function tabOfTarget(target) {
  return (await targets()).find((info) => info.id === target)?.tabId ?? null;
}
