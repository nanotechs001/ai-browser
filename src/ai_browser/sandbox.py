"""Start, reuse, stop and run commands in the Docker sandboxes.

Each profile has two containers on an isolated network (containers cannot reach each other):
- aib-<profile>     Chromium (user `browser`) with the logged-in profile; its DevTools port is
                    published on 127.0.0.1 behind a token only the host engine knows.
- aib-<profile>-sh  the agent's shell (user `agent`): /work and the skills, never the profile.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import CDP_PORT, IMAGE

PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
NETWORK = "aib-net"
READY_TIMEOUT = 20
REUSE_TIMEOUT = 5
EXEC_OUTPUT_CAP = 5_000_000
_DAEMON_DOWN = (
    "cannot connect to the docker daemon",
    "failed to connect to the docker api",
    "error during connect",
    "daemon is running",
)
_HARDENING = ["--init", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--network", NETWORK]


class DockerError(RuntimeError):
    """Docker failed; the message is a one-line fix for the user."""


@dataclass
class SandboxInfo:
    name: str
    profile: str
    http: str
    work_host: Path
    fresh: bool
    created: bool
    token: str = ""
    shell: str = ""
    stale_skills: bool = False  # skill folders changed since the shell started (it was busy)
    chrome: bool = False  # the browser is the user's own Chrome, not a sandbox container


@dataclass
class ExecResult:
    code: int
    output: str
    timed_out: bool


class Sandboxes:
    def __init__(self, home: Path, image: str = IMAGE, mounts: list[tuple[Path, str]] = ()):
        self.home = Path(home)
        self.image = image
        self.mounts = list(mounts)
        self._network_ready = False

    def _docker(self, *args: str, timeout: float = 60, check: bool = True) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=timeout)
        except FileNotFoundError:
            raise DockerError("Docker is not installed. Install Docker Desktop, then retry.") from None
        except subprocess.TimeoutExpired:
            raise DockerError(f"`docker {args[0]}` timed out. Is Docker Desktop running?") from None
        if check and result.returncode != 0:
            message = (result.stderr or result.stdout).strip()
            if any(marker in message.lower() for marker in _DAEMON_DOWN):
                raise DockerError("Docker isn't running. Start Docker Desktop, then retry.")
            last = message.splitlines()[-1] if message else f"exit {result.returncode}"
            raise DockerError(f"`docker {args[0]}` failed: {last}")
        return result

    def check(self) -> None:
        self._docker("info", "--format", "{{.ServerVersion}}", timeout=20)
        if self._docker("image", "inspect", self.image, check=False).returncode != 0:
            raise DockerError(f"The sandbox image {self.image} is missing. Run: uv run ai-browser build")

    def build(self, context: Path) -> None:
        if subprocess.run(["docker", "build", "-t", self.image, str(context)]).returncode != 0:
            raise DockerError("docker build failed; see the output above.")

    def _ensure_network(self) -> None:
        if self._network_ready:
            return
        if self._docker("network", "inspect", NETWORK, check=False).returncode != 0:
            created = self._docker("network", "create", "--driver", "bridge",
                                   "-o", "com.docker.network.bridge.enable_icc=false", NETWORK, check=False)
            if created.returncode != 0 and "already exists" not in created.stderr:
                raise DockerError(f"could not create the {NETWORK} network: {created.stderr.strip()}")
        self._network_ready = True

    def _inspect(self, name: str) -> tuple[str | None, dict]:
        """(status, labels) of a container, or (None, {}) when it does not exist."""
        result = self._docker("inspect", "-f", "{{.State.Status}}|{{json .Config.Labels}}", name, check=False)
        if result.returncode != 0:
            return None, {}
        status, _, labels = result.stdout.strip().partition("|")
        try:
            return status, json.loads(labels) or {}
        except ValueError:
            return status, {}

    def _mounts_label(self) -> str:
        key = json.dumps(sorted([str(host), mount] for host, mount in self.mounts))
        return hashlib.sha1(key.encode()).hexdigest()[:12]

    def start(self, profile: str = "default", fresh: bool = False) -> SandboxInfo:
        if fresh:
            profile = "fresh-" + secrets.token_hex(3)
        elif profile in ("chrome", "app"):  # their folders and sessions belong to your-own-Chrome mode and AI Browser
            raise ValueError(f"profile {profile!r} is reserved (your own Chrome and AI Browser use it): pick another "
                             "profile name")
        elif not PROFILE_RE.match(profile):
            raise ValueError(f"profile {profile!r}: use lowercase letters, digits and dashes (max 31)")
        work_host = self.home / "sandboxes" / profile / "work"
        work_host.mkdir(parents=True, exist_ok=True)
        self.check()
        self._ensure_network()
        info = self._browser(f"aib-{profile}", profile, work_host, fresh)
        info.shell = f"aib-{profile}-sh"
        info.stale_skills = self._shell(info.shell, work_host, fresh)
        return info

    def chrome_shell(self) -> str:
        """The shell container used with the user's own Chrome: one per ai-browser home, never shared between homes."""
        return f"aib-chrome-{hashlib.sha1(str(self.home.resolve()).encode()).hexdigest()[:8]}-sh"

    def start_shell(self, work_host: Path) -> str:
        """Only the shell container (used when the browser is the user's own Chrome)."""
        self.check()
        self._ensure_network()
        name = self.chrome_shell()
        self._shell(name, work_host, fresh=False)
        return name

    def _browser(self, name: str, profile: str, work_host: Path, fresh: bool) -> SandboxInfo:
        state, labels = self._inspect(name)
        token = labels.get("aib.token", "")
        if state == "running" and token:
            other_home = labels.get("aib.work")
            if other_home and other_home != str(work_host):
                raise DockerError(f"profile {profile} is already used by another ai-browser home ({other_home}); "
                                  f"stop it first: docker rm -f {name} {name}-sh")
            info = SandboxInfo(name, profile, f"http://127.0.0.1:{self._port(name)}", work_host, fresh, False, token)
            if self._wait_answering(info, REUSE_TIMEOUT):  # never remove a browser another session may use
                return info
        if state is not None:  # stopped, broken, or from an older ai-browser version
            self._docker("rm", "-f", name)
        token = secrets.token_urlsafe(24)
        args = ["run", "-d", "--name", name, "--label", "ai-browser=1", "--label", f"aib.token={token}",
                "--label", f"aib.work={work_host}", *_HARDENING, "--shm-size=1g", "--memory=2g", "--cpus=2",
                "-e", f"AIB_TOKEN={token}", "-p", f"127.0.0.1::{CDP_PORT}", "-v", f"{work_host}:/work"]
        if fresh:
            args += ["--rm", "--tmpfs", "/profile:uid=1000,gid=1000,mode=0700"]
        else:
            args += ["-v", f"aib-profile-{profile}:/profile"]
        self._docker(*args, self.image)
        info = SandboxInfo(name, profile, f"http://127.0.0.1:{self._port(name)}", work_host, fresh, True, token)
        if not self._wait_answering(info, READY_TIMEOUT):
            logs = self._docker("logs", "--tail", "5", name, check=False)
            tail = " | ".join((logs.stdout + logs.stderr).strip().splitlines()[-3:])
            raise DockerError(f"Chromium in {name} did not start within {READY_TIMEOUT}s: {tail}")
        return info

    def _shell(self, name: str, work_host: Path, fresh: bool) -> bool:
        """Start or reuse the shell container; returns True when it runs with outdated skill folders."""
        state, labels = self._inspect(name)
        wanted = self._mounts_label()
        if state == "running":
            if labels.get("aib.mounts") == wanted:
                return False
            if self._busy(name):  # someone's command is running: refresh later
                return True
        if state is not None:
            self._docker("rm", "-f", name)
        args = ["run", "-d", "--name", name, "--label", "ai-browser=1", "--label", f"aib.mounts={wanted}",
                *_HARDENING, "--memory=1g", "--cpus=1", "--user", "agent", "--entrypoint", "sleep",
                "-v", f"{work_host}:/work"]
        if fresh:
            args.append("--rm")
        for host, mount in self.mounts:
            args += ["-v", f"{host}:{mount}:ro"]
        self._docker(*args, self.image, "infinity")
        return False

    def _busy(self, name: str) -> bool:
        processes = self._docker("top", name, "-eo", "args", check=False).stdout.splitlines()[1:]
        return any("sleep infinity" not in line and "docker-init" not in line for line in processes)

    def _port(self, name: str) -> int:
        out = self._docker("port", name, f"{CDP_PORT}/tcp").stdout.strip().splitlines()
        return int(out[0].rsplit(":", 1)[1])

    @staticmethod
    def _answers(info: SandboxInfo) -> bool:
        try:
            with urllib.request.urlopen(f"{info.http}/{info.token}/json/version", timeout=1) as response:
                return response.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def _wait_answering(self, info: SandboxInfo, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while not self._answers(info):
            if time.monotonic() > deadline:
                return False
            time.sleep(0.1)
        return True

    def ws_url(self, info: SandboxInfo) -> str:
        with urllib.request.urlopen(f"{info.http}/{info.token}/json/version", timeout=5) as response:
            ws = json.load(response)["webSocketDebuggerUrl"]
        return info.http.replace("http://", "ws://") + f"/{info.token}/devtools/" + ws.split("/devtools/", 1)[1]

    def stop(self, name: str) -> None:
        """Stop a profile's containers (browser and shell); logins stay in the profile volume."""
        for container in (name, f"{name}-sh"):
            self._docker("stop", "-t", "5", container, check=False, timeout=30)
            self._docker("rm", "-f", container, check=False)

    def is_running(self, name: str) -> bool:
        return self._inspect(name)[0] == "running"

    def exec(self, name: str, command: str, cwd: str = "/work", timeout: int = 60) -> ExecResult:
        args = ["docker", "exec", "-u", "agent", "-w", cwd, name,
                "timeout", "-s", "KILL", f"{timeout}s", "bash", "-lc", command]
        started = time.monotonic()
        try:
            result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout + 10)
        except subprocess.TimeoutExpired as exc:
            return ExecResult(137, (exc.output or b"").decode(errors="replace"), True)
        output = result.stdout.decode(errors="replace")[:EXEC_OUTPUT_CAP]
        timed_out = result.returncode == 137 and time.monotonic() - started >= timeout - 0.5
        return ExecResult(result.returncode, output, timed_out)
