---
title: Routers per domain, Pydantic models at every boundary
globs: ["**/*.py"]
always: false
---

Put each domain's routes on its own `APIRouter` and mount them in `main.py`
with `include_router`. A single module holding every route is where two people
editing different features collide on the same file.

Declare request and response bodies as Pydantic models, never as bare `dict`.
Declare the return type (or `response_model`) and an explicit `status_code`
on every route. A route without a response model returns whatever the handler
happened to build, and the OpenAPI document stops describing what the client
actually receives.

Obtain shared concerns through `Depends`: the current user, the database
session, the settings object. A module-level global is created at import time,
cannot be overridden in a test, and is the first thing that breaks when a
second entry point shares the module.

Declare a route `async` only when its body awaits something. An `async def`
that calls a blocking client runs on the event loop thread and stalls every
other request for the duration of the call.
