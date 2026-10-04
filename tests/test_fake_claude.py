"""The fake claude's AI-accounts powers, run directly: `auth status` per CLAUDE_CONFIG_DIR, conversations resumed only
under their own folder, and scripted usage limits. No real claude, and never the user's own Claude Code folder."""

import json
import os
import re
import subprocess
from pathlib import Path

from conftest import fake_python
from fake_accounts import EMAIL, ORG_ID, ORG_NAME, SIGNED_IN, sign_in

FAKE = str(Path(__file__).with_name("fake_claude.py"))
STREAM = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]


def fake(*args, config=None, cwd=None, say=None):
    """Run the fake claude once: (exit code, the JSON objects it printed, its stderr)."""
    env = {key: value for key, value in os.environ.items() if key != "CLAUDE_CONFIG_DIR"}
    if config is not None:
        env["CLAUDE_CONFIG_DIR"] = str(config)
    stdin = json.dumps({"type": "user", "message": {"role": "user", "content": say}}) + "\n" if say else ""
    done = subprocess.run([fake_python(), FAKE, *args], env=env, cwd=cwd, input=stdin.encode("utf-8"),
                          capture_output=True, timeout=30)
    printed = [json.loads(line) for line in done.stdout.decode("utf-8").splitlines() if line.startswith("{")]
    return done.returncode, printed, done.stderr.decode("utf-8")


def test_every_test_has_a_signed_in_throwaway_default_folder():
    folder = Path(os.environ["CLAUDE_CONFIG_DIR"])
    assert folder != Path.home() / ".claude" and (folder / SIGNED_IN).is_file()


def test_auth_status_answers_per_folder_and_never_reads_the_users_own(fake_claude, tmp_path):
    _, log, _ = fake_claude
    work, empty = tmp_path / "work", tmp_path / "empty"
    empty.mkdir()
    sign_in(work, plan="max")
    _, [signed], _ = fake("auth", "status", config=work)
    assert signed["loggedIn"] is True and signed["subscriptionType"] == "max"
    assert (signed["email"], signed["orgId"], signed["orgName"]) == (EMAIL, ORG_ID, ORG_NAME)  # Claude Code's shape
    _, [out], _ = fake("auth", "status", config=empty)
    assert out["loggedIn"] is False and out["authMethod"] == "none" and "email" not in out
    _, [nothing], _ = fake("auth", "status")  # no CLAUDE_CONFIG_DIR: signed out, and nothing is read
    assert nothing["loggedIn"] is False
    calls = [json.loads(line) for line in Path(f"{log}.auth").read_text(encoding="utf-8").splitlines()]
    assert [call["config"] for call in calls] == [str(work), str(empty), ""]
    sign_in(empty, say="not json at all")
    code, printed, _ = fake("auth", "status", config=empty)
    assert code == 0 and printed == []


def test_a_conversation_resumes_only_under_its_own_folder(fake_claude, tmp_path):
    _, log, script = fake_claude
    script.write_text(json.dumps([{"type": "system", "subtype": "init", "session_id": "$session"},
                                  {"type": "result", "subtype": "success", "is_error": False, "result": "ok",
                                   "session_id": "$session"}]), encoding="utf-8")
    personal, work, chat = tmp_path / "personal", tmp_path / "work", tmp_path / "agents" / "a1" / "chat"
    chat.mkdir(parents=True)
    code, printed, _ = fake(*STREAM, config=personal, cwd=chat, say="hello")
    session = printed[0]["session_id"]
    assert code == 0 and session.startswith("s-") and printed[-1]["session_id"] == session
    [kept] = list((personal / "projects").glob(f"*/{session}.jsonl"))
    assert kept.parent.name == re.sub(r"[^A-Za-z0-9]", "-", str(chat.resolve()))
    code, printed, _ = fake(*STREAM, "--resume", session, config=personal, cwd=chat, say="again")
    assert code == 0 and printed[0]["session_id"] == session  # a resumed conversation keeps its id
    code, printed, error = fake(*STREAM, "--resume", session, config=work, cwd=chat, say="again")
    assert code == 1 and printed == [] and f"No conversation found with session ID: {session}" in error
    argvs = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.startswith("[")]
    assert argvs[-1][argvs[-1].index("--resume") + 1] == session  # logged before it refused


def test_scripted_usage_limits_and_a_line_in_two_writes(fake_claude, tmp_path):
    _, _, script = fake_claude
    info = {"status": "rejected", "resetsAt": 1890000000, "rateLimitType": "five_hour"}
    delta = {"type": "stream_event", "event": {"type": "content_block_delta",
                                               "delta": {"type": "text_delta", "text": "Half"}}}
    script.write_text(json.dumps([{"type": "system", "subtype": "init", "session_id": "$session"},
                                  {"split": delta, "pause": 0.2}, {"rate_limit": info},
                                  {"usage_limit": "Claude AI usage limit reached|1890000000"}]), encoding="utf-8")
    code, printed, _ = fake(*STREAM, config=tmp_path / "work", cwd=tmp_path, say="go")
    assert code == 0 and [event["type"] for event in printed] == ["system", "stream_event", "rate_limit_event",
                                                                  "result"]
    assert printed[1] == delta
    assert printed[2]["rate_limit_info"] == info and printed[2]["session_id"] == printed[0]["session_id"]
    assert printed[3]["is_error"] is True and printed[3]["result"] == "Claude AI usage limit reached|1890000000"
