"""The Windows test build's steps after PyInstaller (.github/workflows/windows-app.yml), run with the project's own
Python: `python packaging/windows_app.py <step> ...`.
- electron <package>: AI Browser's own app, in <package>/desktop beside AI Browser.exe. The pinned Electron for
  Windows x64 is downloaded with the project's own code (desktop/download.py: Electron's SHASUMS256.txt must list the
  pinned SHA-256, and the zip must have it), unpacked, and built with desktop/assemble.py, as `doctor --setup` builds
  it in <home>/desktop. Whatever fails, nothing is kept.
- zip <package> <archive>: the package folder in one zip, under its own name.
- check <package> [--bundled]: the packaged program starts. The files the engine reads are in its bundle, --help
  lists every command, and its MCP server answers initialize and lists its tools. With --bundled, doctor --setup says
  AI Browser's own app is ready beside it. Each run has a throwaway home folder and AIB_HOME."""

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
    args = parser.parse_args(argv)
    if args.step == "electron":
        electron(args.package)
        return 0
    if args.step == "zip":
        zip_folder(args.package, args.archive)
        print(f"{args.archive}: {args.archive.stat().st_size // 1_000_000} MB")
        return 0
    problems = check(args.package, args.bundled)
    for problem in problems:
        print(f"✗ {problem}", file=sys.stderr)
    print("✗ the package doesn't work" if problems else "✓ the package starts")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
