"""Writing a render plan to disk, safely.

Two rules govern everything here, and both exist because this tool runs inside
repositories full of work it did not create:

1. **Nothing outside the target repository is ever touched.** Every path is
   resolved and checked to be inside the root before a write happens.
2. **Hand edits are never discarded.** A managed block whose content no longer
   matches its recorded digest stops the write and is reported. A whole file
   aidlc owns gets the same treatment, compared against the hash the lockfile
   recorded when it was last written.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from aidlc.render import blocks
from aidlc.render.emitters import Artifact, ArtifactKind
from aidlc.schemas.lock import LockedOutput, Lockfile


class Action(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class Change:
    """One artifact's outcome, whether or not it was actually written."""

    path: str
    action: Action
    detail: str = ""
    sha256: str = ""
    identifier: str | None = None

    @property
    def is_conflict(self) -> bool:
        return self.action is Action.CONFLICT

    @property
    def wrote(self) -> bool:
        return self.action in (Action.CREATED, Action.UPDATED)


class OutsideRootError(Exception):
    """An artifact path escaped the repository root.

    Only reachable through a malformed pack, but the check is unconditional
    because "never writes outside the repo" has to hold against bad input, not
    only against good input.
    """


def _resolve(root: Path, relative: str) -> Path:
    """Absolute path for an artifact, verified to be inside the repository.

    Only the *parent* is resolved. Resolving the full path would follow a
    symlink at the final component, so a link aidlc itself created would come
    back as its target directory and be misread as someone else's folder.
    Resolving the parent still defeats a `../` escape in the artifact path.
    """
    root_resolved = root.resolve()
    candidate = root_resolved / relative
    final = candidate.parent.resolve() / candidate.name

    if not final.is_relative_to(root_resolved):
        raise OutsideRootError(f"refusing to write outside the repository: {relative}")
    return final


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply(
    root: Path,
    artifacts: list[Artifact],
    *,
    dry_run: bool = False,
    allow_create_blocks: bool = False,
    force: bool = False,
    lock: Lockfile | None = None,
) -> list[Change]:
    """Write a plan, or report what writing it would do.

    ``allow_create_blocks`` is what separates `init` from `sync`: only `init`
    may add a managed block to a file that has none. A `sync` run in the wrong
    directory should do nothing rather than quietly annotate someone's README.

    ``lock`` is the previous run's lockfile, when there is one. It is how a
    whole-file artifact knows what aidlc last wrote there, and so whether the
    file on disk has been edited by hand since.
    """
    changes: list[Change] = []
    for artifact in artifacts:
        if artifact.kind is ArtifactKind.BLOCK:
            changes.append(
                _apply_block(
                    root, artifact, dry_run=dry_run, allow_create=allow_create_blocks, force=force
                )
            )
        elif artifact.kind is ArtifactKind.FILE:
            recorded = lock.output_for(artifact.path) if lock is not None else None
            changes.append(
                _apply_file(
                    root,
                    artifact,
                    dry_run=dry_run,
                    force=force,
                    recorded=recorded.sha256 if recorded is not None else None,
                )
            )
        elif artifact.kind is ArtifactKind.SYMLINK:
            changes.append(_apply_symlink(root, artifact, dry_run=dry_run))
    return changes


def _apply_block(
    root: Path, artifact: Artifact, *, dry_run: bool, allow_create: bool, force: bool
) -> Change:
    path = _resolve(root, artifact.path)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""

    result = blocks.upsert(
        existing,
        artifact.identifier,
        artifact.version,
        artifact.content,
        allow_create=allow_create,
        force=force,
    )

    action = {
        blocks.Outcome.CREATED: Action.CREATED,
        blocks.Outcome.UPDATED: Action.UPDATED,
        blocks.Outcome.UNCHANGED: Action.UNCHANGED,
        blocks.Outcome.CONFLICT: Action.CONFLICT,
        blocks.Outcome.ABSENT: Action.SKIPPED,
    }[result.outcome]

    detail = result.detail
    if result.outcome is blocks.Outcome.ABSENT:
        detail = f"{artifact.path} has no aidlc block; run `aidlc init` to add one."

    if action in (Action.CREATED, Action.UPDATED) and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result.text, encoding="utf-8")

    return Change(
        path=artifact.path,
        action=action,
        detail=detail,
        sha256=blocks.content_digest(artifact.content),
        identifier=artifact.identifier,
    )


def _apply_file(
    root: Path,
    artifact: Artifact,
    *,
    dry_run: bool,
    force: bool,
    recorded: str | None,
) -> Change:
    path = _resolve(root, artifact.path)
    digest = _sha256(artifact.content)

    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == artifact.content:
            return Change(path=artifact.path, action=Action.UNCHANGED, sha256=digest)

        # ``recorded`` is what aidlc last wrote here. A file that matches
        # neither that nor the new output was edited by hand in between, and
        # the rule is the same as for a block: refuse, and say so. A file with
        # no record was never written by aidlc, so there is nothing to compare
        # against and it is treated as ours to replace, exactly as before.
        if recorded is not None and _sha256(current) != recorded and not force:
            return Change(
                path=artifact.path,
                action=Action.CONFLICT,
                sha256=digest,
                detail=(
                    f"{artifact.path} has been edited by hand since aidlc generated it. "
                    "Move your changes into a pack, or re-run with --force to discard them."
                ),
            )
        action = Action.UPDATED
    else:
        action = Action.CREATED

    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.content, encoding="utf-8")

    return Change(path=artifact.path, action=action, sha256=digest)


def _apply_symlink(root: Path, artifact: Artifact, *, dry_run: bool) -> Change:
    path = _resolve(root, artifact.path)

    if path.is_symlink():
        if str(path.readlink()) == artifact.target:
            return Change(path=artifact.path, action=Action.UNCHANGED)
        if dry_run:
            return Change(path=artifact.path, action=Action.UPDATED)
        path.unlink()
    elif path.exists():
        # A real directory here is somebody's own skills folder, often managed
        # by a different tool. Replacing it with a link would delete their work.
        return Change(
            path=artifact.path,
            action=Action.CONFLICT,
            detail=(
                f"{artifact.path} exists and is not a symlink, so another tool "
                "is probably managing it. Either move it aside, or set "
                "`emit: {skills: false}` in .aidlc/config.yml to leave skills alone."
            ),
        )

    if dry_run:
        return Change(path=artifact.path, action=Action.CREATED)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(artifact.target, target_is_directory=True)
    return Change(path=artifact.path, action=Action.CREATED)


def to_locked_outputs(
    changes: list[Change], *, previous: Lockfile | None = None
) -> list[LockedOutput]:
    """Record generated outputs for the lockfile.

    A conflicted output keeps its entry from ``previous``: aidlc did not write
    it, so what it last wrote there is still the truth, and it is what the next
    run compares against. Dropping the entry would make the next `sync` see a
    file with no history and overwrite the very edit this run refused to.
    """
    outputs: list[LockedOutput] = []
    for change in sorted(changes, key=lambda c: c.path):
        if change.is_conflict:
            kept = previous.output_for(change.path) if previous is not None else None
            if kept is not None:
                outputs.append(kept)
        elif change.sha256:
            outputs.append(
                LockedOutput(
                    path=change.path,
                    kind="block" if change.identifier else "file",
                    sha256=change.sha256,
                    identifier=change.identifier,
                )
            )
    return outputs
