"""Turning packs and a profile into the files each tool reads.

The design rests on one fact about the 2026 landscape: **AGENTS.md is read
natively by every major agent**, so it is the canonical artifact and everything
else is a narrow supplement. Specifically:

* Claude Code reads AGENTS.md only when no CLAUDE.md exists in the directory or
  any directory above it, so we never generate a CLAUDE.md. Generating one
  would shadow the canonical file everywhere.
* Slash commands are deprecated in both Claude Code and VS Code, with skills as
  the stated migration path, and the argument syntaxes do not survive
  translation. We emit skills and no commands.
* `.agents/skills/` is the cross-tool denominator. Claude Code reads only
  `.claude/skills/`, which gets a symlink rather than a second copy.
* MCP configuration is the one area with genuinely no standard: VS Code uses a
  `servers` key where everyone else uses `mcpServers`. That fan-out is the
  strongest justification for a generator in the whole system.

The only thing AGENTS.md cannot express is a rule scoped to a glob, so
conditional rules are indexed there and emitted in full only to Cursor and
Copilot, which support path scoping natively.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

import yaml

from aidlc.packs.loader import Pack
from aidlc.schemas.config import Config
from aidlc.schemas.pack import Agent, Emit, Rule, Skill
from aidlc.schemas.profile import Profile, Target


class ArtifactKind(StrEnum):
    BLOCK = "block"
    """A managed region inside a file the user owns."""

    FILE = "file"
    """A whole file aidlc owns."""

    SYMLINK = "symlink"
    """A link to a path aidlc owns, used to satisfy one tool's fixed location
    without duplicating content."""


@dataclass(frozen=True, slots=True)
class Artifact:
    """One thing to write into the consumer repository."""

    path: str
    kind: ArtifactKind
    content: str = ""
    identifier: str = ""
    """Block id, for BLOCK artifacts."""
    version: str = ""
    target: str = ""
    """Link destination, for SYMLINK artifacts."""


# -- AGENTS.md ---------------------------------------------------------------


def _project_summary(profile: Profile) -> list[str]:
    """Facts about this repository that an agent cannot cheaply rediscover.

    Kept short on purpose. A generated repository overview is precisely the
    thing the ETH Zurich study found to be unhelpful, so this states only how
    to build and test, which is actionable and hard to infer.
    """
    if not profile.targets:
        return []

    lines = ["## This project", ""]
    for target in profile.targets:
        lines.extend(_target_summary(target, single=len(profile.targets) == 1))
    return lines


def _target_summary(target: Target, *, single: bool) -> list[str]:
    where = "" if single and target.path == "." else f" (`{target.path}`)"
    language = ", ".join(target.languages) or target.ecosystem
    manager = f", managed with {target.manager}" if target.manager else ""

    lines = [f"**{language}{where}**{manager}.", ""]
    commands = [
        f"- {step.name.value}: `{step.command}`"
        for step in target.job.steps
        if step.name.value in {"install", "lint", "typecheck", "test", "build"}
    ]
    if commands:
        lines.append("Run these exactly as written; they are what CI runs.")
        lines.append("")
        lines.extend(commands)
        lines.append("")
    return lines


def agents_md_content(packs: list[Pack], profile: Profile) -> str:
    """Build the managed block for AGENTS.md."""
    sections: list[str] = []
    sections.extend(_project_summary(profile))

    always: list[Rule] = []
    conditional: list[Rule] = []
    for pack in packs:
        if not pack.emits(Emit.AGENTS_MD):
            continue
        for rule in pack.rules:
            (always if rule.always else conditional).append(rule)

    if always:
        sections.extend(["## Working agreement", ""])
        for rule in always:
            sections.append(f"### {rule.title}")
            sections.append("")
            sections.append(rule.body)
            sections.append("")

    if conditional:
        # Indexed, not inlined. Inlining a rule that applies to one file type
        # spends its tokens on every turn, which is the cost the ETH result
        # warns about; tools that support glob scoping load it on demand.
        sections.extend(["## Rules that apply to specific files", ""])
        for rule in conditional:
            globs = ", ".join(f"`{g}`" for g in rule.globs)
            sections.append(f"- When editing {globs}: {rule.title}.")
        sections.append("")

    if skills := [skill for pack in packs for skill in pack.skills]:
        sections.extend(["## Available skills", ""])
        for skill in skills:
            summary = " ".join(skill.description.split())
            sections.append(f"- **{skill.name}** — {summary}")
        sections.append("")

    return "\n".join(sections).strip()


def agents_md(packs: list[Pack], profile: Profile, version: str) -> Artifact:
    return Artifact(
        path="AGENTS.md",
        kind=ArtifactKind.BLOCK,
        identifier="core",
        version=version,
        content=agents_md_content(packs, profile),
    )


# -- Cursor ------------------------------------------------------------------


def cursor_rules(packs: list[Pack]) -> list[Artifact]:
    """Emit `.cursor/rules/*.mdc`, one file per conditional rule.

    This is the emitter that genuinely earns its place: a rule that loads only
    when you touch matching files has no AGENTS.md equivalent. The frontmatter
    fields are Cursor's own, so this is a pass-through rather than a
    translation.
    """
    artifacts: list[Artifact] = []
    for pack in packs:
        if not pack.emits(Emit.CURSOR_RULES):
            continue
        for rule in pack.rules:
            if not rule.is_conditional:
                continue
            globs = ",".join(rule.globs)
            content = (
                "---\n"
                f"description: {rule.title}\n"
                f"globs: {globs}\n"
                "alwaysApply: false\n"
                "---\n\n"
                f"{rule.body}\n"
            )
            artifacts.append(
                Artifact(
                    path=f".cursor/rules/{rule.pack}-{rule.id}.mdc",
                    kind=ArtifactKind.FILE,
                    content=content,
                )
            )
    return artifacts


# -- Copilot -----------------------------------------------------------------


def copilot_instructions(packs: list[Pack]) -> list[Artifact]:
    """Emit `.github/instructions/*.instructions.md` with `applyTo` globs.

    Copilot already reads AGENTS.md, so this adds only the path-scoped
    conditional rules, exactly as the Cursor emitter does.
    """
    artifacts: list[Artifact] = []
    for pack in packs:
        if not pack.emits(Emit.COPILOT_INSTRUCTIONS):
            continue
        for rule in pack.rules:
            if not rule.is_conditional:
                continue
            apply_to = ",".join(rule.globs)
            content = f'---\napplyTo: "{apply_to}"\n---\n\n# {rule.title}\n\n{rule.body}\n'
            artifacts.append(
                Artifact(
                    path=f".github/instructions/{rule.pack}-{rule.id}.instructions.md",
                    kind=ArtifactKind.FILE,
                    content=content,
                )
            )
    return artifacts


# -- Skills ------------------------------------------------------------------


def skill_artifacts(packs: list[Pack]) -> list[Artifact]:
    """Emit skills to `.agents/skills/`, plus a symlink for Claude Code.

    Only `name` and `description` go into the frontmatter we write. Adding
    vendor extensions would make the emitted skill non-portable, which defeats
    the reason for choosing this format.
    """
    artifacts: list[Artifact] = []
    seen: set[str] = set()

    for pack in packs:
        if not pack.emits(Emit.SKILLS):
            continue
        for skill in pack.skills:
            if skill.name in seen:
                continue
            seen.add(skill.name)
            artifacts.append(
                Artifact(
                    path=f".agents/skills/{skill.name}/SKILL.md",
                    kind=ArtifactKind.FILE,
                    content=_skill_text(skill),
                )
            )

    if seen:
        artifacts.append(
            Artifact(
                path=".claude/skills",
                kind=ArtifactKind.SYMLINK,
                target="../.agents/skills",
            )
        )
    return artifacts


def _skill_text(skill: Skill) -> str:
    description = " ".join(skill.description.split())
    return f"---\nname: {skill.name}\ndescription: {description}\n---\n\n{skill.body}\n"


# -- Claude Code agents ------------------------------------------------------


def claude_agent_artifacts(packs: list[Pack]) -> list[Artifact]:
    """Emit `.claude/agents/<name>.md`, one whole file per agent.

    Claude Code alone. The main session is the orchestrator, subagents cannot
    spawn subagents, and each agent is a markdown file whose frontmatter names
    its tools, model and preloaded skills. No other tool reads anything like
    it, so unlike skills there is no cross-tool location to write to and link
    from; the file goes straight where Claude Code looks.
    """
    artifacts: list[Artifact] = []
    seen: set[str] = set()

    for pack in packs:
        if not pack.emits(Emit.CLAUDE_AGENTS):
            continue
        for agent in pack.agents:
            if agent.name in seen:
                continue
            seen.add(agent.name)
            artifacts.append(
                Artifact(
                    path=f".claude/agents/{agent.name}.md",
                    kind=ArtifactKind.FILE,
                    content=_agent_text(agent, pack.version),
                )
            )
    return artifacts


class _FrontmatterDumper(yaml.SafeDumper):
    """A dumper that indents block sequences under their key.

    PyYAML's default puts `- item` flush with the parent key. That is valid
    YAML but not what anyone writes by hand, and Claude Code's own examples
    indent, so the generated file should read like one a person wrote.
    """

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super().increase_indent(flow, False)


#: Wider than any description, so each frontmatter field stays on one line
#: instead of being folded. Folded scalars parse identically but read worse.
_FRONTMATTER_WIDTH = 100_000


def _agent_text(agent: Agent, version: str) -> str:
    fields: dict[str, object] = {
        "name": agent.name,
        "description": " ".join(agent.description.split()),
    }
    if agent.tools:
        fields["tools"] = ", ".join(agent.tools)
    if agent.model:
        fields["model"] = agent.model
    if agent.skills:
        fields["skills"] = list(agent.skills)

    # Dumped by a YAML emitter rather than formatted by hand, so a description
    # containing a colon or a quote still parses. Claude Code drops an agent
    # whose frontmatter does not parse, silently.
    frontmatter = yaml.dump(
        fields,
        Dumper=_FrontmatterDumper,
        sort_keys=False,
        allow_unicode=True,
        width=_FRONTMATTER_WIDTH,
    )

    # After the frontmatter, not before: the opening `---` has to be the first
    # bytes of the file or the frontmatter is not recognised at all.
    header = (
        f"<!-- Generated by aidlc from pack {agent.pack}@{version}. "
        "Edit the pack, then run aidlc sync. -->"
    )
    return f"---\n{frontmatter}---\n{header}\n\n{agent.body}\n"


# -- MCP ---------------------------------------------------------------------


def mcp_artifacts(config: Config) -> list[Artifact]:
    """Fan one server declaration out to every client's own format.

    There is no standard here and convergence recently regressed, so this is
    the emitter with the clearest justification. VS Code's key is `servers`;
    every other client uses `mcpServers`.
    """
    if not config.mcp:
        return []

    servers: dict[str, dict[str, object]] = {}
    for name, server in config.mcp.items():
        entry: dict[str, object] = {}
        if server.url:
            entry["url"] = server.url
        if server.command:
            entry["command"] = server.command
            if server.args:
                entry["args"] = server.args
        if server.env:
            entry["env"] = server.env
        servers[name] = entry

    def dump(root_key: str) -> str:
        return json.dumps({root_key: servers}, indent=2, sort_keys=True) + "\n"

    return [
        Artifact(path=".mcp.json", kind=ArtifactKind.FILE, content=dump("mcpServers")),
        Artifact(path=".cursor/mcp.json", kind=ArtifactKind.FILE, content=dump("mcpServers")),
        Artifact(path=".vscode/mcp.json", kind=ArtifactKind.FILE, content=dump("servers")),
    ]
