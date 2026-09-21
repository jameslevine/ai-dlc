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
