---
title: One role per function, no wildcards, no long-lived keys
globs: ["**/template.y*ml", "**/*.tf", "infra/**", "**/*stack*.py", "**/*stack*.ts"]
always: false
---

Give every function its own execution role. A shared role accumulates the
union of every function's permissions, so a bug in the least important
function carries the access of the most important one.

Never write `*` in `Action` or `Resource`. Name the actions the code calls and
the ARNs it calls them on. In SAM, prefer a policy template such as
`DynamoDBCrudPolicy` with a `TableName` over an inline statement, and never
attach `AdministratorAccess` to anything that runs code.

Add a `Condition` wherever one service is allowed to invoke another: restrict
by `aws:SourceArn` or `aws:SourceAccount`. Without it, any principal that can
reach the service can use your trust relationship.

Do not create IAM users with access keys for deployment. CI authenticates with
OpenID Connect and assumes a role scoped to one repository and branch. A
long-lived key is the credential that is still valid a year after the pipeline
that used it was deleted.
