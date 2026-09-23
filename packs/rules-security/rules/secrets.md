---
title: Secrets never enter the repository
globs: ["**/*.py", "**/*.ts", "**/*.tsx", "**/*.y*ml", ".env*", "**/*.json"]
always: false
---

Never commit a secret: no API key, token, password, private key or connection
string, in code, config, fixtures or CI files. A secret in git history is
visible to everyone who ever clones the repository, including forks you do
not know about.

Keep `.env` files in `.gitignore` and commit a `.env.example` that lists every
key with a placeholder value. The example documents what the process needs;
the real values are never in the tree.

Read secrets from the platform, not from the tree: CI from the repository's
secret store, local from `.env`. On Lambda the platform injects only a
*reference*, the secret's name or ARN in the environment, and the code
fetches the value at runtime from Secrets Manager or Parameter Store. Code
that reads a secret from a file it ships is code that ships the secret.

Treat a leaked secret as compromised the moment it is committed. Rotate it,
then clean the history; removing the commit alone leaves the value valid in
every existing clone.

`gitleaks` runs in CI. Its failure is a finding, not a false positive, until
someone has read the matched line and can say why it is not a secret.
