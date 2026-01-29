# ghrel - GitHub Releases Package Manager

A minimal package manager for installing and updating binaries from GitHub releases.

## Philosophy

- **Config is truth**: Your package files define what should be installed. `ghrel sync` installs and updates to match; `ghrel prune` removes orphans.
- **User-authored only**: No community registry, no supply chain risk. You write all package files.
- **Real Python**: Package files are `.py` modules with full Python power. No DSL limitations.
- **Resilient**: Processing failures don't block other packages. Sync processes all packages and reports a summary. (Config errors like syntax errors exit early to catch mistakes.)

## Installation

```sh
uv tool install ghrel
```

## Quick Start

```sh
# Create a package file
mkdir -p ~/.config/ghrel/packages
echo 'pkg = "junegunn/fzf"' > ~/.config/ghrel/packages/fzf.py
echo 'binary = "fzf"' >> ~/.config/ghrel/packages/fzf.py

# Sync (install/upgrade all packages)
ghrel sync
```

## Package File Format

Package files are Python modules in `~/.config/ghrel/packages/`. The tool imports each `.py` file and reads module-level attributes.

### Minimal Package

```python
# fd.py
pkg = "sharkdp/fd"
binary = "fd"
```

### Full Package (all options)

```python
# ripgrep.py
pkg = "BurntSushi/ripgrep"
binary = "rg"                          # executable name in archive (can be path, see below)
install_as = "rg"                      # name in ~/.local/bin (optional, defaults to binary basename)
asset = "*x86_64*linux*musl*.tar.gz"   # glob pattern for asset selection (optional)
version = "14.1.0"                     # pin to exact version (optional, default: latest)
archive = True                         # whether asset is an archive (optional, default: True)

def pre_install(version, install_dir, previous_version):
    """Called before download/extraction. Optional."""
    # version: str - version being installed
    # install_dir: Path - where binary will be installed
    # previous_version: str | None - currently installed version, or None if fresh install
    pass

def post_install(extracted_dir, install_dir, version):
    """Called after binary is installed. Optional."""
    import shutil
    from pathlib import Path

    # Install shell completions
    completions = extracted_dir / "complete" / "_rg"
    if completions.exists():
        dest = Path.home() / ".zsh" / "completions" / "_rg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(completions, dest)
```

### Package Attributes

| Attribute | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `pkg` | `str` | Yes | - | GitHub repo in `owner/repo` format |
| `binary` | `str` | Yes* | - | Executable path in archive (filename or explicit path like `fd-v10/fd`). *Ignored when `archive = False`. |
| `install_as` | `str` | No | basename of `binary` | Installed binary name |
| `asset` | `str` | No | auto-detect | Glob pattern to match release asset filename |
| `version` | `str` | No | latest | Exact version tag to pin |
| `archive` | `bool` | No | `True` | Set to `False` for raw binary assets (not archived) |

### Hook Functions

| Function | Signature | Description |
|----------|-----------|-------------|
| `pre_install` | `(version: str, install_dir: Path, previous_version: str \| None) -> None` | Called before download/extraction |
| `post_install` | `(extracted_dir: Path \| None, install_dir: Path, version: str) -> None` | Called after binary is installed. `extracted_dir` is `None` for raw binaries (`archive=False`). |

**Hook failure behavior**: If a hook raises an exception, that package is marked as failed and other packages continue processing.
- **pre_install failure**: Download is skipped, binary is not installed.
- **post_install failure**: Binary is already installed; it remains in place but package is marked failed in summary.

## CLI Commands

### ghrel sync

Main command. Ensures installed binaries match package files.

```sh
ghrel sync                    # sync all packages
ghrel sync --dry-run          # show what would change (includes asset URLs)
ghrel sync ~/.dotfiles/ghrel  # sync from custom path
```

Behavior:
- Installs packages that have package files but aren't installed
- Upgrades packages where installed version differs from desired (latest or pinned)
- Verifies checksums of installed binaries (re-downloads if mismatch detected)
- Re-downloads if binary file is missing (warns about state drift)
- **Warns** about orphaned binaries (installed but no package file) - use `ghrel prune` to remove
- Continues on error - failures are reported in summary at end

**Dry-run output** includes asset URLs and binary paths to help debug pattern issues:

```
ghrel sync --dry-run
fd: 9.0.0 → 10.2.0
  asset: https://github.com/sharkdp/fd/releases/download/v10.2.0/fd-v10.2.0-x86_64-apple-darwin.tar.gz
  binary: fd-v10.2.0-x86_64-apple-darwin/fd → ~/.local/bin/fd
fzf: ✓ (up to date)
```

### ghrel list

Show installed packages and their status. This command is offline-only (no GitHub API calls).

```sh
ghrel list
```

Output:
```
fd          9.0.0
ripgrep     14.1.0   (pinned)
fzf         0.54.0
bat         0.24.0   (orphan - no package file)
```

To check for updates, run `ghrel sync --dry-run`.

### ghrel prune

Remove orphaned binaries (installed but no corresponding package file).

```sh
ghrel prune              # remove all orphans
ghrel prune --dry-run    # show what would be removed
```

## Directory Structure

```
~/.config/ghrel/
└── packages/           # Package files (symlink from dotfiles)
    ├── fd.py
    ├── fzf.py
    └── ripgrep.py

~/.local/state/ghrel/
├── state.json          # Installed package state (machine-specific)
└── state.json.lock     # Lock file for concurrent access

~/.local/bin/           # Installed binaries
├── fd
├── fzf
└── rg
```

### State File Format

```json
{
  "packages": {
    "fd": {
      "version": "10.2.0",
      "checksum": "sha256:abc123...",
      "installed_at": "2024-01-15T10:30:00Z",
      "binary_path": "/Users/sam/.local/bin/fd"
    }
  }
}
```

**Timestamps**: All timestamps use ISO 8601 format in UTC (indicated by `Z` suffix).

## Concurrency & Atomicity

### State File Locking

ghrel uses file locking to prevent concurrent modifications:
- `ghrel sync` and `ghrel prune` acquire an exclusive lock on `state.json.lock`
- If another process holds the lock, ghrel exits immediately with an error
- `ghrel list` does not require a lock (read-only)

**Stale locks**: If ghrel crashes, the lock file may be left behind. Delete `~/.local/state/ghrel/state.json.lock` manually to recover.

### Atomic State Writes

State file updates use atomic write (write to temp file, then rename) to prevent corruption if `ghrel list` runs during sync.

### Atomic Installs

To prevent corrupted binaries from interrupted installs:
1. Download asset to system temp directory (`/tmp/ghrel-<random>/`)
2. Extract and locate binary (or use directly if `archive = False`)
3. Copy binary to install directory with `.tmp` suffix
4. Verify checksum of copied file matches downloaded file
5. Set executable permission (`chmod +x`)
6. Atomic rename `.tmp` to final name
7. Update state file

If interrupted at any step, no partial binary is left in the install directory.

**Cross-filesystem note**: If temp and install directories are on different filesystems, rename becomes copy+delete. Step 4 (checksum verification) ensures integrity even if copy is interrupted.

## Asset Selection

When a release has multiple assets, ghrel selects based on:

1. **Explicit pattern**: If `asset` is set, use glob match
2. **Platform detection**: Match current OS (`darwin`, `linux`) and arch (`arm64`, `amd64`, `x86_64`)

**Ambiguity is an error**: If multiple assets match the pattern (or platform heuristics), ghrel fails that package with an error listing the matching assets. This prevents accidentally installing the wrong build.

Asset matching uses fnmatch-style globs against the asset filename:

```python
# Match arm64 macOS tarball specifically
asset = "*darwin*arm64*.tar.gz"

# Match musl Linux builds
asset = "*linux*musl*.tar.gz"
```

**Tip**: Be specific with your asset pattern to avoid ambiguity. Include the archive extension.

## Raw Binary Assets

Some releases ship a raw binary instead of an archive (e.g., just `fzf` not `fzf.tar.gz`).

Set `archive = False` to handle these:

```python
pkg = "some/tool"
binary = "tool"           # ignored when archive = False
asset = "*linux*amd64*"
archive = False           # asset IS the binary, not an archive
```

When `archive = False`:
- The downloaded asset is used directly as the binary
- The `binary` attribute is ignored (asset becomes the binary)
- `install_as` still controls the installed name
- `post_install` receives `extracted_dir=None` (no archive to extract)

## Binary Detection

The `binary` attribute specifies which executable to extract from the archive.

**Simple case** - just the filename:
```python
binary = "fd"  # searches root and all subdirectories for "fd"
```

**Explicit path** - for archives with nested/versioned directories:
```python
binary = "fd-v10.2.0-x86_64-unknown-linux-gnu/fd"
```

Search order for simple filenames:
1. Root of archive for exact filename match
2. Any subdirectory for exact filename match
3. Fails if not found (no guessing)

**Multiple matches**: If a simple filename matches multiple files in the archive, ghrel fails with an error. Use an explicit path to disambiguate.

## Permissions

After copying the binary to the install directory, ghrel always runs `chmod +x` to ensure it's executable. This handles cases where:
- Archive extraction doesn't preserve permissions
- Raw binary downloads don't have execute bit set

## Version Handling

- **Latest (default)**: Fetches most recent non-prerelease, non-draft GitHub release
- **Pinned**: Set `version = "v1.2.3"` for exact tag match (include `v` prefix if the tag has it)

Version comparison is exact string match against GitHub release tags.

## Checksum Verification

ghrel stores a SHA-256 checksum of each installed binary in the state file.

On each sync:
1. Check if binary file exists at expected path
2. If missing: warn about state drift, re-download
3. If present: compute checksum, compare against stored
4. If mismatch: re-download and reinstall

This detects:
- Accidental modifications to installed binaries
- Corruption from disk errors
- External tools overwriting the binary
- Binary deleted but state not updated

Note: This does not verify against upstream checksums (most releases don't provide them).

## GitHub API

### Authentication

- **Optional but recommended**: Set `GITHUB_TOKEN` for higher rate limits
  - Without token: 60 requests/hour
  - With token: 5,000 requests/hour
- ghrel warns on each run without a token. Suppress with `GHREL_NO_TOKEN_WARNING=1`.
- **Invalid token**: If `GITHUB_TOKEN` is set but invalid/revoked, ghrel fails with an error (does not fall back to unauthenticated)

**Recommended token scope**: `public_repo` (read-only access to public repositories). No write permissions needed.

### Retries

3 attempts with exponential backoff on network errors.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | GitHub personal access token for API requests |
| `XDG_CONFIG_HOME` | Override config directory (default: `~/.config`) |
| `XDG_STATE_HOME` | Override state directory (default: `~/.local/state`) |
| `GHREL_BIN` | Override binary install directory (default: `~/.local/bin`) |
| `GHREL_NO_TOKEN_WARNING` | Set to `1` to suppress "no token" warning |

## Output

Minimal progress by default:

```
ghrel sync
⚠ No GITHUB_TOKEN set. API rate limited to 60 requests/hour.
  Set GITHUB_TOKEN to increase limit to 5,000/hour.

fd: 9.0.0 → 10.2.0
fzf: ✓ (up to date)
ripgrep: installed 14.1.0
bat: ⚠ orphan (use 'ghrel prune' to remove)
delta: ⚠ binary missing, re-downloading

✗ 1 failed:
  jq: ambiguous asset match (2 assets matched '*linux*'):
      - jq-linux-amd64
      - jq-linux-arm64
```

## Error Handling

- **Package file load errors**: If any package file fails to load (`SyntaxError`, `ImportError`, or missing required attributes), ghrel exits immediately. This catches config mistakes early.
- **Continue on processing errors**: Once packages are loaded, each is processed independently. Hook failures, network errors, and asset issues don't stop other packages.
- **Summary at end**: Failed packages are listed with error messages after sync completes.
- **Ambiguous asset**: Fails if multiple assets match pattern - lists matching assets.
- **Checksum mismatch**: Re-downloads the binary automatically.
- **Missing binary**: Warns about state drift, re-downloads.
- **Missing binary in archive**: Fails that package if `binary` not found in archive.
- **Hook failure**: Fails that package, continues with others. (post_install failure leaves binary installed)
- **Network errors**: Retries 3x with backoff, then marks package as failed.
- **Invalid token**: Fails immediately with authentication error (no fallback).
- **Lock contention**: Exits immediately if another ghrel process is running. (This is a system-level guard, not a package failure.)

## Dotfiles Integration

Recommended setup with GNU Stow:

```
~/.dotfiles/
└── ghrel/
    └── .config/
        └── ghrel/
            └── packages/
                ├── fd.py
                ├── fzf.py
                └── ripgrep.py
```

```sh
cd ~/.dotfiles && stow ghrel
ghrel sync
```

**Renaming package files**: If you rename `fd.py` to `fd2.py`, the old state entry becomes orphaned. Run `ghrel prune` to clean up, then `ghrel sync` to reinstall under the new name.

## Example Package Files

### Simple (fzf)

```python
pkg = "junegunn/fzf"
binary = "fzf"
```

### Raw binary (no archive)

```python
pkg = "tailwindlabs/tailwindcss"
binary = "tailwindcss"  # ignored when archive=False
asset = "*macos-arm64*"
archive = False
install_as = "tailwindcss"
```

### With completions (fd)

```python
pkg = "sharkdp/fd"
binary = "fd"

def post_install(extracted_dir, install_dir, version):
    import shutil
    from pathlib import Path

    # fd includes completions in autocomplete/
    src = extracted_dir / "autocomplete" / "_fd"
    if src.exists():
        dest = Path.home() / ".zsh" / "completions" / "_fd"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)
```

### With pre-install hook

```python
pkg = "jesseduffield/lazygit"
binary = "lazygit"

def pre_install(version, install_dir, previous_version):
    import subprocess

    if previous_version:
        # Kill running lazygit before upgrade
        subprocess.run(["pkill", "-f", "lazygit"], capture_output=True)
```

### Pinned version (ripgrep)

```python
pkg = "BurntSushi/ripgrep"
binary = "rg"
version = "14.1.0"
asset = "*x86_64*linux*musl*.tar.gz"
```

### Explicit binary path (nested directory)

```python
pkg = "BurntSushi/ripgrep"
binary = "ripgrep-14.1.0-x86_64-unknown-linux-musl/rg"
install_as = "rg"
asset = "*x86_64*linux*musl*.tar.gz"
```

### Multiple binaries from one repo (pi-mono)

```python
# pi.py
pkg = "badlogic/pi-mono"
binary = "pi"
asset = "*darwin*arm64*.tar.gz"
```

```python
# poom.py
pkg = "badlogic/pi-mono"
binary = "poom"
asset = "*darwin*arm64*.tar.gz"
```

## Non-Goals

- **Community registry**: Users write their own package files
- **Non-GitHub sources**: GitHub releases only
- **Dependency resolution**: Each package is independent
- **Rollback**: Replace-in-place, no version history kept
- **GUI**: CLI only
- **Windows support**: macOS and Linux only
