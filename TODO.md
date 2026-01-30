# TODO

Note: use [done] as a prefix for completed items.

1. Align install naming with SPEC: default installed name and hook binary_name should be the package filename stem; only install_as should override; for archive = False do not default to asset filename.
2. Implement verbose output and download progress from IMPLEMENTATION.md (TTY spinner with percentage; non-TTY line logging), or update docs to match current behavior.
3. Update `ghrel list` output to include pinned status based on package files while keeping the command offline, or update SPEC.
4. Align CLI interface with IMPLEMENTATION.md (CLI dataclass with command field) or update docs to match the current tyro usage.
5. Normalize CLI output strings and warnings to match SPEC examples (ok vs checkmark, orphan/warn wording, and no-verify-hook messaging for up-to-date packages).
6. Align error messages and hints with documented examples (version-not-found hint about v prefix, ambiguous asset listing format, binary-not-found archive listing/hints).
7. Update IMPLEMENTATION.md module structure to include `errors.py` and `py.typed`, or adjust code/docs to be consistent.
8. Add missing tests/fixtures listed in IMPLEMENTATION.md (for example `tests/test_github.py` and `tests/fixtures/packages/`), or update docs.
9. Add `ty` to dev dependencies or update IMPLEMENTATION.md to reflect current tooling.
