"""Binary installation and checksums."""

import dataclasses
import datetime
import fnmatch
import hashlib
import os
import pathlib
import shutil
import tempfile

import beartype

import ghrel.archive
import ghrel.errors
import ghrel.github
import ghrel.packages
import ghrel.platform
import ghrel.state


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class InstallResult:
    """Result of an installation."""

    package_state: ghrel.state.PackageState
    extracted_dpath: pathlib.Path | None


@beartype.beartype
def get_bin_dpath() -> pathlib.Path:
    """Get the binary install directory path."""
    env_bin = os.environ.get("GHREL_BIN")
    if env_bin:
        return pathlib.Path(env_bin)
    return pathlib.Path.home() / ".local" / "bin"


@beartype.beartype
def compute_sha256(binary_fpath: pathlib.Path) -> str:
    """Compute SHA-256 checksum of a file."""
    hasher = hashlib.sha256()
    with binary_fpath.open("rb") as fd:
        while True:
            chunk = fd.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


@beartype.beartype
def select_asset(
    package: ghrel.packages.PackageConfig,
    release: ghrel.github.Release,
    os_name: str,
    arch: str,
) -> ghrel.github.ReleaseAsset:
    """Select a release asset based on package config and platform."""
    if package.asset:
        matches = _match_assets_by_pattern(release.assets, package.asset)
        return _require_single_match(matches, package.asset, package.pkg, release.tag)

    matches = _match_assets_by_platform(release.assets, os_name, arch)
    return _require_single_match(matches, None, package.pkg, release.tag)


@beartype.beartype
def install_release_asset(
    package: ghrel.packages.PackageConfig,
    release: ghrel.github.Release,
    asset: ghrel.github.ReleaseAsset,
    bin_dpath: pathlib.Path,
    client: ghrel.github.GitHubClient,
    temp_dpath: pathlib.Path | None = None,
) -> InstallResult:
    """Download, extract, and install a release asset."""
    bin_dpath.mkdir(parents=True, exist_ok=True)

    if temp_dpath is None:
        with tempfile.TemporaryDirectory(prefix="ghrel-") as temp_dpath_str:
            return install_release_asset(
                package,
                release,
                asset,
                bin_dpath,
                client,
                temp_dpath=pathlib.Path(temp_dpath_str),
            )

    assert temp_dpath is not None
    temp_dpath.mkdir(parents=True, exist_ok=True)
    asset_fpath = temp_dpath / asset.name
    client.download_asset(asset.url, asset_fpath)

    extracted_dpath: pathlib.Path | None = None
    source_fpath = asset_fpath
    if package.archive:
        extracted_dpath = temp_dpath / "extract"
        ghrel.archive.extract_archive(asset_fpath, extracted_dpath)
        source_fpath = _find_binary(extracted_dpath, package.binary, asset_fpath)

    install_as = get_install_as(package, asset)
    dest_fpath = bin_dpath / install_as
    checksum = _install_binary(source_fpath, dest_fpath)

    installed_at = _get_utc_now()
    package_state = ghrel.state.PackageState(
        version=release.tag,
        checksum=checksum,
        installed_at=installed_at,
        binary_fpath=dest_fpath,
    )

    return InstallResult(package_state=package_state, extracted_dpath=extracted_dpath)


@beartype.beartype
def _match_assets_by_pattern(
    assets: tuple[ghrel.github.ReleaseAsset, ...],
    pattern: str,
) -> tuple[ghrel.github.ReleaseAsset, ...]:
    """Match assets using a glob pattern."""
    return tuple(asset for asset in assets if fnmatch.fnmatch(asset.name, pattern))


@beartype.beartype
def _match_assets_by_platform(
    assets: tuple[ghrel.github.ReleaseAsset, ...],
    os_name: str,
    arch: str,
) -> tuple[ghrel.github.ReleaseAsset, ...]:
    """Match assets using OS and architecture hints."""
    os_keys = ghrel.platform.get_os_keys(os_name)
    arch_keys = ghrel.platform.get_arch_keys(arch)

    matches = []
    for asset in assets:
        name = asset.name.lower()
        if not _matches_any(name, os_keys):
            continue
        if not _matches_any(name, arch_keys):
            continue
        matches.append(asset)

    return tuple(matches)


@beartype.beartype
def _matches_any(name: str, keys: tuple[str, ...]) -> bool:
    """Return True if name contains any of the keys."""
    for key in keys:
        if key in name:
            return True
    return False


@beartype.beartype
def _require_single_match(
    matches: tuple[ghrel.github.ReleaseAsset, ...],
    pattern: str | None,
    pkg: str,
    version: str,
) -> ghrel.github.ReleaseAsset:
    """Ensure exactly one asset matched."""
    if not matches:
        if pattern:
            raise ghrel.errors.GhrelError(
                message=(f"No assets match pattern '{pattern}' for {pkg} {version}"),
                hint="Make the pattern less specific, or check the release assets.",
            )
        raise ghrel.errors.GhrelError(
            message=f"No assets match platform for {pkg} {version}",
            hint="Set an explicit asset pattern in the package file.",
        )

    if len(matches) > 1:
        names = ", ".join(asset.name for asset in matches)
        if pattern:
            message = f"Multiple assets match '{pattern}' for {pkg} {version}: {names}"
            raise ghrel.errors.GhrelError(
                message=message,
                hint="Make the pattern more specific.",
            )
        raise ghrel.errors.GhrelError(
            message=f"Multiple assets match platform for {pkg} {version}: {names}",
            hint="Set an explicit asset pattern in the package file.",
        )

    return matches[0]


@beartype.beartype
def _find_binary(
    extracted_dpath: pathlib.Path,
    binary: str | None,
    archive_fpath: pathlib.Path,
) -> pathlib.Path:
    """Locate the binary inside the extracted archive."""
    if binary is None:
        raise ghrel.errors.GhrelError(
            message=f"Missing binary for archive {archive_fpath}",
        )

    if "/" in binary or "\\" in binary:
        binary_fpath = extracted_dpath / pathlib.PurePosixPath(binary)
        if binary_fpath.exists():
            return binary_fpath
        entries = ghrel.archive.list_archive_entries(archive_fpath)
        entries_str = _format_archive_entries(entries)
        raise ghrel.errors.GhrelError(
            message=f"Binary '{binary}' not found in archive for {archive_fpath}",
            hint=entries_str,
        )

    root_candidate = extracted_dpath / binary
    if root_candidate.exists():
        return root_candidate

    matches = [match for match in extracted_dpath.rglob(binary) if match.is_file()]
    if not matches:
        entries = ghrel.archive.list_archive_entries(archive_fpath)
        entries_str = _format_archive_entries(entries)
        raise ghrel.errors.GhrelError(
            message=f"Binary '{binary}' not found in archive for {archive_fpath}",
            hint=entries_str,
        )

    if len(matches) > 1:
        matches_str = ", ".join(str(match) for match in matches)
        raise ghrel.errors.GhrelError(
            message=f"Binary '{binary}' matched multiple files: {matches_str}",
            hint="Use an explicit path for the binary in the package file.",
        )

    return matches[0]


@beartype.beartype
def _install_binary(source_fpath: pathlib.Path, dest_fpath: pathlib.Path) -> str:
    """Copy binary to destination using atomic rename, returning checksum."""
    dest_fpath.parent.mkdir(parents=True, exist_ok=True)
    tmp_fpath = dest_fpath.with_name(dest_fpath.name + ".tmp")

    shutil.copy(source_fpath, tmp_fpath)
    source_checksum = compute_sha256(source_fpath)
    tmp_checksum = compute_sha256(tmp_fpath)
    if source_checksum != tmp_checksum:
        raise ghrel.errors.GhrelError(
            message=f"Checksum mismatch copying {source_fpath} to {dest_fpath}",
        )

    os.chmod(tmp_fpath, 0o755)
    os.replace(tmp_fpath, dest_fpath)
    return source_checksum


@beartype.beartype
def get_install_as(
    package: ghrel.packages.PackageConfig,
    asset: ghrel.github.ReleaseAsset,
) -> str:
    """Determine installed binary name."""
    if package.install_as:
        return package.install_as
    if not package.archive:
        return pathlib.PurePosixPath(asset.name).name
    assert package.binary is not None
    return pathlib.PurePosixPath(package.binary).name


@beartype.beartype
def _get_utc_now() -> str:
    """Return current UTC timestamp in ISO 8601 format with Z suffix."""
    now = datetime.datetime.now(tz=datetime.UTC).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z")


@beartype.beartype
def _format_archive_entries(entries: tuple[str, ...]) -> str:
    """Format archive entries for error output."""
    if not entries:
        return "Archive contents: (empty)"
    lines = "\n  - ".join(entries)
    return f"Archive contents:\n  - {lines}"
