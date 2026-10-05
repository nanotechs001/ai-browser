"""The Windows test build's steps after PyInstaller (.github/workflows/windows-app.yml), run with the project's own
Python: `python packaging/windows_app.py <step> ...`.
- electron <package>: AI Browser's own app, in <package>/desktop beside AI Browser.exe. The pinned Electron for
  Windows x64 is downloaded with the project's own code (desktop/download.py: Electron's SHASUMS256.txt must list the
  pinned SHA-256, and the zip must have it), unpacked, and built with desktop/assemble.py, as `doctor --setup` builds
  it in <home>/desktop. Whatever fails, nothing is kept.
- zip <package> <archive>: the package folder in one zip, under its own name.
- check <package> [--bundled]: the packaged program starts. The files the engine reads are in its bundle, --help
  lists every command, and its MCP server answers initialize and lists its tools. With --bundled, doctor --setup says
  AI Browser's own app is ready beside it. Each run has a throwaway home folder and AIB_HOME.
- start <package>: `AI Browser.exe app` for real, as a double-click starts it, with the start log on (AIB_DEBUG_START,
  ai_browser/debugstart.py) and a throwaway home folder. Brave isn't set up there, which the app handles. Its output,
  and the start log AI Browser's own app keeps in its profile, are printed. It fails unless AI Browser's own app drew
  AI Browser and the page connected (a window socket, which needs the window's cookie), within START_SECONDS."""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from collections.abc import Callable
from pathlib import Path

PROGRAM = "AI Browser"  # AI Browser.exe on Windows; on macOS (a check build) a program with no suffix
WORK = "electron-work"  # beside the package, on its drive: the unpacked Electron is moved into it, not copied
BUNDLE = "_internal"  # PyInstaller's folder of everything but the program
BUNDLED = ("ai_browser/app/ui/app.html", "ai_browser/app/ui/icon.png", "ai_browser/desktop/electron/main.js",
           "ai_browser/desktop/electron/thispage.ps1", "ai_browser/brain/readers/gmail.js", "ai_browser/reader.js",
           "ai_browser/qa/probe.js", "ai_browser/static/live.html", "ai_browser/pages/_serve.py",
           "ai_browser/pages/form.html", "skills/website-qa/SKILL.md", "docker/Dockerfile")
COMMANDS = ("mcp", "build", "doctor", "bench", "live", "stop", "app")
TOOLS = ("act", "observe", "open", "find_skills")
WAIT = 120  # seconds for one run of the program (a first start on Windows is slow while Defender scans it)
START_SECONDS = 90  # how long the start check watches `AI Browser.exe app` at most
AFTER_CONNECTED = 15  # seconds it keeps watching once the page connected: the frames' lines come then
OWN_APP = "[start] window: AI Browser's own app"
CONNECTED = "[start] window socket connected"
DEBUG_FILE = "debug-start.log"  # AI Browser's own app's start log, in its profile (main.js)


def windows_asset():
    """The Electron zip the Windows build bundles: the pinned one for Windows x64 (desktop/release.py)."""
    from ai_browser.desktop.release import asset_for

    return asset_for("win32", "x64")


def electron(package: Path, fetch: Callable | None = None, asset=None, out: Callable[[str], None] = print) -> Path:
    """AI Browser's own app, built in <package>/desktop: its path. SetupError (desktop/download.py) when the download
    doesn't match, UnpackError when the zip can't be unpacked safely; nothing is kept then."""
    from ai_browser.desktop import assemble
    from ai_browser.desktop.download import download
    from ai_browser.desktop.release import VERSION
    from ai_browser.desktop.unpack import unpack
    from ai_browser.hearing.model import urlopen_fetch

    package, asset = Path(package), asset or windows_asset()
    work = package.parent / WORK
    shutil.rmtree(work, ignore_errors=True)
    try:
        zipped = download(asset, work, fetch or urlopen_fetch)
        out(f"{asset.name} matches Electron's SHASUMS256.txt and the pinned SHA-256")
        unpack(zipped, work / "electron")
        app = assemble.build(work / "electron", package, asset.system, arch=asset.arch, move=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    out(f"AI Browser's own app (Electron {VERSION}): {app}")
    return app


def zip_folder(folder: Path, archive: Path) -> None:
    """`folder`, with everything in it, as one zip whose top folder has its name."""
    folder = Path(folder)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(folder.rglob("*")):
            zipped.write(path, Path(folder.name, path.relative_to(folder)).as_posix())


def program(package: Path) -> Path:
    return Path(package) / (f"{PROGRAM}.exe" if os.name == "nt" else PROGRAM)


def _mcp(command: list[str], env: dict, log) -> tuple[str, list[str]]:
    """The MCP server's name and its tools' names, asked over stdio as Claude Code asks."""
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, env=env)
    lines: queue.Queue = queue.Queue()

    def read() -> None:
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=read, daemon=True).start()

    def send(message: dict) -> None:
        process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        process.stdin.flush()

    def answer(number: int) -> dict:
        while True:
            line = lines.get(timeout=WAIT)
            if line is None:
                raise RuntimeError(f"the MCP server ended (exit code {process.wait()})")
            message = json.loads(line)
            if message.get("id") == number:
                if "result" not in message:
                    raise RuntimeError(f"the MCP server answered {message}")
                return message["result"]

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "windows-app-check", "version": "1"}}})
        name = answer(1)["serverInfo"]["name"]
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = [tool["name"] for tool in answer(2)["tools"]]
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=WAIT)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    return name, tools


def check(package: Path, bundled: bool = False, out: Callable[[str], None] = print) -> list[str]:
    """What is wrong with the package: [] when it works."""
    from ai_browser.desktop.release import VERSION

    package = Path(package).resolve()
    exe = program(package)
    if not exe.is_file():
        return [f"{exe} is missing"]
    problems = [f"{name} isn't in the bundle" for name in BUNDLED if not (package / BUNDLE / name).is_file()]
    with tempfile.TemporaryDirectory(prefix="aib-check-", ignore_cleanup_errors=True) as folder:
        env = {**os.environ, "HOME": folder, "USERPROFILE": folder, "AIB_HOME": str(Path(folder) / "aib-home")}
        shown = subprocess.run([str(exe), "--help"], env=env, stdin=subprocess.DEVNULL, capture_output=True,
                               timeout=WAIT)
        text = shown.stdout.decode("utf-8", "replace")
        out(f"--help: exit code {shown.returncode}")
        if shown.returncode != 0 or not all(command in text for command in COMMANDS):
            problems.append(f"--help didn't list every command:\n{text}{shown.stderr.decode('utf-8', 'replace')}")
        with open(Path(folder) / "mcp.log", "w+b") as log:
            try:
                name, tools = _mcp([str(exe), "mcp"], env, log)
            except (OSError, RuntimeError, ValueError, queue.Empty) as exc:
                log.seek(0)
                problems.append(f"the MCP server didn't answer ({exc!r}):\n{log.read().decode('utf-8', 'replace')}")
            else:
                out(f"mcp: {name}, {len(tools)} tools")
                if name != "ai-browser" or not set(TOOLS) <= set(tools):
                    problems.append(f"the MCP server is {name!r} with the tools {tools}")
        if bundled:
            done = subprocess.run([str(exe), "doctor", "--setup"], env=env, stdin=subprocess.DEVNULL,
                                  capture_output=True, timeout=WAIT)
            text = done.stdout.decode("utf-8", "replace")
            out(text.rstrip())
            line = next((line for line in text.splitlines() if line.split()[1:2] == ["app"]), "")
            if not (line.startswith("✓") and f"Electron {VERSION}" in line and str(package / "desktop") in line):
                problems.append(f"doctor --setup didn't find AI Browser's own app beside the program: {line!r}")
    return problems


def start_problems(text: str) -> list[str]:
    """What the start log of one `AI Browser.exe app` says went wrong: [] when AI Browser's own app drew AI Browser
    and its page connected."""
    problems = []
    if OWN_APP not in text:
        problems.append("AI Browser's own app didn't draw AI Browser: a browser window did, or nothing")
    if CONNECTED not in text:
        problems.append("AI Browser's page never connected")
    return problems


def _stop(process: subprocess.Popen) -> None:
    """The program and everything it started (AI Browser's own app, a browser window), at once."""
    if process.poll() is None and os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=WAIT)
    if process.poll() is None:
        process.kill()
    process.wait(timeout=WAIT)


def start(package: Path, seconds: float = START_SECONDS, after: float = AFTER_CONNECTED,
          out: Callable[[str], None] = print) -> list[str]:
    """`AI Browser.exe app` started for real with the start log on, watched up to `seconds` (`after` more once its
    page connected), then stopped. Everything it said is printed, and so is any start log its own app kept. What went
    wrong: [] when it works."""
    package = Path(package).resolve()
    with tempfile.TemporaryDirectory(prefix="aib-start-", ignore_cleanup_errors=True) as folder:
        env = {**os.environ, "HOME": folder, "USERPROFILE": folder, "AIB_HOME": str(Path(folder) / "aib-home"),
               "AIB_DEBUG_START": "1", "PYTHONUNBUFFERED": "1"}
        said = Path(folder) / "start.log"
        with open(said, "wb") as log:
            process = subprocess.Popen([str(program(package)), "app"], cwd=package, env=env,
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + seconds
            connected, ended = False, None
            try:
                while time.monotonic() < deadline and process.poll() is None:
                    if not connected and CONNECTED in said.read_text(encoding="utf-8", errors="replace"):
                        connected = True
                        deadline = min(deadline, time.monotonic() + after)
                    time.sleep(0.25)
                ended = process.poll()
            finally:
                _stop(process)
        text = said.read_text(encoding="utf-8", errors="replace")
        out("--- AI Browser.exe app, with the start log on ---")
        out(text.rstrip())
        out(f"--- it ended by itself, with exit code {ended}" if ended is not None else "--- it was stopped")
        for log_file in sorted({*Path(folder).rglob(DEBUG_FILE), *package.rglob(DEBUG_FILE)}):
            out(f"--- AI Browser's own app's start log: {log_file}")
            out(log_file.read_text(encoding="utf-8", errors="replace").rstrip())
    return start_problems(text)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # ✓ in doctor's lines, on Windows' console too
    parser = argparse.ArgumentParser(prog="windows_app.py", description=__doc__.splitlines()[0])
    steps = parser.add_subparsers(dest="step", required=True)
    steps.add_parser("electron").add_argument("package", type=Path)
    zipping = steps.add_parser("zip")
    zipping.add_argument("package", type=Path)
    zipping.add_argument("archive", type=Path)
    checking = steps.add_parser("check")
    checking.add_argument("package", type=Path)
    checking.add_argument("--bundled", action="store_true", help="AI Browser's own app must be beside the program")
    steps.add_parser("start").add_argument("package", type=Path)
    args = parser.parse_args(argv)
    if args.step == "electron":
        electron(args.package)
        return 0
    if args.step == "zip":
        zip_folder(args.package, args.archive)
        print(f"{args.archive}: {args.archive.stat().st_size // 1_000_000} MB")
        return 0
    if args.step == "start":
        problems = start(args.package)
        for problem in problems:
            print(f"✗ {problem}", file=sys.stderr)
        print("✗ AI Browser didn't open" if problems else "✓ AI Browser opened in its own app; its page connected")
        return 1 if problems else 0
    problems = check(args.package, args.bundled)
    for problem in problems:
        print(f"✗ {problem}", file=sys.stderr)
    print("✗ the package doesn't work" if problems else "✓ the package starts")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
