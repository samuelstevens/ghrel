"""User-facing errors with actionable context.

Errors are messages for humans. Each error should answer:
1. What went wrong?
2. What was the context?
3. What can the user do about it?

See https://fast.github.io/blog/stop-forwarding-errors-start-designing-them
"""

import dataclasses
import pathlib

import beartype


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class GhrelError(Exception):
    """Base error with structured context for user-facing messages."""

    message: str
    """What went wrong."""

    hint: str | None = None
    """What the user can do about it."""

    def __str__(self) -> str:
        parts = [self.message]
        if self.hint:
            parts.append(f"Hint: {self.hint}")
        return "\n".join(parts)


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class LockError(GhrelError):
    """Another ghrel process is running."""

    lock_fpath: pathlib.Path = dataclasses.field(kw_only=True)
    """Path to the lock file."""

    @staticmethod
    def make(lock_fpath: pathlib.Path) -> "LockError":
        """Create a LockError with default message and hint."""
        return LockError(
            message=f"Another ghrel process is running (lock: {lock_fpath})",
            hint=f"Wait for it to finish, or delete {lock_fpath} if stale.",
            lock_fpath=lock_fpath,
        )


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class ConfigError(GhrelError):
    """Configuration is missing or invalid."""

    path: pathlib.Path | None = None
    """Related path, if any."""


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class AuthError(GhrelError):
    """GitHub authentication failed."""

    message: str = ""
    hint: str | None = None

    def __post_init__(self) -> None:
        if not self.message:
            object.__setattr__(self, "message", "GitHub authentication failed.")
        if not self.hint:
            object.__setattr__(
                self,
                "hint",
                "Check your GITHUB_TOKEN. If invalid or expired, create a new one.",
            )


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class PlatformError(GhrelError):
    """Unsupported platform or architecture."""


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class ArchiveError(GhrelError):
    """Archive extraction failed or was unsafe."""


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class NotFoundError(GhrelError):
    """Requested resource was not found."""


@beartype.beartype
@dataclasses.dataclass(frozen=True)
class StateError(GhrelError):
    """State file is corrupted or invalid."""

    state_fpath: pathlib.Path = dataclasses.field(kw_only=True)
    """Path to the state file."""

    package_name: str | None = dataclasses.field(default=None, kw_only=True)
    """Package with the issue, if applicable."""

    @staticmethod
    def make(
        message: str, state_fpath: pathlib.Path, package_name: str | None = None
    ) -> "StateError":
        """Create a StateError with default hint."""
        return StateError(
            message=message,
            hint=f"Check {state_fpath} for errors, or delete it to reset state.",
            state_fpath=state_fpath,
            package_name=package_name,
        )
