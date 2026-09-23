# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project uses [semantic versioning](https://semver.org/spec/v2.0.0.html).

Note that the CLI and the content packs are versioned **independently**, under
separate tag namespaces (`v1.2.3` for the CLI and workflows, `rules-python-v1.3.0`
for a pack). This file covers the CLI; each pack carries its own changelog.

## [Unreleased]

### Added

- Project skeleton: `src/` layout, hatchling build, ruff, pyright and pytest
  configuration, and a pre-commit config.
- `aidlc --version`.
- `aidlc doctor`: a read-only report of what the current machine can do,
  grouped by the capability each check enables. Exits non-zero only when a
  genuinely required tool is missing, so optional gaps do not fail CI.
- `aidlc.probe`: bounded, non-raising, side-effect-free subprocess helpers.
- `self-ci.yml` quality gate across Python 3.12 and 3.13, with every action
  pinned by commit SHA.
- Ecosystem detection for Python, Node/TypeScript, JVM, Go, Rust and .NET,
  behind a two-method adapter contract. Commands a project declares for itself
  take precedence over adapter defaults.
- The universal escape hatch: a config target with `setup: none` and explicit
  commands makes any language buildable with no adapter.
- Content packs with independent semver versions and content digests:
  `core`, `rules-python`, `rules-typescript`, `rules-react`, `rules-java`.
- Emitters for AGENTS.md, `.agents/skills/` (with a `.claude/skills` symlink),
  `.cursor/rules/*.mdc`, `.github/instructions/*.instructions.md` and MCP
  configuration fan-out. No CLAUDE.md and no slash commands are generated.
- `aidlc init`, `aidlc sync` and `aidlc check`, with managed blocks that refuse
  to overwrite hand edits, and a committed profile and lockfile.
- Reusable workflows: `aidlc-ci.yml` (the dispatcher consumers call),
  `reusable-lang-ci.yml` (one generic build workflow for all six ecosystems)
  and `reusable-secret-scan.yml`.
- `aidlc ci matrix`, which turns a committed profile into a build matrix.
- A generated caller workflow of about twenty lines, pinned to the platform's
  major tag and declaring its own permissions.
- `release.yml`, which rewrites internal workflow references to the release
  commit SHA before tagging, and refuses to tag if any remain unpinned.
- `VERSIONING.md`, covering the two tag namespaces and the breaking-change
  process.
- `aidlc eval --tier 1`: deterministic checks that run on every commit. A
  token budget on the always-loaded context, plus detection of rules that are
  unreachable, duplicated, or match no file in the repository. Reports the
  estimated context cost whether or not anything fails.
- An `audit` build step, between `test` and `build`, for dependency
  vulnerability scanning. uv projects run `pip-audit` from an ephemeral
  environment; npm, pnpm and yarn run their manager's own `audit`. A Makefile
  target or npm script named `audit` is honoured over the default.
- An `infra` adapter: a directory holding a SAM or CloudFormation template,
  a `samconfig.toml`, or Terraform files is a target of its own, linted with
  `cfn-lint` or `terraform fmt -check`. It selects the AWS and observability
  packs. CDK apps stay with the language adapters that already build them.
- Python typecheck detection from dependencies: `pyright` or `mypy` declared
  in a dependency group is enough to add the step, so a project no longer
  needs a `[tool.pyright]` table it has nothing to put in.
- Packs `rules-fastapi`, `rules-aws`, `rules-observability` and
  `rules-security`, written for a React + FastAPI + SAM service built along
  the Well-Architected pillars. Every rule is conditional, so each costs one
  index line in AGENTS.md. `rules-security` declares `applies_when: always`
  and detection now honours that flag, so it is selected for every repository.
- `docs/PACK-AUTHORING.md`: pack layout, manifest fields, rule frontmatter
  and what `always` costs, what `aidlc eval --tier 1` judges, the voice
  guideline, and how to bump a pack version.
- Claude Code subagents: a pack can ship `agents/<name>.md`, rendered to
  `.claude/agents/<name>.md` when the pack emits `claude_agents` and
  `emit.agents` is on. `core` gains the `reviewer` agent and the `orchestrate`
  skill.
- Whole-file outputs now refuse a hand edit on `sync`, as managed blocks
  already did, by comparing the file against the hash the lockfile recorded.
- `backend`, `frontend` and `infra` agents, shipped by `rules-fastapi`,
  `rules-react` and `rules-aws` respectively, so the `orchestrate` skill has a
  named agent for each target it dispatches to. Each is granted the MCP servers
  it needs (`context7`, `aws-docs`, `playwright`, `github`) and works without
  any that are not configured. Express and Fastify projects now select the
  observability pack, as FastAPI already did.

### Fixed

- Updating a managed block no longer strips the newline after its closing
  marker, which had `sync` and the end-of-file pre-commit hook taking turns
  changing AGENTS.md.
- AGENTS.md now lists every CI step for each target, in the order CI runs
  them. `format` and `audit` were left out by a hard-coded list, which made
  "they are what CI runs" false.
