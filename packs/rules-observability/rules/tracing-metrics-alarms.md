---
title: Trace every hop, emit business metrics, alarm on what users feel
globs: ["**/*.py", "**/*.ts", "**/template.y*ml", "**/*.tf"]
always: false
---

Set `Tracing: Active` on every function and `TracingEnabled: true` on every
REST API (`AWS::Serverless::Api`); an HTTP API has no X-Ray, so give it
`AccessLogSettings` instead. Decorate handlers with Powertools `Tracer` and
patch outbound clients so that DynamoDB, SQS and HTTP calls appear as
subsegments. A trace that stops at the function boundary cannot say which
dependency was slow.

Record business metrics with Powertools `Metrics`, which writes Embedded
Metric Format to the log so that no metric call can fail or add latency.
Invocation counts and errors come for free; `OrdersCreated` and
`PaymentsDeclined` do not, and they are the numbers that say whether the
service is doing its job.

Serve `/health` so that the deploy pipeline and the load balancer can confirm
the service is up without exercising a dependency.

Create at least one CloudWatch alarm per user-facing path: one on the error
rate and one on p95 latency, each with its `Threshold` stated in the template
rather than chosen at the console. Give every alarm an `AlarmDescription` that
says what to check first. An alarm that fires with no instruction is paged
once and ignored thereafter.
