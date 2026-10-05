// The engine's private line to the app: one JSON object per line, each way. When the engine starts the program itself
// (Windows, and the tests' Electron) it is the app's stdin and stdout. When macOS starts the app through
// LaunchServices, it is a socket in a folder only this user can open: --aib-line=<path>. The start address, with its
// one-time code, comes this way, never on a command line.
"use strict";

const LIMIT = 64 * 1024; // characters in one line; a longer one is dropped

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

module.exports = { LIMIT, encode, lineOption, parse, splitter };
