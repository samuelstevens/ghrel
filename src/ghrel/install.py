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
    platform_key = ghrel.platform.get_platform_key(os_name, arch)
    pattern = _get_platform_pattern(
        package.asset, platform_key, "asset", package.package_fpath
    )
    return _select_asset_by_pattern(release, package, pattern)


@beartype.beartype
def get_binary_pattern(
    package: ghrel.packages.PackageConfig,
    os_name: str,
    arch: str,
) -> str | None:
    """Return the binary pattern for the current platform."""
    if not package.archive:
        return None

    platform_key = ghrel.platform.get_platform_key(os_name, arch)
    return _get_platform_pattern(
        package.binary, platform_key, "binary", package.package_fpath
    )


@beartype.beartype
def _select_asset_by_pattern(
    release: ghrel.github.Release,
    package: ghrel.packages.PackageConfig,
    pattern: str,
) -> ghrel.github.ReleaseAsset:
    """Select a release asset using a glob pattern."""
    matches = _match_assets_by_pattern(release.assets, pattern)
    return _require_single_match(matches, pattern, package.pkg, release.tag)


@beartype.beartype
def install_release_asset(
    package: ghrel.packages.PackageConfig,
    release: ghrel.github.Release,
    asset: ghrel.github.ReleaseAsset,
    binary_pattern: str | None,
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
                binary_pattern,
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
        if binary_pattern is None:
            raise ghrel.errors.GhrelError(
                message=f"Missing binary pattern for archive {asset_fpath}",
            )
        source_fpath = _find_binary(extracted_dpath, binary_pattern, asset_fpath)

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
def _get_platform_pattern(
    value: dict[str, str],
    platform_key: str,
    name: str,
    package_fpath: pathlib.Path,
) -> str:
    """Fetch a platform-specific pattern from a dict."""
    if not value:
        lines = [
            f"Platform '{platform_key}' not found in empty {name} dict",
            "",
            f"In {package_fpath}:",
        ]
        for line in _format_dict_block(name, value):
            lines.append(f"  {line}")
        raise ghrel.errors.GhrelError(
            message="\n".join(lines),
            hint=(
                f"Add a '{platform_key}' key with a wildcard match, "
                f"like {{'{platform_key}': '*'}}. Because '*' can match multiple "
                f"assets, run sync again and pick a more specific pattern if "
                f"you get a multiple-assets error."
            ),
        )

    if platform_key in value:
        return value[platform_key]

    closest = _get_closest_matches(platform_key, tuple(value))
    closest_str = ", ".join(closest) if closest else "(none)"

    lines = [
        f"Platform '{platform_key}' not found in {name} dict",
        "",
        f"In {package_fpath}:",
    ]
    for line in _format_dict_block(name, value):
        lines.append(f"  {line}")
    lines.append("")
    lines.append(f"Closest matches: {closest_str}")

    raise ghrel.errors.GhrelError(
        message="\n".join(lines),
        hint=f"Add a '{platform_key}' key to the {name} dict.",
    )


@beartype.beartype
def _format_dict_block(name: str, value: dict[str, str]) -> tuple[str, ...]:
    """Format a dict block for error messages."""
    if not value:
        return (f"{name} = {{}}",)

    lines = [f"{name} = {{"]
    for key in sorted(value):
        lines.append(f"    {key!r}: {value[key]!r},")
    lines.append("}")
    return tuple(lines)


@beartype.beartype
def _get_closest_matches(
    target: str, keys: tuple[str, ...], limit: int = 2
) -> tuple[str, ...]:
    """Return the closest matches by edit distance."""
    if not keys:
        return ()

    scored = sorted(
        ((_levenshtein(target, key), key) for key in keys),
        key=lambda item: (item[0], item[1]),
    )
    return tuple(key for _, key in scored[:limit])


@beartype.beartype
def _levenshtein(left: str, right: str) -> int:
    """Compute Levenshtein edit distance."""
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (left_char != right_char)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


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
        names = _format_asset_matches(matches)
        if pattern:
            message = f"Multiple assets match '{pattern}' for {pkg} {version}:\n{names}"
            raise ghrel.errors.GhrelError(
                message=message,
                hint="Make the pattern more specific.",
            )
        raise ghrel.errors.GhrelError(
            message=f"Multiple assets match platform for {pkg} {version}:\n{names}",
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

    has_wildcard = "*" in binary or "?" in binary
    has_path = "/" in binary or "\\" in binary

    if has_wildcard:
        matches = _match_binary_patterns(
            extracted_dpath, binary, match_basename_only=not has_path
        )
        if not matches:
            entries = ghrel.archive.list_archive_entries(archive_fpath)
            raise ghrel.errors.GhrelError(
                message=f"Binary '{binary}' not found in archive for {archive_fpath}",
                hint=_make_binary_not_found_hint(binary, entries),
            )
        if len(matches) > 1:
            matches_str = _format_binary_matches(matches, extracted_dpath)
            raise ghrel.errors.GhrelError(
                message=f"Binary '{binary}' matched multiple files: {matches_str}",
                hint="Use an explicit path for the binary in the package file.",
            )
        return matches[0]

    if has_path:
        binary_fpath = extracted_dpath / pathlib.PurePosixPath(binary)
        if binary_fpath.exists():
            return binary_fpath
        entries = ghrel.archive.list_archive_entries(archive_fpath)
        raise ghrel.errors.GhrelError(
            message=f"Binary '{binary}' not found in archive for {archive_fpath}",
            hint=_make_binary_not_found_hint(binary, entries),
        )

    root_candidate = extracted_dpath / binary
    if root_candidate.exists():
        return root_candidate

    matches = [match for match in extracted_dpath.rglob(binary) if match.is_file()]
    if not matches:
        entries = ghrel.archive.list_archive_entries(archive_fpath)
        raise ghrel.errors.GhrelError(
            message=f"Binary '{binary}' not found in archive for {archive_fpath}",
            hint=_make_binary_not_found_hint(binary, entries),
        )

    if len(matches) > 1:
        matches_str = _format_binary_matches(matches, extracted_dpath)
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
    return package.name


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


@beartype.beartype
def _format_asset_matches(matches: tuple[ghrel.github.ReleaseAsset, ...]) -> str:
    """Format asset matches for error output."""
    if not matches:
        return "  - (none)"
    lines = "\n  - ".join(asset.name for asset in matches)
    return f"  - {lines}"


@beartype.beartype
def _format_binary_matches(
    matches: list[pathlib.Path], extracted_dpath: pathlib.Path
) -> str:
    """Format binary matches for error output."""
    if not matches:
        return "  - (none)"
    lines = "\n  - ".join(
        _format_match_path(match, extracted_dpath) for match in matches
    )
    return f"\n  - {lines}"


@beartype.beartype
def _format_match_path(match: pathlib.Path, extracted_dpath: pathlib.Path) -> str:
    """Return a match path relative to the extracted directory."""
    try:
        rel_path = match.relative_to(extracted_dpath)
    except ValueError:
        rel_path = match
    return rel_path.as_posix()


@beartype.beartype
def _match_binary_patterns(
    extracted_dpath: pathlib.Path,
    pattern: str,
    *,
    match_basename_only: bool,
) -> list[pathlib.Path]:
    """Return files matching a wildcard pattern."""
    matches = []
    for match in extracted_dpath.rglob("*"):
        if not match.is_file():
            continue
        target = (
            match.name
            if match_basename_only
            else _format_match_path(match, extracted_dpath)
        )
        if fnmatch.fnmatch(target, pattern):
            matches.append(match)
    return matches


@beartype.beartype
def _make_binary_not_found_hint(binary: str, entries: tuple[str, ...]) -> str:
    """Build a hint with archive contents and explicit path guidance."""
    entries_str = _format_archive_entries(entries)
    suggestion = f"Set binary to a dict with your platform key, for example binary = {{'linux-x86_64': '<dir>/{binary}'}} (replace linux-x86_64 with your platform). You can use a wildcard like {{'linux-x86_64': '<dir>*/{binary}'}} to avoid version pinning."  # noqa: E501
    return f"{entries_str}\n{suggestion}"
