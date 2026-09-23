"""Python ecosystem adapter."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from aidlc.detect.adapters.base import TargetFacts, make_job, steps_from_makefile
from aidlc.detect.scanner import RepoIndex
from aidlc.schemas.profile import JobSpec, SetupKind, StepName

#: Manifest and lockfile names that mark a Python project root.
MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")

#: Lockfiles, in the order we prefer them when several are present. A repo
#: mid-migration often has two; the more modern one is the one being adopted.
_LOCKFILES: tuple[tuple[str, str], ...] = (
    ("uv.lock", "uv"),
    ("poetry.lock", "poetry"),
    ("Pipfile.lock", "pipenv"),
    ("pdm.lock", "pdm"),
)

#: Dependency substrings that imply a framework worth a rule pack.
_FRAMEWORK_HINTS: dict[str, str] = {
    "fastapi": "fastapi",
    "django": "django",
    "flask": "flask",
    "aws-cdk-lib": "aws-cdk",
    "boto3": "aws",
    "pydantic": "pydantic",
    "pandas": "data",
}

_REQUIRES_PYTHON = re.compile(r">=\s*(\d+)\.(\d+)")

#: Versions we are willing to put in a CI matrix, newest last.
_KNOWN_VERSIONS = ("3.12", "3.13", "3.14")


@dataclass(frozen=True, slots=True)
class _Toolchain:
    """How CI sets up, installs and runs a project under one package manager."""

    setup: SetupKind
    install: str
    """Empty when the install depends on what the project has; see `_PIP_INSTALLS`."""
    run: str
    """Prefix that runs a tool inside the project environment."""
    audit: str
    """Empty when the manager cannot run pip-audit without the project installing it."""


#: `uv run --with` runs pip-audit from an ephemeral environment, so the
#: project's own lockfile never has to list it. The other managers have no
#: equivalent: `poetry run pip-audit` fails unless the project installs
#: pip-audit itself, so they get no audit step. Poetry has no first-party
#: setup action, so the generic workflow installs nothing and its commands
#: carry their own runner. pipenv and pdm lockfiles are recognised but their
#: projects are installed with pip.
_TOOLCHAINS: dict[str, _Toolchain] = {
    "uv": _Toolchain(
        SetupKind.UV, "uv sync --locked", "uv run ", "uv run --with pip-audit pip-audit"
    ),
    "poetry": _Toolchain(SetupKind.NONE, "poetry install --no-interaction", "poetry run ", ""),
    "pip": _Toolchain(SetupKind.NONE, "", "", ""),
}

#: pip installs from whatever the project actually has, first match wins.
#: Emitting `-r requirements.txt` for a project that has none produces CI
#: that fails on its first step, which is worse than no CI at all; a project
#: with neither gets no install step.
_PIP_INSTALLS: dict[str, str] = {
    "requirements": "python -m pip install -r requirements.txt",
    "installable": "python -m pip install -e .",
}

#: Tools run through the toolchain's `run` prefix, each only when the project
#: configures it. The type checker is whichever of `_TYPE_CHECKERS` it uses.
_TOOLS: dict[StepName, str] = {
    StepName.LINT: "ruff check .",
    StepName.FORMAT: "ruff format --check .",
    StepName.TEST: "pytest",
}
_TYPE_CHECKERS = ("pyright", "mypy")


class PythonAdapter:
    id = "python"

    def detect(self, index: RepoIndex) -> list[TargetFacts]:
        return [
            facts
            for directory in index.dirs_containing(*MARKERS)
            if (facts := self._inspect(index, directory)) is not None
        ]

    def _inspect(self, index: RepoIndex, directory: str) -> TargetFacts | None:
        prefix = "" if directory == "." else directory + "/"
        pyproject = index.read_toml(prefix + "pyproject.toml")

        manager, lockfile = self._manager(index, prefix, pyproject)
        dependencies = self._dependencies(pyproject)

        facts = TargetFacts(
            path=directory,
            ecosystem=self.id,
            languages=["Python"],
            manager=manager,
            frameworks=sorted(
                {
                    label
                    for needle, label in _FRAMEWORK_HINTS.items()
                    if any(needle in dep for dep in dependencies)
                }
            ),
            versions=self._versions(pyproject),
            cache_dependency_glob=(prefix + lockfile) if lockfile else None,
        )

        tool = pyproject.get("tool", {})
        facts.facts = {
            "layout": "src"
            if index.has(prefix + "src/__init__.py") or self._has_src(index, directory)
            else "flat",
            "type_checker": self._type_checker(tool, dependencies),
            "test_framework": "pytest" if self._has_pytest(tool, dependencies) else None,
            "linter": "ruff" if "ruff" in tool else None,
            "lockfile": lockfile,
            "requirements": index.has(prefix + "requirements.txt"),
            "installable": bool(pyproject.get("project") or pyproject.get("tool", {}).get("poetry"))
            or index.has(prefix + "setup.py"),
        }
        facts.declared_steps = steps_from_makefile(index, directory)
        return facts

    @staticmethod
    def _has_src(index: RepoIndex, directory: str) -> bool:
        src = "src" if directory == "." else directory + "/src"
        return src in index.dirs

    @staticmethod
    def _manager(
        index: RepoIndex, prefix: str, pyproject: dict[str, Any]
    ) -> tuple[str, str | None]:
        for lockfile, manager in _LOCKFILES:
            if index.has(prefix + lockfile):
                return manager, lockfile
        # No lockfile: fall back to what the manifest implies.
        if "poetry" in pyproject.get("tool", {}):
            return "poetry", None
        if index.has(prefix + "requirements.txt"):
            return "pip", None
        return "pip", None

    @staticmethod
    def _dependencies(pyproject: dict[str, Any]) -> list[str]:
        project = pyproject.get("project", {})
        deps: list[str] = list(project.get("dependencies", []) or [])
        for group in (project.get("optional-dependencies", {}) or {}).values():
            deps.extend(group or [])
        for group in (pyproject.get("dependency-groups", {}) or {}).values():
            deps.extend(item for item in (group or []) if isinstance(item, str))
        return [dep.lower() for dep in deps if isinstance(dep, str)]

    @staticmethod
    def _versions(pyproject: dict[str, Any]) -> list[str]:
        """Pick a CI matrix from `requires-python`.

        We test the declared floor, because that is the version most likely to
        break and least likely to be run locally. Testing only the newest
        version silently under-tests everything you claim to support.
        """
        requires = pyproject.get("project", {}).get("requires-python")
        if not isinstance(requires, str):
            return ["3.12"]
        match = _REQUIRES_PYTHON.search(requires)
        if not match:
            return ["3.12"]
        floor = f"{match.group(1)}.{match.group(2)}"
        return [floor] if floor in _KNOWN_VERSIONS else ["3.12"]

    @staticmethod
    def _type_checker(tool: dict[str, Any], dependencies: list[str]) -> str | None:
        """Which type checker the project runs, if any.

        A `[tool.pyright]` or `[tool.mypy]` table is the strongest evidence and
        wins outright. Failing that, the checker being a declared dependency is
        enough: a project that installs pyright into its dev group intends to
        run it, whether or not it has written a config table yet.
        """
        for checker in _TYPE_CHECKERS:
            if checker in tool:
                return checker
        for checker in _TYPE_CHECKERS:
            if any(dep.startswith(checker) for dep in dependencies):
                return checker
        return None

    @staticmethod
    def _has_pytest(tool: dict[str, Any], dependencies: list[str]) -> bool:
        return "pytest" in tool or any(dep.startswith("pytest") for dep in dependencies)

    def job_spec(self, facts: TargetFacts) -> JobSpec:
        toolchain = _TOOLCHAINS.get(facts.manager or "", _TOOLCHAINS["pip"])
        install = toolchain.install or next(
            (command for fact, command in _PIP_INSTALLS.items() if facts.facts.get(fact)), ""
        )

        defaults: dict[StepName, str] = {StepName.INSTALL: install}
        if facts.facts.get("linter") == "ruff":
            defaults[StepName.LINT] = toolchain.run + _TOOLS[StepName.LINT]
            defaults[StepName.FORMAT] = toolchain.run + _TOOLS[StepName.FORMAT]
        if checker := facts.facts.get("type_checker"):
            defaults[StepName.TYPECHECK] = f"{toolchain.run}{checker}"
        if facts.facts.get("test_framework") == "pytest":
            defaults[StepName.TEST] = toolchain.run + _TOOLS[StepName.TEST]
        if toolchain.audit:
            defaults[StepName.AUDIT] = toolchain.audit

        return make_job(facts, toolchain.setup, defaults)

    def default_commands(self) -> frozenset[str]:
        toolchains = _TOOLCHAINS.values()
        tools = (*_TOOLS.values(), *_TYPE_CHECKERS)
        return frozenset(
            {toolchain.install for toolchain in toolchains if toolchain.install}
            | set(_PIP_INSTALLS.values())
            | {toolchain.run + tool for toolchain in toolchains for tool in tools}
            | {toolchain.audit for toolchain in toolchains if toolchain.audit}
        )
