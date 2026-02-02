# TODO

Note: use [done] as a prefix for completed items.

1. Align install naming with SPEC: default installed name and hook binary_name should be the package filename stem; only install_as should override; for archive = False do not default to asset filename.
2. Implement verbose output, ANSI status/warn formatting, and download progress from IMPLEMENTATION.md (TTY spinner with percentage; non-TTY line logging), or update docs to match current behavior.
3. Update `ghrel list` output to include pinned status based on package files while keeping the command offline, or update SPEC.
4. Align CLI interface with IMPLEMENTATION.md (CLI dataclass with command field) or update docs to match the current tyro usage.
5. Normalize CLI output strings and warnings to match SPEC examples (ok vs checkmark, orphan/warn wording, and no-verify-hook messaging for up-to-date packages).
6. Align error messages and hints with documented examples (version-not-found hint about v prefix, ambiguous asset listing format, binary-not-found archive listing/hints, platform key errors with Levenshtein suggestions).
7. Update IMPLEMENTATION.md module structure to include `errors.py` and `py.typed`, or adjust code/docs to be consistent.
10. Support `asset` and `binary` as either `str` or `dict[str, str]` per SPEC, or update SPEC to reflect dict-only behavior. Currently implementation only accepts dicts.
11. Add warning when `asset` is omitted. SPEC says default to `"*"` with warning; implementation returns empty dict causing an error.
12. Add `(from <platform> key)` annotation in dry-run output when asset/binary resolved from a dict, per SPEC.
13. Default `binary` to package filename stem when omitted (for archives). Currently defaults to empty dict `{}` causing errors.
14. Warn when `asset` is a dict but `binary` is a string containing wildcards, per SPEC. (Only relevant if string support is added per item 10.)
8. Add missing tests/fixtures listed in IMPLEMENTATION.md (for example `tests/test_github.py` and `tests/fixtures/packages/`), or update docs.
9. Add `ty` to dev dependencies or update IMPLEMENTATION.md to reflect current tooling.
15. Validate platform dict keys against the allowed set (darwin-arm64, darwin-x86_64, linux-arm64, linux-x86_64), or update docs to reflect accepting arbitrary keys.
16. Acquire the state lock for `ghrel prune --dry-run` as stated in SPEC/IMPLEMENTATION, or update docs to reflect the current behavior.
