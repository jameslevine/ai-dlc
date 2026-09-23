#!/usr/bin/env bash
# Cut a release from this machine: the same steps as .github/workflows/release.yml,
# in the same order, with the same guards.
#
# Why this exists: the Actions GITHUB_TOKEN may not push a commit that touches a
# workflow file, and the release commit rewrites `# aidlc:pin` refs inside
# .github/workflows/*.yml. GitHub rejects the tag push with "refusing to allow a
# GitHub App to create or update workflow ... without `workflows` permission",
# and `workflows` cannot be granted through `permissions:`. release.yml works
# with a fine-grained PAT in the RELEASE_TOKEN secret; without one, run this.
#
# The release commit lives only on the tags. `main` is never advanced, so the
# refs on `main` keep pointing at `main` and the next release rewrites them
# again. See VERSIONING.md, "Why the release job rewrites refs".
#
# Usage: scripts/release.sh <version>    e.g. scripts/release.sh 1.2.0
set -euo pipefail

step() { printf '\n==> %s\n' "$*"; }
die() { printf 'release: %s\n' "$*" >&2; exit 1; }

version="${1:-}"
[[ $# -eq 1 ]] || die "usage: scripts/release.sh <version>   (e.g. 1.2.0, no leading v)"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "version must look like 1.2.0, got '${version}'"
major="v${version%%.*}"

cd "$(git rev-parse --show-toplevel)"

# --- Guards: the release is cut from exactly what is on origin/main. -----------
step "Checking the working tree, branch and remote"
[[ -z "$(git status --porcelain)" ]] || die "working tree is dirty; commit or stash first"
branch="$(git branch --show-current)"
[[ "$branch" == "main" ]] || die "on branch '${branch}', releases are cut from main"
git fetch origin
[[ "$(git rev-parse main)" == "$(git rev-parse origin/main)" ]] ||
  die "main is not equal to origin/main; pull or push first"
sha="$(git rev-parse HEAD)"
echo "Releasing v${version} (major tag ${major}) from ${sha}"

# --- Same checks as release.yml's "Verify" step. ------------------------------
step "uv sync --locked"
uv sync --locked
step "uv run pytest"
uv run pytest
step "uv run aidlc check"
uv run aidlc check

# --- From here on the tree is modified; undo on any failure. ------------------
# The release commit goes on a detached HEAD so that main is never advanced.
# On failure, restore the workflow files and return to main. Any local tag
# created in this run is deleted, so a re-run starts from the same place.
tagged=""
pushed=""
cleanup() {
  status=$?
  trap - EXIT
  if [[ $status -ne 0 ]]; then
    echo
    echo "release: failed with exit ${status}; restoring the working tree" >&2
    git checkout -q -- .github/workflows || true
    git checkout -q main || true
    if [[ -n "$tagged" && -z "$pushed" ]]; then
      git tag -d "v${version}" >/dev/null 2>&1 || true
      echo "release: local tag v${version} deleted; ${major} was not pushed" >&2
    fi
  fi
  exit "$status"
}
trap cleanup EXIT

step "Detaching HEAD at ${sha} so main is not advanced"
git checkout -q --detach "$sha"

step "Pinning internal references to ${sha}"
# GNU sed takes `-i`; BSD sed (macOS) needs `-i ''`. `sed --version` only
# succeeds on GNU.
if sed --version >/dev/null 2>&1; then
  sed_in_place=(sed -i -E)
else
  sed_in_place=(sed -i '' -E)
fi
# Rewrite the ref on every line marked `# aidlc:pin`.
find .github/workflows -name '*.yml' -print0 |
  xargs -0 "${sed_in_place[@]}" "s|(uses: jameslevine/ai-dlc/[^@]+)@[^ ]+( # aidlc:pin)|\1@${sha}\2|"

echo "Rewritten references:"
grep -rn 'aidlc:pin' .github/workflows || true

# A remaining `@main` on a pinned line means the rewrite missed it, which
# would ship a release that silently tracks main. The match is anchored on a
# `uses:` line so this file's own text cannot trip it.
if grep -rnE '^[[:space:]]*(- )?uses: [^[:space:]]+@main # aidlc:pin' .github/workflows; then
  die "a pinned reference still points at main"
fi

# A relative internal reference would resolve against the consumer's
# repository. This must never ship.
if grep -rnE '^[[:space:]]*uses: \./' .github/workflows; then
  die "relative uses: found; these resolve against the caller"
fi

step "Committing release: v${version} (detached; main is untouched)"
git commit -q -am "release: v${version}"
git --no-pager log --oneline -1

# The exact version is immutable; the major moves so that consumers pinning
# @v1 receive this release without changing anything.
step "Tagging v${version} and moving ${major}"
git tag -a "v${version}" -m "release: v${version}"
tagged=1
git tag -f "$major"

step "Pushing tags"
git push origin "v${version}"
pushed=1
git push origin -f "$major"

step "Returning to main"
git checkout -q main
git status --short
echo
echo "Released v${version}: ${major} -> $(git rev-parse --short "${major}^{commit}"), main still at $(git rev-parse --short main)"
