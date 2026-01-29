"""Tests for CLI module."""

import pathlib

import pytest

import ghrel.cli
import ghrel.packages


def test_run_prune_errors_on_missing_packages_dir(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """run_prune raises ConfigError if packages directory doesn't exist."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    cmd = ghrel.cli.Prune(dry_run=False, verbose=False)

    with pytest.raises(ghrel.cli.ConfigError, match="does not exist"):
        ghrel.cli.run_prune(cmd)


def test_run_prune_dry_run_with_no_orphans(tmp_path: pathlib.Path, monkeypatch) -> None:
    """run_prune dry-run reports no orphans when none exist."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    packages_dpath = tmp_path / "ghrel" / "packages"
    packages_dpath.mkdir(parents=True)

    cmd = ghrel.cli.Prune(dry_run=True, verbose=False)
    ghrel.cli.run_prune(cmd)  # Should not raise
