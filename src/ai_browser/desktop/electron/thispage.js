// "This page" for AI Browser's floating chat: the address and title of the Brave tab the user is on, read only while
// the chat shows (main.js asks), and only those two. On a Mac it runs osascript with one fixed JavaScript for
// Automation script. On Windows it runs PowerShell with one fixed UI Automation script, shipped beside this file
// (thispage.ps1). Neither is ever built from a page's or the user's text, and neither types into, clicks or opens
// anything: when Brave isn't running, they say so, and Brave stays closed. What they print is parsed as JSON and kept
// to {state, url, title}. The program and its arguments are fixed per system (command), and run without a shell.
"use strict";

const { execFile } = require("node:child_process");
const path = require("node:path");

const OSASCRIPT = "/usr/bin/osascript";
// JavaScript for Automation (osascript -l JavaScript). running() asks macOS, never Brave, so a closed Brave stays
// closed. Then only Brave's front window is asked: whether it is private (then nothing more: the chat's picker), and
// its active tab's address and title. Application() of an app that isn't installed throws, with no box. Brave Beta
// and Nightly are other apps: the chat's picker covers them.
const MAC_SCRIPT = [
  "(() => {",
  "  const answer = (value) => JSON.stringify(value);",
  "  let brave;",
  "  try {",
  '    brave = Application("com.brave.Browser");',
  '    if (!brave.running()) return answer({ state: "closed" });',
  "  } catch (error) {",
  '    return answer({ state: "closed" });',
  "  }",
  "  try {",
  '    if (brave.windows.length === 0) return answer({ state: "nowindow" });',
  '    let mode = "";',
  "    try {",
  "      mode = String(brave.windows[0].mode());",
  "    } catch (error) {",
  '      mode = "";',
  "    }",
  '    if (mode === "incognito") return answer({ state: "private" });',
  "    const tab = brave.windows[0].activeTab;",
  '    return answer({ state: "ok", url: String(tab.url() || ""), title: String(tab.title() || "") });',
  "  } catch (error) {",
  "    const number = Number(error && error.errorNumber);",
  '    const refused = number === -1743 || /-1743|not authori[sz]ed/i.test(String(error && error.message));',
  '    return answer({ state: refused ? "denied" : "failed" });',
  "  }",
  "})()",
].join("\n");
const WAIT = 20000; // ms for one look: the first time, macOS asks the user, and osascript waits for the answer
const OUT_LIMIT = 64 * 1024; // characters a look may print
const URL_LIMIT = 2000;
const TITLE_LIMIT = 300;
const STATES = Object.freeze(["ok", "closed", "nowindow", "private", "unknown", "denied", "failed"]);
const CONTROL = /[\u0000-\u001f\u007f]/g;
const SYSTEM_ROOT = /^[A-Za-z]:\\[A-Za-z0-9_-]+$/; // C:\Windows, or another single folder on a drive

// The one program and its arguments on this system, or null where AI Browser can't see Brave's tabs.
function command(platform, folder = __dirname, env = process.env) {
  if (platform === "darwin") return { file: OSASCRIPT, args: ["-l", "JavaScript", "-e", MAC_SCRIPT] };
  if (platform !== "win32") return null;
  const root = typeof env?.SystemRoot === "string" && SYSTEM_ROOT.test(env.SystemRoot) ? env.SystemRoot : "C:\\Windows";
  return {
    file: path.win32.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
    args: ["-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
           path.win32.join(folder, "thispage.ps1")],
  };
}

function clean(value, limit) {
  return typeof value === "string" ? value.replace(CONTROL, " ").slice(0, limit) : "";
}

// What a look printed: one JSON object with a known state. Anything else is "failed".
function parse(stdout) {
  let value;
  try {
    value = JSON.parse(String(stdout ?? "").trim().slice(0, OUT_LIMIT));
  } catch {
    return { state: "failed" };
  }
  if (!value || typeof value !== "object" || Array.isArray(value) || !STATES.includes(value.state)) {
    return { state: "failed" };
  }
  if (value.state !== "ok") return { state: value.state };
  return { state: "ok", url: clean(value.url, URL_LIMIT), title: clean(value.title, TITLE_LIMIT) };
}

// The real way to run it: no shell, no window on Windows, a time limit, and a cap on what it may print.
function run(file, args, wait = WAIT) {
  return new Promise((resolve) => {
    execFile(file, args, { timeout: wait, maxBuffer: OUT_LIMIT, windowsHide: true, shell: false, encoding: "utf8" },
      (error, stdout, stderr) => {
        const slow = Boolean(error?.killed) && error?.code !== "ERR_CHILD_PROCESS_STDIO_MAXBUFFER";
        resolve({ error: error ? (slow ? "slow" : "failed") : "", stdout: String(stdout ?? ""),
                  stderr: String(stderr ?? "") });
      });
  });
}

// The Brave tab the user is on: {state: "ok", url, title}, or a state alone: "closed" (Brave isn't running),
// "nowindow", "private" (a private window: nothing of it is read), "unknown" (Windows: no address bar of Brave's
// own), "denied" (macOS doesn't let AI Browser control Brave), "slow", "failed", or "unsupported" (this system).
// `runner` is run's stand-in in the tests.
async function read(platform, runner = run, folder = __dirname) {
  const given = command(platform, folder);
  if (!given) return { state: "unsupported" };
  let done;
  try {
    done = await runner(given.file, given.args);
  } catch {
    return { state: "failed" };
  }
  if (done?.error === "slow") return { state: "slow" };
  const answer = parse(done?.stdout);
  if (answer.state === "failed" && /\(-1743\)/.test(String(done?.stderr ?? ""))) return { state: "denied" };
  return answer;
}

module.exports = { MAC_SCRIPT, OSASCRIPT, STATES, WAIT, command, parse, read, run };
