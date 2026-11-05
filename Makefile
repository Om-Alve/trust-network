.PHONY: check fmt test

check:
	uv run ruff format --check . && uv run ruff check . && uv run pytest -q

fmt:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest -q
