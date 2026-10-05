"""ai-browser command line: run the MCP server and manage the sandbox."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import statistics
import sys
import time
from pathlib import Path

from . import platforms
from .config import IMAGE, home, project_root

# operation, budget in ms (spec §7)
BUDGETS = [("observe", 100), ("observe heavy page", 300), ("click step", 150), ("type step", 150),
           ("open local page", 500), ("screenshot", 300)]
STOPPED = "AI Browser stopped (see above). Press Enter to close this window."


def main(argv: list[str] | None = None) -> int:
    """The command in `argv` (else the command line). The packaged AI Browser.exe (packaging/) with no command was
    double-clicked: it runs `app`, and its console window shows the log. When the app can't start, the window waits
    for Enter, so the reason can be read."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv or not platforms.frozen():
        return _command(argv)
    code = _command(["app"])
    if code not in (0, 130) and _interactive():
        _ask(STOPPED)
    return code


def _command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ai-browser", description="Sandboxed browser, shell and skills for Claude.")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    commands.add_parser("mcp", help="run the MCP server on stdio (Claude Code starts this)")
    commands.add_parser("build", help=f"build the sandbox image {IMAGE}")
    doctor = commands.add_parser("doctor", help="check Docker, the image, a sandbox, page reading, screenshots, skills, live view")
    doctor.add_argument("--own", "--chrome", dest="own", action="store_true",
                        help="check your own browser (Brave or Chrome) instead of the sandbox")
    doctor.add_argument("--setup", action="store_true",
                        help="check what `ai-browser app` needs, without Docker and without connecting to a browser")
    bench = commands.add_parser("bench", help="measure speed on local test pages against the budgets")
    bench.add_argument("--runs", type=int, default=15, help="repetitions per measurement (default 15)")
    live = commands.add_parser("live", help="start a sandbox and print its live-view link, to log in to sites yourself")
    live.add_argument("--profile", default="default", help="saved-login profile (default: default)")
    stop = commands.add_parser("stop", help="stop a sandbox container (logins are kept)")
    stop.add_argument("profile", nargs="?", default="default",
                      help="profile to stop (default: default), or chrome for the shell used with your own Chrome")
    stop.add_argument("--all", action="store_true", help="stop every ai-browser container")
    app = commands.add_parser("app", help="open AI Browser in its own window: AI Home, Mission Control and the Brain")
    app.add_argument("--model", choices=["sonnet", "opus", "haiku"], default="sonnet",
                     help="Claude model for new agents until you pick one in AI Home (default: sonnet)")
    app.add_argument("--browser", default=None, metavar="{brave}",
                     help="where agents browse: your Brave (the only choice: AI Browser's own Chrome is gone)")
    app.add_argument("--window", choices=["auto", "chrome", "brave", "edge"], default=None,
                     help="a browser window for this run, drawn by this browser (default: AI Browser's own app once "
                          "it is set up, else the Settings choice)")
    args = parser.parse_args(argv)
    if args.command != "mcp":  # the mcp library writes its own UTF-8 stream
        _utf8_console()

    if args.command == "mcp":
        from .server import build_server

        build_server().run("stdio")
        return 0
    if args.command == "build":
        from .sandbox import DockerError, Sandboxes

        try:
            Sandboxes(home()).build(project_root() / "docker")
        except DockerError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "stop":
        return _stop(args.profile, args.all)
    try:
        if args.command == "doctor":
            if args.setup:
                return _doctor_setup()
            return asyncio.run(_doctor_own() if args.own else _doctor())
        if args.command == "bench":
            return asyncio.run(_bench(args.runs))
        if args.command == "live":
            return asyncio.run(_live(args.profile))
        if args.command == "app":
            from .app.run import run_app

            return asyncio.run(run_app(home(), args.model, browser=args.browser, window_browser=args.window))
    except KeyboardInterrupt:
        return 130
    return 2


def _stop(profile: str, everything: bool) -> int:
    from .sandbox import PROFILE_RE, DockerError, Sandboxes

    boxes = Sandboxes(home())
    try:
        if everything:
            names = boxes._docker("ps", "--filter", "label=ai-browser=1", "--format", "{{.Names}}").stdout.split()
        elif profile == "chrome":  # the sandboxed shell used with the user's own Chrome
            names = [name for name in [boxes.chrome_shell()] if boxes.is_running(name)]
        elif not PROFILE_RE.match(profile):
            print(f"error: profile {profile!r}: use lowercase letters, digits and dashes", file=sys.stderr)
            return 2
        else:
            names = [f"aib-{profile}"] if boxes.is_running(f"aib-{profile}") else []
        for name in names:
            boxes.stop(name)
            print(f"stopped {name}" + ("" if name.endswith("-sh") else " (logins are kept in its profile)"))
        if not names:
            print("nothing to stop")
    except DockerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _elapsed(text: str) -> str:
    return text.rsplit("⏱", 1)[-1].strip() if "⏱" in text else "?"


def _utf8_console() -> None:
    """✓ and ✗ print on any console and into files (`doctor > log.txt`): Windows' code page can't encode them."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError, OSError):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _first_free(ports: range) -> int | None:
    from .live import _bind

    for port in ports:
        sock = _bind("127.0.0.1", port)
        if sock is not None:
            sock.close()
            return port
    return None


def _doctor_setup() -> int:
    """What `ai-browser app` needs, checked without Docker and without opening a DevTools connection, so no browser
    asks Allow. Python, Claude Code, a browser that can draw AI Browser's window and a config.json that is there must
    pass; the rest is information."""
    import platform

    from .app.server import APP_PORTS
    from .chrome import brave_binary, browser_name, chrome_binary, inspect_address, own_browser_dir, switch_on
    from .claudecli import ClaudeNotUsable, claude_argv
    from .config import LIVE_PORTS, config_problem

    failed = False

    def report(mark: str, label: str, detail: str, required: bool = False) -> None:
        nonlocal failed
        failed |= required and mark == "✗"
        print(f"{mark} {label:<11} {detail}")

    version = platform.python_version()
    if sys.version_info >= (3, 12):
        report("✓", "Python", version, True)
    else:
        report("✗", "Python", f"{version}: ai-browser needs 3.12 or newer (`uv sync` installs it)", True)
    try:
        claude = claude_argv()[0]
    except ClaudeNotUsable as exc:  # an npm claude.cmd on Windows: its message says what to do
        report("✗", "Claude Code", str(exc), True)
    else:
        if Path(claude).is_file():
            report("✓", "Claude Code", claude, True)
        else:
            report("✗", "Claude Code", f"not found ({claude}): install Claude Code, then sign in once with `claude`",
                   True)
    from .app.window import pick
    from .settings import Settings

    setting = Settings(home()).get()["window_browser"]
    found = pick(setting)  # reads installed apps' files only: no browser starts, nothing connects
    if found is None:
        report("✗", "window", "AI Browser needs Google Chrome, Brave or Microsoft Edge to draw its window: install "
                              "one, or set AIB_CHROME_BINARY to the full path of chrome", True)
    else:
        report("✓", "window", f"{found.browser.name} ({'Auto' if setting == 'auto' else 'Settings'}) "
                              f"{found.browser.binary}", True)
        if found.note:
            report("-", "window", found.note)
    chrome = chrome_binary()
    if chrome and Path(chrome).is_file():
        report("✓", "Chrome", chrome)
    else:
        report("-", "Chrome", "not installed (optional: agents can browse in it)")
    brave = brave_binary()
    report("✓" if brave else "-", "Brave", brave or "not installed (optional: your everyday browser, where agents and "
                                                    "the Brain can work)")
    folder = own_browser_dir()
    name = browser_name(folder)
    if not folder.is_dir():
        report("-", "everyday", f"{name}: no profile folder at {folder}")
    elif switch_on(folder):  # a TCP check of DevToolsActivePort's port: no DevTools session, so no Allow question
        report("✓", "everyday", f"{name}: profile folder found; remote debugging is on")
    else:
        report("-", "everyday", f"{name}: profile folder found; remote debugging is off ({inspect_address(folder)})")
    ranges = f"app {APP_PORTS.start}-{APP_PORTS.stop - 1} and live view {LIVE_PORTS.start}-{LIVE_PORTS.stop - 1}"
    if _first_free(APP_PORTS) and _first_free(LIVE_PORTS):
        report("✓", "ports", f"{ranges} have free ports")
    else:
        report("✗", "ports", f"no free port in {ranges}: see \"no free port\" in the README")
    problem = config_problem(home())
    if problem:  # the skills the user blocked would load again, with no other sign
        report("✗", "config", problem, True)
    report("-", "Docker", "not checked here: run `uv run ai-browser doctor`")
    _desktop_check(report)
    print("some checks failed" if failed else "all good")
    return 1 if failed else 0


def _interactive() -> bool:
    """Whether someone can see a question here and answer it: a terminal both ways, not a pipe or a file."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _ask(question: str) -> str:
    try:
        return input(question)
    except EOFError:
        return ""


def _desktop_check(report) -> None:
    """AI Browser's own app: set up, or not. While it isn't, or uses an older Electron, and someone can answer: the
    offer (the version, the size, the address), the question, and after a typed yes, the setup. Nothing is
    downloaded without that yes."""
    from .desktop import layout
    from .desktop.download import SetupError
    from .desktop.release import SETUP_COMMAND, VERSION, asset_for, offer
    from .desktop.setup import set_up

    root = home()
    asset, built = asset_for(), layout.installed(root)
    if asset is None:
        report("-", "app", "AI Browser's own app runs on macOS and on Windows (x64): here it opens in a browser window")
        return
    if built is not None and built.get("electron") == VERSION:
        report("✓", "app", f"AI Browser's own app (Electron {VERSION}): {layout.app_path(root)}")
        return
    problem = layout.problem(root)
    if problem:
        report("-", "app", f"the last setup didn't finish: {problem}")
    now = (f"AI Browser's own app uses Electron {built.get('electron')}, and {VERSION} is out" if built is not None
           else "AI Browser's own app isn't set up: AI Browser opens in a browser window")
    if not _interactive():
        report("-", "app", f"{now}. To set it up, run `{SETUP_COMMAND}` in a terminal (it asks first)")
        return
    report("-", "app", now)
    print("\n".join(offer(asset, layout.folder(root))))
    if _ask("Download it now? Type y and press Enter: ").strip().lower() not in ("y", "yes"):
        print("Skipped: nothing was downloaded.")
        return
    try:
        set_up(root, asset)
    except SetupError as exc:
        report("✗", "app", str(exc), True)
        return
    report("✓", "app", "AI Browser's own app is ready: start it with `uv run ai-browser app`")


async def _doctor() -> int:
    from . import testpages
    from .engine import Engine
    from .sandbox import DockerError, Sandboxes

    failed = False

    def report(passed: bool, label: str, detail: str) -> None:
        nonlocal failed
        failed |= not passed
        print(f"{'✓' if passed else '✗'} {label:<11} {detail}")

    boxes = Sandboxes(home())
    try:
        version = boxes._docker("info", "--format", "{{.ServerVersion}}", timeout=20).stdout.strip()
        report(True, "Docker", f"running (server {version})")
    except DockerError as exc:
        report(False, "Docker", str(exc))
        return 1
    if boxes._docker("image", "inspect", IMAGE, check=False).returncode != 0:
        report(False, "image", f"{IMAGE} is missing; run: uv run ai-browser build")
        return 1
    report(True, "image", IMAGE)

    engine = Engine()
    try:
        started = await engine.sandbox_start(fresh=True)
        if started.text.startswith("error"):
            report(False, "sandbox", started.text.splitlines()[0])
            return 1
        report(True, "sandbox", f"{engine.info.name} (throwaway) ready in {_elapsed(started.text)}")
        product = (await engine.cdp.send("Browser.getVersion"))["product"]
        report(True, "browser", product)
        base, _ = testpages.serve(engine.sandboxes, engine.info)
        opened = await engine.open(base + "form.html")
        rows = sum(1 for line in opened.text.splitlines() if line[:1] == "e" and line[1:2].isdigit())
        report(rows > 0, "page read", f"{rows} elements in {_elapsed(opened.text)}")
        shot = await engine.screenshot()
        report(len(shot.images) == 1, "screenshot", shot.text.splitlines()[0].split(" saved ")[0])
        counts: dict[str, int] = {}
        for skill in engine.catalog.all():
            counts[skill.namespace] = counts.get(skill.namespace, 0) + 1
        summary = ", ".join(f"{namespace} {count}" for namespace, count in counts.items()) or "none installed"
        report(True, "skills", f"{sum(counts.values())} found ({summary})")
        report(bool(engine.live and engine.live.url), "live view", engine.live.url if engine.live else "not started")
    finally:
        await engine.close()
    print("some checks failed" if failed else "all good")
    return 1 if failed else 0



async def _doctor_own() -> int:
    """Check that the engine can drive the user's own browser (Brave or Chrome; it may ask them to click Allow)."""
    from . import testpages
    from .chrome import ChromeError, browser_name, find_ws_url, own_browser_dir
    from .engine import Engine

    folder = own_browser_dir()
    name = browser_name(folder)
    try:
        find_ws_url(folder, timeout=3)  # the browser may have just been opened
    except ChromeError as exc:
        print(f"✗ {name:<11} {exc}")
        return 1
    print(f"✓ {name:<11} remote debugging allowed (click Allow if {name} asks now)")
    engine = Engine()
    base, _, stop_pages = testpages.serve_host()
    failed = False
    try:
        started = await engine.sandbox_start(chrome=True)
        if started.text.startswith("error"):
            print(f"✗ connect     {started.text.splitlines()[0]}")
            return 1
        print(f"✓ connect     {started.text.splitlines()[-1]}")
        opened = await engine.open(base + "form.html")
        rows = sum(1 for line in opened.text.splitlines() if line[:1] == "e" and line[1:2].isdigit())
        failed = rows == 0
        print(f"{'✗' if failed else '✓'} page read   {rows} elements in {_elapsed(opened.text)}")
    finally:
        await engine.close()
        stop_pages()
    print("some checks failed" if failed else "all good (this session's tab was closed again)")
    return 1 if failed else 0


async def _bench(runs: int) -> int:
    from . import testpages
    from .browser import Browser
    from .cdp import CDP
    from .config import Config
    from .sandbox import Sandboxes
    from .steps import parse_step
    from .workfs import WorkDir

    async def median_ms(make) -> float:
        timings = []
        for _ in range(runs):
            started = time.perf_counter()
            await make()
            timings.append((time.perf_counter() - started) * 1000)
        return statistics.median(timings)

    boxes = Sandboxes(home())
    info = await asyncio.to_thread(boxes.start, "default", True)
    cdp = await CDP.connect(await asyncio.to_thread(boxes.ws_url, info))
    browser = Browser(cdp, WorkDir(info.work_host, "bench"), Config())
    try:
        await browser.start()
        base, _ = testpages.serve(boxes, info)
        form = base + "form.html"
        results = {}
        await browser.open(base + "heavy.html")
        results["observe heavy page"] = await median_ms(browser.observe)
        await browser.open(form)
        results["observe"] = await median_ms(browser.observe)
        ids = {row["name"]: row["id"] for row in (await browser.state())["rows"]}
        click, name = ids["Increment"], ids["Full name"]
        results["click step"] = await median_ms(lambda: browser.act([parse_step(f"click {click}")]))
        results["type step"] = await median_ms(lambda: browser.act([parse_step(f'type {name} "Bob"')]))
        results["screenshot"] = await median_ms(browser.screenshot)
        results["open local page"] = await median_ms(lambda: browser.open(form))
    finally:
        await browser.close()
        await cdp.close()
        await asyncio.to_thread(boxes.stop, info.name)

    print(f"{'operation':<20} {'median':>9} {'budget':>9}  result   ({runs} runs each)")
    over = False
    for operation, budget in BUDGETS:
        ms = results[operation]
        over |= ms >= budget
        print(f"{operation:<20} {ms:>6.0f} ms {budget:>6} ms  {'PASS' if ms < budget else 'OVER'}")
    return 1 if over else 0


async def _live(profile: str) -> int:
    from .engine import Engine

    engine = Engine(default_profile=profile)
    try:
        started = await engine.sandbox_start(profile=profile)
        print(started.text)
        if started.text.startswith("error"):
            return 1
        print("\nOpen the live view link above to watch or log in. Ctrl-C stops watching; the sandbox keeps running.")
        await asyncio.Event().wait()
    finally:
        await engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
