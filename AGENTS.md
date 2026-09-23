<!-- aidlc:begin id=core version=core@0.2.0+rules-security@0.1.0+rules-python@0.1.0 digest=sha256:ec2586333c886acb -->
## This project

**Python**, managed with uv.

Run these exactly as written; they are what CI runs.

- install: `uv sync --locked`
- lint: `uv run ruff check .`
- typecheck: `uv run pyright`
- test: `uv run pytest`

## Working agreement

### Match the code that is already here

Read neighbouring code before writing new code. Follow the conventions you find
there over the conventions you prefer: naming, error handling, module layout,
test style.

Reuse what exists rather than adding a parallel implementation. If a helper
does almost what you need, extend it or call it; a second near-identical
function is a maintenance cost that compounds.

Do not add a dependency when the standard library covers the need. When a
dependency is genuinely warranted, say why in the commit message.

### Deliver the requested scope, no more and no less

Do the task as asked. Do not quietly widen it into adjacent refactors, and do
not quietly narrow it to the easy part.

If part of the work turns out to be blocked or wrong, finish everything else in
full and say explicitly what you left out and why. Scaling the work down is the
requester's decision, not yours.

If you disagree with the approach, say so in a sentence or two and then build
the thing that was asked for, under stated assumptions.

### Claims about the code must be verified

Before stating that something works, run it and read the output. Before stating
that a test passes, run the test. Before stating that a file contains
something, read the file.

When you cannot verify a claim, say so plainly in the same sentence as the
claim. "The tests pass" and "the tests should pass, I have not run them" are
different statements, and the difference is the whole value of the first one.

Report failures with the actual output. A summary of an error loses the detail
that identifies it.

## Rules that apply to specific files

- When editing `**/*.py`, `**/*.ts`, `**/*.tsx`: Validate at the boundary with a schema; reject, never coerce.
- When editing `**/*.py`, `**/*.ts`, `**/*.tsx`, `**/*.y*ml`, `.env*`, `**/*.json`: Secrets never enter the repository.
- When editing `**/pyproject.toml`, `**/package.json`, `**/uv.lock`, `**/package-lock.json`, `**/pnpm-lock.yaml`, `.github/workflows/*.y*ml`: Frozen installs, pinned actions, and a reason for every dependency.
- When editing `pyproject.toml`, `uv.lock`, `**/*.py`: Dependencies go through uv, never pip.
- When editing `tests/**/*.py`, `**/test_*.py`, `**/*_test.py`: Tests state what should be true, not what the code does.
- When editing `**/*.py`: Annotate at the boundaries and keep the type checker clean.

## Available skills

- **build** — Implement an agreed plan while keeping an append-only log of decisions and the corrections a human made to them. Use when starting implementation, or when asked to "build" or "implement" an existing plan.
- **orchestrate** — Run an agreed plan by dispatching each acceptance criterion to the downstream agent that owns that part of the repository, then reviewing the result. Use when asked to orchestrate, run, or execute a plan across backend, frontend and infrastructure.
- **plan** — Start a new unit of work by writing a plan the human corrects before any code is written. Use when beginning a feature, a fix, or any change worth more than a single commit, or when asked to "plan" something.
- **review** — Close out a unit of work by comparing what shipped against what was planned, and turning what was learned into a concrete rule change. Use when finishing a piece of work, before opening a pull request, or when asked to "review" a completed unit.
<!-- aidlc:end -->
