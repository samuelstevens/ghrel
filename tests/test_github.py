"""Tests for GitHub API response parsing."""

import pathlib

import ghrel.github
import ghrel.install
import ghrel.packages


def test_parse_release_uses_api_url_for_downloads() -> None:
    """Release assets use the API URL for authenticated downloads."""
    release = ghrel.github._parse_release({
        "tag_name": "v1",
        "assets": [
            {
                "name": "tool.tar.gz",
                "url": "https://api.github.com/repos/owner/repo/releases/assets/1",
                "browser_download_url": "https://github.com/owner/repo/releases/download/v1/tool.tar.gz",
            },
        ],
    })

    assert release.assets[0].name == "tool.tar.gz"
    assert (
        release.assets[0].api_url
        == "https://api.github.com/repos/owner/repo/releases/assets/1"
    )
    assert (
        release.assets[0].url
        == "https://github.com/owner/repo/releases/download/v1/tool.tar.gz"
    )


def test_parse_release_accepts_missing_browser_url() -> None:
    """GitHub's browser URL is display-only; the API URL is enough."""
    release = ghrel.github._parse_release({
        "tag_name": "v1",
        "assets": [
            {
                "name": "tool.tar.gz",
                "url": "https://api.github.com/repos/owner/repo/releases/assets/1",
            },
        ],
    })

    assert (
        release.assets[0].api_url
        == "https://api.github.com/repos/owner/repo/releases/assets/1"
    )
    assert (
        release.assets[0].url
        == "https://api.github.com/repos/owner/repo/releases/assets/1"
    )


def test_install_downloads_api_url_when_available(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """Private release assets need the GitHub API asset URL."""
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
        name="tool",
        url="https://github.com/owner/repo/releases/download/v1/tool",
        api_url="https://api.github.com/repos/owner/repo/releases/assets/1",
    )
    release = ghrel.github.Release(tag="v1", assets=(asset,))
    downloaded_urls: list[str] = []

    def fake_download_asset(
        self: ghrel.github.GitHubClient, url: str, dest_fpath: pathlib.Path
    ) -> None:
        downloaded_urls.append(url)
        dest_fpath.write_text("payload")

    monkeypatch.setattr(
        ghrel.github.GitHubClient, "download_asset", fake_download_asset
    )

    result = ghrel.install.install_release_asset(
        package,
        release,
        asset,
        binary_pattern=None,
        bin_dpath=tmp_path / "bin",
        client=ghrel.github.GitHubClient(token=None),
        temp_dpath=tmp_path / "tmp",
    )

    assert downloaded_urls == [
        "https://api.github.com/repos/owner/repo/releases/assets/1"
    ]
    assert result.package_state.binary_fpath.read_text() == "payload"
