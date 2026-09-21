"""Python ecosystem adapter."""

from __future__ import annotations

import re
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
            "type_checker": self._type_checker(tool),
            "test_framework": "pytest" if self._has_pytest(tool, dependencies) else None,
            "linter": "ruff" if "ruff" in tool else None,
            "lockfile": lockfile,
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
    def _type_checker(tool: dict[str, Any]) -> str | None:
        if "pyright" in tool:
            return "pyright"
        if "mypy" in tool:
            return "mypy"
        return None

    @staticmethod
    def _has_pytest(tool: dict[str, Any], dependencies: list[str]) -> bool:
        return "pytest" in tool or any(dep.startswith("pytest") for dep in dependencies)

    def job_spec(self, facts: TargetFacts) -> JobSpec:
        manager = facts.manager
        locked = facts.facts.get("lockfile")

        if manager == "uv":
            install = "uv sync --locked" if locked else "uv sync"
            run = "uv run "
            setup = SetupKind.UV
        elif manager == "poetry":
            install = "poetry install --no-interaction"
            run = "poetry run "
            setup = SetupKind.NONE
        else:
            install = (
                "python -m pip install -r requirements.txt"
                if facts.facts.get("lockfile") is None
                else "python -m pip install -e ."
            )
            run = ""
            setup = SetupKind.NONE

        defaults: dict[StepName, str] = {StepName.INSTALL: install}
        if facts.facts.get("linter") == "ruff":
            defaults[StepName.LINT] = f"{run}ruff check ."
            defaults[StepName.FORMAT] = f"{run}ruff format --check ."
        if checker := facts.facts.get("type_checker"):
            defaults[StepName.TYPECHECK] = f"{run}{checker}"
        if facts.facts.get("test_framework") == "pytest":
            defaults[StepName.TEST] = f"{run}pytest"

        return make_job(facts, setup, defaults)
