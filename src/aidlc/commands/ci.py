"""`aidlc ci matrix` — turn a committed profile into a GitHub Actions matrix.

The dispatcher workflow cannot read a profile itself, so this command does it:
one matrix entry per (target, toolchain version), carrying everything the
generic build workflow needs as plain strings.

Flattening versions here rather than in YAML keeps the workflow free of nested
matrix logic, and means `aidlc ci matrix` can be run locally to see exactly
what CI will do.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from aidlc.schemas.profile import Profile, StepName
from aidlc.workspace import Workspace, WorkspaceError, find_root


def _entries(profile: Profile) -> list[dict[str, str]]:
    """One matrix entry per target and toolchain version."""
    entries: list[dict[str, str]] = []

    for target in profile.targets:
        # An empty version list means "whatever the runner provides", which is
        # the honest result when a project never declared one. It still needs
        # exactly one matrix entry, so a single empty string stands in.
        for version in target.job.versions or [""]:
            entry: dict[str, str] = {
                "name": _entry_name(target.path, target.ecosystem, version),
                "target": target.path,
                "ecosystem": target.ecosystem,
                "setup": target.job.setup.value,
                "version": version,
                "cache": target.job.cache_dependency_glob or "",
            }
            for step_name in StepName:
                step = target.job.step(step_name)
                entry[step_name.value] = step.command if step else ""
            entries.append(entry)

    return entries


def _entry_name(path: str, ecosystem: str, version: str) -> str:
    """A readable job name, since this is what shows up in the checks list."""
    where = "" if path == "." else f" {path}"
    which = f" {version}" if version else ""
    return f"{ecosystem}{where}{which}"


def _emit(name: str, value: str) -> None:
    """Write a step output, or print it when running outside Actions."""
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with Path(target).open("a", encoding="utf-8") as handle:
            # The multiline-safe form. A JSON matrix containing a newline
            # would otherwise break the key=value parser.
            handle.write(f"{name}<<__AIDLC__\n{value}\n__AIDLC__\n")
    else:
        print(f"{name}={value}")


def matrix(path: Path | None = None) -> int:
    """Emit the build matrix for the dispatcher workflow."""
    root = find_root(path or Path.cwd())
    workspace = Workspace(root=root)

    try:
        profile = workspace.stored_profile()
    except WorkspaceError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if profile is None:
        print(
            f"{root} has no .aidlc/profile.json. Run `aidlc init` and commit the result.",
            file=sys.stderr,
        )
        return 1

    entries = _entries(profile)

    # An empty matrix is a workflow error rather than a no-op, so the caller
    # guards on this flag instead of discovering it at runtime.
    _emit("any", "true" if entries else "false")
    _emit("matrix", json.dumps({"include": entries}, sort_keys=True))
    return 0
