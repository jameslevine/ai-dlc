# Versioning

Two things in this repository are versioned, and they move independently.

| What | Tags | Consumers pin |
|---|---|---|
| The CLI and the workflows | `v1`, `v1.4.2` | `@v1` in their generated caller |
| Each content pack | `rules-python-v1`, `rules-python-v1.3.0` | a `pins:` entry in `.aidlc/config.yml` |

Separate namespaces because the two change for unrelated reasons. Improving a
rule should not force a CLI release, and a CLI bugfix should not imply that
anyone's rules changed. GitHub Actions does not parse tag semantics, so
`uses: owner/repo/.github/workflows/x.yml@rules-python-v1.3.0` is just a git
ref and this works.

One caveat to test before relying on it: Dependabot's Actions updater keys off
semver-looking tags and may not understand component-prefixed ones.

## Moving major tags

`v1` moves; `v1.4.2` does not. Consumers pin the major, so they receive
patches without doing anything and are never broken by a new major.

This means **immutable releases must stay disabled** for these tags. GitHub's
immutable releases cannot be moved or deleted, which is flatly incompatible
with the convention. That is a real trade-off: the guarantee we give up is
"this tag will always mean the same commit", and the one we keep is "consumers
get fixes without a pull request each".

Anyone who wants the stronger guarantee can pin a SHA in their caller.

## Why the release job rewrites refs

A relative `uses: ./.github/workflows/x.yml` inside a called workflow resolves
against the **caller's** repository, not this one. If the caller happens to
have a file at that path, theirs runs instead of ours, silently and with no
error. So every internal reference is fully qualified.

But `uses:` cannot take an expression, so those refs are literal strings that
would otherwise point at `main` forever, and a consumer pinning `@v1` would
still execute whatever `main` says today. `release.yml` therefore rewrites
every line marked `# aidlc:pin` to the release commit SHA before tagging.

This is not optional. Without it, pinning a version buys nothing.

## Making a breaking change

1. **Cut the new major.** Tag `v2.0.0`, create the moving `v2`. Leave `v1`
   where it is. Nobody breaks today, which is the entire point of major tags.
2. **Ship a bridge release on `v1`** that emits
   `echo "::warning::<what is changing> — see MIGRATION.md"` on every run.
   People see the deprecation in their own checks, not in a channel they have
   muted.
3. **Write the migration as a diff.** If the change is one line in a caller,
   include that line verbatim. State the reason as well as the deadline; a
   platform change with no visible motivation teaches people to resist the
   next one.
4. **Track adoption, not announcements.** `gh search code` for the old ref
   across your repositories, and `aidlc check` in each repo's CI is the
   per-repo signal. For a single maintainer this is a list, not a dashboard,
   and pretending otherwise would be theatre.
5. **End the old major loudly.** After the window, the final `v1` release
   fails with a pointed error and a link. A workflow that errors with
   "migrate to v2: <link>" costs five minutes. One that quietly stops running
   your type checker costs an outage.

## The knob ledger

Every configuration key is support burden: documentation, tests across six
ecosystems, and a deprecation when it eventually goes. The config surface is
capped at seven top-level keys.

The standing rule: **any key that has only ever been set to its default, in
every repository using it, is deleted at the next major.** The first answer to
"can we add a setting?" is "can the default just be better?".
