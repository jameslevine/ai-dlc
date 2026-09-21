# aidlc

A versioned, tool-agnostic AI development lifecycle.

One source of truth for agent instructions, skills, MCP configuration, CI/CD and
quality measurement. It installs into any repository, works under any IDE or CLI
agent, and with any model.

## What it does

`aidlc` reads a repository, works out what it is, and generates the agent and CI
configuration that repository needs. Then it measures whether that configuration
is actually helping.

```
aidlc init      # detect the project, write config and generate everything
aidlc sync      # regenerate after a rule or pack change
aidlc check     # no writes; exits 1 on drift. Use in CI and pre-commit
aidlc doctor    # what can this machine do?
```

## Two design commitments

**It never touches anything outside the repository you point it at.** No writes
to your home directory, no global configuration, no assumptions about what you
have installed. A test asserts this by running the whole CLI with `HOME` pointed
at an empty temporary directory and checking that the directory stays empty.

**It never clobbers your work.** Generated content lives between delimited
markers carrying a content digest. If you edit inside a managed block, `sync`
refuses rather than overwriting, and `check` fails so CI tells you. Files
`aidlc` did not create are read and reported, never modified.

## Why measure at all

ETH Zurich published a study in February 2026 (arXiv:2602.11988) testing agent
context files across SWE-bench Lite and 138 tasks drawn from repositories with
real, developer-committed instruction files. The files **did not generally
improve task success rate**, and they **added over 20% to token cost**.
Repository overviews, the thing most guides tell you to write first, were
specifically unhelpful.

That result is why this tool exists in the shape it does. Rules are versioned
artifacts with scores attached, token budget is a first-class metric, and the
expected honest outcome is that a rule set gets *smaller* over time. A tool that
can only ever tell you to add more instructions is not measuring anything.

## Status

Early. See `docs/` for the design, and `CHANGELOG.md` for what has landed.

## Licence

MIT.
