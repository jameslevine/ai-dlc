"""The ecosystem adapter contract.

An adapter answers two questions about a repository, and nothing else:

1. ``detect`` — which directories here are buildable units of my kind, and what
   do their manifests say?
2. ``job_spec`` — given one of those units, what should CI run?

Keeping the contract this narrow is what makes adding a language cheap. A new
ecosystem is a table of marker files plus a mapping to commands; nothing in the
renderer, the CI workflow, the lockfile or the eval loop changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from aidlc.detect.scanner import RepoIndex
from aidlc.schemas.profile import JobSpec, SetupKind, Step, StepName, StepSource


@dataclass(slots=True)
class TargetFacts:
    """What an adapter learned about one buildable directory.

    This is the adapter's output and the profile's input. It is a plain
    dataclass rather than a pydantic model because it is internal: only the
    assembled :class:`~aidlc.schemas.profile.Target` is ever serialised.
    """

    path: str
    ecosystem: str
    languages: list[str] = field(default_factory=list)
    manager: str | None = None
    frameworks: list[str] = field(default_factory=list)
    facts: dict[str, object] = field(default_factory=dict)

    declared_steps: dict[StepName, str] = field(default_factory=dict)
    """Commands the project declares for itself: npm scripts, Makefile targets,
    Gradle tasks. These take precedence over any default the adapter holds."""

    versions: list[str] = field(default_factory=list)
    cache_dependency_glob: str | None = None


class EcosystemAdapter(Protocol):
    """One language ecosystem's detection and CI knowledge."""

    id: str

    def detect(self, index: RepoIndex) -> list[TargetFacts]:
        """Find buildable units of this ecosystem. Must not raise."""
        ...

    def job_spec(self, facts: TargetFacts) -> JobSpec:
        """Turn detected facts into the CI job that builds them."""
        ...


def resolve_steps(
    facts: TargetFacts,
    defaults: dict[StepName, str],
    *,
    overrides: dict[StepName, str] | None = None,
) -> list[Step]:
    """Combine declared, default and configured commands into ordered steps.

    Precedence, lowest to highest: the adapter's default, then whatever the
    project declares for itself, then an explicit override from
    ``.aidlc/config.yml``.

    The middle rule is the important one. A repository that chose Biome over
    ESLint, or wired its tests through a Makefile, has already made a decision.
    Overriding it with our opinion would make the generated CI wrong and make
    the tool feel like something to fight. Opinionated where the project is
    silent, deferential where it has spoken.
    """
    overrides = overrides or {}
    steps: list[Step] = []

    for name in StepName:
        if name in overrides:
            command, source = overrides[name], StepSource.CONFIG
        elif name in facts.declared_steps:
            command, source = facts.declared_steps[name], StepSource.PROJECT
        elif name in defaults:
            command, source = defaults[name], StepSource.DEFAULT
        else:
            continue

        # An explicitly empty command is how a config disables a step.
        if command.strip():
            steps.append(Step(name=name, command=command, source=source))

    return steps


def make_job(
    facts: TargetFacts,
    setup: SetupKind,
    defaults: dict[StepName, str],
    *,
    overrides: dict[StepName, str] | None = None,
) -> JobSpec:
    """Assemble a :class:`JobSpec` from facts plus the adapter's defaults."""
    return JobSpec(
        setup=setup,
        versions=facts.versions,
        cache_dependency_glob=facts.cache_dependency_glob,
        working_directory=facts.path,
        steps=resolve_steps(facts, defaults, overrides=overrides),
    )


def makefile_targets(index: RepoIndex, directory: str) -> set[str]:
    """Target names declared by a Makefile in ``directory``.

    Deliberately a shallow parse: a line starting at column zero with an
    identifier followed by a colon. Running `make -qp` would be exact but means
    executing the project's build system during detection, which is neither
    safe nor fast.
    """
    prefix = "" if directory == "." else directory + "/"
    text = index.read_text(prefix + "Makefile") or index.read_text(prefix + "makefile")
    if not text:
        return set()

    targets: set[str] = set()
    for line in text.splitlines():
        if not line or line[0].isspace() or line.startswith((".", "#")):
            continue
        head, separator, _ = line.partition(":")
        if not separator:
            continue
        name = head.strip()
        if name and name.replace("-", "").replace("_", "").isalnum():
            targets.add(name)
    return targets


def steps_from_makefile(index: RepoIndex, directory: str) -> dict[StepName, str]:
    """Map conventional Makefile target names onto build steps.

    Only exact, unambiguous names are used. Guessing that `check` means `lint`
    would silently run the wrong thing, which is worse than running nothing.
    """
    available = makefile_targets(index, directory)
    mapping = {
        StepName.INSTALL: ("install", "deps"),
        StepName.LINT: ("lint",),
        StepName.FORMAT: ("format",),
        StepName.TYPECHECK: ("typecheck",),
        StepName.TEST: ("test",),
        StepName.BUILD: ("build",),
    }
    return {
        step: f"make {name}"
        for step, candidates in mapping.items()
        for name in candidates
        if name in available
    }
