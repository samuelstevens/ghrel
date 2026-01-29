"""Package file loading and validation."""

import os
import pathlib

import beartype


@beartype.beartype
def get_packages_dpath() -> pathlib.Path:
    """Get the packages directory path, respecting XDG_CONFIG_HOME."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return pathlib.Path(xdg_config) / "ghrel" / "packages"
    return pathlib.Path.home() / ".config" / "ghrel" / "packages"


@beartype.beartype
def list_package_names(packages_dpath: pathlib.Path | None = None) -> set[str]:
    """List package names (stems of .py files) in the packages directory."""
    if packages_dpath is None:
        packages_dpath = get_packages_dpath()

    if not packages_dpath.exists():
        return set()

    return {f.stem for f in packages_dpath.glob("*.py")}
