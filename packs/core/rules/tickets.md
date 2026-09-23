---
title: Work starts from a ticket and progress lives on it
always: true
---

Every task maps to a GitHub issue before any code is written, and the issue
number appears in the commit message: `refs #N` while in progress, `closes #N`
when the acceptance criteria are met.

A bug or todo noticed mid-task is filed immediately with `gh issue create` and
left for `pm` to prioritise. It is never kept in a note, a todo list or session
memory; those vanish with the session, and the issue does not.

Decisions, human corrections and verification output are recorded as comments
on the issue, so nothing about progress lives only in a session.
