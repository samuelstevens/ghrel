"""Tests for install helpers."""

import hashlib
import pathlib
import tempfile

import hypothesis
import hypothesis.strategies as st
import pytest

import ghrel.errors
import ghrel.github
import ghrel.install
import ghrel.packages


@hypothesis.given(data=st.binary(min_size=0, max_size=2048))
def test_compute_sha256_matches_hashlib(data: bytes) -> None:
    """compute_sha256 matches hashlib output."""
    with tempfile.TemporaryDirectory() as temp_dpath_str:
        temp_dpath = pathlib.Path(temp_dpath_str)
        binary_fpath = temp_dpath / "bin"
        binary_fpath.write_bytes(data)

        expected = "sha256:" + hashlib.sha256(data).hexdigest()
        assert ghrel.install.compute_sha256(binary_fpath) == expected


def test_get_install_as_prefers_install_as(tmp_path: pathlib.Path) -> None:
    """get_install_as prefers explicit install_as."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary="tool",
        install_as="tool2",
        asset=None,
        version=None,
        archive=True,
        pre_install=None,
        post_install=None,
        package_fpath=tmp_path / "tool.py",
    )
    asset = ghrel.github.ReleaseAsset(name="tool.tar.gz", url="https://example.com")
    assert ghrel.install.get_install_as(package, asset) == "tool2"


def test_get_install_as_uses_binary_basename(tmp_path: pathlib.Path) -> None:
    """get_install_as uses binary basename when install_as missing."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary="bin/tool",
        install_as=None,
        asset=None,
        version=None,
        archive=True,
        pre_install=None,
        post_install=None,
        package_fpath=tmp_path / "tool.py",
    )
    asset = ghrel.github.ReleaseAsset(name="tool.tar.gz", url="https://example.com")
    assert ghrel.install.get_install_as(package, asset) == "tool"


def test_get_install_as_archive_false_uses_asset_name(tmp_path: pathlib.Path) -> None:
    """get_install_as ignores binary when archive is False."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary="ignored",
        install_as=None,
        asset=None,
        version=None,
        archive=False,
        pre_install=None,
        post_install=None,
        package_fpath=tmp_path / "tool.py",
    )
    asset = ghrel.github.ReleaseAsset(
        name="tool-linux-amd64", url="https://example.com"
    )
    assert ghrel.install.get_install_as(package, asset) == "tool-linux-amd64"


def test_select_asset_pattern(tmp_path: pathlib.Path) -> None:
    """select_asset uses explicit pattern."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary="tool",
        install_as=None,
        asset="*linux*",
        version=None,
        archive=True,
        pre_install=None,
        post_install=None,
        package_fpath=tmp_path / "tool.py",
    )
    assets = (
        ghrel.github.ReleaseAsset(name="tool-linux.tar.gz", url="a"),
        ghrel.github.ReleaseAsset(name="tool-darwin.tar.gz", url="b"),
    )
    release = ghrel.github.Release(tag="v1", assets=assets)
    selected = ghrel.install.select_asset(package, release, "linux", "x86_64")
    assert selected.name == "tool-linux.tar.gz"


def test_select_asset_pattern_ambiguous(tmp_path: pathlib.Path) -> None:
    """select_asset fails on ambiguous pattern."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary="tool",
        install_as=None,
        asset="*linux*",
        version=None,
        archive=True,
        pre_install=None,
        post_install=None,
        package_fpath=tmp_path / "tool.py",
    )
    assets = (
        ghrel.github.ReleaseAsset(name="tool-linux-amd64.tar.gz", url="a"),
        ghrel.github.ReleaseAsset(name="tool-linux-arm64.tar.gz", url="b"),
    )
    release = ghrel.github.Release(tag="v1", assets=assets)
    with pytest.raises(ghrel.errors.GhrelError, match="Multiple assets match"):
        ghrel.install.select_asset(package, release, "linux", "x86_64")


def test_select_asset_platform(tmp_path: pathlib.Path) -> None:
    """select_asset matches by platform when no pattern provided."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary="tool",
        install_as=None,
        asset=None,
        version=None,
        archive=True,
        pre_install=None,
        post_install=None,
        package_fpath=tmp_path / "tool.py",
    )
    assets = (
        ghrel.github.ReleaseAsset(name="tool-linux-amd64.tar.gz", url="a"),
        ghrel.github.ReleaseAsset(name="tool-linux-arm64.tar.gz", url="b"),
        ghrel.github.ReleaseAsset(name="tool-darwin-arm64.tar.gz", url="c"),
    )
    release = ghrel.github.Release(tag="v1", assets=assets)
    selected = ghrel.install.select_asset(package, release, "linux", "x86_64")
    assert selected.name == "tool-linux-amd64.tar.gz"
