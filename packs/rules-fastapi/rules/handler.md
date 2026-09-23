---
title: One Mangum handler, nothing at import time, settings from the environment
globs: ["**/*.py", "**/template.y*ml"]
always: false
---

Expose the ASGI app to Lambda with `handler = Mangum(app)` in one module, and
point the function's `Handler` in the template at it. Hand-written event
parsing beside the app is a second router that disagrees with the first.

Do no network or filesystem work at import time: no client that opens a
connection, no read from S3 or Parameter Store, no table scan. Module import
runs on every cold start, and anything that fails there fails before a single
request can be logged.

Read configuration through a `pydantic-settings` `BaseSettings` subclass with
typed fields, constructed lazily behind a dependency. `os.environ[...]`
scattered through the code has no default, no validation and no single place
that says what the service needs.

Serve `GET /health` from a route that does no I/O and returns a fixed body. It
exists so a deploy can be confirmed alive independently of every downstream
dependency; a health check that touches the database reports the database,
not the service.
