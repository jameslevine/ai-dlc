.PHONY: install lint test

install:
	uv sync --locked

lint:
	custom-linter --all

test:
	uv run pytest -x
