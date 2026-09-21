---
name: review
description: >-
  Close out a unit of work by comparing what shipped against what was planned,
  and turning what was learned into a concrete rule change. Use when finishing
  a piece of work, before opening a pull request, or when asked to "review" a
  completed unit.
---

# Review a completed unit of work

Write `ai-dlc/<NNN>-<slug>/review.md`.

## Sections

**Shipped versus planned.** Each acceptance criterion, and whether it was met,
dropped or changed. A dropped criterion needs a reason; a changed one needs the
new wording.

**What the checks said.** The actual result of the test suite, the linters and
any eval run. Paste the summary line rather than characterising it.

**Cost.** Roughly what this unit consumed, if the figure is available. Cheap
work that solved the problem and expensive work that solved the problem are
different outcomes and should not read identically.

**Rule changes this work suggests.** The section that closes the loop.

## The loop-closing section

This is the reason the lifecycle exists. Look back at the corrections logged in
`build.md` and ask which of them were a *general* failure rather than a
one-off. Each general one becomes a proposed change to a rule pack.

Propose deletions as readily as additions. Instruction files are known to add
over 20% to token cost without reliably improving task success, so a rule that
has not prevented a correction in months is costing you on every single turn
for nothing. Name it and delete it.

Write each proposal concretely enough to act on:

```markdown
- **Add** to `rules-python`: "Prefer pathlib over os.path" — corrected three
  times in builds 004, 006, 007.
- **Delete** from `core`: "Write clear code" — never referenced in any
  correction; unmeasurable and costs tokens on every turn.
```
