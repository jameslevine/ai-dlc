"""Node and TypeScript adapter, covering React, Next, Vite and friends.

This adapter leans hardest on the "project declarations win" rule, because the
Node ecosystem has no consensus toolchain. A repo might lint with ESLint, Biome
or oxlint, and test with Jest, Vitest, node:test or Playwright. Guessing is
worse than asking: if `package.json` declares a script, that script is what CI
runs.
"""

from __future__ import annotations

import re
from typing import Any

from aidlc.detect.adapters.base import TargetFacts, make_job
from aidlc.detect.scanner import RepoIndex
from aidlc.schemas.profile import JobSpec, SetupKind, StepName

MARKERS = ("package.json",)

#: Lockfile to package manager, with the frozen-install flag each one uses.
#: Getting this wrong is the classic Node CI bug: a non-frozen install in CI
#: silently resolves different versions than the lockfile pins.
_MANAGERS: tuple[tuple[str, str, str], ...] = (
    ("pnpm-lock.yaml", "pnpm", "pnpm install --frozen-lockfile"),
    ("bun.lockb", "bun", "bun install --frozen-lockfile"),
    ("bun.lock", "bun", "bun install --frozen-lockfile"),
    ("yarn.lock", "yarn", "yarn install --immutable"),
    ("package-lock.json", "npm", "npm ci"),
)

#: Dependency name to framework label. Order matters: the first match wins for
#: meta-frameworks that also depend on the thing they wrap.
_FRAMEWORK_HINTS: tuple[tuple[str, str], ...] = (
    ("next", "next"),
    ("nuxt", "nuxt"),
    ("@remix-run/react", "remix"),
    ("@angular/core", "angular"),
    ("svelte", "svelte"),
    ("vue", "vue"),
    ("react", "react"),
    ("express", "express"),
    ("fastify", "fastify"),
    ("vite", "vite"),
    ("aws-cdk-lib", "aws-cdk"),
)

#: Script names in package.json that map onto our fixed step vocabulary.
#: Only exact names; a script called `check` is too ambiguous to wire up.
_SCRIPT_STEPS: dict[str, StepName] = {
    "lint": StepName.LINT,
    "format:check": StepName.FORMAT,
    "typecheck": StepName.TYPECHECK,
    "type-check": StepName.TYPECHECK,
    "test": StepName.TEST,
    "build": StepName.BUILD,
}

_SEMVER_MAJOR = re.compile(r"(\d+)")


class NodeAdapter:
    id = "node"

    def detect(self, index: RepoIndex) -> list[TargetFacts]:
        results: list[TargetFacts] = []
        for directory in index.dirs_containing(*MARKERS):
            facts = self._inspect(index, directory)
            if facts is not None:
                results.append(facts)
        return results

    def _inspect(self, index: RepoIndex, directory: str) -> TargetFacts | None:
        prefix = "" if directory == "." else directory + "/"
        manifest = index.read_json(prefix + "package.json")
        if not manifest:
            return None

        # A workspace root that only lists workspaces is not itself buildable;
        # its members are detected separately and building it twice is waste.
        scripts = manifest.get("scripts", {}) or {}
        if manifest.get("workspaces") and not scripts:
            return None

        manager, install_command, lockfile = self._manager(index, prefix, manifest)
        dependencies = self._dependencies(manifest)
        typescript = self._is_typescript(index, prefix, dependencies)

        facts = TargetFacts(
            path=directory,
            ecosystem=self.id,
            languages=["TypeScript"] if typescript else ["JavaScript"],
            manager=manager,
            frameworks=[label for name, label in _FRAMEWORK_HINTS if name in dependencies],
            versions=self._versions(index, prefix, manifest),
            cache_dependency_glob=(prefix + lockfile) if lockfile else None,
        )
        facts.facts = {
            "typescript": typescript,
            "lockfile": lockfile,
            "install_command": install_command,
            "scripts": sorted(scripts),
            "workspace_root": bool(manifest.get("workspaces")),
        }
        facts.declared_steps = self._declared_steps(manager, scripts)
        return facts

    @staticmethod
    def _declared_steps(manager: str, scripts: dict[str, Any]) -> dict[StepName, str]:
        """Map declared package scripts onto build steps.

        `npm run` is used for npm/pnpm/yarn alike because all three accept it,
        which keeps the generated command readable and portable.
        """
        runner = "bun run" if manager == "bun" else f"{manager} run"
        declared: dict[StepName, str] = {}
        for script_name, step in _SCRIPT_STEPS.items():
            if script_name in scripts and step not in declared:
                declared[step] = f"{runner} {script_name}"
        return declared

    @staticmethod
    def _manager(
        index: RepoIndex, prefix: str, manifest: dict[str, Any]
    ) -> tuple[str, str, str | None]:
        for lockfile, name, install in _MANAGERS:
            if index.has(prefix + lockfile):
                return name, install, lockfile

        # No lockfile beside the manifest. `packageManager` is the declared
        # intent and is honoured; otherwise fall back to npm without `ci`,
        # which requires a lockfile that does not exist here.
        declared = manifest.get("packageManager")
        if isinstance(declared, str) and "@" in declared:
            name = declared.split("@", 1)[0]
            return name, f"{name} install", None
        return "npm", "npm install", None

    @staticmethod
    def _dependencies(manifest: dict[str, Any]) -> set[str]:
        names: set[str] = set()
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            section = manifest.get(key) or {}
            if isinstance(section, dict):
                names.update(section)
        return names

    @staticmethod
    def _is_typescript(index: RepoIndex, prefix: str, dependencies: set[str]) -> bool:
        return index.has(prefix + "tsconfig.json") or "typescript" in dependencies

    @staticmethod
    def _versions(index: RepoIndex, prefix: str, manifest: dict[str, Any]) -> list[str]:
        """Resolve a Node major version from the usual declarations.

        Checked in order of specificity: a pinned version file, then the
        `engines` range. An empty result means "use the runner default", which
        is the honest answer when the project never said.
        """
        for filename in (".nvmrc", ".node-version"):
            text = index.read_text(prefix + filename) or index.read_text(filename)
            if text and (match := _SEMVER_MAJOR.search(text)):
                return [match.group(1)]

        engines = manifest.get("engines", {})
        node_range = engines.get("node") if isinstance(engines, dict) else None
        if isinstance(node_range, str) and (match := _SEMVER_MAJOR.search(node_range)):
            return [match.group(1)]
        return []

    def job_spec(self, facts: TargetFacts) -> JobSpec:
        install = str(facts.facts.get("install_command") or "npm install")
        defaults: dict[StepName, str] = {StepName.INSTALL: install}

        # The one default worth holding: a TypeScript project with a tsconfig
        # but no typecheck script still benefits from a compile check, and
        # `tsc --noEmit` is unambiguous in a way that "lint" is not.
        if facts.facts.get("typescript"):
            runner = "bunx" if facts.manager == "bun" else "npx"
            defaults[StepName.TYPECHECK] = f"{runner} tsc --noEmit"

        return make_job(facts, SetupKind.NODE, defaults)
