---
name: orchestrate
description: Run an agreed plan by dispatching each acceptance criterion to the downstream agent that owns that part of the repository, then reviewing the result. Use when asked to orchestrate, run, or execute a plan across backend, frontend and infrastructure.
---

# Orchestrate a plan

Read `ai-dlc/<NNN>-<slug>/plan.md` first. You are the main session, and a
subagent cannot spawn subagents, so every dispatch, every review and every
commit is yours.

## Step 0: tickets

Always `pm` first. It files the epic and the child issues if they do not
exist yet, refreshes the ones that do, and returns the ordered list of open
issues with their numbers and which are blocked on a spike. That list is the
work; nothing else is.

## Spikes and refinement

For every ticket labelled `needs:spike` or `needs:refinement`, dispatch the
specialised agent for its area in refinement mode: `backend`, `frontend` or
`infra` by `area:` label, and `reviewer` for a cross-cutting question. Give
it a timebox, the ticket text and `pm`'s question verbatim. When its spike
comment lands on the issue, hand the ticket back to `pm` for prioritisation.
No build work starts on a ticket until `pm` has given it a priority.

## Dispatch

Build dispatch is one issue at a time, in `pm`'s order. Send each to
`backend`, `frontend` or `infra` when an agent of that name exists under
`.claude/agents/`, and to the general-purpose agent when none does.

A subagent starts with none of your context, so the brief has to stand alone:

- the issue number, as `Issue: #N`, and the issue body verbatim;
- the commands from `AGENTS.md` for that target, exactly as written;
- the titles of the rules that apply to the files it will touch, taken from
  the "Rules that apply to specific files" index;
- the instruction to report the exact verification command it ran, with the
  summary line, and to post that report as a comment on the issue.

Serial by default. Run issues in parallel only when their directories are
disjoint; two agents editing one directory produce a merge, not a result.

Any bug or todo a subagent reports is filed as an issue with
`gh issue create` before you continue. It is never carried in your own notes.

## Review

After each issue, run the `reviewer` agent on what it produced. Its findings
are corrections: send the severe ones back to the downstream agent before
moving on to the next issue. The log is the issue thread; there is no
`build.md`.

## Commit

A subagent never commits. After each issue, confirm its report against
`git diff --stat`: a file it did not mention, or one it mentioned that did not
change, is a discrepancy to resolve before anything is committed. Then commit
with `refs #N` while the issue is open and `closes #N` when its acceptance
criteria are met.
