"""OS/arch detection and normalization."""

import platform

import beartype

import ghrel.errors


@beartype.beartype
def get_os() -> str:
    """Get normalized OS name."""
    system = platform.system().lower()
    if system == "darwin":
        return "darwin"
    if system == "linux":
        return "linux"
    raise ghrel.errors.PlatformError(
        message=f"Unsupported operating system: {system}",
        hint="ghrel supports macOS and Linux only.",
    )


@beartype.beartype
def get_arch() -> str:
    """Get normalized architecture name."""
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    if machine in {"x86_64", "amd64", "x64"}:
        return "x86_64"
    raise ghrel.errors.PlatformError(
        message=f"Unsupported architecture: {machine}",
        hint="ghrel supports x86_64 and arm64 only.",
    )


@beartype.beartype
def get_os_keys(os_name: str) -> tuple[str, ...]:
    """Return filename keys used to match the OS."""
    if os_name == "darwin":
        return ("darwin", "macos", "mac", "osx")
    if os_name == "linux":
        return ("linux",)
    raise ghrel.errors.PlatformError(
        message=f"Unsupported operating system: {os_name}",
        hint="ghrel supports macOS and Linux only.",
    )


@beartype.beartype
def get_arch_keys(arch: str) -> tuple[str, ...]:
    """Return filename keys used to match the architecture."""
    if arch == "arm64":
        return ("arm64", "aarch64")
    if arch == "x86_64":
        return ("x86_64", "amd64", "x64")
    raise ghrel.errors.PlatformError(
        message=f"Unsupported architecture: {arch}",
        hint="ghrel supports x86_64 and arm64 only.",
    )
