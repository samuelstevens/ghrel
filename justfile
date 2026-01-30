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

