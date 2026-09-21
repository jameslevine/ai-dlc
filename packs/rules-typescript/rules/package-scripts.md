---
title: Run work through package scripts, and match the project's package manager
globs: ["package.json", "**/*.ts", "**/*.tsx", "**/*.js"]
always: false
---

Use the scripts declared in `package.json` rather than invoking tools directly.
The script is what CI runs, so a command that works only when typed by hand is
a difference nobody notices until the pipeline disagrees.

Use the package manager the lockfile implies: `pnpm-lock.yaml` means pnpm,
`package-lock.json` means npm, `yarn.lock` means yarn. Mixing them produces a
second lockfile and two different dependency trees.

Install with the frozen variant in any automated context: `pnpm install
--frozen-lockfile`, `npm ci`, `yarn install --immutable`. A plain install can
quietly resolve versions the lockfile does not pin.
