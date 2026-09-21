"""`aidlc init`, `aidlc sync` and `aidlc check`.

These three share almost all of their behaviour and differ in exactly two
dimensions, which is why they live together: whether they may create a managed
block in a file that has none, and whether they may write at all.

| command | creates blocks | writes | exit code |
|---|---|---|---|
| `init`  | yes | yes | 1 on conflict |
| `sync`  | no  | yes | 1 on conflict |
| `check` | no  | no  | 1 on any drift |
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from aidlc.detect import detect
from aidlc.render import plan
from aidlc.render.materialize import Action, Change, apply, to_locked_outputs
from aidlc.schemas.config import Strictness
from aidlc.workspace import (
    Workspace,
    WorkspaceError,
    build_lock,
    find_root,
    profile_digest,
)

#: Written on `init` only. Commented rather than empty so that the available
#: settings are discoverable without reading documentation, and minimal so that
#: a repository which needs nothing declares nothing.
_STARTER_CONFIG = """\
# aidlc configuration. Every key is optional; absent means platform defaults.
#
# strictness: standard | strict   (strict fails CI on profile drift)
# packs:      explicit pack list; omit to let detection choose
# pins:       exact pack versions, e.g. {rules-python: "1.2.0"}
# emit:       {skills: true, cursor: true, copilot: true, mcp: true}
# detect:     {ignore: ["vendor"]}
# targets:    per-directory overrides, and the escape hatch for any language
# mcp:        MCP servers, fanned out to every client's own config format

schema: 1
"""


@dataclass(slots=True)
class Report:
    """What a run did, in a form the caller can render or assert on."""

    changes: list[Change]
    profile_drifted: bool
    profile_diff: str = ""

    @property
    def conflicts(self) -> list[Change]:
        return [c for c in self.changes if c.is_conflict]

    @property
    def written(self) -> list[Change]:
        return [c for c in self.changes if c.wrote]

    @property
    def drifted(self) -> bool:
        return self.profile_drifted or bool(self.written) or bool(self.conflicts)


def _run(
    root: Path,
    *,
    write: bool,
    allow_create_blocks: bool,
    force: bool = False,
) -> Report:
    """The shared body of all three commands."""
    workspace = Workspace(root=root)
    config = workspace.config()

    fresh = detect(root, config)
    stored = workspace.stored_profile()
    drifted = stored is not None and profile_digest(stored) != profile_digest(fresh)

    packs = workspace.packs(fresh.packs_selected)
    artifacts = plan(packs, fresh, config)

    changes = apply(
        root,
        artifacts,
        dry_run=not write,
        allow_create_blocks=allow_create_blocks,
        force=force,
    )

    if write:
        # The profile and lockfile are written even when an artifact conflicted.
        # A conflict on one optional emitter must not leave the workspace
        # half-generated with no profile, because `check` would then be unable
        # to run at all and the repository would be stuck. The conflict is still
        # reported and still makes the command exit non-zero; the lockfile
        # simply records what was actually written.
        workspace.write_profile(fresh)
        workspace.write_lock(build_lock(fresh, packs, to_locked_outputs(changes)))

    diff = ""
    if drifted and stored is not None:
        diff = _profile_summary(stored, fresh)

    return Report(changes=changes, profile_drifted=drifted, profile_diff=diff)


def _profile_summary(old, new) -> str:
    """Describe profile drift in terms someone can act on.

    A JSON diff would be accurate and unreadable. What matters is which
    targets and packs appeared or vanished.
    """
    lines: list[str] = []

    old_targets = {t.path for t in old.targets}
    new_targets = {t.path for t in new.targets}
    for path in sorted(new_targets - old_targets):
        lines.append(f"  + target {path}")
    for path in sorted(old_targets - new_targets):
        lines.append(f"  - target {path}")

    old_packs, new_packs = set(old.packs_selected), set(new.packs_selected)
    for name in sorted(new_packs - old_packs):
        lines.append(f"  + pack {name}")
    for name in sorted(old_packs - new_packs):
        lines.append(f"  - pack {name}")

    if not lines:
        lines.append("  target details changed (commands or versions)")
    return "\n".join(lines)


def _print(changes: list[Change], *, verb: str) -> None:
    interesting = [c for c in changes if c.action is not Action.UNCHANGED]
    if not interesting:
        print("Everything is up to date.")
        return

    for change in sorted(interesting, key=lambda c: c.path):
        if change.is_conflict:
            print(f"  conflict  {change.path}")
            print(f"            {change.detail}")
        elif change.action is Action.SKIPPED:
            print(f"  skipped   {change.path}")
            if change.detail:
                print(f"            {change.detail}")
        else:
            print(f"  {change.action.value:<9} {change.path}")

    written = sum(1 for c in changes if c.wrote)
    if written:
        print(f"\n{verb} {written} file{'s' if written != 1 else ''}.")


def init(path: Path | None = None, *, force: bool = False) -> int:
    """Detect the project and generate everything for the first time."""
    root = find_root(path or Path.cwd())
    workspace = Workspace(root=root)

    try:
        if not workspace.config_path.exists():
            workspace.aidlc_dir.mkdir(parents=True, exist_ok=True)
            workspace.config_path.write_text(_STARTER_CONFIG, encoding="utf-8")
            print(f"Wrote {workspace.config_path.relative_to(root)}")

        report = _run(root, write=True, allow_create_blocks=True, force=force)
    except WorkspaceError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _print(report.changes, verb="Wrote")

    profile = workspace.stored_profile()
    if profile is not None and profile.conflicts:
        print("\nLeft alone (aidlc will not modify these):")
        for conflict in profile.conflicts:
            print(f"  {conflict.path}")
            print(f"    {conflict.note}")

    return 1 if report.conflicts else 0


def sync(path: Path | None = None, *, force: bool = False, dry_run: bool = False) -> int:
    """Regenerate after a pack, config or project change."""
    root = find_root(path or Path.cwd())
    workspace = Workspace(root=root)

    if not workspace.initialised:
        print(
            f"{root} has no .aidlc/profile.json. Run `aidlc init` first.",
            file=sys.stderr,
        )
        return 1

    try:
        report = _run(root, write=not dry_run, allow_create_blocks=False, force=force)
    except WorkspaceError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if report.profile_drifted:
        print("Project shape changed:")
        print(report.profile_diff)
        print()

    _print(report.changes, verb="Would write" if dry_run else "Wrote")
    return 1 if report.conflicts else 0


def check(path: Path | None = None) -> int:
    """Report drift without writing anything.

    This is the pre-commit hook and the first step of the CI dispatcher. It
    answers one question: would running `sync` change anything? A clean `check`
    means the committed files match what the packs and the project imply.
    """
    root = find_root(path or Path.cwd())
    workspace = Workspace(root=root)

    if not workspace.initialised:
        print(f"{root} has no .aidlc/profile.json. Run `aidlc init` first.", file=sys.stderr)
        return 1

    try:
        config = workspace.config()
        report = _run(root, write=False, allow_create_blocks=False)
    except WorkspaceError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    strict = config.strictness is Strictness.STRICT
    failed = False

    if report.profile_drifted:
        label = "error" if strict else "warning"
        print(f"{label}: the committed profile no longer matches this project:")
        print(report.profile_diff)
        print("  run `aidlc sync` to update it")
        failed = failed or strict

    for conflict in report.conflicts:
        print(f"error: {conflict.path}: {conflict.detail}")
        failed = True

    stale = [c for c in report.changes if c.wrote]
    if stale:
        print("error: generated files are out of date:")
        for change in stale:
            print(f"  {change.path}")
        print("  run `aidlc sync`")
        failed = True

    if not failed:
        print("Up to date.")
    return 1 if failed else 0
