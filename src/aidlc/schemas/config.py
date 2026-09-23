"""`.aidlc/config.yml` — the only file in a consumer repo a human edits.

The configuration surface is deliberately capped. Every knob is support
burden: something to document, to test across ecosystems, to keep working
through a major version, and to eventually deprecate. The first answer to "can
we add a setting?" is "can the default just be better?".

Unknown keys are a hard error rather than a warning. A silently ignored setting
is worse than a missing one, because the author believes they have a control
they do not have, and the failure surfaces much later as inexplicable
behaviour.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from aidlc.schemas.profile import SetupKind, StepName

CONFIG_SCHEMA_VERSION = 1


class ConfigError(Exception):
    """Raised when a config file cannot be trusted.

    Carries a message written for the person who has to fix the file, not for
    a stack trace.
    """


class Strictness(StrEnum):
    STANDARD = "standard"
    """Profile drift is a warning. The default: a stale profile should not
    block an unrelated change."""

    STRICT = "strict"
    """Profile drift fails the build. Right once a repo's shape has settled."""


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EmitConfig(Base):
    """Which tool-specific files to generate alongside AGENTS.md.

    AGENTS.md itself is not optional: it is the canonical artifact every other
    emitter is derived from, and every major agent reads it.

    The keys are `skills`, `cursor`, `copilot`, `mcp` and `agents`. The last
    controls Claude Code subagent files under `.claude/agents/`.
    """

    skills: bool = True
    cursor: bool = True
    copilot: bool = True
    mcp: bool = True
    agents: bool = True


class DetectConfig(Base):
    ignore: list[str] = Field(default_factory=list)
    """Extra directory names to prune during the scan."""


class TargetOverride(Base):
    """A hand-written target, or corrections to a detected one.

    With ``setup: none`` plus explicit ``steps`` this is the universal escape
    hatch: it makes any language usable immediately, with no adapter written.
    """

    path: str
    setup: SetupKind | None = None
    versions: list[str] | None = None
    steps: dict[StepName, str] = Field(default_factory=dict)
    ecosystem: str | None = None


class McpServer(Base):
    """One MCP server, in the shape the major clients agree on."""

    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    """Set instead of ``command`` for a remote server."""


class Config(Base):
    schema_version: int = Field(default=CONFIG_SCHEMA_VERSION, alias="schema")
    strictness: Strictness = Strictness.STANDARD
    packs: list[str] | None = None
    """Explicit pack selection. Omit to let detection choose."""

    pins: dict[str, str] = Field(default_factory=dict)
    """Exact pack versions. The per-repository rollback lever."""

    emit: EmitConfig = Field(default_factory=EmitConfig)
    detect: DetectConfig = Field(default_factory=DetectConfig)
    targets: list[TargetOverride] = Field(default_factory=list)
    mcp: dict[str, McpServer] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    def override_for(self, path: str) -> TargetOverride | None:
        return next((t for t in self.targets if t.path == path), None)


def load(path: Path) -> Config:
    """Read and validate a config file. Absent file means all defaults.

    An absent config is a supported, normal state: it means "use the platform
    defaults", which is what most repositories should do.
    """
    if not path.exists():
        return Config()

    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{path} could not be read: {exc}") from exc

    if raw is None:
        return Config()
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level.")

    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_explain(path, exc)) from exc


def _explain(path: Path, error: ValidationError) -> str:
    """Turn a pydantic error into advice.

    Unknown keys get the full list of valid ones, because the usual cause is a
    typo or a half-remembered setting, and both are fixed instantly by seeing
    the real names.
    """
    top_level = sorted(name for name in Config.model_fields)
    lines = [f"{path} is not valid:"]
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "(root)"
        if item["type"] == "extra_forbidden":
            lines.append(f"  unknown key: {location}")
        else:
            lines.append(f"  {location}: {item['msg']}")
    lines.append("")
    lines.append(f"Valid top-level keys: {', '.join(top_level)}")
    return "\n".join(lines)
