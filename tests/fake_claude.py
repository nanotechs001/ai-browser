"""A stand-in for `claude -p --input-format stream-json --output-format stream-json`, for the app tests.

It logs its arguments (one JSON line) and every stdin line to $FAKE_CLAUDE_LOG, and answers each user message with the
events listed in $FAKE_CLAUDE_SCRIPT: events are printed as JSON lines, {"sleep": s} pauses, {"spawn": s} starts a
child that sleeps s seconds and logs {"child": pid}, and {"exit": n} exits with that code. The script is a JSON list,
or a dict {"default": [...], "<word>": [...]} where the first key found in the user's message picks the list. Control
requests get a success response at once, even mid-answer. An interrupt ends the answer in progress the way Claude Code
2.1.263 does (a result with subtype error_during_execution), unless the script starts with {"ignore_interrupt": true}.
{"ask_permission": {"tool_name", "input"}} asks for a tool the way Claude Code does (a can_use_tool control request)
(its request may name the tool use it is for: `tool_use_id`) and waits for the app's answer. Without --input-format (a probe), the prompt comes from the command line.

AI accounts (tests/fake_accounts.py):
- `auth status` answers per CLAUDE_CONFIG_DIR: a folder holding SIGNED_IN is signed in, and the answer then has the
  email and the organisation too, as Claude Code's has. Without the variable it says signed out and reads nothing:
  never the user's own ~/.claude. Each call is logged to $FAKE_CLAUDE_LOG.auth.
- Conversations are kept the way Claude Code keeps them, in <CLAUDE_CONFIG_DIR>/projects/<the working folder, every
  character but letters and digits turned into "-">/<session id>.jsonl (not with --no-session-persistence, and never
  without the variable). `--resume <id>` finds a conversation only there: else it prints "No conversation found with
  session ID: <id>" and exits 1 before any event. "session_id": "$session" in a script's event is this process's
  session: the resumed one, or a new one.
- {"usage_limit": text} prints a failed result with that text; {"rate_limit": info} prints a rate_limit_event with that
  rate_limit_info; {"split": event, "pause": s} prints one event's line in two writes, s seconds apart.

One-shot mode (`--output-format json` without `--input-format`, as the Brain calls it): the whole of stdin is the
prompt, logged as {"oneshot": prompt, "argv": [...], "config": CLAUDE_CONFIG_DIR}. The script's list (or the dict's
list picked by a key found in the prompt) gives one entry per call, in order, the last one repeating: {"result": text}
answers, {"is_error": true} marks it failed, {"sleep": s} waits first, {"exit": n} exits without an answer."""

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid

from fake_accounts import EMAIL, ORG_ID, ORG_NAME, SIGNED_IN

for stream in (sys.stdin, sys.stdout, sys.stderr):  # UTF-8 on every OS, as Claude Code's own streams are
    stream.reconfigure(encoding="utf-8")

API_VARIABLES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def auth_status() -> None:
    """`claude auth status`, as Claude Code 2.1.263 prints it (JSON), for the folder in CLAUDE_CONFIG_DIR."""
    folder = os.environ.get("CLAUDE_CONFIG_DIR") or ""
    with open(os.environ["FAKE_CLAUDE_LOG"] + ".auth", "a", encoding="utf-8") as calls:
        calls.write(json.dumps({"config": folder, "api": [key for key in API_VARIABLES if key in os.environ]}) + "\n")
    signed = None
    if folder and os.path.isfile(os.path.join(folder, SIGNED_IN)):
        with open(os.path.join(folder, SIGNED_IN), encoding="utf-8") as marker:
            signed = json.load(marker)
    if signed is not None and signed.get("sleep"):
        time.sleep(signed["sleep"])
    if signed is not None and "say" in signed:
        print(signed["say"], flush=True)
        return
    answer = {"loggedIn": False, "authMethod": "none", "apiProvider": "firstParty", "analyticsDisabled": False,
              "projectsDirectory": os.path.join(folder, "projects")}
    if signed is not None:
        answer.update({"loggedIn": True, "authMethod": "claude.ai", "email": EMAIL, "orgId": ORG_ID,
                       "orgName": ORG_NAME, "subscriptionType": signed.get("plan")})
    print(json.dumps(answer), flush=True)


if sys.argv[1:3] == ["auth", "status"]:
    auth_status()
    sys.exit(0)

with open(os.environ["FAKE_CLAUDE_LOG"] + ".env", "w", encoding="utf-8") as env_log:  # credentials it was given, if any
    json.dump({**{key: os.environ.get(key) for key in (*API_VARIABLES, "MAX_THINKING_TOKENS", "CLAUDE_CONFIG_DIR")},
               "cwd": os.getcwd(), "pid": os.getpid()}, env_log)


def one_shot(argv: list[str]) -> None:
    prompt = sys.stdin.read()
    try:
        with open(os.environ["FAKE_CLAUDE_LOG"], encoding="utf-8") as earlier_log:
            earlier = sum(1 for line in earlier_log if line.startswith('{"oneshot"'))
    except FileNotFoundError:
        earlier = 0
    with open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8") as call_log:
        call_log.write(json.dumps({"oneshot": prompt, "argv": argv,
                                   "config": os.environ.get("CLAUDE_CONFIG_DIR")}) + "\n")
    with open(os.environ["FAKE_CLAUDE_SCRIPT"], encoding="utf-8") as script:
        entries = json.load(script)
    if isinstance(entries, dict):
        entries = next((entries[key] for key in entries if key != "default" and key in prompt),
                       entries.get("default", []))
    entry = entries[min(earlier, len(entries) - 1)] if entries else {}
    if "sleep" in entry:
        time.sleep(entry["sleep"])
    if "exit" in entry:
        os._exit(entry["exit"])
    failed = bool(entry.get("is_error"))
    print(json.dumps({"type": "result", "subtype": "error_during_execution" if failed else "success",
                      "is_error": failed, "result": entry.get("result", ""),
                      "total_cost_usd": entry.get("cost", 0.001), "session_id": "s-oneshot"}), flush=True)


if "--input-format" not in sys.argv and "--output-format" in sys.argv \
        and sys.argv[sys.argv.index("--output-format") + 1] == "json":
    one_shot(sys.argv[1:])
    sys.exit(0)

RESUME = sys.argv[sys.argv.index("--resume") + 1] if "--resume" in sys.argv else None
SESSION = RESUME or f"s-{uuid.uuid4().hex[:12]}"  # what "$session" in a script's event becomes
PERSIST = "--no-session-persistence" not in sys.argv
printing = threading.Lock()
messages: queue.Queue = queue.Queue()
responses: queue.Queue = queue.Queue()  # the app's answers to our permission requests
interrupted = threading.Event()
asked = 0
last_session = "s-1"  # the session the script named last: an interrupted answer's result names it too


def project_folder() -> str | None:
    """Where Claude Code keeps this working folder's conversations; None without CLAUDE_CONFIG_DIR."""
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return os.path.join(config, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.getcwd())) if config else None


def stamped(event):
    global last_session
    if isinstance(event, dict) and event.get("session_id") == "$session":
        event = {**event, "session_id": SESSION}
    if isinstance(event, dict) and isinstance(event.get("session_id"), str):
        last_session = event["session_id"]
    return event


def remember(event) -> None:
    """The conversation, as Claude Code keeps it: every event with a session id, one JSON line each."""
    folder = project_folder()
    session = event.get("session_id") if isinstance(event, dict) else None
    if PERSIST and folder is not None and isinstance(session, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", session):
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, f"{session}.jsonl"), "a", encoding="utf-8") as transcript:
            transcript.write(json.dumps(event) + "\n")


def emit(event: dict) -> None:
    event = stamped(event)
    with printing:
        print(json.dumps(event), flush=True)
    remember(event)


def read(log) -> None:
    for line in sys.stdin:
        log.write(line if line.endswith("\n") else line + "\n")
        message = json.loads(line)
        if message.get("type") == "control_request":
            if message.get("request", {}).get("subtype") == "interrupt":
                interrupted.set()
            emit({"type": "control_response",
                  "response": {"subtype": "success", "request_id": message.get("request_id")}})
        elif message.get("type") == "control_response":
            responses.put(message)
        elif message.get("type") == "user":
            messages.put(message)
    messages.put(None)


def ask_permission(request: dict) -> str:
    """A can_use_tool request, as Claude Code 2.1.263 sends it; returns the app's behavior (deny after 30 s)."""
    global asked
    asked += 1
    request_id = f"perm-{asked}"
    emit({"type": "control_request", "request_id": request_id,
          "request": {"subtype": "can_use_tool", "tool_use_id": f"toolu_{asked}", **request}})
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            reply = responses.get(timeout=0.05)
        except queue.Empty:
            continue
        if reply.get("response", {}).get("request_id") == request_id:
            return reply["response"].get("response", {}).get("behavior", "deny")
    return "deny"


with open(os.environ["FAKE_CLAUDE_LOG"], "a", buffering=1, encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
    if RESUME is not None and project_folder() is not None \
            and not os.path.isfile(os.path.join(project_folder(), f"{RESUME}.jsonl")):
        print(f"No conversation found with session ID: {RESUME}", file=sys.stderr, flush=True)
        sys.exit(1)
    if "--input-format" not in sys.argv:  # a probe: the prompt is on the command line
        messages.put({"type": "user", "message": {"content": sys.argv[sys.argv.index("-p") + 1]}})
        messages.put(None)
    else:
        threading.Thread(target=read, args=(log,), daemon=True).start()
    while (message := messages.get()) is not None:
        with open(os.environ["FAKE_CLAUDE_SCRIPT"], encoding="utf-8") as script:
            events = json.load(script)
        if isinstance(events, dict):
            content = json.dumps(message.get("message", {}).get("content", ""))
            events = next((events[key] for key in events if key != "default" and key in content), events["default"])
        stoppable = not (events and events[0].get("ignore_interrupt"))
        interrupted.clear()
        for event in events:
            if "ignore_interrupt" in event:
                continue
            if "spawn" in event:  # a child of its own, as Claude Code starts its MCP servers
                child = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({float(event['spawn'])})"])
                log.write(json.dumps({"child": child.pid}) + "\n")
                continue
            if "ask_permission" in event:
                behavior = ask_permission(event["ask_permission"])
                emit({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {
                    "type": "text_delta", "text": "allowed" if behavior == "allow" else "denied"}}})
                continue
            if "usage_limit" in event:  # a turn refused at a usage limit
                emit({"type": "result", "subtype": "success", "is_error": True, "result": event["usage_limit"],
                      "session_id": last_session})
                continue
            if "rate_limit" in event:
                emit({"type": "rate_limit_event", "rate_limit_info": event["rate_limit"], "session_id": last_session})
                continue
            if "split" in event:  # one event's line in two writes: a read may end in the middle of it
                payload = stamped(event["split"])
                line = json.dumps(payload) + "\n"
                with printing:
                    sys.stdout.write(line[:len(line) // 2])
                    sys.stdout.flush()
                    time.sleep(event.get("pause", 0.3))
                    sys.stdout.write(line[len(line) // 2:])
                    sys.stdout.flush()
                remember(payload)
                continue
            if "sleep" in event:
                deadline = time.monotonic() + event["sleep"]
                while time.monotonic() < deadline and not (stoppable and interrupted.is_set()):
                    time.sleep(0.02)
            elif "exit" in event:
                sys.stdout.flush()
                os._exit(event["exit"])
            if stoppable and interrupted.is_set():
                emit({"type": "result", "subtype": "error_during_execution", "is_error": True,
                      "session_id": last_session})
                break
            if "sleep" not in event:
                emit(event)
