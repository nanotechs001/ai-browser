"""The shell's seatbelt refuses the crawl pattern from the task logs, and nothing else."""

import pytest

from ai_browser.shellguard import PARALLEL, SKIPPED, USER_AGENT, shell_problem


@pytest.mark.parametrize("command", [
    'curl -A "Mozilla/5.0" https://example.com',
    "curl -A'Mozilla/5.0' https://example.com",
    "curl --user-agent='Mozilla/5.0 (Macintosh)' https://example.com",
    "curl -H 'User-Agent: Mozilla/5.0' https://example.com",
    'wget -U "Chrome/120" https://example.com',
    'curl -sA "Mozilla/5.0" https://example.com',  # combined short options (Review Focus 4)
    'wget --header="User-Agent: Mozilla/5.0" https://example.com',
    'curl -A "Mozilla/5.0 https://example.com',  # broken quoting: read as plain words
    "curl -A Googlebot/2.1 https://example.com",
])
def test_a_browsers_user_agent_is_refused(command):
    assert shell_problem(command) == USER_AGENT


@pytest.mark.parametrize("command", [
    "cat urls | xargs -n1 -P4 curl -s",
    "xargs -P 10 -I{} curl {}",
    "xargs -P 0 curl",
    "parallel curl ::: a b",
    "cat urls|xargs -P4 curl -s",  # no spaces around the pipe (Review Focus 4)
    "xargs --max-procs=8 wget -q",
])
def test_parallel_fetching_is_refused(command):
    assert shell_problem(command) == PARALLEL


def test_a_skipped_site_is_refused_wherever_it_appears():
    assert shell_problem("curl -s https://www.google.com/", skipped=["google.com"]) == SKIPPED.format(site="google.com")
    assert shell_problem("python3 fetch.py --host maps.google.com", skipped=["google.com"]) == \
        SKIPPED.format(site="google.com")
    assert shell_problem("curl -s http://localhost:8123/x", skipped=["localhost"]) == SKIPPED.format(site="localhost")


@pytest.mark.parametrize("command, skipped", [
    ("curl -s https://example.com", ()),
    ('curl -A "my-script/1.0" https://example.com', ()),
    ("xargs -P 1 curl", ()),
    ("grep -P 'x' file", ()),
    ("curl -s https://example.com", ["google.com"]),
    ("curl -s https://notgoogle.com/", ["google.com"]),
    ("grep -A 3 'Mozilla/5.0' access.log", ()),  # -A belongs to grep here (Review Focus 4)
    ("curl -s https://example.com && wget -q https://example.org", ()),  # one at a time
    ("cat report.html | wc -l", ["google.com"]),
])
def test_ordinary_commands_run(command, skipped):
    assert shell_problem(command, skipped) is None


def test_the_reasons_say_what_to_do_instead():
    assert USER_AGENT == ("the shell doesn't send a browser's user agent (curl -A \"Mozilla/…\"): use curl's own, or "
                          "open the page with open")
    assert PARALLEL == ("the shell doesn't fetch in parallel (xargs -P 10 … curl): fetch one URL at a time, or use qa "
                        "for a whole site")
    assert SKIPPED.format(site="google.com") == ("the shell doesn't reach google.com: the user skipped it after a bot "
                                                 "check. Ask the user if you need it.")
