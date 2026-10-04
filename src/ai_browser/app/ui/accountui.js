// The AI accounts' pieces that AI Home, Mission Control and Settings share (never Brave's watcher): when a usage limit
// resets, and what an account's status says. Every text is built here and set as text; none is an email.

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function resetTime(seconds, now = new Date()) { // "3:00 pm", or "Tue 3:00 pm" on another day
  const when = new Date(seconds * 1000);
  const hours = when.getHours();
  const clock = `${hours % 12 || 12}:${String(when.getMinutes()).padStart(2, "0")} ${hours < 12 ? "am" : "pm"}`;
  return when.toDateString() === now.toDateString() ? clock : `${DAYS[when.getDay()]} ${clock}`;
}

export function statusText(row) { // what Settings → Accounts says of an account: signed in, and its plan, only
  if (!row.checked) return "Checking…";
  if (row.signed_in === true) return row.plan ? `Signed in · ${row.plan}` : "Signed in";
  if (row.signed_in === false) return "Not signed in";
  return "Couldn't check: is Claude Code installed?";
}
