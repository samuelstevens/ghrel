# Project Conventions

- Use `uv run SCRIPT.py` or `uv run python ARGS` to run python instead of plain `python`.
- After making edits, run `uvx ruff format --preview .` to format the file, then run `uvx ruff check --fix .` to lint, then run `uvx ty check FILEPATH` to type check. Only do this if you think you're finished, or if you can't figure out a bug. Maybe linting will make it obvious. Don't fix linting or typing errors in files you haven't modified.

# Gathering Context

- Reference both SPEC.md and IMPLEMENTATION.md.

# Code Style

- Prefer immutable datastructures (dataclasses.dataclass(frozen=True), tuples, tp.NamedTuples, etc) over mutable where possible.
- Don't hard-wrap comments. Only use linebreaks for new paragraphs. Let the editor soft wrap content.
- Don't hard-wrap string literals. Keep each log or user-facing message in a single source line and rely on soft wrapping when reading it.
- Prefer negative if statements in combination with early returns/continues. Rather than nesting multiple positive if statements, just check if a condition is False, then return/continue in a loop. This reduces indentation.
- This project uses Python 3.12. You can use `dict`, `list`, `tuple` instead of the imports from `typing`. You can use `| None` instead of `Optional`.
- File descriptors from `open()` are called `fd`.
- Use types where possible, including `jaxtyping` hints.
- Decorate functions with `beartype.beartype`.
- Variables referring to a absolute filepath should be suffixed with `_fpath`. Filenames are `_fname`. Directories are `_dpath`.
- Prefer `make` over `build` when naming functions that construct objects, and use `get` when constructing primitives (like string paths or config values).
- Only use `setup` for naming functions that don't return anything.
- Source files are UTF-8 but must contain only ASCII characters. Do not use smart quotes, ellipses, em-dashes, emoji, or other non-ASCII glyphs. If you would use unicode to represent math, use pseudo-LaTeX instead in comments: 10⁶ should be 10^6, 3×10⁷ should be 3x10^7.
- Try to keep code short. Shorter code is in principle easier to read. If variable names are really long, shorten based on conventions in this codebase (..._indices -> ..._i). Since you use `uvx ruff format --preview`, if you can make a small variable name change to fit everything on one line, that's a good idea. When variables are used once, simply inline it.
- If you make edits to a file and notice that I made edits to your edits, note the changes I make compared to your initial version and explicitly describe the style of changes. Keep these preferences in mind as you write the rest of the code.
- Use asserts to validate assumptions frequently.
- Prefer `import x.y` over `from x import y`. This makes it immediately clear where each function comes from when reading code (e.g., `datasets.load_dataset()` vs `load_dataset()`), avoids name collisions, and makes grep-ing for usages unambiguous. Relative imports like `from . import module` are fine, but avoid `from .module import function`.
- Don't add complexity for marginal performance gains. Simpler code that's slightly slower is often better. Only optimize when profiling shows a real bottleneck.

# Git Workflow

- Before committing, run `git status` to check for already-staged files. If asked to commit only specific files, unstage everything first, then stage only the requested files, then after the commit, restage the already-staged files.
- Write single-line commit messages; never say you co-authored a commit.
- Never use `git stash`. It's error-prone and easy to lose work. Instead, create WIP commits and push to remote branches when you need to switch context or test old code.
- To test old code: commit current work as "wip: description", push to a (new) remote branch, then checkout the old commit.

# No hacks: ask for help instead

Due to the difficulty of implementing this codebase, we must strive to keep the code high quality, clean, modular, simple and functional; more like an Agda codebase, less like a C codebase.
Hacks and duct tape must be COMPLETELY AVOIDED, in favor of robust, simple and general solutions.
In some cases, you will be asked to perform a seemingly impossible task, either because it is (and the developer is unaware), or because you don't grasp how to do it properly.
In these cases, do not attempt to implement a half-baked solution just to satisfy the developer's request.
If the task seems too hard, be honest that you couldn't solve it in the proper way, leave the code unchanged, explain the situation to the developer and ask for further feedback and clarifications.
The developer is a domain expert that will be able to assist you in these cases.

# Testing

- Use pytest with fixtures and parameterization.
- Use Hypothesis for property-based tests, especially in helpers.
- Mark slow integration tests with `@pytest.mark.slow`.

---

Notes: The following guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 4. Goal-Driven Execution

Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

- "Add validation" -> "Write tests for invalid inputs, then make them pass"
- "Fix the bug" -> "Write a test that reproduces it, then make it pass"
- "Refactor X" -> "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
