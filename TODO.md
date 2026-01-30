# TODO

Note: use [done] as a prefix for completed items.

1. Align hook API with SPEC/IMPLEMENTATION: load `ghrel_post_install` and `ghrel_verify` (keyword-only args) instead of `pre_install`/`post_install`, or update docs to match current hook names/signatures.
2. Fix hook execution order to match docs: install -> ghrel_post_install (with extracted_dir still present) -> cleanup -> ghrel_verify -> write state.
3. Ensure state is only written after hooks succeed (currently state is written before post_install and there is no verify hook).
4. Restore default install naming to package filename stem (and use `install_as` to override), not binary basename/asset name.
5. Add missing verify-hook warning output ("installed ... (no verify hook)") and ensure verify runs on both install and update.
6. Implement verbose mode and download progress behavior described in IMPLEMENTATION.md, or update docs to match current output.
7. Update `ghrel list` output to include pinned status (and confirm how to detect pinned versions while staying offline) or adjust docs.
8. Normalize CLI output strings and warning labels to match SPEC examples (ok vs checkmark, orphan/warn wording).
9. Align error messages/hints with documented examples (version-not-found hint about v prefix, ambiguous asset listing format, binary-not-found hint to use explicit path).
