# Run all checks
check: fmt lint types test

fmt:
    uv run ruff format src tests

lint:
    uv run ruff check --fix src tests

types:
    uvx ty check src

test:
    uv run pytest tests -v

