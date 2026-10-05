"""AI Browser's own app: Electron (a Chromium with a window, a menu-bar icon, a global shortcut and native
notifications of its own) over the Python engine. `ai-browser doctor --setup` downloads one pinned Electron after the
user's yes, checks it and builds the app in <home>/desktop/ (setup.py). `ai-browser app` then starts it (launch.py),
or a browser window (app/window.py) while it isn't set up. The app's own JavaScript is in desktop/electron/."""
