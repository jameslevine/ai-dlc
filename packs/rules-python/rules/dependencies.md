---
title: Dependencies go through uv, never pip
globs: ["pyproject.toml", "uv.lock", "**/*.py"]
always: false
---

Add dependencies with `uv add`, development ones with `uv add --dev`. Run
project commands through `uv run` so they use the locked environment.

Never run `pip install` in a uv project. It writes into the environment without
updating `uv.lock`, so the next `uv sync --locked` silently removes whatever
you installed and the failure appears somewhere unrelated.

Never edit `uv.lock` by hand.
