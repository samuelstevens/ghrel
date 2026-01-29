"""Tests for packages module."""

import pathlib

import ghrel.packages


def test_list_package_names_missing_dir(tmp_path: pathlib.Path) -> None:
    """list_package_names returns empty set when directory doesn't exist."""
    names = ghrel.packages.list_package_names(tmp_path / "nonexistent")
    assert names == set()


def test_list_package_names_with_files(tmp_path: pathlib.Path) -> None:
    """list_package_names returns stems of .py files."""
    (tmp_path / "fd.py").write_text("pkg = 'sharkdp/fd'")
    (tmp_path / "ripgrep.py").write_text("pkg = 'BurntSushi/ripgrep'")
    (tmp_path / "readme.txt").write_text("not a package")

    names = ghrel.packages.list_package_names(tmp_path)
    assert names == {"fd", "ripgrep"}
