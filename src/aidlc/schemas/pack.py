"""Pack metadata: the shape of a versioned unit of content.

A pack is the artifact under test. Its version is what a consumer pins, what a
promotion moves and what a rollback reverts; its digest is what an eval record
is keyed on. The two are different on purpose — see :mod:`aidlc.packs.digest`.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PackKind(StrEnum):
    RULES = "rules"
    SKILLS = "skills"
    MODELS = "models"
    EVALS = "evals"
    LIFECYCLE = "lifecycle"
    MIXED = "mixed"
    """A pack carrying more than one kind of content, such as `core`."""


class Emit(StrEnum):
    """Artifacts a pack's content can be rendered into."""

    AGENTS_MD = "agents_md"
    CURSOR_RULES = "cursor_rules"
    COPILOT_INSTRUCTIONS = "copilot_instructions"
    SKILLS = "skills"
    MCP = "mcp"
    CLAUDE_AGENTS = "claude_agents"


class AppliesWhen(BaseModel):
    """Conditions under which detection selects this pack automatically."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ecosystems: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    always: bool = False
    """True for packs like `core` that apply to every repository."""


class PackMeta(BaseModel):
    """Parsed `pack.yaml`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    version: str
    kind: PackKind
    summary: str
    requires: dict[str, str] = Field(default_factory=dict)
    applies_when: AppliesWhen = Field(default_factory=AppliesWhen)
    emits: list[Emit] = Field(default_factory=list)


class Rule(BaseModel):
    """One rule, authored once and rendered into several formats.

    The frontmatter is a deliberate superset of Cursor's `.mdc` format, so the
    Cursor emitter is a pass-through rather than a translation, and the same
    fields drive Copilot's `applyTo` and the AGENTS.md index.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    """Slug taken from the filename; stable across edits to the title."""

    title: str
    body: str
    globs: list[str] = Field(default_factory=list)
    always: bool = False
    """Always-on rules are inlined into AGENTS.md. Conditional rules are
    indexed there and emitted in full only to tools that support path
    scoping, because inlining them would spend tokens on every turn."""

    pack: str = ""
    """Owning pack name, for attribution in eval records and error messages."""

    @property
    def is_conditional(self) -> bool:
        return not self.always and bool(self.globs)


class Skill(BaseModel):
    """An Agent Skill: a folder with a SKILL.md and optional resources.

    Only `name` and `description` are required by the specification, and we do
    not add fields of our own to the frontmatter we write, so that the emitted
    skill stays portable across every tool that reads the format.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    body: str
    pack: str = ""
    resources: dict[str, bytes] = Field(default_factory=dict)
    """Extra files under the skill directory, keyed by relative path."""


class Agent(BaseModel):
    """A Claude Code subagent: `.claude/agents/<name>.md` with frontmatter.

    Only Claude Code gets these. No other tool has an equivalent format: a
    subagent is a separate context with its own system prompt, tool grant and
    model, dispatched by the main session, and neither Cursor nor Copilot
    expose that. So there is nothing to translate to, and the AGENTS.md index
    stays the canonical artifact; an agent supplements it for one tool exactly
    as `.cursor/rules` does for another.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    tools: list[str] = Field(default_factory=list)
    """Tool names the agent may use. Empty means it inherits every tool the
    main session has. `mcp__<server>` grants every tool of that MCP server."""

    model: str | None = None
    """Model alias such as `sonnet`. None inherits the session's model."""

    skills: list[str] = Field(default_factory=list)
    """Skills preloaded into the agent's context."""

    body: str
    """The agent's system prompt."""

    pack: str = ""
    """Owning pack name, for attribution in the generated file's header."""
