"""Tests for install helpers."""

import hashlib
import pathlib
import tarfile
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
        binary={},
        install_as="tool2",
        asset={},
        version=None,
        archive=True,
        post_install=None,
        verify=None,
        package_fpath=tmp_path / "tool.py",
    )
    asset = ghrel.github.ReleaseAsset(name="tool.tar.gz", url="https://example.com")
    assert ghrel.install.get_install_as(package, asset) == "tool2"


def test_get_install_as_defaults_to_package_name(tmp_path: pathlib.Path) -> None:
    """get_install_as defaults to package name when install_as missing."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary={"linux-x86_64": "bin/tool"},
        install_as=None,
        asset={},
        version=None,
        archive=True,
        post_install=None,
        verify=None,
        package_fpath=tmp_path / "tool.py",
    )
    asset = ghrel.github.ReleaseAsset(name="tool.tar.gz", url="https://example.com")
    assert ghrel.install.get_install_as(package, asset) == "tool"


def test_get_install_as_archive_false_defaults_to_package_name(
    tmp_path: pathlib.Path,
) -> None:
    """get_install_as ignores binary when archive is False."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary={},
        install_as=None,
        asset={},
        version=None,
        archive=False,
        post_install=None,
        verify=None,
        package_fpath=tmp_path / "tool.py",
    )
    asset = ghrel.github.ReleaseAsset(
        name="tool-linux-amd64", url="https://example.com"
    )
    assert ghrel.install.get_install_as(package, asset) == "tool"


def test_select_asset_pattern(tmp_path: pathlib.Path) -> None:
    """select_asset uses explicit pattern."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary={},
        install_as=None,
        asset={"linux-x86_64": "*linux*"},
        version=None,
        archive=True,
        post_install=None,
        verify=None,
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
        binary={},
        install_as=None,
        asset={"linux-x86_64": "*linux*"},
        version=None,
        archive=True,
        post_install=None,
        verify=None,
        package_fpath=tmp_path / "tool.py",
    )
    assets = (
        ghrel.github.ReleaseAsset(name="tool-linux-amd64.tar.gz", url="a"),
        ghrel.github.ReleaseAsset(name="tool-linux-arm64.tar.gz", url="b"),
    )
    release = ghrel.github.Release(tag="v1", assets=assets)
    with pytest.raises(ghrel.errors.GhrelError) as err:
        ghrel.install.select_asset(package, release, "linux", "x86_64")
    err_str = str(err.value)
    assert "Multiple assets match '*linux*' for owner/repo v1:" in err_str
    assert "  - tool-linux-amd64.tar.gz" in err_str
    assert "  - tool-linux-arm64.tar.gz" in err_str


def test_select_asset_dict_pattern_single_asset(tmp_path: pathlib.Path) -> None:
    """select_asset uses dict pattern for a single match."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary={},
        install_as=None,
        asset={"linux-x86_64": "*"},
        version=None,
        archive=True,
        post_install=None,
        verify=None,
        package_fpath=tmp_path / "tool.py",
    )
    assets = (ghrel.github.ReleaseAsset(name="tool-any.tar.gz", url="a"),)
    release = ghrel.github.Release(tag="v1", assets=assets)
    selected = ghrel.install.select_asset(package, release, "linux", "x86_64")
    assert selected.name == "tool-any.tar.gz"


def test_select_asset_dict_pattern_ambiguous(tmp_path: pathlib.Path) -> None:
    """select_asset fails when dict pattern matches multiple assets."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary={},
        install_as=None,
        asset={"linux-x86_64": "*"},
        version=None,
        archive=True,
        post_install=None,
        verify=None,
        package_fpath=tmp_path / "tool.py",
    )
    assets = (
        ghrel.github.ReleaseAsset(name="tool-linux-amd64.tar.gz", url="a"),
        ghrel.github.ReleaseAsset(name="tool-linux-arm64.tar.gz", url="b"),
    )
    release = ghrel.github.Release(tag="v1", assets=assets)
    with pytest.raises(ghrel.errors.GhrelError) as err:
        ghrel.install.select_asset(package, release, "linux", "x86_64")
    err_str = str(err.value)
    assert "Multiple assets match '*' for owner/repo v1:" in err_str
    assert "  - tool-linux-amd64.tar.gz" in err_str
    assert "  - tool-linux-arm64.tar.gz" in err_str


def test_select_asset_dict_uses_platform_key(tmp_path: pathlib.Path) -> None:
    """select_asset uses platform key to resolve asset dict."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary={},
        install_as=None,
        asset={
            "linux-x86_64": "*linux-amd64.tar.gz",
            "linux-arm64": "*linux-arm64.tar.gz",
        },
        version=None,
        archive=True,
        post_install=None,
        verify=None,
        package_fpath=tmp_path / "tool.py",
    )
    assets = (
        ghrel.github.ReleaseAsset(name="tool-linux-amd64.tar.gz", url="a"),
        ghrel.github.ReleaseAsset(name="tool-linux-arm64.tar.gz", url="b"),
    )
    release = ghrel.github.Release(tag="v1", assets=assets)
    selected = ghrel.install.select_asset(package, release, "linux", "x86_64")
    assert selected.name == "tool-linux-amd64.tar.gz"


def test_select_asset_dict_missing_platform_key(tmp_path: pathlib.Path) -> None:
    """select_asset fails with closest matches when key missing."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary={},
        install_as=None,
        asset={
            "darwin-arm64": "*darwin-arm64.tar.gz",
            "darwin-x86_64": "*darwin-x86_64.tar.gz",
        },
        version=None,
        archive=True,
        post_install=None,
        verify=None,
        package_fpath=tmp_path / "tool.py",
    )
    assets = (
        ghrel.github.ReleaseAsset(name="tool-linux-amd64.tar.gz", url="a"),
        ghrel.github.ReleaseAsset(name="tool-linux-arm64.tar.gz", url="b"),
    )
    release = ghrel.github.Release(tag="v1", assets=assets)
    with pytest.raises(ghrel.errors.GhrelError) as err:
        ghrel.install.select_asset(package, release, "linux", "x86_64")
    err_str = str(err.value)
    assert "Platform 'linux-x86_64' not found in asset dict" in err_str
    assert "Closest matches" in err_str
    assert "Add a 'linux-x86_64' key" in err_str


def test_select_asset_dict_empty(tmp_path: pathlib.Path) -> None:
    """select_asset fails when asset dict is empty."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary={},
        install_as=None,
        asset={},
        version=None,
        archive=True,
        post_install=None,
        verify=None,
        package_fpath=tmp_path / "tool.py",
    )
    assets = (ghrel.github.ReleaseAsset(name="tool-linux-amd64.tar.gz", url="a"),)
    release = ghrel.github.Release(tag="v1", assets=assets)
    with pytest.raises(ghrel.errors.GhrelError) as err:
        ghrel.install.select_asset(package, release, "linux", "x86_64")
    err_str = str(err.value)
    assert "Platform 'linux-x86_64' not found in empty asset dict" in err_str


def test_get_binary_pattern_resolves_platform_key(tmp_path: pathlib.Path) -> None:
    """get_binary_pattern resolves binary dict for current platform."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary={
            "linux-x86_64": "bin/tool",
            "linux-arm64": "bin/tool-arm",
        },
        install_as=None,
        asset={},
        version=None,
        archive=True,
        post_install=None,
        verify=None,
        package_fpath=tmp_path / "tool.py",
    )
    pattern = ghrel.install.get_binary_pattern(package, "linux", "x86_64")
    assert pattern == "bin/tool"


def test_get_binary_pattern_missing_platform_key(tmp_path: pathlib.Path) -> None:
    """get_binary_pattern fails when binary dict missing platform key."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary={"darwin-x86_64": "bin/tool"},
        install_as=None,
        asset={},
        version=None,
        archive=True,
        post_install=None,
        verify=None,
        package_fpath=tmp_path / "tool.py",
    )
    with pytest.raises(ghrel.errors.GhrelError) as err:
        ghrel.install.get_binary_pattern(package, "linux", "x86_64")
    err_str = str(err.value)
    assert "Platform 'linux-x86_64' not found in binary dict" in err_str


def test_get_binary_pattern_archive_false_returns_none(
    tmp_path: pathlib.Path,
) -> None:
    """get_binary_pattern returns None for raw binaries."""
    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary={},
        install_as=None,
        asset={},
        version=None,
        archive=False,
        post_install=None,
        verify=None,
        package_fpath=tmp_path / "tool.py",
    )
    assert ghrel.install.get_binary_pattern(package, "linux", "x86_64") is None


def test_find_binary_error_includes_archive_contents_list_and_wildcard_hint(
    tmp_path: pathlib.Path,
) -> None:
    """_find_binary error includes archive contents list and wildcard suggestion."""
    extracted_dpath = tmp_path / "extracted"
    extracted_dpath.mkdir()
    (extracted_dpath / "alpha").write_text("nope")
    (extracted_dpath / "beta").write_text("nope")

    archive_fpath = tmp_path / "tool.tar.gz"
    with tarfile.open(archive_fpath, "w:gz") as tar:
        for name in ("alpha", "beta"):
            info = tarfile.TarInfo(name)
            info.size = 0
            tar.addfile(info)

    with pytest.raises(ghrel.errors.GhrelError) as err:
        ghrel.install._find_binary(extracted_dpath, "tool", archive_fpath)

    err_str = str(err.value)
    assert "Archive contents:" in err_str
    assert "  - alpha" in err_str
    assert "  - beta" in err_str
    assert "binary = {'linux-x86_64': '<dir>/tool'}" in err_str
    assert "wildcard" in err_str
    assert "*" in err_str


def test_find_binary_multiple_matches_list_format(tmp_path: pathlib.Path) -> None:
    """_find_binary lists multiple matches with bullets."""
    extracted_dpath = tmp_path / "extracted"
    extracted_dpath.mkdir()
    (extracted_dpath / "bin").mkdir()
    (extracted_dpath / "alt").mkdir()
    (extracted_dpath / "bin" / "tool").write_text("one")
    (extracted_dpath / "alt" / "tool").write_text("two")

    archive_fpath = tmp_path / "tool.tar.gz"
    with tarfile.open(archive_fpath, "w:gz") as tar:
        for name in ("bin/tool", "alt/tool"):
            info = tarfile.TarInfo(name)
            info.size = 0
            tar.addfile(info)

    with pytest.raises(ghrel.errors.GhrelError) as err:
        ghrel.install._find_binary(extracted_dpath, "tool", archive_fpath)

    err_str = str(err.value)
    assert "Binary 'tool' matched multiple files:" in err_str
    assert "\n  - " in err_str
    assert "bin/tool" in err_str
    assert "alt/tool" in err_str


def test_find_binary_wildcard_path_match(tmp_path: pathlib.Path) -> None:
    """_find_binary matches wildcard paths against full relative paths."""
    extracted_dpath = tmp_path / "extracted"
    extracted_dpath.mkdir()
    (extracted_dpath / "fd-v1.0.0-x86_64-unknown-linux-musl").mkdir()
    binary_fpath = extracted_dpath / "fd-v1.0.0-x86_64-unknown-linux-musl" / "fd"
    binary_fpath.write_text("bin")

    archive_fpath = tmp_path / "fd.tar.gz"
    with tarfile.open(archive_fpath, "w:gz") as tar:
        info = tarfile.TarInfo("fd-v1.0.0-x86_64-unknown-linux-musl/fd")
        info.size = 0
        tar.addfile(info)

    selected = ghrel.install._find_binary(
        extracted_dpath,
        "fd-*-x86_64-unknown-linux-musl/fd",
        archive_fpath,
    )
    assert selected == binary_fpath
