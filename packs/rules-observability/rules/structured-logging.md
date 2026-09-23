---
title: Log JSON with a correlation id, one event per line
globs: ["**/*.py", "**/*.ts"]
always: false
---

Emit logs as JSON with a request or correlation id on every line: AWS Lambda
Powertools `Logger` with `inject_lambda_context` in Python, pino or an
equivalent structured logger in Node. A log line that cannot be joined to the
request that produced it cannot be used to explain a failure.

Log one event per thing that happened, `order.created` or
`payment.declined`, with its facts as fields, not a line per statement in the
code. Narrating the code path costs money to ingest and hides the event that
matters among the ones that do not.

Never log personal data, tokens, passwords or full request bodies. Log the
identifier that lets you look the record up, not the record. A log store has
wider access and longer retention than the database it describes.

Take the log level from configuration, `LOG_LEVEL` or `POWERTOOLS_LOG_LEVEL`,
never from a literal in the code. Turning on debug logging in production
should be a configuration change, not a deploy.
