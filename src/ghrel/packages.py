"""Package file loading and validation."""

import collections.abc
import dataclasses
import importlib.util
import os
import pathlib
import types
import typing as tp

import beartype

import ghrel.errors


@tp.runtime_checkable
class PostInstallHook(tp.Protocol):
    """Signature for ghrel_post_install hook."""

    def __call__(
        self,
        *,
        version: str,
        binary_name: str,
        binary_path: pathlib.Path,
        checksum: str,
        pkg: str,
        bin_dir: pathlib.Path,
        extracted_dir: pathlib.Path | None,
    ) -> None: ...


@tp.runtime_checkable
class VerifyHook(tp.Protocol):
    """Signature for ghrel_verify hook."""

    def __call__(
        self,
        *,
        version: str,
        binary_name: str,
        binary_path: pathlib.Path,
        checksum: str,
        pkg: str,
    ) -> None: ...


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class PackageConfig:
    """Validated package configuration loaded from a package file."""

    name: str
    """Package name (stem of .py file)."""

    pkg: str
    """GitHub repo in owner/repo format."""

    binary: str | None
    """Executable path inside archive, or None for raw binaries."""

    install_as: str | None
    """Installed binary name, or None to derive later."""

    asset: str | None
    """Asset glob pattern."""

    version: str | None
    """Pinned version tag, or None for latest."""

    archive: bool
    """Whether the asset is an archive."""

    post_install: PostInstallHook | None
    """Hook called after install."""

    verify: VerifyHook | None
    """Hook called to verify the installed binary."""

    package_fpath: pathlib.Path
    """Absolute path to the package file."""


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

    return {fpath.stem for fpath in packages_dpath.glob("*.py")}


@beartype.beartype
def load_packages(packages_dpath: pathlib.Path) -> dict[str, PackageConfig]:
    """Load and validate all package files in a directory."""
    packages = {}
    for package_fpath in sorted(packages_dpath.glob("*.py")):
        config = _load_package(package_fpath)
        packages[config.name] = config
    return packages


@beartype.beartype
def _load_package(package_fpath: pathlib.Path) -> PackageConfig:
    """Load a single package file and validate its attributes."""
    module = _load_module(package_fpath)
    name = package_fpath.stem

    pkg = _get_required_attr(module, "pkg", str, package_fpath)
    _validate_pkg_name(pkg, package_fpath)

    archive = _get_optional_attr(module, "archive", bool, package_fpath, default=True)

    binary = _get_optional_attr(module, "binary", str, package_fpath, default=None)
    if archive and binary is None:
        raise ghrel.errors.ConfigError(
            message=f"Missing required attribute 'binary' in {package_fpath}",
            path=package_fpath,
        )

    install_as = _get_optional_attr(
        module, "install_as", str, package_fpath, default=None
    )
    if archive and install_as is None:
        assert binary is not None
        install_as = pathlib.PurePosixPath(binary).name
    if install_as is not None and not install_as:
        raise ghrel.errors.ConfigError(
            message=f"Invalid install_as '{install_as}' in {package_fpath}",
            hint="install_as must be a non-empty filename.",
            path=package_fpath,
        )
    if install_as is not None and ("/" in install_as or "\\" in install_as):
        raise ghrel.errors.ConfigError(
            message=f"Invalid install_as '{install_as}' in {package_fpath}",
            hint="install_as must be a filename, not a path.",
            path=package_fpath,
        )

    asset = _get_optional_attr(module, "asset", str, package_fpath, default=None)
    version = _get_optional_attr(module, "version", str, package_fpath, default=None)

    post_install_raw = _get_optional_callable_attr(
        module, "ghrel_post_install", package_fpath
    )
    post_install = tp.cast(PostInstallHook | None, post_install_raw)
    verify_raw = _get_optional_callable_attr(module, "ghrel_verify", package_fpath)
    verify = tp.cast(VerifyHook | None, verify_raw)

    return PackageConfig(
        name=name,
        pkg=pkg,
        binary=binary,
        install_as=install_as,
        asset=asset,
        version=version,
        archive=archive,
        post_install=post_install,
        verify=verify,
        package_fpath=package_fpath,
    )


@beartype.beartype
def _load_module(package_fpath: pathlib.Path) -> types.ModuleType:
    """Import a package file as a Python module."""
    module_name = f"ghrel_pkg_{package_fpath.stem}"
    spec = importlib.util.spec_from_file_location(module_name, package_fpath)
    if spec is None or spec.loader is None:
        raise ghrel.errors.ConfigError(
            message=f"Unable to import package file: {package_fpath}",
            path=package_fpath,
        )

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as err:
        raise ghrel.errors.ConfigError(
            message=f"Failed to load package file {package_fpath}: {err}",
            path=package_fpath,
        ) from None

    return module


@beartype.beartype
def _validate_pkg_name(pkg: str, package_fpath: pathlib.Path) -> None:
    """Validate that pkg is in owner/repo format."""
    if "/" not in pkg:
        raise ghrel.errors.ConfigError(
            message=f"Invalid pkg '{pkg}' in {package_fpath}",
            hint="Expected format 'owner/repo'.",
            path=package_fpath,
        )

    owner, repo = pkg.split("/", maxsplit=1)
    if not owner or not repo:
        raise ghrel.errors.ConfigError(
            message=f"Invalid pkg '{pkg}' in {package_fpath}",
            hint="Expected format 'owner/repo'.",
            path=package_fpath,
        )


@beartype.beartype
def _get_required_attr(
    module: types.ModuleType,
    name: str,
    expected_type: type,
    package_fpath: pathlib.Path,
) -> tp.Any:
    """Fetch a required attribute from a module and validate its type."""
    if not hasattr(module, name):
        raise ghrel.errors.ConfigError(
            message=f"Missing required attribute '{name}' in {package_fpath}",
            path=package_fpath,
        )

    value = getattr(module, name)
    if not isinstance(value, expected_type):
        raise ghrel.errors.ConfigError(
            message=(
                f"Invalid type for '{name}' in {package_fpath} "
                f"(expected {expected_type.__name__})"
            ),
            path=package_fpath,
        )

    return value


@beartype.beartype
def _get_optional_attr(
    module: types.ModuleType,
    name: str,
    expected_type: type,
    package_fpath: pathlib.Path,
    default: tp.Any,
) -> tp.Any:
    """Fetch an optional attribute from a module and validate its type."""
    if not hasattr(module, name):
        return default

    value = getattr(module, name)
    if value is None:
        return default
    if not isinstance(value, expected_type):
        raise ghrel.errors.ConfigError(
            message=(
                f"Invalid type for '{name}' in {package_fpath} "
                f"(expected {expected_type.__name__})"
            ),
            path=package_fpath,
        )

    return value


@beartype.beartype
def _get_optional_callable_attr(
    module: types.ModuleType,
    name: str,
    package_fpath: pathlib.Path,
) -> collections.abc.Callable[..., tp.Any] | None:
    """Fetch an optional callable attribute from a module."""
    if not hasattr(module, name):
        return None

    value = getattr(module, name)
    if value is None:
        return None
    if not callable(value):
        raise ghrel.errors.ConfigError(
            message=f"'{name}' in {package_fpath} must be callable",
            path=package_fpath,
        )
    return tp.cast(collections.abc.Callable[[tp.Any], tp.Any], value)
