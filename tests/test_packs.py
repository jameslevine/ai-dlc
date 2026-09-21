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
