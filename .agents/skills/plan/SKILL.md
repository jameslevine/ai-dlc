---
name: plan
description: Start a new unit of work by writing a plan the human corrects before any code is written. Use when beginning a feature, a fix, or any change worth more than a single commit, or when asked to "plan" something.
---

# Plan a unit of work

Produce `ai-dlc/<NNN>-<slug>/plan.md`, where `NNN` is the next unused
three-digit number in `ai-dlc/`.

## Steps

1. **Restate the intent** in two or three sentences, in your own words. If your
   restatement differs from what was asked, you have found an ambiguity worth
   raising now rather than after the work.

2. **Ask the questions that change the design.** Not a checklist of everything
   unclear: only the points where two reasonable readings lead to materially
   different work. Write the answers into the plan. Unanswered questions stay
   in the file marked as assumptions.

3. **Name what is out of scope.** An empty out-of-scope list usually means the
   boundaries were never examined.

4. **Write acceptance criteria that map to something runnable.** "Handles bad
   input gracefully" is not a criterion. "Returns 422 with a field-level error
   body when `amount` is negative, covered by a test" is.

## Template

```markdown
---
id: <NNN>-<slug>
status: planned
created: <YYYY-MM-DD>
---

# <Title>

## Intent
<two or three sentences>

## Questions and answers
| Question | Answer |
|---|---|

## Out of scope
- <thing deliberately not done>

## Acceptance criteria
- [ ] <criterion that maps to a test or command>

## Assumptions
- <anything answered by assumption rather than by the human>
```

## The gate

Do not start building until a human has read the plan and corrected at least
something. A plan that comes back untouched usually means it was not read, and
an unread plan provides none of the value the step exists for.
