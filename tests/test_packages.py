"""Tests for packages module."""

import pathlib

import pytest

import ghrel.errors
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


def test_load_packages_defaults_binary_to_package_name(
    tmp_path: pathlib.Path,
) -> None:
    """load_packages defaults binary to package filename when missing."""
    packages_dpath = tmp_path / "packages"
    packages_dpath.mkdir()
    (packages_dpath / "tool.py").write_text("pkg = 'owner/repo'\n")

    packages = ghrel.packages.load_packages(packages_dpath)
    assert packages["tool"].binary == "tool"


def test_load_packages_archive_false_allows_missing_binary(
    tmp_path: pathlib.Path,
) -> None:
    """load_packages allows missing binary when archive is False."""
    packages_dpath = tmp_path / "packages"
    packages_dpath.mkdir()
    (packages_dpath / "tool.py").write_text("pkg = 'owner/repo'\narchive = False\n")

    packages = ghrel.packages.load_packages(packages_dpath)
    assert packages["tool"].binary is None


def test_load_packages_loads_ghrel_hooks(tmp_path: pathlib.Path) -> None:
    """load_packages loads ghrel_post_install and ghrel_verify hooks."""
    packages_dpath = tmp_path / "packages"
    packages_dpath.mkdir()
    (packages_dpath / "tool.py").write_text(
        "pkg = 'owner/repo'\n"
        "binary = 'tool'\n"
        "\n"
        "def ghrel_post_install(*, version, binary_name, binary_path, checksum, pkg, "
        "bin_dir, extracted_dir):\n"
        "    pass\n"
        "\n"
        "def ghrel_verify(*, version, binary_name, binary_path, checksum, pkg):\n"
        "    pass\n"
    )

    packages = ghrel.packages.load_packages(packages_dpath)
    config = packages["tool"]
    assert config.post_install is not None
    assert config.verify is not None
