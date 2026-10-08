# PyInstaller's recipe for AI Browser.exe, the Windows test build (.github/workflows/windows-app.yml):
#   uv sync --locked --group packaging
#   uv run --no-sync pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/ai-browser.spec
# It makes one folder, dist/AI Browser/: the program AI Browser.exe (`ai-browser`'s command line; with no command it
# runs `app`) and its bundle in _internal/. packaging/windows_app.py then adds AI Browser's own app (Electron) beside
# it in desktop/. The same recipe builds on macOS, for a check there.
#
# The engine reads these files at run time, and they are bundled where it looks for them:
# - every file of the ai_browser package that isn't Python code, at its place in the package (Path(__file__)'s
#   neighbours): the app's pages (app/ui), the Electron app's JavaScript (desktop/electron), the Brain's readers,
#   reader.js, the live view (static/) and the test pages (pages/);
# - pages/_serve.py, which testpages.py loads as a file, not as a module;
# - the repository's docker/ (config.project_root() is the bundle's folder when frozen).
# Voice input isn't in this build: faster-whisper and what it brings are left out, and the app says how to add it.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent  # SPECPATH: this file's folder (packaging/)
PACKAGE = ROOT / "src" / "ai_browser"

datas = collect_data_files("ai_browser", excludes=["**/.DS_Store", "**/__pycache__/**"])
datas += [
    (str(PACKAGE / "pages" / "_serve.py"), "ai_browser/pages"),
    (str(ROOT / "docker"), "docker"),
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=["http.server"],  # pages/_serve.py's: nothing else imports it
    excludes=["faster_whisper", "ctranslate2", "onnxruntime", "av", "tokenizers", "huggingface_hub", "numpy",
              "PyInstaller", "pytest", "_pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AI Browser",
    console=True,  # its console window shows the log; closing it stops AI Browser
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="AI Browser", upx=False)
