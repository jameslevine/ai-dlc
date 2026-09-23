---
title: Validate at the boundary with a schema; reject, never coerce
globs: ["**/*.py", "**/*.ts", "**/*.tsx"]
always: false
---

Parse every input that crosses a trust boundary through a schema: Pydantic
models in Python, zod in TypeScript. Request bodies, query strings, headers,
queue messages and webhook payloads all count. Code past the boundary then
handles typed values, not whatever arrived.

Reject input that does not match; do not coerce it into shape. A string
`"123"` silently becoming the integer `123` is how a field meant as an
identifier becomes an amount. Use strict mode where the library offers it.

Query the database only through an ORM or a parameterised query. Never build
SQL, a shell command or a filesystem path by concatenating user input; the
concatenation is the injection.

Allowlist CORS origins by name. Set an explicit maximum body size on the
server or the gateway, so that a request cannot exhaust memory before
validation even runs.
