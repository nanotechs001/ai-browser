"""AI Browser.exe's entry point (packaging/ai-browser.spec): the ai-browser command line. Double-clicked, with no
command, it runs `app` (cli.main)."""

from ai_browser.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
