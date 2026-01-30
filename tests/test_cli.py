"""Tests for CLI module."""

import io
import pathlib
import shutil
import tarfile

import pytest

import ghrel.cli
import ghrel.errors
import ghrel.github
import ghrel.install
import ghrel.packages
import ghrel.state


def test_run_prune_errors_on_missing_packages_dir(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """run_prune raises ConfigError if packages directory doesn't exist."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    cmd = ghrel.cli.Prune(dry_run=False, verbose=False)

    with pytest.raises(ghrel.errors.ConfigError, match="does not exist"):
        ghrel.cli.run_prune(cmd)


def test_run_prune_dry_run_with_no_orphans(tmp_path: pathlib.Path, monkeypatch) -> None:
    """run_prune dry-run reports no orphans when none exist."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    packages_dpath = tmp_path / "ghrel" / "packages"
    packages_dpath.mkdir(parents=True)

    cmd = ghrel.cli.Prune(dry_run=True, verbose=False)
    ghrel.cli.run_prune(cmd)  # Should not raise


def test_run_verify_calls_hook(tmp_path: pathlib.Path) -> None:
    """_run_verify calls ghrel_verify hook with expected args."""
    calls: dict[str, object] = {}

    def verify(
        *,
        version: str,
        binary_name: str,
        binary_path: pathlib.Path,
        checksum: str,
        pkg: str,
    ) -> None:
        calls["version"] = version
        calls["binary_name"] = binary_name
        calls["binary_path"] = binary_path
        calls["checksum"] = checksum
        calls["pkg"] = pkg

    package = ghrel.packages.PackageConfig(
        name="tool",
        pkg="owner/repo",
        binary="tool",
        install_as=None,
        asset=None,
        version=None,
        archive=True,
        post_install=None,
        verify=verify,
        package_fpath=tmp_path / "tool.py",
    )
    release = ghrel.github.Release(
        tag="v1",
        assets=(ghrel.github.ReleaseAsset(name="tool.tar.gz", url="https://e"),),
    )
    plan = ghrel.cli.PackagePlan(
        name="tool",
        package=package,
        current_state=None,
        current_version=None,
        desired_version="v1",
        release=release,
        asset=release.assets[0],
        install_fpath=tmp_path / "bin" / "tool",
        action="install",
        reason=None,
    )
    package_state = ghrel.state.PackageState(
        version="v1",
        checksum="sha256:abc123",
        installed_at="2024-01-01T00:00:00Z",
        binary_fpath=plan.install_fpath,
    )
    install_result = ghrel.install.InstallResult(
        package_state=package_state,
        extracted_dpath=None,
    )

    err = ghrel.cli._run_verify(package, plan, install_result)
    assert err is None
    assert calls["version"] == "v1"
    assert calls["binary_name"] == "tool"
    assert calls["binary_path"] == plan.install_fpath
    assert calls["checksum"] == "sha256:abc123"
    assert calls["pkg"] == "owner/repo"


def test_run_sync_post_install_sees_extracted_dir(
    tmp_path: pathlib.Path, monkeypatch, capsys
) -> None:
    """run_sync keeps extracted_dir for post_install and cleans before verify."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("GHREL_BIN", str(tmp_path / "bin"))
    monkeypatch.setenv("GHREL_NO_TOKEN_WARNING", "1")

    packages_dpath = tmp_path / "ghrel" / "packages"
    packages_dpath.mkdir(parents=True)
    (packages_dpath / "tool.py").write_text(
        "import pathlib\n"
        "pkg = 'owner/repo'\n"
        "binary = 'tool'\n"
        "asset = 'tool.tar.gz'\n"
        "EXTRACTED_DIR = None\n"
        "\n"
        "def ghrel_post_install(*, version, binary_name, binary_path, checksum, pkg, "
        "bin_dir, extracted_dir):\n"
        "    global EXTRACTED_DIR\n"
        "    EXTRACTED_DIR = extracted_dir\n"
        "    assert extracted_dir is not None\n"
        "    assert extracted_dir.exists()\n"
        "\n"
        "def ghrel_verify(*, version, binary_name, binary_path, checksum, pkg):\n"
        "    assert EXTRACTED_DIR is not None\n"
        "    assert not EXTRACTED_DIR.exists()\n"
    )

    archive_fpath = tmp_path / "tool.tar.gz"
    with tarfile.open(archive_fpath, "w:gz") as tar:
        payload = b"binary"
        info = tarfile.TarInfo("tool")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))

    release = ghrel.github.Release(
        tag="v1",
        assets=(ghrel.github.ReleaseAsset(name="tool.tar.gz", url="https://e"),),
    )

    def fake_get_latest_release(self, pkg: str) -> ghrel.github.Release:
        return release

    def fake_download_asset(self, url: str, dest_fpath: pathlib.Path) -> None:
        shutil.copy(archive_fpath, dest_fpath)

    monkeypatch.setattr(
        ghrel.github.GitHubClient, "get_latest_release", fake_get_latest_release
    )
    monkeypatch.setattr(
        ghrel.github.GitHubClient, "download_asset", fake_download_asset
    )

    cmd = ghrel.cli.Sync(packages_dpath=packages_dpath, dry_run=False, verbose=False)
    ghrel.cli.run_sync(cmd)
    output = capsys.readouterr().out
    assert "post_install failed" not in output
    assert "verify failed" not in output
