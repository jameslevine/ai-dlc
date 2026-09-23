.PHONY: install lint test

install:
	uv sync --locked

lint:
	cfn-lint template.yaml

test:
	uv run pytest
