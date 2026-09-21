---
title: Types describe intent; never reach for any
globs: ["**/*.ts", "**/*.tsx"]
always: false
---

Type the exported surface of every module explicitly. Inference is fine inside
a function and unhelpful across a boundary, where the annotation is the
documentation.

`any` disables checking for everything downstream of it. Use `unknown` and
narrow, or write the type. When a third-party library genuinely has no types,
declare the shape you rely on rather than casting the whole value.

Prefer a discriminated union over optional fields that are only valid in
certain combinations. `{ status: "ok"; data: T } | { status: "error"; error: E }`
makes the invalid state unrepresentable; `{ data?: T; error?: E }` invites the
bug where both are set.
