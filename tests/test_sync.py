"""End-to-end tests for init, sync and check against real temporary repos.

These are the tests that would have caught every bug found by hand during
development: the symlink being resolved through, a pack selected but not
installed, and unquoted YAML in a shipped pack.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from aidlc.commands.sync import check, init, sync

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway copy of the polyglot fixture.

    Copied rather than used in place: these tests write, and a test that
    mutates its own fixtures is a test that passes once.
    """
    destination = tmp_path / "repo"
    shutil.copytree(FIXTURES / "polyglot", destination)
    return destination


def read(repo: Path, relative: str) -> str:
    return (repo / relative).read_text(encoding="utf-8")


# -- init --------------------------------------------------------------------


def test_init_generates_the_expected_artifacts(repo: Path) -> None:
    assert init(repo) == 0

    assert (repo / "AGENTS.md").exists()
    assert (repo / ".aidlc/profile.json").exists()
    assert (repo / ".aidlc/aidlc.lock").exists()
    assert (repo / ".aidlc/config.yml").exists()
    assert (repo / ".agents/skills/plan/SKILL.md").exists()
    assert (repo / ".cursor/rules").is_dir()
    assert (repo / ".github/instructions").is_dir()


def test_init_never_writes_a_claude_md(repo: Path) -> None:
    """Claude Code reads AGENTS.md only when no CLAUDE.md shadows it.

    Generating one would silently disable the canonical file for that tool.
    """
    init(repo)
    assert not (repo / "CLAUDE.md").exists()


def test_init_never_writes_slash_commands(repo: Path) -> None:
    """Commands are deprecated in favour of skills in both major tools."""
    init(repo)
    assert not (repo / ".claude/commands").exists()
    assert not (repo / ".github/prompts").exists()


def test_claude_skills_is_a_symlink_not_a_copy(repo: Path) -> None:
    init(repo)
    link = repo / ".claude/skills"

    assert link.is_symlink(), "a second copy would drift from the canonical one"
    assert (link / "plan/SKILL.md").exists()


def test_init_leaves_existing_workflows_alone(repo: Path) -> None:
    before = read(repo, ".github/workflows/deploy.yml")
    init(repo)

    assert read(repo, ".github/workflows/deploy.yml") == before


def test_agents_md_documents_how_to_build_each_target(repo: Path) -> None:
    init(repo)
    agents = read(repo, "AGENTS.md")

    assert "uv sync --locked" in agents
    assert "npm ci" in agents


def test_conditional_rules_are_indexed_not_inlined(repo: Path) -> None:
    """Glob-scoped rules must not spend their tokens on every turn.

    AGENTS.md gets a one-line pointer; the body goes to the tools that can
    load it on demand.
    """
    init(repo)
    agents = read(repo, "AGENTS.md")
    mdc = read(repo, ".cursor/rules/rules-python-dependencies.mdc")

    assert "Dependencies go through uv" in agents
    assert "Never edit `uv.lock` by hand." not in agents
    assert "Never edit `uv.lock` by hand." in mdc


def test_cursor_rules_carry_cursor_frontmatter(repo: Path) -> None:
    init(repo)
    mdc = read(repo, ".cursor/rules/rules-python-dependencies.mdc")

    assert mdc.startswith("---\n")
    assert "globs: pyproject.toml,uv.lock,**/*.py" in mdc
    assert "alwaysApply: false" in mdc


def test_copilot_instructions_carry_apply_to(repo: Path) -> None:
    init(repo)
    instructions = read(repo, ".github/instructions/rules-python-dependencies.instructions.md")

    assert 'applyTo: "pyproject.toml,uv.lock,**/*.py"' in instructions


def test_skill_frontmatter_stays_portable(repo: Path) -> None:
    """Only the two fields the specification requires.

    Vendor extensions would make the emitted skill non-portable, which defeats
    the reason for choosing the format.
    """
    init(repo)
    skill = read(repo, ".agents/skills/plan/SKILL.md")
    header = skill.split("---")[1]

    assert "name: plan" in header
    assert "description:" in header
    for vendor_field in ("allowed-tools", "user-invocable", "context:", "argument-hint"):
        assert vendor_field not in header


def test_init_writes_the_reviewer_agent_with_frontmatter_claude_code_can_read(
    repo: Path,
) -> None:
    """Claude Code parses the frontmatter as YAML and silently drops an agent
    whose frontmatter does not parse, so the generated file must parse and
    must start with the delimiter at byte 0."""
    init(repo)
    text = read(repo, ".claude/agents/reviewer.md")

    assert text.startswith("---\n")
    header = yaml.safe_load(text.split("---\n")[1])
    assert header["name"] == "reviewer"
    assert header["description"].strip()
    assert header["tools"] == "Read, Grep, Glob, Bash"
    assert header["skills"] == ["review"]
    assert "model" not in header, "an omitted model must inherit, not be written as null"
    assert "Generated by aidlc from pack core@" in text

    assert (repo / ".agents/skills/orchestrate/SKILL.md").exists()
    assert (repo / ".claude/skills").is_symlink(), "agents must not disturb the skills link"


def test_agents_can_be_switched_off(repo: Path) -> None:
    (repo / ".aidlc").mkdir(parents=True, exist_ok=True)
    (repo / ".aidlc/config.yml").write_text("schema: 1\nemit:\n  agents: false\n", encoding="utf-8")

    assert init(repo) == 0
    assert not (repo / ".claude/agents").exists()
    assert (repo / ".claude/skills").is_symlink()


# -- idempotency -------------------------------------------------------------


def test_sync_twice_produces_no_change(repo: Path) -> None:
    """The single most important property of a generator."""
    init(repo)
    first = _snapshot(repo)

    assert sync(repo) == 0
    assert _snapshot(repo) == first


def test_check_passes_on_a_freshly_initialised_repo(repo: Path) -> None:
    init(repo)
    assert check(repo) == 0


# -- safety ------------------------------------------------------------------


def test_sync_refuses_after_a_hand_edit_and_changes_nothing(repo: Path) -> None:
    init(repo)
    agents = repo / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8").replace("## This project", "## MINE\n\nkeep me"),
        encoding="utf-8",
    )
    before = agents.read_text(encoding="utf-8")

    assert sync(repo) == 1
    assert agents.read_text(encoding="utf-8") == before
    assert "keep me" in agents.read_text(encoding="utf-8")


def test_force_discards_a_hand_edit_when_explicitly_asked(repo: Path) -> None:
    init(repo)
    agents = repo / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8").replace("## This project", "## MINE\n\nkeep me"),
        encoding="utf-8",
    )

    assert sync(repo, force=True) == 0
    assert "keep me" not in agents.read_text(encoding="utf-8")


def test_check_reports_a_hand_edit(repo: Path) -> None:
    init(repo)
    agents = repo / "AGENTS.md"
    agents.write_text(agents.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    agents.write_text(
        agents.read_text(encoding="utf-8").replace("Run these exactly", "Run nothing"),
        encoding="utf-8",
    )
    assert check(repo) == 1


def test_a_hand_edited_agent_is_refused_not_overwritten(repo: Path) -> None:
    """A whole file aidlc owns is protected the way a managed block is.

    The lockfile records what was written; a file matching neither that nor
    the new output was edited by hand, and that work is not ours to discard.
    The refusal must survive a second `sync`, and only `--force` may override.
    """
    init(repo)
    agent = repo / ".claude/agents/reviewer.md"
    agent.write_text(
        agent.read_text(encoding="utf-8") + "\nAlso check the changelog.\n", encoding="utf-8"
    )
    before = agent.read_text(encoding="utf-8")

    assert check(repo) == 1
    assert sync(repo) == 1
    assert agent.read_text(encoding="utf-8") == before
    assert sync(repo) == 1, "a refused edit must still be refused on the next run"
    assert agent.read_text(encoding="utf-8") == before

    assert sync(repo, force=True) == 0
    assert "Also check the changelog." not in agent.read_text(encoding="utf-8")
    assert check(repo) == 0


def test_check_detects_a_newly_added_language(repo: Path) -> None:
    init(repo)
    (repo / "worker").mkdir()
    (repo / "worker/go.mod").write_text("module example.com/worker\n\ngo 1.24\n", encoding="utf-8")

    assert check(repo) == 1


def test_sync_updates_the_profile_when_the_project_changes(repo: Path) -> None:
    init(repo)
    (repo / "worker").mkdir()
    (repo / "worker/go.mod").write_text("module example.com/worker\n\ngo 1.24\n", encoding="utf-8")

    assert sync(repo) == 0
    assert check(repo) == 0
    assert "go test ./..." in read(repo, "AGENTS.md")


def test_dry_run_writes_nothing(repo: Path) -> None:
    init(repo)
    (repo / "worker").mkdir()
    (repo / "worker/go.mod").write_text("module example.com/worker\n\ngo 1.24\n", encoding="utf-8")
    before = _snapshot(repo)

    sync(repo, dry_run=True)
    assert _snapshot(repo) == before


def test_sync_before_init_refuses(repo: Path) -> None:
    assert sync(repo) == 1
    assert not (repo / "AGENTS.md").exists()


def test_check_before_init_refuses(repo: Path) -> None:
    assert check(repo) == 1


def test_a_real_directory_at_the_symlink_path_is_not_replaced(repo: Path) -> None:
    """Someone's own .claude/skills folder is their work, not ours.

    Several real repositories manage skills with a different tool, so this is
    the common case rather than an edge case.
    """
    own = repo / ".claude/skills/mine"
    own.mkdir(parents=True)
    (own / "SKILL.md").write_text("mine\n", encoding="utf-8")

    assert init(repo) == 1
    assert (own / "SKILL.md").read_text(encoding="utf-8") == "mine\n"


def test_a_conflict_still_leaves_a_usable_workspace(repo: Path) -> None:
    """One optional emitter conflicting must not strand the repository.

    Without the profile and lockfile, `check` cannot run at all, so a repo that
    merely has its own .claude/skills folder would be permanently stuck.
    """
    (repo / ".claude/skills").mkdir(parents=True)

    assert init(repo) == 1
    assert (repo / ".aidlc/profile.json").exists()
    assert (repo / ".aidlc/aidlc.lock").exists()
    assert (repo / "AGENTS.md").exists()


def test_claude_md_is_reported_as_shadowing_agents_md(repo: Path) -> None:
    """A pre-existing CLAUDE.md silently disables AGENTS.md for Claude Code.

    aidlc will not touch the file, but staying quiet about it would leave the
    generated instructions mysteriously ignored by one tool.
    """
    (repo / "CLAUDE.md").write_text("project notes\n", encoding="utf-8")
    init(repo)

    import json

    profile = json.loads(read(repo, ".aidlc/profile.json"))
    kinds = {c["kind"] for c in profile["conflicts"]}

    assert "claude_md_shadows_agents_md" in kinds
    assert read(repo, "CLAUDE.md") == "project notes\n"


def test_unknown_config_key_is_rejected_with_the_valid_names(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / ".aidlc").mkdir(parents=True, exist_ok=True)
    (repo / ".aidlc/config.yml").write_text("schema: 1\nstrictnes: strict\n", encoding="utf-8")

    assert init(repo) == 1
    output = capsys.readouterr()
    assert "unknown key" in output.err
    assert "strictness" in output.err, "the error must name the real keys"


def test_init_writes_nothing_outside_the_repository(tmp_path: Path) -> None:
    """The machine-portability promise, enforced rather than asserted."""
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURES / "python-uv", repo)

    import os

    original = dict(os.environ)
    os.environ["HOME"] = str(home)
    os.environ["XDG_CONFIG_HOME"] = str(home)
    try:
        init(repo)
    finally:
        os.environ.clear()
        os.environ.update(original)

    assert list(home.iterdir()) == [], "aidlc wrote outside the target repository"


def _snapshot(repo: Path) -> dict[str, str]:
    """Content of every file aidlc could have written."""
    snapshot: dict[str, str] = {}
    for path in sorted(repo.rglob("*")):
        if path.is_symlink():
            snapshot[str(path.relative_to(repo))] = "link:" + str(path.readlink())
        elif path.is_file():
            snapshot[str(path.relative_to(repo))] = path.read_text(encoding="utf-8")
    return snapshot
