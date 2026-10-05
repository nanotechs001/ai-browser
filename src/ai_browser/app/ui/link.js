// The line to `ai-browser app`. AI Browser's window (an http page the app serves) opens /ws on its own address: the
// window's cookie goes with it, and a page that this run of the app didn't open is refused (close code 4403), so it
// stops trying. Pings from the server keep the socket alive.
"use strict";

const REFUSED = 4403; // the server's close code for a socket it won't take

function address() {
  return `ws://${location.host}/ws`; // the window: its cookie goes along
}

export function connect({ view, onMessage = () => {}, onState = () => {} }) {
  let socket = null;
  let retries = 0;
  let refused = false;
  const waiters = [];

  function retry() {
    if (!refused) setTimeout(open, Math.min(5000, 250 * 2 ** retries++));
  }

  async function open() {
    onState("connecting");
    let ws;
    try {
      ws = new WebSocket(address());
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
    ws.onclose = (event) => {
      if (socket === ws) socket = null;
      if (event.code === REFUSED) { // not this run's window: retrying can't help
        refused = true;
        onState("refused");
        return;
      }
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
