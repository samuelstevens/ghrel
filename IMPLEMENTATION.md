# ghrel Implementation Details

Technical decisions and implementation notes for the ghrel package manager.

## Overview

| Aspect | Decision |
|--------|----------|
| Language | Python 3.12+ |
| Build System | hatchling (via uv) |
| Project Layout | src layout (`src/ghrel/`) |
| Type Checker | ty (Astral's new type checker) |
| Formatter/Linter | ruff |
| Test Framework | pytest + pytest-cov + pytest-timeout |

## Dependencies

### Runtime Dependencies

| Package | Purpose |
|---------|---------|
| requests | HTTP client for GitHub API and downloads |
| filelock | Cross-platform file locking for state.json.lock |
| tyro | CLI framework (dataclass-based argument parsing) |

### Dev Dependencies

| Package | Purpose |
|---------|---------|
| pytest | Test framework |
| pytest-cov | Coverage reporting |
| pytest-timeout | Protection against hanging tests |
| ruff | Formatting and linting |
| ty | Type checking |

## Module Structure

```
src/ghrel/
├── __init__.py
├── __main__.py          # Entry point
├── cli.py               # CLI definition (tyro dataclasses)
├── github.py            # GitHub API client, release fetching
├── packages.py          # Package file loading and validation
├── state.py             # State file management, locking
├── archive.py           # Archive extraction (tar/zip)
├── install.py           # Binary installation, checksums
└── platform.py          # OS/arch detection and normalization
```

## Key Implementation Decisions

### Security & Trust

- **Package file execution**: Full trust model. Package files are Python modules imported via `importlib.util.spec_from_file_location`. No sandboxing - users author their own files.
- **Archive extraction**: Use `tarfile`/`zipfile` directly (not `shutil.unpack_archive`) to validate paths and prevent path traversal attacks.

### HTTP & Networking

- **HTTP client**: `requests` library (sync, well-understood)
- **Retry logic**: Manual implementation with exponential backoff (3 attempts)
- **API caching**: In-memory cache per command execution (avoid redundant release fetches when multiple packages share a repo)
- **Download progress**: Spinner with percentage for TTY, line-based logging for non-TTY

### Error Handling

- **Error model**: Exceptions with try/catch at package-processing boundary
- **Package file load errors**: Exit early on `SyntaxError`, `ImportError`, or `AttributeError` (missing required attributes). Only `pkg` is required. These indicate broken config files that need user attention.
- **Hook errors**: `ghrel_post_install`/`ghrel_verify` exceptions are per-package failures - continue processing other packages, report in summary. Binary remains installed but state is not updated (next sync will retry).
- **Network/processing errors**: Continue to next package, collect failures for summary
- **Corrupted state file**: Fail with error, don't auto-recover (let user decide)
- **Invalid GITHUB_TOKEN**: Fail immediately with authentication error. Do not fall back to unauthenticated requests (explicit is better than silent degradation).

### State Management

- **Serialization**: Dataclasses with manual `to_dict()`/`from_dict()` methods (no pydantic)
- **Locking**: `filelock` library for state.json.lock
- **Atomic writes**: Write to temp file, then rename

### Installation

- **Naming convention**: The package filename stem determines the installed binary name. `rg.py` installs to `~/.local/bin/rg`. Use `install_as` to override.
- **Atomic install sequence**:
  1. Download asset to temp directory (`/tmp/ghrel-<random>/`)
  2. Extract archive (or use directly if `archive=False`)
  3. Locate binary in extracted contents
  4. `shutil.copy` binary to install dir with `.tmp` suffix (e.g., `fd.tmp`)
  5. Verify SHA-256 checksum of copied `.tmp` file matches source
  6. `chmod +x` on the `.tmp` file
  7. `os.rename` from `.tmp` to final name (atomic on same filesystem)
  8. Run `ghrel_post_install` hook (if defined) - extracted_dir still available
  9. Clean up extracted temp directory
  10. Run `ghrel_verify` hook (if defined) - extracted_dir no longer available
  11. Update state file (only if all hooks succeeded)
- **Checksum**: SHA-256, computed by streaming in chunks (handles large files)
- **Raw binary hooks**: `ghrel_post_install` receives `extracted_dir=None` for `archive=False` packages (hook must handle `None`)

### Hooks

- **Naming**: Hooks use `ghrel_` prefix: `ghrel_post_install`, `ghrel_verify`
- **Arguments**: Typed keyword arguments (no `**kwargs` required for forward compat)
- **Execution order**: install → `ghrel_post_install` → cleanup → `ghrel_verify` → write state
- **Failure handling**:
  - `ghrel_post_install` failure: Chain stops, verify doesn't run, state not updated
  - `ghrel_verify` failure: State not updated (next sync will retry)
  - Just exception message shown (not full traceback)
- **Missing `ghrel_verify`**: Warning shown per-package (e.g., `fd: installed 10.2.0 (no verify hook)`)
- **Verify guidelines**: Run binary from PATH (not absolute path) to verify PATH setup is correct
- **Verify on up-to-date**: Verify runs even when a package is already up to date

### Platform Detection

- **Approach**: Direct use of `platform.system()`/`platform.machine()` with normalization
- **Aliases**: Normalize common variations (e.g., `x86_64` ↔ `amd64`, `arm64` ↔ `aarch64`)

### CLI & Output

- **CLI framework**: tyro (dataclass-based)
- **Console output**: Plain print with ANSI escape codes (no rich dependency)
- **Progress display**:
  - TTY: Spinner that updates with percentage
  - Non-TTY: Line-based progress logging
- **Verbose mode**: `--verbose` flag for detailed output (HTTP requests, extraction steps)
- **Token warning**: Warn on every run if `GITHUB_TOKEN` not set (rate limited to 60 req/hr). Suppress entirely via `GHREL_NO_TOKEN_WARNING=1` env var. No state tracking - simpler than warn-once logic.

### Version Handling

- **Latest resolution**: When no `version` specified, use GitHub's `/releases/latest` endpoint which returns the most recent non-prerelease, non-draft release.
- **Matching**: Strict string match against GitHub release tags
- **v-prefix**: No fuzzy matching - if tag is `v1.0.0`, user must write `version = "v1.0.0"`
- **Helpful errors**: Print available tags when version not found to help user identify correct format

### Processing

- **Sync parallelism**: Sequential processing (cleaner output, easier debugging)
- **Dry-run**: Fetches real release info from GitHub (shows asset URLs, versions, and binary paths)
- **List command**: Offline only - reads state file, no GitHub API calls. Use `sync --dry-run` to check for updates.

## Key Behaviors

### Asset Selection

1. If `asset` pattern specified: use `fnmatch` against asset filenames
2. If no pattern: auto-detect based on OS (`darwin`/`linux`) and arch (`arm64`/`x86_64`/`amd64`)
3. **Ambiguity is an error**: If multiple assets match, fail with error listing all matches. User must make pattern more specific.

### Binary Search Order

If `binary` is omitted, default it to the package filename stem.

For simple `binary = "name"` (no path separator):
1. Look for exact filename match in archive root
2. Look for exact filename match in any subdirectory
3. Fail if not found or if multiple matches

For explicit path `binary = "dir/name"`:
- Match exactly, fail if not found

### State & Locking

- `sync` and `prune` acquire exclusive lock on `state.json.lock`
- `list` is read-only, no lock required
- **Lock contention**: If lock held by another process, exit immediately with error (don't wait)
- **Stale locks**: User must manually delete `state.json.lock` if ghrel crashes

### Orphan Detection

- During `sync`: Warn about packages in state file with no corresponding `.py` file
- `prune` command: Remove orphaned binaries (state entry + binary file)
- Detection based on state file entries, not filesystem scanning

### Sync-Time Verification

On each sync, for each package:
1. Check if binary exists at `binary_path` from state
2. If missing: warn about state drift, re-download
3. If present: compute SHA-256 checksum, compare against stored `checksum`
4. If mismatch: re-download and reinstall (binary may have been modified externally)
5. Run `ghrel_verify` when defined, even if the package is already up to date

## Testing Strategy

### Approach

- **Unit tests**: Each module tested in isolation
- **Integration tests**: All mocked (no real network, no real filesystem writes)
- **API mocking**: Dependency injection - pass client interface, swap implementations in tests
- **Fixtures**: Sample package files in test fixtures directory

### Test Organization

```
tests/
├── conftest.py           # Shared fixtures
├── test_cli.py           # CLI argument parsing
├── test_github.py        # GitHub API client
├── test_packages.py      # Package file loading
├── test_state.py         # State management
├── test_archive.py       # Archive extraction
├── test_install.py       # Installation logic
└── fixtures/
    └── packages/         # Sample .py package files
```

### What to Test

- Package file loading: valid files, syntax errors, missing attributes
- GitHub API: release listing, asset selection, error responses, rate limiting
- Archive extraction: tar.gz, zip, path traversal prevention
- State file: read/write/locking, corruption detection
- Installation: atomic writes, checksum verification, chmod
- CLI: argument parsing, dry-run output format
- Platform detection: OS/arch normalization

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `GITHUB_TOKEN` | GitHub API authentication |
| `XDG_CONFIG_HOME` | Override config directory |
| `XDG_STATE_HOME` | Override state directory |
| `GHREL_BIN` | Override binary install directory |
| `GHREL_NO_TOKEN_WARNING` | Suppress "no token" warning when set to `1` |

## CLI Interface (tyro)

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class SyncCommand:
    """Sync all packages to match package files."""
    path: Path | None = None  # Custom packages directory
    dry_run: bool = False     # Show what would change
    verbose: bool = False     # Detailed output

@dataclass
class ListCommand:
    """Show installed packages and their status."""
    verbose: bool = False

@dataclass
class PruneCommand:
    """Remove orphaned binaries."""
    dry_run: bool = False
    verbose: bool = False

@dataclass
class CLI:
    """ghrel - GitHub Releases Package Manager"""
    command: SyncCommand | ListCommand | PruneCommand
```

## Error Messages

Design errors to be actionable:

```
# Version not found
Error: Version '1.0.0' not found for sharkdp/fd
  Available tags: v10.2.0, v10.1.0, v10.0.0, v9.0.0, ...
  Hint: Tags usually include a 'v' prefix

# Ambiguous asset match
Error: Multiple assets match pattern '*linux*' for sharkdp/fd v10.2.0:
  - fd-v10.2.0-x86_64-unknown-linux-gnu.tar.gz
  - fd-v10.2.0-x86_64-unknown-linux-musl.tar.gz
  Hint: Make your pattern more specific (e.g., '*linux*musl*')

# Binary not found in archive (binary defaults to package name if not specified)
Error: Binary 'fd' not found in archive for sharkdp/fd v10.2.0
  Archive contents:
    fd-v10.2.0-x86_64-unknown-linux-gnu/
    fd-v10.2.0-x86_64-unknown-linux-gnu/fd
    fd-v10.2.0-x86_64-unknown-linux-gnu/README.md
  Hint: Set binary = "fd-v10.2.0-x86_64-unknown-linux-gnu/fd"
  Hint: Use wildcards for version independence: binary = "fd-*-x86_64-unknown-linux-gnu/fd"
```

## File Structure

```
ghrel/
├── pyproject.toml
├── README.md
├── SPEC.md
├── IMPLEMENTATION.md
├── src/
│   └── ghrel/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── github.py
│       ├── packages.py
│       ├── state.py
│       ├── archive.py
│       ├── install.py
│       └── platform.py
└── tests/
    ├── conftest.py
    ├── test_cli.py
    ├── test_github.py
    ├── test_packages.py
    ├── test_state.py
    ├── test_archive.py
    ├── test_install.py
    └── fixtures/
        └── packages/
```
