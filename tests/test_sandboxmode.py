"""Which sandbox AI Browser uses (sandboxmode.py, the no-Docker spec): Settings → Sandbox's Auto, Docker or Local,
AIB_SANDBOX for one process, and Docker's readiness, looked at no more than every LOOK_AGAIN seconds. No test here
reaches Docker: its look (Sandboxes.check) is replaced."""

import pytest


@pytest.fixture
def docker(monkeypatch):
    """Docker's look, replaced: {"ready": bool, "looks": count}. The cache starts empty."""
    from ai_browser import sandboxmode
    from ai_browser.sandbox import DockerError, Sandboxes

    state = {"ready": True, "looks": 0}

    def check(self):
        state["looks"] += 1
        if not state["ready"]:
            raise DockerError("Docker isn't running. Start Docker Desktop, then retry.")

    monkeypatch.setattr(Sandboxes, "check", check)
    monkeypatch.setattr(sandboxmode, "_looked", {})
    monkeypatch.delenv("AIB_SANDBOX", raising=False)
    return state


def test_the_choice_is_auto_docker_or_local(tmp_path):
    from ai_browser.settings import Settings

    settings = Settings(tmp_path, system="darwin")
    assert settings.get()["sandbox"] == "auto"  # the default: Docker when it is ready, Local otherwise
    for value in ("podman", "", None, True, "Local"):
        with pytest.raises(ValueError, match="Auto, Docker or Local"):
            settings.set("sandbox", value)
    assert settings.set("sandbox", "local")["sandbox"] == "local"
    assert settings.set("sandbox", "docker")["sandbox"] == "docker"


def test_auto_picks_docker_when_it_is_ready_and_local_otherwise(tmp_path, docker):
    from ai_browser import sandboxmode

    assert sandboxmode.resolve(tmp_path) == "docker"
    assert sandboxmode.describe(tmp_path) == {"choice": "auto", "using": "docker",
                                              "line": "Sandbox: Docker (Auto: Docker is ready)"}
    docker["ready"] = False
    sandboxmode._looked.clear()  # past LOOK_AGAIN
    assert sandboxmode.resolve(tmp_path) == "local"
    assert sandboxmode.describe(tmp_path) == {"choice": "auto", "using": "local",
                                              "line": "Sandbox: Local, without Docker (Auto: Docker isn't ready)"}


def test_docker_is_asked_at_most_every_look_again_seconds(tmp_path, docker, monkeypatch):
    from ai_browser import sandboxmode

    now = [1000.0]
    monkeypatch.setattr(sandboxmode, "clock", lambda: now[0])
    for _ in range(5):
        sandboxmode.resolve(tmp_path)
    assert docker["looks"] == 1
    now[0] += sandboxmode.LOOK_AGAIN + 1
    sandboxmode.resolve(tmp_path)
    assert docker["looks"] == 2


def test_the_users_choice_and_aib_sandbox_need_no_look_at_docker(tmp_path, docker, monkeypatch):
    from ai_browser import sandboxmode
    from ai_browser.settings import Settings

    Settings(tmp_path).set("sandbox", "local")
    assert sandboxmode.resolve(tmp_path) == "local"
    assert sandboxmode.describe(tmp_path)["line"] == "Sandbox: Local, without Docker"
    Settings(tmp_path).set("sandbox", "docker")
    assert sandboxmode.resolve(tmp_path) == "docker" and docker["looks"] == 0
    docker["ready"] = False
    assert sandboxmode.describe(tmp_path)["line"] == (
        "Sandbox: Docker, which isn't ready: Docker isn't running. Start Docker Desktop, then retry.")
    monkeypatch.setenv("AIB_SANDBOX", "local")  # the app sets it for an agent's tools: it wins over the setting
    looks = docker["looks"]
    assert sandboxmode.resolve(tmp_path) == "local"
    assert sandboxmode.describe(tmp_path) == {"choice": "docker", "using": "local",
                                              "line": "Sandbox: Local, without Docker (set by AIB_SANDBOX)"}
    assert docker["looks"] == looks
    monkeypatch.setenv("AIB_SANDBOX", "kubernetes")  # anything else: as if unset
    assert sandboxmode.resolve(tmp_path) == "docker"
    assert sandboxmode.resolve(tmp_path, env={"AIB_SANDBOX": " Local "}) == "local"
