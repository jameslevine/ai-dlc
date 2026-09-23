---
title: Work starts from a ticket and progress lives on it
always: true
---

Every task maps to a GitHub issue before any code is written, and the commit
message carries its number: `refs #N` in progress, `closes #N` once the
acceptance criteria are met.

A bug or todo noticed mid-task is filed at once with `gh issue create` for
`pm` to prioritise, never parked in a note, a todo list or session memory;
those vanish with the session and the issue does not.

Decisions, human corrections and verification output are comments on the
issue, so nothing about progress lives only in a session.
