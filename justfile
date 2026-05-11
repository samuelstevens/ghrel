# Run all checks
check: fmt lint types test

fmt:
    uvx ruff format --preview src tests

lint:
    uvx ruff check --fix src tests

types:
    uvx ty check src

test:
    uv run pytest tests -v

# Run mutation testing with 8 parallel workers.
# Workers clone from git, so commit changes first.
mutate:
    #!/usr/bin/env bash
    set -euo pipefail
    rm -f session.sqlite
    uv run cosmic-ray init pyproject.toml session.sqlite
    uv run python -m cosmic_ray.tools.filters.operators_filter session.sqlite pyproject.toml
    uv run cr-http-workers pyproject.toml . &
    worker_pid=$!
    kill_tree() {
        local pid="$1"
        local child
        for child in $(pgrep -P "$pid" 2>/dev/null || true); do
            kill_tree "$child"
        done
        kill "$pid" 2>/dev/null || true
    }
    cleanup() {
        kill_tree "$worker_pid"
        wait "$worker_pid" 2>/dev/null || true
    }
    trap cleanup EXIT
    sleep 3
    uv run cosmic-ray baseline pyproject.toml
    uv run cosmic-ray --verbosity INFO exec pyproject.toml session.sqlite
    uv run cr-report session.sqlite
