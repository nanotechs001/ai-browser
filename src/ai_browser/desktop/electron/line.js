// The engine's private line to the app: one JSON object per line, each way. When macOS starts the app through
// LaunchServices, it is a socket in a folder only this user can open: --aib-line=<path>. On Windows it is a port on
// 127.0.0.1 (--aib-line=tcp:<port>) that the app joins by sending first the key the engine put in its environment
// (AIB_LINE_KEY): the packaged Electron's stdin ends as it starts there, so it can't be the line. With no
// --aib-line (the tests' Electron), it is the app's stdin and stdout. The start address, with its one-time code, comes
// this way, never on a command line.
"use strict";

const LIMIT = 64 * 1024; // characters in one line; a longer one is dropped
const LINE_KEY = "AIB_LINE_KEY"; // Windows: the line's key, in the app's environment only

function parse(line) { // an object with a string "type", or null
  if (!line.trim() || line.length > LIMIT) return null;
  try {
    const message = JSON.parse(line);
    return message && typeof message === "object" && !Array.isArray(message) && typeof message.type === "string"
      ? message : null;
  } catch {
    return null;
  }
}

// Text as it comes (any chunks) to whole messages. A line that grows past LIMIT before its end is dropped whole.
function splitter(onMessage) {
  let buffer = "";
  let dropping = false;
  return (chunk) => {
    buffer += chunk;
    let end;
    while ((end = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, end);
      buffer = buffer.slice(end + 1);
      if (dropping) {
        dropping = false;
        continue;
      }
      const message = parse(line);
      if (message) onMessage(message);
    }
    if (buffer.length > LIMIT) {
      buffer = "";
      dropping = true;
    }
  };
}

function encode(message) {
  return `${JSON.stringify(message)}\n`;
}

function lineOption(argv) { // macOS: the socket's path; null: stdin and stdout
  const found = (argv || []).find((arg) => typeof arg === "string" && arg.startsWith("--aib-line="));
  return found ? found.slice("--aib-line=".length) || null : null;
}

// Where --aib-line points: a socket's path (macOS), or a port on 127.0.0.1 and the key to send first (Windows, the key
// from `env`); null when it names neither.
function lineTarget(option, env) {
  if (typeof option !== "string" || !option) return null;
  if (!option.startsWith("tcp:")) return { path: option };
  const found = /^tcp:(\d{1,5})$/.exec(option);
  const port = found ? Number(found[1]) : 0;
  if (port < 1 || port > 65535) return null;
  const key = env && typeof env[LINE_KEY] === "string" ? env[LINE_KEY] : "";
  return { host: "127.0.0.1", port, key };
}

module.exports = { LIMIT, LINE_KEY, encode, lineOption, lineTarget, parse, splitter };
