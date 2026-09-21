"""Turn a repository into a profile.

This is the orchestration layer: scan once, ask every adapter what it sees,
apply the user's overrides, record what we refused to touch, and choose the
rule packs that apply. It holds no per-language knowledge of its own.
"""

from __future__ import annotations

from pathlib import Path

from aidlc import __version__, probe
from aidlc.detect.adapters import ADAPTERS, by_id
from aidlc.detect.adapters.base import TargetFacts, make_job
from aidlc.detect.scanner import RepoIndex, scan
from aidlc.schemas.config import Config, TargetOverride
from aidlc.schemas.profile import (
    Conflict,
    JobSpec,
    Profile,
    SetupKind,
    Step,
    StepName,
    StepSource,
    Target,
    VcsInfo,
)

#: Rule packs implied by an ecosystem being present.
_ECOSYSTEM_PACKS: dict[str, tuple[str, ...]] = {
    "python": ("rules-python",),
    "node": ("rules-typescript",),
    "jvm": ("rules-java",),
    "go": ("rules-go",),
    "rust": ("rules-rust",),
    "dotnet": ("rules-dotnet",),
}

#: Rule packs implied by a detected framework.
_FRAMEWORK_PACKS: dict[str, str] = {
    "react": "rules-react",
    "next": "rules-react",
    "aws-cdk": "rules-aws-cdk",
    "fastapi": "rules-fastapi",
    "spring-boot": "rules-spring",
}


def detect(root: Path, config: Config | None = None) -> Profile:
    """Build a profile for the repository rooted at ``root``."""
    config = config or Config()
    index = scan(root, extra_ignores=frozenset(config.detect.ignore))

    targets = _detected_targets(index, config)
    targets = _apply_overrides(targets, config)

    return Profile(
        generated_by=f"aidlc {__version__}",
        vcs=_vcs(root),
        targets=targets,
        packs_selected=_select_packs(targets, config),
        conflicts=_conflicts(index),
    )


def _detected_targets(index: RepoIndex, config: Config) -> list[Target]:
    targets: list[Target] = []
    for adapter in ADAPTERS:
        for facts in adapter.detect(index):
            override = config.override_for(facts.path)
            job = adapter.job_spec(facts)
            if override is not None:
                job = _merge_job(job, override, facts)
            targets.append(_to_target(facts, job))
    return sorted(targets, key=lambda t: (t.path, t.ecosystem))


def _to_target(facts: TargetFacts, job: JobSpec) -> Target:
    return Target(
        path=facts.path,
        ecosystem=facts.ecosystem,
        languages=facts.languages,
        manager=facts.manager,
        frameworks=facts.frameworks,
        facts=dict(facts.facts),
        job=job,
    )


def _merge_job(job: JobSpec, override: TargetOverride, facts: TargetFacts) -> JobSpec:
    """Layer a config override onto a detected job spec.

    Config always wins: it is the most specific statement of intent available,
    and the escape hatch depends on it being unconditional.
    """
    steps = {step.name: step for step in job.steps}
    for name, command in override.steps.items():
        if command.strip():
            steps[name] = Step(name=name, command=command, source=StepSource.CONFIG)
        else:
            steps.pop(name, None)

    return JobSpec(
        setup=override.setup if override.setup is not None else job.setup,
        versions=override.versions if override.versions is not None else job.versions,
        cache_dependency_glob=job.cache_dependency_glob,
        working_directory=facts.path,
        steps=[steps[name] for name in StepName if name in steps],
    )


def _apply_overrides(targets: list[Target], config: Config) -> list[Target]:
    """Add targets that exist only because the config declares them.

    This is the escape hatch in action: a directory no adapter recognises
    becomes a first-class target the moment someone writes down how to build
    it. No language is ever unsupported; some are merely less automatic.
    """
    known = {target.path for target in targets}
    extras: list[Target] = []

    for override in config.targets:
        if override.path in known:
            continue
        facts = TargetFacts(
            path=override.path,
            ecosystem=override.ecosystem or "custom",
            versions=override.versions or [],
        )
        adapter = by_id(override.ecosystem) if override.ecosystem else None
        if adapter is not None:
            job = _merge_job(adapter.job_spec(facts), override, facts)
        else:
            job = make_job(
                facts,
                override.setup or SetupKind.NONE,
                defaults={},
                overrides=override.steps,
            )
        extras.append(_to_target(facts, job))

    return sorted([*targets, *extras], key=lambda t: (t.path, t.ecosystem))


def _select_packs(targets: list[Target], config: Config) -> list[str]:
    """Choose rule packs from what was detected.

    An explicit `packs` list in config replaces this entirely rather than
    adding to it, so that a repository can opt out of a pack it dislikes.
    """
    if config.packs is not None:
        return list(config.packs)

    selected: dict[str, None] = {"core": None}
    for target in targets:
        for pack in _ECOSYSTEM_PACKS.get(target.ecosystem, ()):
            selected.setdefault(pack, None)
        for framework in target.frameworks:
            if pack := _FRAMEWORK_PACKS.get(framework):
                selected.setdefault(pack, None)

    # Infrastructure rules are language-independent: a CDK app written in
    # TypeScript wants the same guidance as one written in Python.
    return list(selected)


def _conflicts(index: RepoIndex) -> list[Conflict]:
    """Record pre-existing files aidlc will read but never modify.

    Reporting these rather than silently working around them is what makes the
    tool safe to run on a repository that already has opinions.
    """
    conflicts: list[Conflict] = []

    for path in sorted(index.files):
        if path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml")):
            if path.endswith("/aidlc.yml"):
                continue
            conflicts.append(
                Conflict(
                    kind="existing_workflow",
                    path=path,
                    note="Pre-existing workflow. aidlc will not modify it.",
                )
            )

    if index.has("CLAUDE.md"):
        conflicts.append(
            Conflict(
                kind="claude_md_shadows_agents_md",
                path="CLAUDE.md",
                note=(
                    "Claude Code reads AGENTS.md only when no CLAUDE.md exists in this "
                    "directory or above it, so this file shadows the generated AGENTS.md "
                    "for Claude Code specifically. Other agents are unaffected."
                ),
            )
        )

    return conflicts


def _vcs(root: Path) -> VcsInfo:
    result = probe.run(["git", "-C", str(root), "remote", "get-url", "origin"])
    if not result.ok or not result.stdout:
        return VcsInfo()

    url = result.stdout
    host = "github" if "github.com" in url else None
    repo = None
    if host == "github":
        tail = url.split("github.com", 1)[1].lstrip(":/")
        repo = tail.removesuffix(".git") or None
    return VcsInfo(host=host, repo=repo)
