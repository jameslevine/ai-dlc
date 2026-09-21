"""Tests for the tier-1 deterministic checks."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from aidlc.commands.evaluate import evaluate
from aidlc.commands.sync import init
from aidlc.detect import scan
from aidlc.evals import deterministic as det
from aidlc.evals.deterministic import Severity
from aidlc.packs.loader import load_pack_from_files

FIXTURES = Path(__file__).parent / "fixtures"

META = b"""
name: demo
version: 1.0.0
kind: rules
summary: Demo.
emits: [agents_md]
"""


def pack_with(*rules: tuple[str, str]) -> object:
    files: dict[str, bytes] = {"pack.yaml": META}
    for name, content in rules:
        files[f"rules/{name}.md"] = content.encode("utf-8")
    return load_pack_from_files(files)


# -- token budget ------------------------------------------------------------


def test_token_budget_passes_under_the_limit() -> None:
    assert det.check_token_budget("short text", budget=100) == []


def test_token_budget_fails_over_the_limit() -> None:
    findings = det.check_token_budget("x" * 10_000, budget=100)

    assert len(findings) == 1
    assert findings[0].severity is Severity.ERROR
    assert "budget" in findings[0].message


def test_token_estimate_scales_with_length() -> None:
    assert det.estimate_tokens("a" * 400) > det.estimate_tokens("a" * 40)


# -- unreachable rules -------------------------------------------------------


def test_rule_with_neither_always_nor_globs_is_an_error() -> None:
    """Such a rule can never be loaded by any tool, so it is pure cost."""
    pack = pack_with(("orphan", "---\ntitle: Orphan\n---\n\nbody\n"))
    findings = det.check_unreachable_rules([pack])  # type: ignore[list-item]

    assert len(findings) == 1
    assert findings[0].check == "unreachable-rule"
    assert findings[0].severity is Severity.ERROR


def test_always_on_rule_is_reachable() -> None:
    pack = pack_with(("fine", "---\ntitle: Fine\nalways: true\n---\n\nbody\n"))
    assert det.check_unreachable_rules([pack]) == []  # type: ignore[list-item]


# -- duplicates --------------------------------------------------------------


def test_duplicate_titles_are_flagged() -> None:
    """Two rules saying the same thing cost twice and help once."""
    pack = pack_with(
        ("one", "---\ntitle: Use uv\nalways: true\n---\n\nbody\n"),
        ("two", "---\ntitle: use   UV\nalways: true\n---\n\nother\n"),
    )
    findings = det.check_duplicate_rules([pack])  # type: ignore[list-item]

    assert len(findings) == 1
    assert findings[0].check == "duplicate-rule"


# -- idle rules --------------------------------------------------------------


def test_rule_matching_no_file_here_is_a_warning(tmp_path: Path) -> None:
    """A rule scoped to a language this repo does not contain cannot fire.

    A warning rather than an error: a pack is shared across repositories, and
    a rule idle here may be essential elsewhere.
    """
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    index = scan(tmp_path)
    pack = pack_with(("rust", "---\ntitle: Rust rule\nglobs: ['**/*.rs']\n---\n\nbody\n"))

    findings = det.check_globs_match_something([pack], index)  # type: ignore[list-item]

    assert len(findings) == 1
    assert findings[0].severity is Severity.WARNING
    assert findings[0].check == "idle-rule"


def test_rule_matching_a_file_here_is_not_flagged(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    index = scan(tmp_path)
    pack = pack_with(("py", "---\ntitle: Py rule\nglobs: ['**/*.py']\n---\n\nbody\n"))

    assert det.check_globs_match_something([pack], index) == []  # type: ignore[list-item]


def test_double_star_glob_matches_a_root_file(tmp_path: Path) -> None:
    """`**/*.py` must match main.py at the root, which plain fnmatch does not."""
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    index = scan(tmp_path)

    assert det._glob_matches("**/*.py", index)


# -- the command -------------------------------------------------------------


def test_eval_passes_on_a_fresh_repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURES / "python-uv", repo)
    init(repo)

    assert evaluate(repo) == 0
    assert "Context cost" in capsys.readouterr().out


def test_eval_reports_the_context_cost_even_when_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The number is the point, not just the pass. It is what you watch."""
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURES / "python-uv", repo)
    init(repo)
    evaluate(repo)

    assert "tokens (estimate)" in capsys.readouterr().out


def test_eval_fails_when_the_budget_is_exceeded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURES / "python-uv", repo)
    init(repo)

    assert evaluate(repo, budget=10) == 1
    assert "token-budget" in capsys.readouterr().out


def test_unimplemented_tier_is_refused_clearly(capsys: pytest.CaptureFixture[str]) -> None:
    assert evaluate(tier=2) == 2
    assert "not implemented" in capsys.readouterr().err


def test_shipped_packs_pass_their_own_checks() -> None:
    """The packs this project ships must satisfy the rules it enforces."""
    from aidlc.packs.loader import available_builtin, load_builtin

    packs = [load_builtin(name) for name in available_builtin()]
    findings = det.check_unreachable_rules(packs) + det.check_duplicate_rules(packs)

    assert [f.format() for f in findings] == []
