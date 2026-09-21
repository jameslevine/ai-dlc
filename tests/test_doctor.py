"""Tests for `aidlc doctor`.

The point of these tests is not that doctor reports the right versions; it is
that doctor is *safe*. It must run on a machine with nothing installed, it must
not write anything, and it must not fail the process over optional tooling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aidlc.commands import doctor as doctor_mod
from aidlc.commands.doctor import Capability, Check, Status


def test_collect_returns_capabilities() -> None:
    capabilities = doctor_mod.collect()
    assert capabilities, "doctor must report at least one capability group"
    assert all(isinstance(c, Capability) for c in capabilities)
    assert all(c.checks for c in capabilities), "every group must contain checks"


def test_collect_never_raises_with_empty_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no executables on PATH at all, doctor still produces a report.

    This is the machine-portability promise in miniature: a fresh machine gets
    a useful report, not a traceback.
    """
    monkeypatch.setenv("PATH", "")
    for var in ("AWS_REGION", "AWS_PROFILE", "AWS_ACCESS_KEY_ID", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    capabilities = doctor_mod.collect()
    rendered = doctor_mod.render(capabilities)
    assert "aidlc" in rendered


def test_render_includes_hints_only_for_problems() -> None:
    capabilities = [
        Capability(
            title="Example",
            enables="nothing",
            checks=(
                Check("fine", Status.OK, "1.0", hint="should not appear"),
                Check("broken", Status.WARN, "missing", hint="install the thing"),
            ),
        )
    ]
    rendered = doctor_mod.render(capabilities)
    assert "install the thing" in rendered
    assert "should not appear" not in rendered


def test_doctor_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Doctor must not create a single file, anywhere it can reach."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    doctor_mod.doctor()

    assert list(tmp_path.iterdir()) == [], "doctor wrote to the filesystem"


def test_doctor_succeeds_when_only_optional_tools_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing optional tool is a warning, never a non-zero exit."""
    monkeypatch.setattr(
        doctor_mod,
        "collect",
        lambda: [
            Capability(
                title="Example",
                enables="nothing",
                checks=(Check("optional", Status.WARN, "not installed"),),
            )
        ],
    )
    assert doctor_mod.doctor() == 0


def test_doctor_fails_when_a_required_tool_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        doctor_mod,
        "collect",
        lambda: [
            Capability(
                title="Example",
                enables="everything",
                checks=(Check("git", Status.FAIL, "not installed"),),
            )
        ],
    )
    assert doctor_mod.doctor() == 1
