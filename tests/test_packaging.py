"""The Windows test build (packaging/, .github/workflows/windows-app.yml): the workflow runs only by hand, and its
helper builds AI Browser's own app beside AI Browser.exe with the project's own download and assemble code, then zips
the package. The Electron release is a miniature (tests/fake_electron_zip.py): no test downloads Electron, and no
test runs PyInstaller."""

import importlib.util
import re
import zipfile
from pathlib import Path

import pytest

from fake_electron_zip import ReleaseFetch, checksum, windows_zip

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def windows_app():
    spec = importlib.util.spec_from_file_location("windows_app", ROOT / "packaging" / "windows_app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def release():
    """A miniature of Electron's Windows release, and its fetch (it records every address asked for)."""
    from ai_browser.desktop.release import Asset

    data = windows_zip()
    asset = Asset("win32", "x64", "electron-test-win32-x64.zip", len(data), checksum(data), "Windows (x64)")
    return asset, ReleaseFetch(asset, data)


def test_the_build_bundles_the_pinned_electron_for_windows(windows_app):
    from ai_browser.desktop.release import ASSETS, VERSION

    asset = windows_app.windows_asset()
    assert asset in ASSETS and (asset.system, asset.arch) == ("win32", "x64")
    assert asset.name == f"electron-v{VERSION}-win32-x64.zip" and len(asset.sha256) == 64


def test_the_app_is_built_beside_the_program_from_a_checked_download(windows_app, release, tmp_path):
    from ai_browser.desktop import fuses, layout
    from ai_browser.desktop.release import SHASUMS, VERSION

    asset, fetch = release
    package = tmp_path / "dist" / "AI Browser"
    package.mkdir(parents=True)
    said = []
    app = windows_app.electron(package, fetch, asset, said.append)
    assert app == package / "desktop" / "AI Browser"
    assert (app / "AI Browser.exe").is_file() and fuses.states(app / "AI Browser.exe") == ["000000011"]
    assert fetch.urls == [SHASUMS, asset.url]  # the checksums first, then the zip
    stamp = layout.stamp(package)
    assert (stamp["electron"], stamp["system"], stamp["arch"]) == (VERSION, "win32", "x64")
    assert sorted(path.name for path in (package / "desktop").iterdir()) == ["AI Browser", "app.json"]
    assert sorted(path.name for path in package.parent.iterdir()) == ["AI Browser"]  # no download left beside it
    assert said[0] == f"{asset.name} matches Electron's SHASUMS256.txt and the pinned SHA-256"


def test_a_download_that_doesnt_match_keeps_nothing(windows_app, release, tmp_path):
    from ai_browser.desktop.download import MISMATCH, SetupError

    asset, fetch = release
    fetch.corrupt = True
    package = tmp_path / "dist" / "AI Browser"
    package.mkdir(parents=True)
    with pytest.raises(SetupError, match=MISMATCH):
        windows_app.electron(package, fetch, asset, lambda line: None)
    assert list(package.iterdir()) == [] and sorted(path.name for path in package.parent.iterdir()) == ["AI Browser"]


def test_the_zip_holds_the_package_under_its_own_name(windows_app, tmp_path):
    package = tmp_path / "AI Browser"
    (package / "_internal" / "skills").mkdir(parents=True)
    (package / "AI Browser.exe").write_bytes(b"MZ")
    (package / "_internal" / "skills" / "SKILL.md").write_bytes(b"# skill")
    archive = tmp_path / "AI-Browser-windows.zip"
    windows_app.zip_folder(package, archive)
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        assert zipped.read("AI Browser/_internal/skills/SKILL.md") == b"# skill"
    assert "AI Browser/AI Browser.exe" in names and all(name.startswith("AI Browser/") for name in names)


def test_the_windows_build_runs_only_by_hand_with_pinned_actions():
    import yaml

    text = (ROOT / ".github" / "workflows" / "windows-app.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    assert workflow["name"] == "Build Windows app"
    assert list(workflow[True]) == ["workflow_dispatch"]  # PyYAML reads `on:` as True: never a push or a schedule
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["build"]
    assert job["runs-on"] == "windows-latest" and job["timeout-minutes"] == 40
    tests = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    pins = set(re.findall(r"uses: (\S+@[0-9a-f]{40}) +# v\d", tests))
    uses = [step["uses"] for step in job["steps"] if "uses" in step]
    assert len(uses) == 3 and set(uses) == pins  # checkout, setup-uv and upload-artifact, pinned as tests.yml pins them
    assert len(re.findall(r"uses: \S+@[0-9a-f]{40} +# v\d", text)) == 3
    assert "secrets." not in text
    runs = [step.get("run", "") for step in job["steps"]]
    assert "uv sync --locked --group packaging" in runs  # the project with PyInstaller, and no voice extra
    assert any("pyinstaller" in run and "packaging/ai-browser.spec" in run for run in runs)
    assert any("windows_app.py electron" in run for run in runs)
    assert any("windows_app.py zip" in run and "AI-Browser-windows.zip" in run for run in runs)
    upload = next(index for index, step in enumerate(job["steps"]) if "upload-artifact" in step.get("uses", ""))
    given = job["steps"][upload]["with"]
    assert given["path"] == "AI-Browser-windows.zip" and given["archive"] is False  # the zip itself, not a zip in a zip
    assert given["retention-days"] == 14 and given["if-no-files-found"] == "error"
    assert "windows_app.py check" in job["steps"][upload + 1]["run"]  # after the upload: the zip is there either way
    checkout = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["persist-credentials"] is False


def test_the_readme_says_how_to_get_and_start_the_windows_build():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    section = text.split("## Windows test build", 1)[1].split("\n## ", 1)[0]
    for needed in ("Actions", "Build Windows app", "Run workflow", "Artifacts", "AI-Browser-windows.zip",
                   "AI Browser.exe", "Windows protected your PC", "More info", "Run anyway", "Claude Code",
                   "brave://inspect/#remote-debugging", "Docker", "voice"):
        assert needed in section, needed
