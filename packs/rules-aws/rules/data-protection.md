---
title: Encrypt every store, force TLS, keep secrets out of the template
globs: ["**/template.y*ml", "**/*.tf", "infra/**", "**/*stack*.py", "**/*stack*.ts"]
always: false
---

Enable encryption at rest on every store: `SSESpecification` on DynamoDB,
`BucketEncryption` on S3, `KmsMasterKeyId` on SQS and SNS, `KmsKeyId` on log
groups. Use a customer-managed key where the data is regulated, so the audit
trail shows who used it.

Deny plaintext transport in policy, not by convention: a bucket policy that
rejects `aws:SecureTransport: false`, and an API that serves HTTPS only. A
default that happens to be TLS today is not a control.

Reference secrets dynamically, `{{resolve:ssm-secure:...}}` or
`{{resolve:secretsmanager:...}}`, or fetch them at runtime from Parameter
Store or Secrets Manager. Never put a literal secret in
`Environment.Variables`: the template is committed, and the console shows the
value to anyone who can describe the function.

Set `PublicAccessBlockConfiguration` with all four flags true on every
bucket. List CORS origins by name; `*` exposes the API to any page on the
internet, and browsers reject it when credentials are involved anyway.
