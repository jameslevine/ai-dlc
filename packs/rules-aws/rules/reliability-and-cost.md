---
title: Every function has limits, retries land in a DLQ, every resource is tagged
globs: ["**/template.y*ml", "**/*.tf", "infra/**", "**/*stack*.py", "**/*stack*.ts"]
always: false
---

Set `Timeout` and `MemorySize` explicitly on every function, sized from a
measurement rather than the default. The default timeout is three seconds,
which fails a cold start behind a VPC; the default memory buys the least CPU,
which is often the most expensive per request.

Give every asynchronous invocation a retry policy with backoff and a
`DeadLetterQueue` or an `OnFailure` destination. A failed event with nowhere
to go is dropped silently, and the first sign is a customer asking where their
order went.

Make writes idempotent with an idempotency key, so a retried event does not
create a second record. Powertools `@idempotent` on the handler is the
smallest correct implementation.

Declare a `LogGroup` for each function with `RetentionInDays` set. A log group
Lambda creates on its own retains forever, and that is where the bill grows
without anyone choosing it.

Tag every resource with `Project`, `Environment` and `Owner`, keep an
`AWS::Budgets::Budget` with a notification, and give every resource a one-line
comment in the template saying why it exists. A resource nobody can explain is
a resource nobody will delete.
