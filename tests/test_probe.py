"""Tests for the subprocess probes.

These enforce the three rules in `aidlc.probe`: never raise, never write,
always bounded.
"""

from __future__ import annotations

from pathlib import Path

from aidlc import probe


def test_missing_executable_is_data_not_an_exception() -> None:
    result = probe.run(["this-binary-does-not-exist-anywhere"])
    assert result.ok is False
    assert result.missing is True


def test_empty_command_is_rejected() -> None:
    result = probe.run([])
    assert result.ok is False
    assert result.error == "empty-command"


def test_non_zero_exit_is_reported_without_raising(tmp_path: Path) -> None:
    # Asking for the toplevel outside a repository is a genuine failure.
    # (`rev-parse` with an unknown flag is not: it echoes the flag and exits 0.)
    result = probe.run(["git", "-C", str(tmp_path), "rev-parse", "--show-toplevel"])
    assert result.ok is False
    # It ran and failed, which is different from not being installed.
    assert result.missing is False


def test_timeout_is_captured() -> None:
    result = probe.run(["sleep", "5"], timeout=0.1)
    assert result.ok is False
    assert result.error == "timeout"


def test_tool_version_returns_none_when_absent() -> None:
    assert probe.tool_version("this-binary-does-not-exist-anywhere") is None


def test_git_toplevel_outside_a_repo(tmp_path: Path) -> None:
    assert probe.git_toplevel(tmp_path) is None


def test_git_toplevel_inside_this_repo() -> None:
    top = probe.git_toplevel(Path(__file__).parent)
    assert top is not None
    assert (top / "pyproject.toml").exists()
