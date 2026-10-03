"""A stand-in for `claude -p --input-format stream-json --output-format stream-json`, for the app tests.

It logs its arguments (one JSON line) and every stdin line to $FAKE_CLAUDE_LOG, and answers each user message with the
events listed in $FAKE_CLAUDE_SCRIPT: events are printed as JSON lines, {"sleep": s} pauses, {"spawn": s} starts a
child that sleeps s seconds and logs {"child": pid}, and {"exit": n} exits with that code. The script is a JSON list,
or a dict {"default": [...], "<word>": [...]} where the first key found in the user's message picks the list. Control
requests get a success response at once, even mid-answer. An interrupt ends the answer in progress the way Claude Code
2.1.263 does (a result with subtype error_during_execution), unless the script starts with {"ignore_interrupt": true}.
{"ask_permission": {"tool_name", "input"}} asks for a tool the way Claude Code does (a can_use_tool control request)
and waits for the app's answer. Without --input-format (a probe), the prompt comes from the command line.

One-shot mode (`--output-format json` without `--input-format`, as the Brain calls it): the whole of stdin is the
prompt, logged as {"oneshot": prompt, "argv": [...]}. The script's list (or the dict's list picked by a key found in
the prompt) gives one entry per call, in order, the last one repeating: {"result": text} answers, {"is_error": true}
marks it failed, {"sleep": s} waits first, {"exit": n} exits without an answer."""

import json
import os
import queue
import subprocess
import sys
import threading
import time

for stream in (sys.stdin, sys.stdout, sys.stderr):  # UTF-8 on every OS, as Claude Code's own streams are
    stream.reconfigure(encoding="utf-8")

with open(os.environ["FAKE_CLAUDE_LOG"] + ".env", "w", encoding="utf-8") as env_log:  # credentials it was given, if any
    json.dump({**{key: os.environ.get(key) for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "MAX_THINKING_TOKENS")},
               "cwd": os.getcwd(), "pid": os.getpid()}, env_log)


def one_shot(argv: list[str]) -> None:
    prompt = sys.stdin.read()
    try:
        with open(os.environ["FAKE_CLAUDE_LOG"], encoding="utf-8") as earlier_log:
            earlier = sum(1 for line in earlier_log if line.startswith('{"oneshot"'))
    except FileNotFoundError:
        earlier = 0
    with open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8") as call_log:
        call_log.write(json.dumps({"oneshot": prompt, "argv": argv}) + "\n")
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

printing = threading.Lock()
messages: queue.Queue = queue.Queue()
responses: queue.Queue = queue.Queue()  # the app's answers to our permission requests
interrupted = threading.Event()
asked = 0


def emit(event: dict) -> None:
    with printing:
        print(json.dumps(event), flush=True)


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
          "request": {"subtype": "can_use_tool", **request, "tool_use_id": f"toolu_{asked}"}})
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
            if "sleep" in event:
                deadline = time.monotonic() + event["sleep"]
                while time.monotonic() < deadline and not (stoppable and interrupted.is_set()):
                    time.sleep(0.02)
            elif "exit" in event:
                sys.stdout.flush()
                os._exit(event["exit"])
            if stoppable and interrupted.is_set():
                emit({"type": "result", "subtype": "error_during_execution", "is_error": True, "session_id": "s-1"})
                break
            if "sleep" not in event:
                emit(event)
