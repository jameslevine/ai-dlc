"""Planning and writing the files aidlc generates.

Rendering is split deliberately into two phases:

1. **Plan** — pure functions turn packs plus a profile into a list of
   :class:`~aidlc.render.emitters.Artifact` values. Nothing touches disk, so
   golden tests compare rendered output without a filesystem, and `--dry-run`
   is the same code path as a real run.
2. **Apply** — the materializer writes that plan, honouring block semantics and
   refusing to clobber hand edits.

Keeping them apart is what makes `check` trustworthy: it runs phase one and
compares, and it cannot accidentally write.
"""

from __future__ import annotations

from aidlc.packs.loader import Pack
from aidlc.render.emitters import (
    Artifact,
    ArtifactKind,
    agents_md,
    claude_agent_artifacts,
    copilot_instructions,
    cursor_rules,
    mcp_artifacts,
    skill_artifacts,
)
from aidlc.render.workflow import workflow_artifact
from aidlc.schemas.config import Config
from aidlc.schemas.profile import Profile

__all__ = ["Artifact", "ArtifactKind", "plan"]


def plan(packs: list[Pack], profile: Profile, config: Config) -> list[Artifact]:
    """Everything that should exist in the repository, as data.

    AGENTS.md is unconditional: it is the canonical artifact every other
    emitter supplements, and every major agent reads it. The rest are
    switchable because they serve one tool each.
    """
    version = _combined_version(packs)
    artifacts: list[Artifact] = [agents_md(packs, profile, version)]

    # The caller workflow is emitted only for repositories hosted on GitHub
    # and only when there is something to build. Writing a workflow into a
    # repository with no targets would add a permanently green check that
    # verifies nothing.
    if profile.vcs.host == "github" and profile.targets:
        artifacts.append(workflow_artifact(strictness=config.strictness.value))

    if config.emit.cursor:
        artifacts.extend(cursor_rules(packs))
    if config.emit.copilot:
        artifacts.extend(copilot_instructions(packs))
    if config.emit.skills:
        artifacts.extend(skill_artifacts(packs))
    if config.emit.mcp:
        artifacts.extend(mcp_artifacts(config))
    if config.emit.agents:
        artifacts.extend(claude_agent_artifacts(packs))

    return sorted(artifacts, key=lambda a: a.path)


def _combined_version(packs: list[Pack]) -> str:
    """A single version string describing the whole pack set.

    Recorded in the AGENTS.md marker so that a version bump in any pack shows
    up as a change to the block rather than being invisible.
    """
    return "+".join(f"{pack.name}@{pack.version}" for pack in packs) or "none"
