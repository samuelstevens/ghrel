"""CLI definition using tyro."""

import dataclasses
import os
import pathlib
import sys
import tempfile
import typing as tp

import beartype
import tyro

import ghrel.errors
import ghrel.github
import ghrel.install
import ghrel.packages
import ghrel.platform
import ghrel.state


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class Sync:
    """Sync all packages to match package files."""

    packages_dpath: tp.Annotated[pathlib.Path | None, tyro.conf.arg(name="path")] = None
    """Custom packages directory."""

    dry_run: bool = False
    """Show what would change without making changes."""

    verbose: bool = False
    """Show detailed output."""


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class List:
    """Show installed packages and their status."""

    verbose: bool = False
    """Show detailed output."""


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class Prune:
    """Remove orphaned binaries (installed but no package file)."""

    dry_run: bool = False
    """Show what would be removed without removing."""

    verbose: bool = False
    """Show detailed output."""


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class PackagePlan:
    """Resolved plan for a single package."""

    name: str
    package: ghrel.packages.PackageConfig
    current_state: ghrel.state.PackageState | None
    current_version: str | None
    desired_version: str
    release: ghrel.github.Release
    asset: ghrel.github.ReleaseAsset
    install_fpath: pathlib.Path
    action: str
    reason: str | None


@beartype.beartype
def run_list(cmd: List) -> None:
    """Run the list command."""
    state = ghrel.state.read_state()
    package_names = ghrel.packages.list_package_names()

    if not state.packages:
        print("No packages installed.")
        return

    max_name_len = max(len(name) for name in state.packages)

    for name in sorted(state.packages):
        pkg = state.packages[name]
        status = ""
        if name not in package_names:
            status = "  (orphan - no package file)"

        print(f"{name:<{max_name_len}}  {pkg.version}{status}")


@beartype.beartype
def run_sync(cmd: Sync) -> None:
    """Run the sync command."""
    packages_dpath = cmd.packages_dpath or ghrel.packages.get_packages_dpath()
    if not packages_dpath.exists():
        raise ghrel.errors.ConfigError(
            message=f"Packages directory does not exist: {packages_dpath}",
            hint=f"Create it with: mkdir -p {packages_dpath}",
            path=packages_dpath,
        )

    packages = ghrel.packages.load_packages(packages_dpath)
    if not packages:
        print("No packages found.")
        with ghrel.state.acquire_lock():
            state = ghrel.state.read_state()
            orphans = list(state.packages)
            for name in sorted(orphans):
                print(f"{name}: WARN orphan (use 'ghrel prune' to remove)")
        return

    token = os.environ.get("GITHUB_TOKEN")
    if not token and os.environ.get("GHREL_NO_TOKEN_WARNING") != "1":
        print("Warning: No GITHUB_TOKEN set. API rate limited to 60 requests/hour.")
        print("  Set GITHUB_TOKEN to increase limit to 5,000/hour.")
        print("")

    os_name = ghrel.platform.get_os()
    arch = ghrel.platform.get_arch()
    client = ghrel.github.GitHubClient(token=token)
    bin_dpath = ghrel.install.get_bin_dpath()

    failures: list[tuple[str, str]] = []

    with ghrel.state.acquire_lock():
        state = ghrel.state.read_state()
        state_packages = dict(state.packages)

        orphans = [name for name in state_packages if name not in packages]
        for name in sorted(orphans):
            print(f"{name}: WARN orphan (use 'ghrel prune' to remove)")

        for name in sorted(packages):
            package = packages[name]
            try:
                plan = _make_plan(
                    package,
                    state_packages.get(name),
                    client,
                    os_name,
                    arch,
                    bin_dpath,
                )
            except ghrel.errors.AuthError:
                raise
            except ghrel.errors.GhrelError as err:
                failures.append((name, str(err)))
                continue
            except Exception as err:
                failures.append((name, f"Unexpected error: {err}"))
                continue

            if plan.reason:
                _print_warning(plan.name, plan.reason)

            if cmd.dry_run:
                _print_plan(plan, dry_run=True)
                continue

            if plan.action == "up_to_date":
                _print_plan(plan, dry_run=False)
                continue

            install_result: ghrel.install.InstallResult | None = None
            with tempfile.TemporaryDirectory(prefix="ghrel-") as temp_dpath_str:
                temp_dpath = pathlib.Path(temp_dpath_str)
                try:
                    install_result = ghrel.install.install_release_asset(
                        package,
                        plan.release,
                        plan.asset,
                        bin_dpath,
                        client,
                        temp_dpath=temp_dpath,
                    )
                except ghrel.errors.GhrelError as err:
                    failures.append((name, str(err)))
                    continue
                except Exception as err:
                    failures.append((name, f"Unexpected error: {err}"))
                    continue

                post_install_err = _run_post_install(package, plan, install_result)
                if post_install_err:
                    failures.append((name, post_install_err))
                    continue

            assert install_result is not None

            verify_missing = package.verify is None
            verify_err = _run_verify(package, plan, install_result)
            if verify_err:
                failures.append((name, verify_err))
                continue

            state_packages[name] = install_result.package_state
            ghrel.state.write_state(ghrel.state.State(packages=state_packages))

            _print_plan(plan, dry_run=False, verify_missing=verify_missing)

        if failures:
            print("")
            print(f"Failed: {len(failures)} package(s)")
            for name, message in failures:
                print(f"  {name}: {message}")


@beartype.beartype
def run_prune(cmd: Prune) -> None:
    """Run the prune command."""
    packages_dpath = ghrel.packages.get_packages_dpath()
    if not packages_dpath.exists():
        raise ghrel.errors.ConfigError(
            message=f"Packages directory does not exist: {packages_dpath}",
            hint=f"Create it with: mkdir -p {packages_dpath}",
            path=packages_dpath,
        )

    package_names = ghrel.packages.list_package_names()

    if cmd.dry_run:
        state = ghrel.state.read_state()
        orphans = [name for name in state.packages if name not in package_names]

        if not orphans:
            print("No orphaned packages.")
            return

        for name in sorted(orphans):
            pkg = state.packages[name]
            print(f"Would remove: {name} ({pkg.version}) - {pkg.binary_fpath}")
        return

    with ghrel.state.acquire_lock():
        state = ghrel.state.read_state()
        orphans = [name for name in state.packages if name not in package_names]

        if not orphans:
            print("No orphaned packages.")
            return

        remaining_packages = dict(state.packages)

        for name in sorted(orphans):
            pkg = state.packages[name]

            if pkg.binary_fpath.exists():
                pkg.binary_fpath.unlink()
                print(f"Removed: {name} ({pkg.version}) - {pkg.binary_fpath}")
            else:
                print(f"Removed: {name} ({pkg.version}) - binary already missing")

            del remaining_packages[name]

        new_state = ghrel.state.State(packages=remaining_packages)
        ghrel.state.write_state(new_state)


@beartype.beartype
def main() -> None:
    """Main entry point."""
    command = tyro.cli(Sync | List | Prune)  # type: ignore[arg-type]

    try:
        match command:
            case Sync() as cmd:
                run_sync(cmd)
            case List() as cmd:
                run_list(cmd)
            case Prune() as cmd:
                run_prune(cmd)
    except (
        ghrel.errors.AuthError,
        ghrel.errors.ConfigError,
        ghrel.errors.PlatformError,
        ghrel.errors.StateError,
        ghrel.errors.LockError,
    ) as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


@beartype.beartype
def _make_plan(
    package: ghrel.packages.PackageConfig,
    current_state: ghrel.state.PackageState | None,
    client: ghrel.github.GitHubClient,
    os_name: str,
    arch: str,
    bin_dpath: pathlib.Path,
) -> PackagePlan:
    """Resolve the desired version, asset, and install action."""
    release = (
        client.get_release_by_tag(package.pkg, package.version)
        if package.version
        else client.get_latest_release(package.pkg)
    )
    desired_version = release.tag
    asset = ghrel.install.select_asset(package, release, os_name, arch)
    install_as = ghrel.install.get_install_as(package, asset)
    install_fpath = bin_dpath / install_as

    if current_state is None:
        return PackagePlan(
            name=package.name,
            package=package,
            current_state=current_state,
            current_version=None,
            desired_version=desired_version,
            release=release,
            asset=asset,
            install_fpath=install_fpath,
            action="install",
            reason=None,
        )

    current_version = current_state.version
    if current_state.binary_fpath != install_fpath:
        return PackagePlan(
            name=package.name,
            package=package,
            current_state=current_state,
            current_version=current_version,
            desired_version=desired_version,
            release=release,
            asset=asset,
            install_fpath=install_fpath,
            action="reinstall",
            reason="binary_path_changed",
        )

    if current_version != desired_version:
        return PackagePlan(
            name=package.name,
            package=package,
            current_state=current_state,
            current_version=current_version,
            desired_version=desired_version,
            release=release,
            asset=asset,
            install_fpath=install_fpath,
            action="update",
            reason=None,
        )

    if not current_state.binary_fpath.exists():
        return PackagePlan(
            name=package.name,
            package=package,
            current_state=current_state,
            current_version=current_version,
            desired_version=desired_version,
            release=release,
            asset=asset,
            install_fpath=install_fpath,
            action="reinstall",
            reason="binary_missing",
        )

    existing_checksum = ghrel.install.compute_sha256(current_state.binary_fpath)
    if existing_checksum != current_state.checksum:
        return PackagePlan(
            name=package.name,
            package=package,
            current_state=current_state,
            current_version=current_version,
            desired_version=desired_version,
            release=release,
            asset=asset,
            install_fpath=install_fpath,
            action="reinstall",
            reason="checksum_mismatch",
        )

    return PackagePlan(
        name=package.name,
        package=package,
        current_state=current_state,
        current_version=current_version,
        desired_version=desired_version,
        release=release,
        asset=asset,
        install_fpath=install_fpath,
        action="up_to_date",
        reason=None,
    )


@beartype.beartype
def _print_plan(
    plan: PackagePlan, *, dry_run: bool, verify_missing: bool = False
) -> None:
    """Print status for a package plan."""
    if plan.action == "up_to_date":
        print(f"{plan.name}: ok (up to date)")
        return

    if plan.action == "install":
        if dry_run:
            line = f"{plan.name}: would install {plan.desired_version}"
        else:
            line = f"{plan.name}: installed {plan.desired_version}"
    elif plan.action == "update":
        line = f"{plan.name}: {plan.current_version} -> {plan.desired_version}"
    elif plan.action == "reinstall":
        if dry_run:
            line = f"{plan.name}: would reinstall {plan.desired_version}"
        else:
            line = f"{plan.name}: reinstalled {plan.desired_version}"
    else:
        line = f"{plan.name}: {plan.desired_version}"

    if (
        verify_missing
        and not dry_run
        and plan.action in {"install", "update", "reinstall"}
    ):
        line = f"{line} (no verify hook)"

    print(line)
    if not dry_run:
        return

    binary_display = plan.package.binary
    if not plan.package.archive:
        binary_display = plan.asset.name
    if not binary_display:
        binary_display = plan.asset.name

    print(f"  asset: {plan.asset.url}")
    print(f"  binary: {binary_display} -> {_format_path(plan.install_fpath)}")


@beartype.beartype
def _print_warning(name: str, reason: str) -> None:
    """Print a warning for a package action."""
    if reason == "binary_missing":
        message = "WARN binary missing, re-downloading"
    elif reason == "checksum_mismatch":
        message = "WARN checksum mismatch, re-downloading"
    elif reason == "binary_path_changed":
        message = "WARN binary path changed, re-downloading"
    else:
        message = "WARN re-downloading"
    print(f"{name}: {message}")


@beartype.beartype
@beartype.beartype
def _run_post_install(
    package: ghrel.packages.PackageConfig,
    plan: PackagePlan,
    install_result: ghrel.install.InstallResult,
) -> str | None:
    """Run ghrel_post_install hook if present."""
    if package.post_install is None:
        return None

    try:
        package.post_install(
            version=plan.desired_version,
            binary_name=plan.install_fpath.name,
            binary_path=plan.install_fpath,
            checksum=install_result.package_state.checksum,
            pkg=package.pkg,
            bin_dir=plan.install_fpath.parent,
            extracted_dir=install_result.extracted_dpath,
        )
    except Exception as err:
        return f"post_install failed: {err}"

    return None


@beartype.beartype
def _run_verify(
    package: ghrel.packages.PackageConfig,
    plan: PackagePlan,
    install_result: ghrel.install.InstallResult,
) -> str | None:
    """Run ghrel_verify hook if present."""
    if package.verify is None:
        return None

    try:
        package.verify(
            version=plan.desired_version,
            binary_name=plan.install_fpath.name,
            binary_path=plan.install_fpath,
            checksum=install_result.package_state.checksum,
            pkg=package.pkg,
        )
    except Exception as err:
        return f"verify failed: {err}"

    return None


@beartype.beartype
def _format_path(path: pathlib.Path) -> str:
    """Format paths with ~ for the home directory."""
    home_dpath = pathlib.Path.home()
    try:
        relative = path.relative_to(home_dpath)
    except ValueError:
        return str(path)
    return f"~/{relative}"
