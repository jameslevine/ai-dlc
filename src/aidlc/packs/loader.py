"""Reading packs from disk or from inside the installed wheel.

Builtin packs ship as package data and are read through ``importlib.resources``
rather than by walking up from ``__file__``. Path arithmetic on ``__file__``
breaks the moment the package is zipped, installed as a tool, or vendored, and
the failure is confusing because it only appears after packaging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

import yaml
from pydantic import ValidationError

from aidlc.packs.digest import digest_files
from aidlc.schemas.pack import Agent, Emit, PackMeta, Rule, Skill

#: Directory inside the wheel holding the builtin packs.
_BUILTIN_ANCHOR = "aidlc._packs"

#: Files never treated as pack content, and excluded from the digest so that
#: editor noise cannot change a pack's identity.
_IGNORED_NAMES = frozenset({".DS_Store", "Thumbs.db"})

#: Every frontmatter key an agent file may carry. Anything else is rejected,
#: as `PackMeta` rejects an unknown manifest key: a misspelt `tool:` would
#: otherwise load cleanly and grant nothing.
_AGENT_KEYS = ("name", "description", "tools", "model", "skills")


class PackError(Exception):
    """A pack could not be read or is not valid. Message is for a human."""


@dataclass(slots=True)
class Pack:
    """A loaded pack: its metadata, its content, and its identity."""

    meta: PackMeta
    rules: list[Rule] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    agents: list[Agent] = field(default_factory=list)
    files: dict[str, bytes] = field(default_factory=dict, repr=False)
    """Every file in the pack, keyed by path relative to the pack root. This is
    what the digest is computed over, so it must include `pack.yaml`."""

    source: str = "builtin"

    @property
    def name(self) -> str:
        return self.meta.name

    @property
    def version(self) -> str:
        return self.meta.version

    @property
    def digest(self) -> str:
        return digest_files(self.files)

    def emits(self, emit: Emit) -> bool:
        return emit in self.meta.emits


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split YAML frontmatter from a markdown body.

    Returns an empty mapping when there is no frontmatter, which is a valid
    state: a rule file may be pure prose.
    """
    if not text.startswith("---"):
        return {}, text

    lines = text.splitlines()
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            raw = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :])
            try:
                parsed = yaml.safe_load(raw)
            except yaml.YAMLError as exc:
                raise PackError(f"invalid frontmatter: {exc}") from exc
            if parsed is None:
                parsed = {}
            if not isinstance(parsed, dict):
                raise PackError("frontmatter must be a mapping")
            return parsed, body.lstrip("\n")

    # An opening delimiter with no close is a truncated file, not prose.
    raise PackError("frontmatter opened with '---' but was never closed")


def _read_rule(pack_name: str, relative: str, text: str) -> Rule:
    frontmatter, body = parse_frontmatter(text)
    slug = Path(relative).stem

    # `globs: "*.py"` and `globs: ["*.py"]` are both natural to write, so both
    # are accepted; anything else is ignored rather than crashing the load.
    raw_globs = frontmatter.get("globs") or []
    if isinstance(raw_globs, str):
        globs = [raw_globs]
    elif isinstance(raw_globs, list):
        globs = [str(item) for item in raw_globs]
    else:
        globs = []

    title = frontmatter.get("title")
    if not isinstance(title, str) or not title.strip():
        raise PackError(f"{pack_name}:{relative} has no 'title' in its frontmatter")

    if not body.strip():
        raise PackError(f"{pack_name}:{relative} has a title but no body")

    return Rule(
        id=slug,
        title=title.strip(),
        body=body.strip(),
        globs=globs,
        always=bool(frontmatter.get("always", False)),
        pack=pack_name,
    )


def _read_skill(pack_name: str, directory: str, text: str, resources_: dict[str, bytes]) -> Skill:
    frontmatter, body = parse_frontmatter(text)
    name = frontmatter.get("name")
    description = frontmatter.get("description")

    # The specification requires exactly these two fields, and requires `name`
    # to match the directory. Enforcing it here means a malformed skill fails
    # at pack-load time rather than being silently ignored by an agent.
    if not isinstance(name, str) or not name:
        raise PackError(f"{pack_name}: skill '{directory}' has no 'name'")
    if not isinstance(description, str) or not description:
        raise PackError(f"{pack_name}: skill '{directory}' has no 'description'")
    if name != directory:
        raise PackError(f"{pack_name}: skill name '{name}' must match its directory '{directory}'")

    return Skill(
        name=name,
        description=description,
        body=body.strip(),
        pack=pack_name,
        resources=resources_,
    )


def _read_agent(pack_name: str, relative: str, text: str) -> Agent:
    frontmatter, body = parse_frontmatter(text)
    stem = Path(relative).stem

    for key in frontmatter:
        if key not in _AGENT_KEYS:
            raise PackError(
                f"{pack_name}: agent '{stem}' has unknown frontmatter key '{key}'; "
                f"allowed keys are {', '.join(_AGENT_KEYS)}"
            )

    name = frontmatter.get("name")
    description = frontmatter.get("description")

    # Claude Code addresses an agent by the `name` in its frontmatter and finds
    # it by filename, so a mismatch is an agent that exists under one name and
    # is invoked under another. Same rule as skills, enforced at the same point.
    if not isinstance(name, str) or not name:
        raise PackError(f"{pack_name}: agent '{stem}' has no 'name'")
    if not isinstance(description, str) or not description:
        raise PackError(f"{pack_name}: agent '{stem}' has no 'description'")
    if name != stem:
        raise PackError(f"{pack_name}: agent name '{name}' must match its filename '{stem}'")
    if not body.strip():
        raise PackError(f"{pack_name}: agent '{stem}' has a description but no body")

    model = frontmatter.get("model")
    if model is not None and not isinstance(model, str):
        raise PackError(f"{pack_name}: agent '{stem}' has a 'model' that is not a string")

    return Agent(
        name=name,
        description=description,
        tools=_name_list(pack_name, stem, "tools", frontmatter.get("tools")),
        model=model,
        skills=_name_list(pack_name, stem, "skills", frontmatter.get("skills")),
        body=body.strip(),
        pack=pack_name,
    )


def _name_list(pack_name: str, agent: str, key: str, raw: object) -> list[str]:
    """Read a list of names written either as YAML or comma-separated.

    Claude Code's own examples write `tools: Read, Bash`, so that form has to
    work; a YAML list is the natural alternative and reads to the same thing.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [item.strip() for item in raw.split(",") if item.strip()]
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return [str(item).strip() for item in raw if str(item).strip()]
    raise PackError(
        f"{pack_name}: agent '{agent}' has '{key}' that is neither a list "
        "nor a comma-separated string"
    )


def load_pack_from_files(files: dict[str, bytes], *, source: str = "builtin") -> Pack:
    """Build a :class:`Pack` from an in-memory file mapping.

    Taking a mapping rather than a directory keeps loading identical whether
    the bytes came from the filesystem or from inside a wheel, and makes the
    loader trivially testable.
    """
    raw_meta = files.get("pack.yaml")
    if raw_meta is None:
        raise PackError(f"{source}: no pack.yaml")

    try:
        parsed = yaml.safe_load(raw_meta.decode("utf-8")) or {}
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise PackError(f"{source}: pack.yaml is not valid YAML: {exc}") from exc

    try:
        meta = PackMeta.model_validate(parsed)
    except ValidationError as exc:
        raise PackError(f"{source}: pack.yaml is not valid:\n{exc}") from exc

    pack = Pack(meta=meta, files=files, source=source)

    for path in sorted(files):
        if path.startswith("rules/") and path.endswith(".md"):
            pack.rules.append(_read_rule(meta.name, path, files[path].decode("utf-8")))

    for path in sorted(files):
        if path.startswith("skills/") and path.endswith("/SKILL.md"):
            directory = path.split("/")[1]
            prefix = f"skills/{directory}/"
            extras = {
                inner[len(prefix) :]: content
                for inner, content in files.items()
                if inner.startswith(prefix) and inner != path
            }
            pack.skills.append(
                _read_skill(meta.name, directory, files[path].decode("utf-8"), extras)
            )

    for path in sorted(files):
        if path.startswith("agents/") and path.endswith(".md"):
            pack.agents.append(_read_agent(meta.name, path, files[path].decode("utf-8")))

    return pack


def read_directory(root: Path) -> dict[str, bytes]:
    """Read every file under ``root`` into a path-keyed mapping."""
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in _IGNORED_NAMES:
            continue
        files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def load_from_path(root: Path) -> Pack:
    """Load a pack from a directory. Used for `path` sources and tests."""
    if not root.is_dir():
        raise PackError(f"{root} is not a directory")
    return load_pack_from_files(read_directory(root), source=f"path:{root}")


def _builtin_root() -> Traversable | None:
    """Locate the bundled packs, whether installed or running from source.

    In a wheel they live at ``aidlc/_packs`` as package data. In a development
    checkout, and under an editable install, that module does not exist, so we
    fall back to the ``packs/`` directory beside ``src/``. Both a
    ``Traversable`` and a ``Path`` support the small interface used here.
    """
    try:
        anchor = resources.files(_BUILTIN_ANCHOR)
    except (ModuleNotFoundError, TypeError, ImportError):
        anchor = None
    if anchor is not None and anchor.is_dir():
        return anchor

    # src/aidlc/packs/loader.py -> src/aidlc -> src -> repository root
    source_tree = Path(__file__).resolve().parents[3] / "packs"
    return source_tree if source_tree.is_dir() else None


def available_builtin() -> list[str]:
    """Names of packs bundled with this installation."""
    root = _builtin_root()
    if root is None:
        return []
    return sorted(entry.name for entry in root.iterdir() if entry.is_dir())


def load_builtin(name: str) -> Pack:
    """Load a pack bundled with this installation."""
    root = _builtin_root()
    if root is None:  # pragma: no cover - only in a broken installation
        raise PackError(
            "no builtin packs found. This aidlc installation is incomplete; reinstall it."
        )

    anchor = root.joinpath(name)
    if not anchor.is_dir():
        known = ", ".join(available_builtin()) or "none"
        raise PackError(f"no builtin pack named '{name}'. Available: {known}")

    files: dict[str, bytes] = {}

    def walk(entry: Traversable, prefix: str) -> None:
        for child in entry.iterdir():
            path = f"{prefix}{child.name}"
            if child.is_dir():
                walk(child, path + "/")
            elif child.name not in _IGNORED_NAMES:
                files[path] = child.read_bytes()

    walk(anchor, "")
    return load_pack_from_files(files, source="builtin")


def load_many(names: list[str], *, search_paths: dict[str, Path] | None = None) -> list[Pack]:
    """Load a set of packs by name, preferring an explicit path source.

    A path source is how a candidate version is evaluated against a baseline:
    check out the branch, point at it, and run the suite. That covers the
    experiment case without a resolver, a registry or a network fetch.
    """
    search_paths = search_paths or {}
    packs: list[Pack] = []
    for name in names:
        if name in search_paths:
            packs.append(load_from_path(search_paths[name]))
        else:
            packs.append(load_builtin(name))
    return packs
