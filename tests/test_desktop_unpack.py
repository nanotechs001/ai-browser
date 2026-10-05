"""Electron's zip unpacked with its links and executable bits (desktop/unpack.py), and its Node fuses turned off
(desktop/fuses.py), on miniature zips with Electron's own layout (tests/fake_electron_zip.py)."""

import io
import os
import stat
import zipfile

import pytest

from fake_electron_zip import FRAMEWORK, WIRE, add_file, add_link, mac_zip, windows_zip


def zipped(tmp_path, data: bytes, name: str = "electron.zip"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.mark.posix_only  # links, and executable bits
def test_links_and_executable_bits_come_out_as_they_went_in(tmp_path):
    from ai_browser.desktop.unpack import unpack

    unpack(zipped(tmp_path, mac_zip()), tmp_path / "out")
    app, framework = tmp_path / "out" / "Electron.app", tmp_path / "out" / FRAMEWORK
    assert os.readlink(framework / "Versions" / "Current") == "A"
    assert os.readlink(framework / "Electron Framework") == "Versions/Current/Electron Framework"
    assert (framework / "Electron Framework").read_bytes().startswith(b"\x00framework\x00")  # through the links
    assert os.access(app / "Contents" / "MacOS" / "Electron", os.X_OK)
    assert not os.access(app / "Contents" / "Info.plist", os.X_OK)


def test_the_windows_zip_comes_out_as_files(tmp_path):
    from ai_browser.desktop.unpack import unpack

    unpack(zipped(tmp_path, windows_zip()), tmp_path / "out")
    assert (tmp_path / "out" / "electron.exe").read_bytes().count(WIRE) == 1
    assert (tmp_path / "out" / "resources" / "default_app.asar").is_file()


@pytest.mark.posix_only
def test_nothing_lands_outside_the_folder(tmp_path):
    from ai_browser.desktop.unpack import UnpackError, unpack

    for name, kind, entry, value in (("dots", "file", "../outside.txt", b"x"),
                                     ("link-out", "link", "evil", "../.."),
                                     ("absolute-link", "link", "evil", "/etc")):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            (add_file if kind == "file" else add_link)(archive, entry, value)
        with pytest.raises(UnpackError):
            unpack(zipped(tmp_path, buffer.getvalue(), f"{name}.zip"), tmp_path / name)
    assert not (tmp_path / "outside.txt").exists()


def test_a_broken_zip_and_a_folder_already_there_are_refused(tmp_path):
    from ai_browser.desktop.unpack import UnpackError, unpack

    with pytest.raises(UnpackError, match="^Electron's zip can't be read$"):
        unpack(zipped(tmp_path, b"not a zip"), tmp_path / "out")
    with pytest.raises(FileExistsError):
        unpack(zipped(tmp_path, windows_zip(), "again.zip"), tmp_path / "out")  # "out" is there from the first try


def test_the_node_fuses_go_off_and_the_rest_stay(tmp_path):
    from ai_browser.desktop import fuses

    binary = tmp_path / "Electron Framework"
    binary.write_bytes(b"\x00head\x00" + WIRE + b"\x00tail")
    binary.chmod(0o755)
    assert fuses.states(binary) == ["101100011"]  # as Electron ships it
    fuses.lock_down(binary)
    assert fuses.states(binary) == ["000000011"]  # runAsNode, nodeOptions and nodeCliInspect off
    fuses.lock_down(binary)  # again: nothing changes
    assert fuses.states(binary) == ["000000011"]
    data = binary.read_bytes()
    assert data.startswith(b"\x00head\x00") and data.endswith(b"\x00tail")
    if os.name != "nt":
        assert stat.S_IMODE(binary.stat().st_mode) == 0o755


def test_a_removed_fuse_stays_removed_and_two_wires_both_go_off(tmp_path):
    from ai_browser.desktop import fuses

    binary = tmp_path / "universal"
    removed = WIRE[:-9] + b"r01100011"  # runAsNode removed from this build
    binary.write_bytes(WIRE + b"\x00between\x00" + removed)
    fuses.lock_down(binary)
    assert fuses.states(binary) == ["000000011", "r00000011"]


def test_fuses_that_cant_be_read_stop_everything_and_change_nothing(tmp_path):
    from ai_browser.desktop import fuses

    sentinel = fuses.SENTINEL
    for data, said in ((b"no fuses here", "no fuses"),
                       (sentinel + bytes([2, 9]) + b"101100011", "doesn't know"),  # a newer wire version
                       (sentinel + bytes([1, 3]) + b"101", "doesn't know"),  # too short for nodeCliInspect
                       (sentinel + bytes([1, 9]) + b"10110x011", "doesn't know"),  # not a fuse state
                       (sentinel + bytes([1, 9]) + b"1011", "doesn't know"),  # cut off
                       (b"", "no fuses")):  # an empty file
        binary = tmp_path / "binary"
        binary.write_bytes(data)
        with pytest.raises(fuses.FuseError, match=said):
            fuses.lock_down(binary)
        assert binary.read_bytes() == data
