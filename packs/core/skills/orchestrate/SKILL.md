---
name: orchestrate
description: >-
  Run an agreed plan by dispatching each acceptance criterion to the downstream
  agent that owns that part of the repository, then reviewing the result. Use
  when asked to orchestrate, run, or execute a plan across backend, frontend
  and infrastructure.
---

# Orchestrate a plan

Read `ai-dlc/<NNN>-<slug>/plan.md` first. You are the main session, and a
subagent cannot spawn subagents, so every dispatch, every review and every
commit is yours.

## Group the work

Group the acceptance criteria by the target directory they touch. The targets
are listed at the top of `AGENTS.md`, each with the commands that verify it.

## Dispatch

For each group, dispatch one downstream agent: `backend`, `frontend` or
`infra` when an agent of that name exists under `.claude/agents/`, and the
general-purpose agent when none does.

A subagent starts with none of your context, so the brief has to stand alone:

- the criterion text, verbatim;
- the commands from `AGENTS.md` for that target, exactly as written;
- the titles of the rules that apply to the files it will touch, taken from
  the "Rules that apply to specific files" index;
- the instruction to report the exact verification command it ran, with the
  summary line.

Serial by default. Run groups in parallel only when their directories are
disjoint; two agents editing one directory produce a merge, not a result.

## Review

After each group, run the `reviewer` agent on what it produced. Its findings
are corrections: send the severe ones back to the downstream agent before
moving on to the next group.

## Log

Append one entry per criterion to `ai-dlc/<NNN>-<slug>/build.md`, in the
format the `build` skill defines, recording every correction the human made.
The corrections are the point of the log.

## Commit

A subagent never commits. After each group, confirm its report against
`git diff --stat`: a file it did not mention, or one it mentioned that did not
change, is a discrepancy to resolve before anything is committed. Then commit
the code and the log entry together.
