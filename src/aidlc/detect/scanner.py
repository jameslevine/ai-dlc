"""A single, cached read of a repository's shape.

Every ecosystem adapter needs to ask the same kinds of question: does this
directory contain a manifest, what does that manifest say, which lockfile sits
beside it. Walking the tree once and answering from an index keeps detection
fast on large repos and, more importantly, keeps adapters small — an adapter is
a table of marker files and a mapping to commands, not a file crawler.

The walk prunes before descending. Recursing into `node_modules` and then
filtering is the difference between milliseconds and seconds.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

#: Directories never worth descending into. Dependency trees, build output,
#: virtualenvs and VCS internals. Pruned before descent, not filtered after.
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".tox",
        ".nox",
        "dist",
        "build",
        "target",
        "bin",
        "obj",
        ".gradle",
        ".next",
        ".nuxt",
        ".svelte-kit",
        ".turbo",
        ".parcel-cache",
        "vendor",
        "cdk.out",
        ".terraform",
        ".idea",
        ".vscode-test",
        "coverage",
        "htmlcov",
        ".cargo",
        ".dart_tool",
        "Pods",
        # Test data that frequently contains whole manifests. Without these, a
        # repository's own fixtures are detected as buildable targets and CI is
        # generated to build them. Only names that are unambiguous conventions
        # appear here; `testdata` is ignored by the Go toolchain itself. For
        # anything less standard, use `detect.ignore` in .aidlc/config.yml.
        "testdata",
        "__fixtures__",
        "__snapshots__",
        "__mocks__",
        # Agent tooling. These hold instructions, skills and their bundled
        # templates, and a skill that ships an example project would otherwise
        # be detected as a buildable target of the repository hosting it.
        ".agents",
        ".aidlc",
        ".claude",
        ".codex",
        ".copilot",
        ".cursor",
        ".windsurf",
        ".gemini",
    }
)

#: Cap on how deep a manifest may be nested. A manifest twelve levels down is a
#: vendored copy or a test fixture, not a target someone wants built.
MAX_DEPTH = 6

#: Refuse to parse manifests above this size. A multi-megabyte "pyproject.toml"
#: is not a manifest, and parsing it would stall the CLI.
MAX_MANIFEST_BYTES = 2 * 1024 * 1024


@dataclass(slots=True)
class RepoIndex:
    """An immutable-by-convention view of the files in a repository.

    Paths are stored relative to ``root`` and use forward slashes, so profiles
    generated on Windows and macOS compare equal.
    """

    root: Path
    files: frozenset[str]
    dirs: frozenset[str]
    _text_cache: dict[str, str | None] = field(default_factory=dict, repr=False)
    _parsed_cache: dict[str, Any] = field(default_factory=dict, repr=False)

    # -- existence ---------------------------------------------------------

    def has(self, relpath: str) -> bool:
        """True if a file exists at this exact relative path."""
        return relpath in self.files

    def has_any(self, *relpaths: str) -> bool:
        return any(p in self.files for p in relpaths)

    def dirs_containing(self, *names: str) -> list[str]:
        """Directories holding at least one of ``names``, nearest root first.

        Returned as relative directory paths, with "." for the repository root.
        Sorted by depth then name so that a parent is always considered before
        its children, which matters when deciding monorepo layout.
        """
        found: set[str] = set()
        for name in names:
            for file_path in self.files:
                if file_path == name:
                    found.add(".")
                elif file_path.endswith("/" + name):
                    found.add(file_path[: -(len(name) + 1)])
        return sorted(found, key=lambda d: (0 if d == "." else d.count("/") + 1, d))

    def glob_names(self, directory: str, suffix: str) -> list[str]:
        """Files directly inside ``directory`` whose name ends with ``suffix``."""
        prefix = "" if directory == "." else directory + "/"
        results = [
            path
            for path in self.files
            if path.startswith(prefix) and "/" not in path[len(prefix) :] and path.endswith(suffix)
        ]
        return sorted(results)

    # -- reading -----------------------------------------------------------

    def read_text(self, relpath: str) -> str | None:
        """File contents, or None if absent, oversized or undecodable.

        Unreadable is deliberately indistinguishable from absent here: an
        adapter's job is to detect what it can, not to adjudicate why a file
        could not be parsed.
        """
        if relpath in self._text_cache:
            return self._text_cache[relpath]

        result: str | None = None
        if relpath in self.files:
            path = self.root / relpath
            try:
                if path.stat().st_size <= MAX_MANIFEST_BYTES:
                    result = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                result = None

        self._text_cache[relpath] = result
        return result

    def read_toml(self, relpath: str) -> dict[str, Any]:
        """Parsed TOML, or an empty mapping when absent or malformed."""
        return self._parse(relpath, lambda text: tomllib.loads(text))

    def read_json(self, relpath: str) -> dict[str, Any]:
        """Parsed JSON, or an empty mapping when absent or malformed."""
        return self._parse(relpath, json.loads)

    def read_yaml(self, relpath: str) -> dict[str, Any]:
        """Parsed YAML, or an empty mapping when absent or malformed."""
        return self._parse(relpath, lambda text: yaml.safe_load(text))

    def _parse(self, relpath: str, parser: Any) -> dict[str, Any]:
        if relpath in self._parsed_cache:
            return self._parsed_cache[relpath]

        text = self.read_text(relpath)
        parsed: dict[str, Any] = {}
        if text:
            try:
                candidate = parser(text)
                if isinstance(candidate, dict):
                    parsed = candidate
            except Exception:  # noqa: BLE001 - a broken manifest is not our error
                parsed = {}

        self._parsed_cache[relpath] = parsed
        return parsed


def scan(root: Path, *, extra_ignores: frozenset[str] | None = None) -> RepoIndex:
    """Walk ``root`` once and build an index of it.

    Symlinked directories are not followed. A symlink loop would otherwise hang
    detection, and a symlinked dependency tree is not part of this repository.
    """
    ignores = DEFAULT_IGNORE_DIRS | (extra_ignores or frozenset())
    root = root.resolve()
    files: set[str] = set()
    dirs: set[str] = set()

    def walk(directory: Path, depth: int) -> None:
        if depth > MAX_DEPTH:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError:
            return

        for entry in entries:
            try:
                is_dir = entry.is_dir() and not entry.is_symlink()
                is_file = entry.is_file()
            except OSError:
                continue

            relative = entry.relative_to(root).as_posix()
            if is_dir:
                if entry.name in ignores:
                    continue
                dirs.add(relative)
                walk(entry, depth + 1)
            elif is_file:
                files.add(relative)

    walk(root, 0)
    return RepoIndex(root=root, files=frozenset(files), dirs=frozenset(dirs))
