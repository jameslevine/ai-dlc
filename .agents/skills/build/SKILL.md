---
name: build
description: Implement an agreed plan while keeping an append-only log of decisions and the corrections a human made to them. Use when starting implementation, or when asked to "build" or "implement" an existing plan.
---

# Build against a plan

Read `ai-dlc/<NNN>-<slug>/plan.md` first. The unit of work is a GitHub
issue, not a criterion in a file: your brief names one (`Issue: #N`), and
everything you record goes on it.

## How to work

Take one issue at a time. For each: propose the approach, get it corrected
if it is wrong, implement it, and verify it by running something. Commit
with the issue in the message, `refs #N` while it is in progress and
`closes #N` when its acceptance criteria are met, so the reasoning and the
change never drift apart.

When you hit something the plan did not anticipate, write it down before acting
on it. The moment of surprise is the useful record; reconstructing it later
produces a tidier and less truthful account. A bug or todo you notice on the
way is filed with `gh issue create` and left for `pm`, not fixed in passing.

## The log

The log is the issue thread. Post each entry as a comment
(`gh issue comment N --body-file -`) rather than appending to a file; a
comment cannot be rewritten by the next session. Never rewrite an earlier
entry, including one that turned out to be wrong: a decision that was
reversed is more informative than one that was quietly deleted.

```markdown
## <YYYY-MM-DD> — <criterion>

**Decision:** <what was chosen>
**Proposed by:** agent | human
**Corrected:** <what the human changed, or "not corrected">
**Why:** <the reason, not the restatement>
**Verified by:** <the command that was actually run>
```

## What this is for

The corrections column is the point. It is the record of where the agent was
about to go wrong and a human redirected it, and reading a month of those
entries tells you which rules are missing far more reliably than introspection
does.
