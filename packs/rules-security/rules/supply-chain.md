---
title: Frozen installs, pinned actions, and a reason for every dependency
globs: ["**/pyproject.toml", "**/package.json", "**/uv.lock", "**/package-lock.json", "**/pnpm-lock.yaml", ".github/workflows/*.y*ml"]
always: false
---

Install from the lockfile in CI: `uv sync --locked`, `npm ci`, `pnpm install
--frozen-lockfile`. An unfrozen install resolves whatever was published last
night, so the build that passed and the build that deploys can differ in
packages nobody chose.

Pin every third-party GitHub Action to a full commit SHA, with the tag in a
comment on the same line: `uses: actions/checkout@<sha> # v4.2.2`. A tag can
be moved to point at anything; a SHA cannot.

The `audit` CI step must pass. Suppress an advisory only with its identifier
and a reason in the same file, so the next person can see whether the reason
still holds. A blanket ignore is an audit step that reports nothing.

Never pipe `curl` into a shell unless the URL is a pinned, immutable ref and
the script's checksum is verified. Add a dependency with a one-line reason in
the commit message; a package nobody can explain is one nobody will remove
when it is abandoned.
