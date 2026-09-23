---
title: Errors leave the API as structured responses, never as stack traces
globs: ["**/*.py"]
always: false
---

Raise `HTTPException` with a `detail` that is a mapping, `{"code": ...,
"message": ...}`, not a free-text string. Clients branch on `code`; a message
that is reworded later must not break them.

Register an `@app.exception_handler` for each domain error type, so that the
mapping from `OrderNotFound` to 404 exists in one place. A `try`/`except` in
every route drifts, and one of them ends up returning 500.

Never return a stack trace, a library's exception message, or an internal
identifier such as a table name or an ARN to the client. Those are
reconnaissance for an attacker and noise for a user. Log them; respond with
the structured detail.

Leave FastAPI's 422 validation response alone. Clients and tests already
depend on its shape, and a handler that reformats it is a second contract to
maintain.

Log the exception with the request id before converting it to a response. A
500 with no correlated log line cannot be reproduced.
