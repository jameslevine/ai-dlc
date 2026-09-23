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

Put only a secret's name or ARN in `Environment.Variables` and fetch the
value at runtime with Powertools `parameters.get_secret` or `get_parameter`,
cached with a `max_age`. A dynamic reference there is the failure it looks
like it avoids: CloudFormation does not support `ssm-secure` in Lambda
environment variables, and `{{resolve:secretsmanager:...}}` resolves at
deploy time into plaintext on the function configuration, shown to anyone
who can describe the function. Use dynamic references only for properties
CloudFormation resolves outside Lambda, such as an RDS master password.

Set `PublicAccessBlockConfiguration` with all four flags true on every
bucket. List CORS origins by name; `*` exposes the API to any page on the
internet, and browsers reject it when credentials are involved anyway.
