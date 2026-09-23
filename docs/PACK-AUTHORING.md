# Authoring a pack

A pack is a directory under `packs/` that `aidlc` renders into a consumer
repository. This guide covers rule packs; skills follow the same layout under
`skills/<name>/SKILL.md`.

## Layout

```
packs/rules-fastapi/
  pack.yaml            # metadata, version, when it applies, what it emits
  rules/
    routing.md         # one rule per file; the filename is the rule id
    errors.md
```

The filename slug is the rule's stable id. It names the emitted files
(`.cursor/rules/rules-fastapi-routing.mdc`), so renaming a file is a change
consumers see even when the text is identical.

## `pack.yaml`

| field | meaning |
|---|---|
| `name` | must equal the directory name |
| `version` | the pack's own semver; see below |
| `kind` | `rules`, `skills`, `models`, `evals`, `lifecycle` or `mixed` |
| `summary` | one sentence, shown in listings |
| `requires` | `{aidlc: ">=1,<2"}`: the CLI range this pack was written against |
| `applies_when` | when detection selects the pack automatically |
| `emits` | `agents_md`, `cursor_rules`, `copilot_instructions`, `skills`, `mcp`, `claude_agents` |

`applies_when` takes one of three forms:

- `ecosystems: [python]`: selected when a target of that ecosystem exists.
- `frameworks: [fastapi, aws]`: selected when a target reports that framework
  (`boto3` implies `aws`, a SAM template implies `aws` and `sam`, and so on).
- `always: true`: selected for every repository, right after `core`.

Detection honours `always` directly. Ecosystem and framework selection goes
through the tables in `src/aidlc/detect/profile.py`, so a new pack needs a
row there as well as the declaration; the declaration is what a reader of the
pack sees, and the table is what a test pins. An explicit `packs:` list in a
consumer's `.aidlc/config.yml` replaces selection entirely.

## Rule frontmatter

```markdown
---
title: Annotate at the boundaries and keep the type checker clean
globs: ["**/*.py"]
always: false
---
```

- `title`: the sentence that appears in the AGENTS.md index. It must be
  unique across every shipped pack; the eval flags a repeat.
- `globs`: paths the rule applies to, in `fnmatch` form. `**/*.py` also
  matches a root-level file.
- `always`: `true` inlines the whole body into AGENTS.md, where every turn in
  every session pays for it. `false` costs one index line in AGENTS.md and a
  full copy in Cursor and Copilot, which load it only for matching files.

Default to `always: false`. The `core` pack is the only one that should carry
always-on rules, and its four are the whole working agreement.

## What `aidlc eval --tier 1` judges

| check | severity | fires when |
|---|---|---|
| `token-budget` | error | the always-on text exceeds the budget (default 1500 estimated tokens) |
| `unreachable-rule` | error | a rule is neither `always: true` nor has `globs`, so no tool can load it |
| `duplicate-rule` | warning | two rules share a title after whitespace and case are normalised |
| `idle-rule` | warning | a rule's globs match no file in the repository being evaluated |

An `idle-rule` warning in a consumer repository is a deletion candidate for
that consumer. An `idle-rule` warning in *this* repository, for a pack that
is always selected, means the globs are wrong: widen them to match a real
file here rather than accepting the warning.

## Voice

The reason this tool exists is the ETH Zurich finding (arXiv:2602.11988) that
instruction files add over 20% to token cost without reliably improving
outcomes. So every rule must earn its tokens:

- Imperative. State the rule, then the failure it prevents. A rule with no
  named failure is a preference, and preferences are cut first.
- Concrete enough that an agent can be caught violating it. "Write clean
  code" cannot be checked; "never return a stack trace to the client" can.
- Three to five short paragraphs. If a rule needs more, it is two rules.
- No filler, no motivation paragraphs, no restating the title.

`packs/rules-python/rules/typing.md` is the reference for tone and length.

## Bumping a version

Packs are versioned independently of the CLI (see `VERSIONING.md`). A change
to any file in the pack changes its digest and therefore the lockfile in every
consumer; the version says what kind of change it was.

- **patch**: wording tightened, a typo fixed, a glob widened. Consumers see
  a diff in generated files and nothing more.
- **minor**: a rule added, or a rule's scope extended to new paths.
- **major**: a rule removed or its meaning reversed, or a rule id renamed,
  because that deletes an emitted file a consumer may reference.

Bump `version` in `pack.yaml` in the same commit as the content change, and
tag it `<pack>-v<version>` at release. Then run `aidlc sync` in this
repository so its own generated files and lockfile follow.
