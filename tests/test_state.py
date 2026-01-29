"""Tests for state module."""

import json
import pathlib

import pytest

import ghrel.state


def test_read_state_missing_file(tmp_path: pathlib.Path, monkeypatch) -> None:
    """read_state returns empty State when file doesn't exist."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    state = ghrel.state.read_state()
    assert state.packages == {}


def test_read_state_with_packages(tmp_path: pathlib.Path, monkeypatch) -> None:
    """read_state parses packages correctly."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    state_dpath = tmp_path / "ghrel"
    state_dpath.mkdir(parents=True)
    state_fpath = state_dpath / "state.json"
    state_fpath.write_text(
        json.dumps({
            "packages": {
                "fd": {
                    "version": "10.2.0",
                    "checksum": "sha256:abc123",
                    "installed_at": "2024-01-15T10:30:00Z",
                    "binary_path": "/home/user/.local/bin/fd",
                }
            }
        })
    )

    state = ghrel.state.read_state()
    assert "fd" in state.packages
    assert state.packages["fd"].version == "10.2.0"
    assert state.packages["fd"].checksum == "sha256:abc123"
    assert state.packages["fd"].binary_fpath == pathlib.Path("/home/user/.local/bin/fd")


def test_write_state_creates_file(tmp_path: pathlib.Path, monkeypatch) -> None:
    """write_state creates state file and directories."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    pkg = ghrel.state.PackageState(
        version="1.0.0",
        checksum="sha256:test",
        installed_at="2024-01-01T00:00:00Z",
        binary_fpath=pathlib.Path("/usr/local/bin/test"),
    )
    state = ghrel.state.State(packages={"test": pkg})
    ghrel.state.write_state(state)

    state_fpath = tmp_path / "ghrel" / "state.json"
    assert state_fpath.exists()

    data = json.loads(state_fpath.read_text())
    assert data["packages"]["test"]["version"] == "1.0.0"
    assert data["packages"]["test"]["binary_path"] == "/usr/local/bin/test"


def test_read_write_roundtrip(tmp_path: pathlib.Path, monkeypatch) -> None:
    """State survives read/write roundtrip."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    pkg = ghrel.state.PackageState(
        version="2.0.0",
        checksum="sha256:roundtrip",
        installed_at="2024-06-01T12:00:00Z",
        binary_fpath=pathlib.Path("/home/user/.local/bin/tool"),
    )
    original = ghrel.state.State(packages={"tool": pkg})
    ghrel.state.write_state(original)

    loaded = ghrel.state.read_state()
    assert loaded.packages["tool"].version == "2.0.0"
    assert loaded.packages["tool"].checksum == "sha256:roundtrip"
    assert loaded.packages["tool"].binary_fpath == pathlib.Path(
        "/home/user/.local/bin/tool"
    )


def test_acquire_lock_works(tmp_path: pathlib.Path, monkeypatch) -> None:
    """acquire_lock allows code to run inside context."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    executed = False
    with ghrel.state.acquire_lock():
        executed = True

    assert executed


def test_acquire_lock_fails_when_held(tmp_path: pathlib.Path, monkeypatch) -> None:
    """acquire_lock raises LockError if lock already held."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    with ghrel.state.acquire_lock():
        with pytest.raises(ghrel.state.LockError):
            with ghrel.state.acquire_lock():
                pass
