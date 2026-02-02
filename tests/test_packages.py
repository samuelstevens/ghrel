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


def test_load_packages_defaults_asset_and_binary_to_empty_dict(
    tmp_path: pathlib.Path,
) -> None:
    """load_packages defaults asset and binary to empty dicts."""
    packages_dpath = tmp_path / "packages"
    packages_dpath.mkdir()
    (packages_dpath / "tool.py").write_text("pkg = 'owner/repo'\n")

    packages = ghrel.packages.load_packages(packages_dpath)
    config = packages["tool"]
    assert config.asset == {}
    assert config.binary == {}


def test_load_packages_archive_false_allows_missing_binary(
    tmp_path: pathlib.Path,
) -> None:
    """load_packages allows missing binary when archive is False."""
    packages_dpath = tmp_path / "packages"
    packages_dpath.mkdir()
    (packages_dpath / "tool.py").write_text("pkg = 'owner/repo'\narchive = False\n")

    packages = ghrel.packages.load_packages(packages_dpath)
    config = packages["tool"]
    assert config.asset == {}
    assert config.binary == {}


def test_load_packages_loads_ghrel_hooks(tmp_path: pathlib.Path) -> None:
    """load_packages loads ghrel_post_install and ghrel_verify hooks."""
    packages_dpath = tmp_path / "packages"
    packages_dpath.mkdir()
    (packages_dpath / "tool.py").write_text(
        "pkg = 'owner/repo'\n"
        "binary = {'linux-x86_64': 'tool'}\n"
        "\n"
        "def ghrel_post_install(*, version, bin_name, bin_path, checksum, pkg, "
        "bin_dir, extracted_dir):\n"
        "    pass\n"
        "\n"
        "def ghrel_verify(*, version, bin_name):\n"
        "    pass\n"
    )

    packages = ghrel.packages.load_packages(packages_dpath)
    config = packages["tool"]
    assert config.post_install is not None
    assert config.verify is not None


def test_load_packages_accepts_asset_dict(tmp_path: pathlib.Path) -> None:
    """load_packages accepts asset dict values."""
    packages_dpath = tmp_path / "packages"
    packages_dpath.mkdir()
    (packages_dpath / "tool.py").write_text(
        "pkg = 'owner/repo'\nasset = {'linux-x86_64': '*linux*'}\n"
    )

    packages = ghrel.packages.load_packages(packages_dpath)
    asset = packages["tool"].asset
    assert isinstance(asset, dict)
    assert asset["linux-x86_64"] == "*linux*"


def test_load_packages_accepts_binary_dict(tmp_path: pathlib.Path) -> None:
    """load_packages accepts binary dict values."""
    packages_dpath = tmp_path / "packages"
    packages_dpath.mkdir()
    (packages_dpath / "tool.py").write_text(
        "pkg = 'owner/repo'\nbinary = {'linux-x86_64': 'tool'}\n"
    )

    packages = ghrel.packages.load_packages(packages_dpath)
    binary = packages["tool"].binary
    assert isinstance(binary, dict)
    assert binary["linux-x86_64"] == "tool"


def test_load_packages_rejects_asset_string(tmp_path: pathlib.Path) -> None:
    """load_packages rejects string asset values."""
    packages_dpath = tmp_path / "packages"
    packages_dpath.mkdir()
    (packages_dpath / "tool.py").write_text(
        "pkg = 'owner/repo'\nasset = 'tool.tar.gz'\n"
    )

    with pytest.raises(ghrel.errors.ConfigError, match="Invalid type for 'asset'"):
        ghrel.packages.load_packages(packages_dpath)


def test_load_packages_rejects_binary_string(tmp_path: pathlib.Path) -> None:
    """load_packages rejects string binary values."""
    packages_dpath = tmp_path / "packages"
    packages_dpath.mkdir()
    (packages_dpath / "tool.py").write_text("pkg = 'owner/repo'\nbinary = 'tool'\n")

    with pytest.raises(ghrel.errors.ConfigError, match="Invalid type for 'binary'"):
        ghrel.packages.load_packages(packages_dpath)


def test_load_packages_rejects_binary_dict_bad_value(
    tmp_path: pathlib.Path,
) -> None:
    """load_packages rejects empty binary dict values."""
    packages_dpath = tmp_path / "packages"
    packages_dpath.mkdir()
    (packages_dpath / "tool.py").write_text(
        "pkg = 'owner/repo'\nbinary = {'linux-x86_64': ''}\n"
    )

    with pytest.raises(ghrel.errors.ConfigError, match="Invalid value for 'binary'"):
        ghrel.packages.load_packages(packages_dpath)


def test_load_packages_rejects_binary_dict_bad_key(
    tmp_path: pathlib.Path,
) -> None:
    """load_packages rejects non-string binary dict keys."""
    packages_dpath = tmp_path / "packages"
    packages_dpath.mkdir()
    (packages_dpath / "tool.py").write_text(
        "pkg = 'owner/repo'\nbinary = {1: 'tool'}\n"
    )

    with pytest.raises(ghrel.errors.ConfigError, match="Invalid key for 'binary'"):
        ghrel.packages.load_packages(packages_dpath)


def test_load_packages_rejects_asset_dict_bad_value(
    tmp_path: pathlib.Path,
) -> None:
    """load_packages rejects empty asset dict values."""
    packages_dpath = tmp_path / "packages"
    packages_dpath.mkdir()
    (packages_dpath / "tool.py").write_text(
        "pkg = 'owner/repo'\nasset = {'linux-x86_64': ''}\n"
    )

    with pytest.raises(ghrel.errors.ConfigError, match="Invalid value for 'asset'"):
        ghrel.packages.load_packages(packages_dpath)


def test_load_packages_rejects_asset_dict_bad_key(
    tmp_path: pathlib.Path,
) -> None:
    """load_packages rejects non-string asset dict keys."""
    packages_dpath = tmp_path / "packages"
    packages_dpath.mkdir()
    (packages_dpath / "tool.py").write_text(
        "pkg = 'owner/repo'\nasset = {1: '*linux*'}\n"
    )

    with pytest.raises(ghrel.errors.ConfigError, match="Invalid key for 'asset'"):
        ghrel.packages.load_packages(packages_dpath)
