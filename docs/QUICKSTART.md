# Quickstart

## Install

```bash
uv tool install --force /Users/james/Coding/ai-dlc
aidlc --version
```

Once this repository is pushed to GitHub, the same command works from anywhere:

```bash
uv tool install "git+https://github.com/jameslevine/ai-dlc@v1"
```

Reinstall after changing the CLI or a pack, since `uv tool install` copies
rather than links:

```bash
uv tool install --force /Users/james/Coding/ai-dlc
```

## Check your machine

```bash
aidlc doctor
```

Read-only. It groups checks by what each one enables, so a warning tells you
which capability is unavailable rather than just naming a missing binary. It
exits non-zero only when something genuinely required is missing, so `git` not
being installed fails and no AWS credentials does not.

## Try it without touching anything you care about

The safest test is a throwaway repository:

```bash
mkdir -p /tmp/aidlc-demo && cd /tmp/aidlc-demo
git init -b main .
printf '[project]\nname="demo"\nversion="0.1.0"\nrequires-python=">=3.12"\n[tool.ruff]\nline-length=100\n' > pyproject.toml

aidlc init
```

Then read what it produced. `AGENTS.md` is the canonical file every major
agent reads; the rest supplement it for one tool each.

## Try it on a real project, safely

Clone rather than running in place, so a surprise cannot touch real work:

```bash
git clone --depth 1 file:///Users/james/Coding/<project> /tmp/probe
cd /tmp/probe && aidlc init && git diff --stat
```

Use `git clone`, not `git worktree`. A worktree shares the real `.git`, so a
stray write lands in the actual repository's index.

When you are satisfied, run `aidlc init` in the real project and commit the
result. `.aidlc/profile.json` and `.aidlc/aidlc.lock` are meant to be
committed; they are what `aidlc check` compares against.

## The four commands

| Command | What it does |
|---|---|
| `aidlc init` | Detect the project and generate everything, once |
| `aidlc sync` | Regenerate after a pack, config or project change |
| `aidlc check` | Report drift. Writes nothing. Exits 1 if anything is stale |
| `aidlc eval` | Report what your rules cost, and which cannot be earning it |

## Convince yourself it is safe

These are worth running once, because the whole design rests on them.

**It is idempotent.** Running twice changes nothing:

```bash
aidlc sync && aidlc sync && git status --porcelain
```

**It will not overwrite your edits.** Change something inside the managed block
in `AGENTS.md`, then:

```bash
aidlc check     # exits 1 and names the file
aidlc sync      # refuses; your edit is still there
```

Pass `--force` only when you genuinely want your edit discarded.

**It notices when the project changes.** Add a new language and watch it be
detected:

```bash
mkdir worker && printf 'module example.com/worker\n\ngo 1.24\n' > worker/go.mod
aidlc check     # reports the new target
aidlc sync      # picks it up
```

**It stays inside the repository.** The test suite asserts this by running the
whole CLI with `HOME` pointed at an empty temporary directory and checking it
is still empty afterwards.

## If it refuses to run

**`.claude/skills exists and is not a symlink`** means another tool already
manages your skills. Either move that directory aside, or leave skills alone:

```yaml
# .aidlc/config.yml
schema: 1
emit:
  skills: false
```

**A pre-existing `CLAUDE.md`** is reported as a conflict and never modified.
It is worth knowing about: Claude Code reads `AGENTS.md` only when no
`CLAUDE.md` exists in that directory or above it, so while it is there, Claude
Code ignores the generated file. Other agents are unaffected.

**Existing workflows** are reported and never touched. `aidlc` only ever writes
`.github/workflows/aidlc.yml`.

## Reading `aidlc eval`

```
Context cost
  always-on rules      3
  AGENTS.md            ~713 tokens (estimate)

warning: idle-rule [rules-python:typing]: matches no file here (**/*.py).
```

The token figure is the number to watch. Every turn, in every session, in
every tool pays it.

This matters more than it might appear. ETH Zurich (arXiv:2602.11988, February
2026) tested agent context files across SWE-bench Lite and 138 tasks drawn from
repositories with real committed instruction files. They **did not generally
improve task success rate**, and they added **over 20% to token cost**.

So treat a growing rule set as a cost you are choosing, and treat `idle-rule`
warnings as deletion candidates. A tool that can only ever tell you to add more
instructions is not measuring anything.

## What does not work yet

`aidlc eval --tier 2`, the judged evals, is not implemented and says so.
Nothing writes to AWS yet, and there is no metrics collection. The CI workflows
exist and lint clean but have not run on GitHub, because this repository has no
remote.
