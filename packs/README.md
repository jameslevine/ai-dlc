# Packs

Content packs: the rules, skills, lifecycle templates and model config that
`aidlc` renders into a consumer repository.

Packs are the artifact under test. Each carries its own semver version and is
identified in eval records by `name@version+digest`, so a score can always be
traced back to the exact bytes that produced it.

A pack is a directory containing `pack.yaml` plus whatever its `kind` implies:

| kind | contains |
|---|---|
| `rules` | `rules/*.md` with `title`, `globs`, `always` frontmatter |
| `skills` | `skills/<name>/SKILL.md` |
| `models` | `models.yml` |
| `evals` | `cases/*.yaml` |
| `lifecycle` | `lifecycle/*.md.j2` |

These ship inside the wheel as package data and are read with
`importlib.resources`, never by path arithmetic from `__file__`.

See `docs/PACK-AUTHORING.md` for the authoring guide.
