import json
import subprocess
import time
import urllib.error
import urllib.request

import pytest

from ai_browser.sandbox import DockerError, Sandboxes

PROFILE = "pytest"


def test_invalid_profile_rejected(tmp_path):
    with pytest.raises(ValueError, match="profile"):
        Sandboxes(tmp_path).start("Bad Name!")


def test_check_reports_docker_down(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "unix:///nonexistent/docker.sock")
    with pytest.raises(DockerError, match="Docker Desktop"):
        Sandboxes(tmp_path).check()


def test_chrome_is_a_reserved_profile_name(tmp_path, monkeypatch):
    def no_docker(self):
        raise AssertionError("reached Docker")

    monkeypatch.setattr(Sandboxes, "check", no_docker)
    for name in ("chrome", "app"):  # their folders and names belong to the user's-own-Chrome mode and AI Browser
        with pytest.raises(ValueError, match="reserved"):
            Sandboxes(tmp_path).start(name)


def test_each_home_gets_its_own_chrome_shell(tmp_path):
    first, second = Sandboxes(tmp_path / "a"), Sandboxes(tmp_path / "b")
    assert first.chrome_shell() != second.chrome_shell()
    assert first.chrome_shell() == Sandboxes(tmp_path / "a").chrome_shell()
    assert first.chrome_shell().startswith("aib-chrome-") and first.chrome_shell().endswith("-sh")


@pytest.fixture(scope="module")
def boxes(tmp_path_factory):
    sandboxes = Sandboxes(tmp_path_factory.mktemp("aib"))
    yield sandboxes
    sandboxes.stop(f"aib-{PROFILE}")
    subprocess.run(["docker", "volume", "rm", f"aib-profile-{PROFILE}"], capture_output=True)


def ip_of(container: str) -> str:
    return subprocess.run(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                           container], capture_output=True, text=True, encoding="utf-8").stdout.strip()


@pytest.mark.docker
def test_start_creates_and_answers_cdp(boxes):
    info = boxes.start(PROFILE)
    assert (info.name, info.shell, info.profile, info.fresh) == ("aib-pytest", "aib-pytest-sh", PROFILE, False)
    version = json.load(urllib.request.urlopen(f"{info.http}/{info.token}/json/version", timeout=5))
    assert "Chrom" in version["Browser"]
    ws = boxes.ws_url(info)
    assert ws.startswith(info.http.replace("http://", "ws://") + f"/{info.token}/devtools/browser/")


@pytest.mark.docker
def test_cdp_port_requires_the_token(boxes):
    info = boxes.start(PROFILE)
    for path in ("/json/version", "/wrong-token/json/version"):
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(info.http + path, timeout=5)
        assert caught.value.code == 403


@pytest.mark.docker
def test_start_reuses_running_container(boxes):
    boxes.start(PROFILE)
    started = time.monotonic()
    info = boxes.start(PROFILE)
    assert info.created is False
    assert time.monotonic() - started < 1.5


@pytest.mark.docker
def test_exec_runs_as_agent_in_cwd(boxes):
    info = boxes.start(PROFILE)
    result = boxes.exec(info.shell, "echo hello && pwd && whoami", cwd="/work")
    assert result.code == 0
    assert result.output.split() == ["hello", "/work", "agent"]


@pytest.mark.docker
def test_exec_reports_failure_code(boxes):
    info = boxes.start(PROFILE)
    result = boxes.exec(info.shell, "echo oops >&2; exit 3")
    assert (result.code, result.output.strip(), result.timed_out) == (3, "oops", False)


@pytest.mark.docker
def test_exec_timeout_kills(boxes):
    info = boxes.start(PROFILE)
    started = time.monotonic()
    result = boxes.exec(info.shell, "sleep 30", timeout=1)
    assert result.timed_out is True
    assert time.monotonic() - started < 5


@pytest.mark.docker
def test_work_dir_is_shared_with_host(boxes):
    info = boxes.start(PROFILE)
    (info.work_host / "hello.txt").write_text("from host", encoding="utf-8")
    assert boxes.exec(info.shell, "cat /work/hello.txt").output.strip() == "from host"
    boxes.exec(info.shell, "echo from-box > /work/out.txt")
    assert (info.work_host / "out.txt").read_text(encoding="utf-8").strip() == "from-box"


@pytest.mark.docker
def test_the_shell_cannot_reach_the_logged_in_browser(boxes):
    info = boxes.start(PROFILE)
    port = info.http.rsplit(":", 1)[1]
    profile = boxes.exec(info.shell, "ls /profile")
    assert profile.code != 0
    direct = boxes.exec(info.shell, f"curl -s -m 3 -o /dev/null -w '%{{http_code}}' "
                                    f"http://{ip_of(info.name)}:9223/{info.token}/json/version", timeout=10)
    assert direct.output.strip() != "200"
    via_host = boxes.exec(info.shell, f"curl -s -m 3 -o /dev/null -w '%{{http_code}}' "
                                      f"http://host.docker.internal:{port}/json/version", timeout=10)
    assert via_host.output.strip() != "200"


@pytest.mark.docker
def test_sandboxes_cannot_reach_each_other(tmp_path_factory):
    sandboxes = Sandboxes(tmp_path_factory.mktemp("aib-net"))
    first, second = sandboxes.start(fresh=True), sandboxes.start(fresh=True)
    try:
        probe = sandboxes.exec(first.shell, f"curl -s -m 3 -o /dev/null -w '%{{http_code}}' "
                                            f"http://{ip_of(second.name)}:9223/{second.token}/json/version",
                               timeout=10)
        assert probe.output.strip() != "200"
    finally:
        sandboxes.stop(first.name)
        sandboxes.stop(second.name)


@pytest.mark.docker
def test_fresh_container_is_removed_on_stop(boxes):
    info = boxes.start(fresh=True)
    assert info.fresh and info.name.startswith("aib-fresh-")
    boxes.stop(info.name)
    assert not boxes.is_running(info.name)
    for name in (info.name, info.shell):
        listed = subprocess.run(["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
                                capture_output=True, text=True, encoding="utf-8").stdout
        assert listed.strip() == ""


@pytest.mark.docker
def test_changed_skill_mounts_keep_the_browser_running(tmp_path_factory):
    home = tmp_path_factory.mktemp("aib3")
    first, second = tmp_path_factory.mktemp("skills-a"), tmp_path_factory.mktemp("skills-b")
    (second / "new.txt").write_text("new skill", encoding="utf-8")
    try:
        Sandboxes(home, mounts=[(first, "/skills/personal")]).start("pytest-mounts")
        refreshed = Sandboxes(home, mounts=[(second, "/skills/personal")])
        info = refreshed.start("pytest-mounts")
        assert info.created is False  # the browser, its tabs and logins were not touched
        assert refreshed.exec(info.shell, "cat /skills/personal/new.txt").output.strip() == "new skill"
    finally:
        Sandboxes(home).stop("aib-pytest-mounts")
        subprocess.run(["docker", "volume", "rm", "aib-profile-pytest-mounts"], capture_output=True)


@pytest.mark.docker
def test_skill_mounts_are_read_only(tmp_path_factory):
    skills = tmp_path_factory.mktemp("skills")
    (skills / "s.txt").write_text("skill", encoding="utf-8")
    sandboxes = Sandboxes(tmp_path_factory.mktemp("aib2"), mounts=[(skills, "/skills/personal")])
    info = sandboxes.start(fresh=True)
    try:
        assert sandboxes.exec(info.shell, "cat /skills/personal/s.txt").output.strip() == "skill"
        assert sandboxes.exec(info.shell, "touch /skills/personal/x").code != 0
    finally:
        sandboxes.stop(info.name)
