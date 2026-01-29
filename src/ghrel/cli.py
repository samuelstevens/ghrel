"""CLI definition using tyro."""

import dataclasses
import pathlib
import sys
import typing as tp

import beartype
import tyro

import ghrel.packages
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


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


@beartype.beartype
def run_prune(cmd: Prune) -> None:
    """Run the prune command."""
    packages_dpath = ghrel.packages.get_packages_dpath()
    if not packages_dpath.exists():
        raise ConfigError(f"Packages directory does not exist: {packages_dpath}")

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
            case Sync():
                print("sync not implemented yet")
            case List() as cmd:
                run_list(cmd)
            case Prune() as cmd:
                run_prune(cmd)
    except (ghrel.state.LockError, ConfigError) as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)
