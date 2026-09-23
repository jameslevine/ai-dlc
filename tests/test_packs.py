"""Tests for pack loading, and validation of every pack that ships.

The shipped-pack test is the one that matters most: a pack with a YAML syntax
error or a rule missing its title is invisible until someone runs `init` in a
repository that selects it, and by then it looks like a tool bug.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aidlc.packs import digest
from aidlc.packs.loader import (
    PackError,
    available_builtin,
    load_builtin,
    load_pack_from_files,
    parse_frontmatter,
)

MINIMAL_META = b"""
name: demo
version: 1.0.0
kind: rules
summary: A demo pack.
emits: [agents_md]
"""


# -- frontmatter -------------------------------------------------------------


def test_parse_frontmatter_splits_metadata_from_body() -> None:
    front, body = parse_frontmatter("---\ntitle: T\n---\n\nbody here\n")
    assert front == {"title": "T"}
    assert body.strip() == "body here"


def test_missing_frontmatter_is_allowed() -> None:
    front, body = parse_frontmatter("just prose\n")
    assert front == {}
    assert body == "just prose\n"


def test_unclosed_frontmatter_is_an_error() -> None:
    """A truncated file should fail loudly, not be read as prose."""
    with pytest.raises(PackError, match="never closed"):
        parse_frontmatter("---\ntitle: T\nbody\n")


# -- pack loading ------------------------------------------------------------


def test_pack_requires_a_manifest() -> None:
    with pytest.raises(PackError, match="no pack.yaml"):
        load_pack_from_files({"rules/a.md": b"x"})


def test_rule_without_a_title_is_rejected() -> None:
    files = {"pack.yaml": MINIMAL_META, "rules/a.md": b"---\nglobs: ['*.py']\n---\n\nbody\n"}
    with pytest.raises(PackError, match="no 'title'"):
        load_pack_from_files(files)


def test_rule_without_a_body_is_rejected() -> None:
    """A title with no body is a stub that would emit an empty rule."""
    files = {"pack.yaml": MINIMAL_META, "rules/a.md": b"---\ntitle: T\n---\n\n"}
    with pytest.raises(PackError, match="no body"):
        load_pack_from_files(files)


def test_skill_name_must_match_its_directory() -> None:
    """The specification requires it, and agents silently skip skills that
    violate it, so catching it at load time is the only way to notice."""
    files = {
        "pack.yaml": MINIMAL_META,
        "skills/deploy/SKILL.md": b"---\nname: other\ndescription: d\n---\n\nbody\n",
    }
    with pytest.raises(PackError, match="must match its directory"):
        load_pack_from_files(files)


def test_agent_tools_may_be_written_as_a_comma_separated_string() -> None:
    """Claude Code's own examples write `tools: Read, Bash`, so that form must
    load to the same list a YAML sequence would."""
    files = {
        "pack.yaml": MINIMAL_META,
        "agents/reviewer.md": (
            b"---\nname: reviewer\ndescription: d\ntools: Read, Grep, Bash\n"
            b"skills: [review]\nmodel: sonnet\n---\n\nbody\n"
        ),
    }
    pack = load_pack_from_files(files)

    assert len(pack.agents) == 1
    agent = pack.agents[0]
    assert agent.tools == ["Read", "Grep", "Bash"]
    assert agent.skills == ["review"]
    assert agent.model == "sonnet"
    assert agent.body == "body"


def test_agent_name_must_match_its_filename() -> None:
    """Claude Code addresses an agent by the name in its frontmatter and finds
    it by filename, so a mismatch is an agent that exists under one name and
    is invoked under another."""
    files = {
        "pack.yaml": MINIMAL_META,
        "agents/reviewer.md": b"---\nname: other\ndescription: d\n---\n\nbody\n",
    }
    with pytest.raises(PackError, match="must match its filename"):
        load_pack_from_files(files)


def test_unknown_manifest_key_is_rejected() -> None:
    files = {"pack.yaml": MINIMAL_META + b"\nunknown_key: 1\n"}
    with pytest.raises(PackError, match="not valid"):
        load_pack_from_files(files)


# -- digests -----------------------------------------------------------------


def test_digest_changes_when_content_changes() -> None:
    a = digest.digest_files({"a.md": b"one"})
    b = digest.digest_files({"a.md": b"two"})
    assert a != b


def test_digest_is_independent_of_iteration_order() -> None:
    a = digest.digest_files({"a.md": b"1", "b.md": b"2"})
    b = digest.digest_files({"b.md": b"2", "a.md": b"1"})
    assert a == b


def test_digest_is_not_confused_by_path_boundaries() -> None:
    """Length-prefixing the path is what prevents this collision."""
    a = digest.digest_files({"ab/c.md": b"x"})
    b = digest.digest_files({"a/bc.md": b"x"})
    assert a != b


def test_qualified_name_carries_version_and_digest() -> None:
    name = digest.qualified("rules-python", "1.3.0", "sha256:a7f3c9e12b04deadbeef")
    assert name.startswith("rules-python@1.3.0+")


# -- every shipped pack ------------------------------------------------------


def test_at_least_one_pack_ships() -> None:
    assert available_builtin(), "no builtin packs were found"


@pytest.mark.parametrize("name", available_builtin())
def test_shipped_pack_loads_and_is_well_formed(name: str) -> None:
    pack = load_builtin(name)

    assert pack.name == name, "pack.yaml name must match its directory"
    assert pack.version, "every pack needs a version"
    assert pack.meta.summary.strip(), "every pack needs a summary"
    assert pack.meta.emits, "a pack that emits nothing can never reach a repo"


@pytest.mark.parametrize("name", available_builtin())
def test_shipped_pack_rules_are_usable(name: str) -> None:
    pack = load_builtin(name)
    for rule in pack.rules:
        assert rule.title.strip()
        assert rule.body.strip()
        # A rule that is neither always-on nor scoped can never be selected,
        # so it would cost authoring effort and reach no one.
        assert rule.always or rule.globs, f"{name}:{rule.id} is unreachable"


@pytest.mark.parametrize("name", available_builtin())
def test_shipped_pack_skills_are_usable(name: str) -> None:
    pack = load_builtin(name)
    for skill in pack.skills:
        assert skill.description.strip()
        assert skill.body.strip()


@pytest.mark.parametrize("name", available_builtin())
def test_shipped_pack_agents_are_usable(name: str) -> None:
    pack = load_builtin(name)
    for agent in pack.agents:
        assert agent.description.strip()
        assert agent.body.strip()


def test_loading_from_a_path_works(tmp_path: Path) -> None:
    """Path sources are how a candidate pack version is evaluated."""
    from aidlc.packs.loader import load_from_path

    pack_dir = tmp_path / "demo"
    (pack_dir / "rules").mkdir(parents=True)
    (pack_dir / "pack.yaml").write_bytes(MINIMAL_META)
    (pack_dir / "rules/a.md").write_text("---\ntitle: T\nalways: true\n---\n\nbody\n")

    pack = load_from_path(pack_dir)
    assert pack.name == "demo"
    assert pack.source.startswith("path:")
    assert len(pack.rules) == 1


# -- the packs written for a serverless web service ---------------------------


@pytest.mark.parametrize(
    "name", ["rules-fastapi", "rules-aws", "rules-observability", "rules-security"]
)
def test_service_packs_carry_only_conditional_rules(name: str) -> None:
    """Each rule costs one index line in AGENTS.md, never a body on every
    turn. An always-on rule here would be paid for by repositories that never
    touch the files it is about."""
    pack = load_builtin(name)
    assert pack.rules, f"{name} ships no rules"
    for rule in pack.rules:
        assert rule.is_conditional, f"{name}:{rule.id} is not glob-scoped"


def test_security_pack_declares_itself_universal() -> None:
    assert load_builtin("rules-security").meta.applies_when.always is True
