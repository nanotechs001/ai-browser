"""The Windows test build (packaging/): its helper builds AI Browser's own app beside AI Browser.exe with the project's
own download and assemble code, then zips the package. The Electron release is a miniature
(tests/fake_electron_zip.py): no test downloads Electron, and no test runs PyInstaller."""

import importlib.util
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

