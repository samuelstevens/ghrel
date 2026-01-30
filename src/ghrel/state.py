"""State file management and locking."""

import collections.abc
import contextlib
import dataclasses
import json
import os
import pathlib
import tempfile

import beartype
import filelock

import ghrel.errors


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class PackageState:
    """State of an installed package."""

    version: str
    """Installed version tag (e.g., "v10.2.0")."""

    checksum: str
    """SHA-256 checksum of installed binary with "sha256:" prefix."""

    installed_at: str
    """ISO 8601 timestamp in UTC when package was installed."""

    binary_fpath: pathlib.Path
    """Absolute path to the installed binary."""


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class State:
    """Full state file contents."""

    packages: dict[str, PackageState] = dataclasses.field(default_factory=dict)
    """Map from package name (stem of .py file) to its state."""


@beartype.beartype
def get_state_dpath() -> pathlib.Path:
    """Get the state directory path, respecting XDG_STATE_HOME."""
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        return pathlib.Path(xdg_state) / "ghrel"
    return pathlib.Path.home() / ".local" / "state" / "ghrel"


@beartype.beartype
def get_state_fpath() -> pathlib.Path:
    """Get the state file path."""
    return get_state_dpath() / "state.json"


@beartype.beartype
def get_lock_fpath() -> pathlib.Path:
    """Get the lock file path."""
    return get_state_dpath() / "state.json.lock"


@contextlib.contextmanager
@beartype.beartype
def acquire_lock() -> collections.abc.Iterator[None]:
    """Acquire exclusive lock on state file. Exits immediately if lock is held."""
    lock_fpath = get_lock_fpath()
    lock_fpath.parent.mkdir(parents=True, exist_ok=True)

    lock = filelock.FileLock(lock_fpath)
    try:
        lock.acquire(timeout=0)
    except filelock.Timeout:
        raise ghrel.errors.LockError.make(lock_fpath) from None

    try:
        yield
    finally:
        lock.release()


@beartype.beartype
def read_state() -> State:
    """Read state from state.json. Returns empty state if file doesn't exist."""
    state_fpath = get_state_fpath()
    if not state_fpath.exists():
        return State()

    text = state_fpath.read_text()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise ghrel.errors.StateError.make(
            f"Invalid JSON in state file: {err}", state_fpath
        ) from None

    packages = {}
    required_keys = ("version", "checksum", "installed_at", "binary_path")
    for name, pkg_data in data.get("packages", {}).items():
        for key in required_keys:
            if key not in pkg_data:
                raise ghrel.errors.StateError.make(
                    f"Missing '{key}' for package '{name}'", state_fpath, name
                )

        packages[name] = PackageState(
            version=pkg_data["version"],
            checksum=pkg_data["checksum"],
            installed_at=pkg_data["installed_at"],
            binary_fpath=pathlib.Path(pkg_data["binary_path"]),
        )

    return State(packages=packages)


@beartype.beartype
def write_state(state: State) -> None:
    """Write state to state.json atomically."""
    state_fpath = get_state_fpath()
    state_fpath.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "packages": {
            name: {
                "version": pkg.version,
                "checksum": pkg.checksum,
                "installed_at": pkg.installed_at,
                "binary_path": str(pkg.binary_fpath),
            }
            for name, pkg in state.packages.items()
        }
    }

    # Atomic write: write to temp file, then rename
    with tempfile.NamedTemporaryFile(
        mode="w", dir=state_fpath.parent, delete=False, suffix=".tmp"
    ) as fd:
        json.dump(data, fd, indent=2)
        tmp_fpath = pathlib.Path(fd.name)

    os.replace(tmp_fpath, state_fpath)
