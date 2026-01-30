"""GitHub API client for fetching releases."""

import dataclasses
import json
import pathlib
import time
import typing as tp

import beartype
import requests

import ghrel.errors

_API_BASE = "https://api.github.com"


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class ReleaseAsset:
    """Release asset metadata."""

    name: str
    url: str


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class Release:
    """GitHub release metadata."""

    tag: str
    assets: tuple[ReleaseAsset, ...]


class GitHubClient:
    """GitHub API client with basic caching and retries."""

    def __init__(self, token: str | None) -> None:
        self._token = token
        self._session = requests.Session()
        self._release_cache: dict[tuple[str, str], Release] = {}
        self._tags_cache: dict[str, tuple[str, ...]] = {}

    @beartype.beartype
    def get_latest_release(self, pkg: str) -> Release:
        """Fetch latest non-prerelease, non-draft release."""
        cache_key = (pkg, "latest")
        cached = self._release_cache.get(cache_key)
        if cached is not None:
            return cached

        owner, repo = _split_pkg(pkg)
        url = f"{_API_BASE}/repos/{owner}/{repo}/releases/latest"
        data = self._request_json(url)
        if not isinstance(data, dict):
            raise ghrel.errors.GhrelError(
                message=f"Unexpected response from GitHub for {pkg} latest release",
            )
        release = _parse_release(data)
        self._release_cache[cache_key] = release
        return release

    @beartype.beartype
    def get_release_by_tag(self, pkg: str, tag: str) -> Release:
        """Fetch release with the given tag."""
        cache_key = (pkg, tag)
        cached = self._release_cache.get(cache_key)
        if cached is not None:
            return cached

        owner, repo = _split_pkg(pkg)
        url = f"{_API_BASE}/repos/{owner}/{repo}/releases/tags/{tag}"
        try:
            data = self._request_json(url)
        except ghrel.errors.NotFoundError:
            recent = self.get_recent_tags(pkg)
            tags_str = ", ".join(recent) if recent else "(none)"
            raise ghrel.errors.GhrelError(
                message=f"Version '{tag}' not found for {pkg}",
                hint=f"Available tags: {tags_str}",
            ) from None

        if not isinstance(data, dict):
            raise ghrel.errors.GhrelError(
                message=f"Unexpected response from GitHub for {pkg} {tag} release",
            )
        release = _parse_release(data)
        self._release_cache[cache_key] = release
        return release

    @beartype.beartype
    def get_recent_tags(self, pkg: str, limit: int = 10) -> tuple[str, ...]:
        """Fetch recent release tags for a repo."""
        cached = self._tags_cache.get(pkg)
        if cached is not None:
            return cached

        owner, repo = _split_pkg(pkg)
        url = f"{_API_BASE}/repos/{owner}/{repo}/releases"
        data = self._request_json(url, params={"per_page": str(limit)})
        if not isinstance(data, list):
            raise ghrel.errors.GhrelError(
                message=f"Unexpected response from GitHub for {pkg} tags",
            )
        tags = []
        for item in data:
            if not isinstance(item, dict):
                continue
            item_data = tp.cast(dict[str, object], item)
            tag = item_data.get("tag_name")
            if not isinstance(tag, str):
                continue
            tags.append(tag)
        tags_tuple = tuple(tags)
        self._tags_cache[pkg] = tags_tuple
        return tags_tuple

    @beartype.beartype
    def download_asset(self, url: str, dest_fpath: pathlib.Path) -> None:
        """Download a release asset to dest_fpath."""
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        headers["Accept"] = "application/octet-stream"

        response = self._request_raw(url, headers=headers, stream=True)
        dest_fpath.parent.mkdir(parents=True, exist_ok=True)
        with dest_fpath.open("wb") as fd:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                fd.write(chunk)

    @beartype.beartype
    def _request_json(
        self, url: str, params: dict[str, str] | None = None
    ) -> dict[str, object] | list[object]:
        """GET JSON with retries and error handling."""
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        response = self._request_raw(url, headers=headers, params=params, stream=False)
        try:
            return response.json()
        except json.JSONDecodeError as err:
            raise ghrel.errors.GhrelError(
                message=f"Invalid JSON response from GitHub: {err}",
            ) from None

    @beartype.beartype
    def _request_raw(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        stream: bool,
    ) -> requests.Response:
        """Perform a request with retries and handle GitHub errors."""
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                response = self._session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=30,
                    stream=stream,
                )
            except requests.RequestException as err:
                last_err = err
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise ghrel.errors.GhrelError(
                    message=f"Network error contacting GitHub: {err}",
                ) from None

            if response.status_code == 404:
                raise ghrel.errors.NotFoundError(
                    message=f"Resource not found: {url}",
                )

            if response.status_code in {401, 403}:
                if self._token:
                    raise ghrel.errors.AuthError()
                raise ghrel.errors.GhrelError(
                    message="GitHub API rate limit exceeded.",
                    hint="Set GITHUB_TOKEN to increase the limit.",
                )

            if response.status_code >= 400:
                raise ghrel.errors.GhrelError(
                    message=f"GitHub API error ({response.status_code}) for {url}",
                )

            return response

        assert last_err is not None
        raise ghrel.errors.GhrelError(
            message=f"Network error contacting GitHub: {last_err}",
        ) from None


@beartype.beartype
def _parse_release(data: dict[str, object]) -> Release:
    """Parse release JSON into a Release object."""
    tag = data.get("tag_name")
    if not isinstance(tag, str) or not tag:
        raise ghrel.errors.GhrelError(
            message="Release JSON missing tag_name",
        )

    assets_data = data.get("assets")
    if not isinstance(assets_data, list):
        raise ghrel.errors.GhrelError(
            message="Release JSON missing assets",
        )

    assets = []
    for asset in assets_data:
        if not isinstance(asset, dict):
            continue
        asset_data = tp.cast(dict[str, object], asset)
        name = asset_data.get("name")
        url = asset_data.get("browser_download_url")
        if not isinstance(name, str) or not isinstance(url, str):
            continue
        assets.append(ReleaseAsset(name=name, url=url))

    return Release(tag=tag, assets=tuple(assets))


@beartype.beartype
def _split_pkg(pkg: str) -> tuple[str, str]:
    """Split owner/repo string."""
    if "/" not in pkg:
        raise ghrel.errors.GhrelError(
            message=f"Invalid pkg '{pkg}'",
            hint="Expected format 'owner/repo'.",
        )
    owner, repo = pkg.split("/", maxsplit=1)
    if not owner or not repo:
        raise ghrel.errors.GhrelError(
            message=f"Invalid pkg '{pkg}'",
            hint="Expected format 'owner/repo'.",
        )
    return owner, repo
