"""Tests for the CI layer: the matrix command, the caller, and the workflows.

The workflow tests are static checks on this repository's own YAML. They exist
because the failure modes they guard against are silent: a relative `uses:`
runs the caller's file instead of ours with no error, and an unrewritten ref
makes a pinned release track `main` while looking pinned.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from aidlc.commands.ci import matrix
from aidlc.commands.sync import init
from aidlc.render.workflow import PLATFORM_REF, PLATFORM_REPO, WORKFLOW_PATH, caller_workflow

FIXTURES = Path(__file__).parent / "fixtures"
WORKFLOWS = Path(__file__).parents[1] / ".github/workflows"


@pytest.fixture(autouse=True)
def outside_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    """The matrix should arrive on stdout when not running under Actions.

    A runner sets ``GITHUB_OUTPUT`` for every step, including the one running
    this suite, and the command would then write to the step-output file and
    print nothing. These tests are about the matrix, not the transport, so
    they must not depend on where they happen to run.
    """
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    destination = tmp_path / "repo"
    shutil.copytree(FIXTURES / "polyglot", destination)
    return destination


def matrix_for(repo: Path, capsys: pytest.CaptureFixture[str]) -> list[dict[str, str]]:
    assert matrix(repo) == 0
    output = capsys.readouterr().out
    line = next(line for line in output.splitlines() if line.startswith("matrix="))
    return json.loads(line.removeprefix("matrix="))["include"]


# -- the matrix --------------------------------------------------------------


def test_matrix_has_one_entry_per_target(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    init(repo)
    entries = matrix_for(repo, capsys)

    assert {entry["target"] for entry in entries} == {"api", "web"}


def test_matrix_carries_the_commands_for_each_target(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    init(repo)
    entries = {entry["target"]: entry for entry in matrix_for(repo, capsys)}

    assert entries["api"]["install"] == "uv sync --locked"
    assert entries["api"]["setup"] == "uv"
    assert entries["web"]["setup"] == "node"


def test_matrix_entry_names_are_readable(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """These strings become the check names people read in a pull request."""
    init(repo)
    names = {entry["name"] for entry in matrix_for(repo, capsys)}

    assert "python api 3.13" in names


def test_a_target_with_no_declared_version_still_gets_one_entry(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty version list means the runner default, not zero builds."""
    init(repo)
    web = next(entry for entry in matrix_for(repo, capsys) if entry["target"] == "web")

    assert web["version"] == ""


def test_matrix_reports_when_there_is_nothing_to_build(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty matrix is a workflow error, so the flag must be emitted."""
    (tmp_path / ".aidlc").mkdir()
    init(tmp_path)

    assert matrix(tmp_path) == 0
    assert "any=false" in capsys.readouterr().out


def test_matrix_without_a_profile_fails_with_advice(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert matrix(repo) == 1
    assert "aidlc init" in capsys.readouterr().err


# -- the generated caller ----------------------------------------------------


def test_caller_declares_its_own_permissions() -> None:
    """Permissions only shrink down a call chain.

    The platform workflow cannot grant itself anything, so if the caller does
    not declare this, nothing downstream can have it.
    """
    parsed = yaml.safe_load(caller_workflow())
    assert parsed["permissions"] == {"contents": "read"}


def test_caller_pins_the_platform_to_a_major_tag() -> None:
    parsed = yaml.safe_load(caller_workflow())
    uses = parsed["jobs"]["ci"]["uses"]

    assert uses.startswith(f"{PLATFORM_REPO}/.github/workflows/aidlc-ci.yml@")
    assert uses.endswith(f"@{PLATFORM_REF}")


def test_caller_cancels_superseded_runs() -> None:
    parsed = yaml.safe_load(caller_workflow())
    assert parsed["concurrency"]["cancel-in-progress"] is True


def test_caller_is_marked_generated() -> None:
    assert "Do not edit" in caller_workflow()


def test_workflow_is_emitted_only_for_github_repos_with_targets(repo: Path) -> None:
    """A workflow in a repo with nothing to build is a check that always
    passes and verifies nothing, which is worse than no check."""
    init(repo)
    # The fixture has no git remote, so no host is detected.
    assert not (repo / ".github/workflows/aidlc.yml").exists()


# -- this repository's own workflows -----------------------------------------


def _workflow_files() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml"))


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_workflow_parses(path: Path) -> None:
    assert yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_no_relative_uses_anywhere(path: Path) -> None:
    """A relative `uses:` inside a called workflow resolves against the
    CALLER's repository. If the caller has a file at the same path, theirs
    runs instead of ours, silently. This must never ship."""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("uses:"):
            assert "./" not in stripped, f"{path.name}:{number} uses a relative path"


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_third_party_actions_are_pinned_by_sha(path: Path) -> None:
    """Tags move; SHAs do not. `astral-sh/setup-uv` does not even publish a
    moving major tag, so a tag pin there would not resolve at all."""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped.startswith("uses:"):
            continue
        reference = stripped.removeprefix("uses:").split("#")[0].strip()
        if reference.startswith(PLATFORM_REPO):
            continue  # our own refs are rewritten at release time
        _, _, ref = reference.partition("@")
        assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref), (
            f"{path.name}:{number} pins {reference} by tag rather than SHA"
        )


def test_internal_references_are_marked_for_release_rewriting() -> None:
    """Every internal ref in the platform's workflows must carry the marker the
    release job rewrites.

    An unmarked one would keep pointing at main forever, so a consumer pinning
    a version would silently run whatever main says today.

    The generated caller is exempt by design: it is this repository consuming
    its own platform, and its major-tag ref is the consumer pin that must
    survive the rewrite. The caller tests above hold it to that ref.
    """
    generated_caller = WORKFLOWS.parents[1] / WORKFLOW_PATH
    for path in _workflow_files():
        if path == generated_caller:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("uses:") and PLATFORM_REPO in stripped:
                assert "# aidlc:pin" in stripped, (
                    f"{path.name}:{number} references the platform without a pin marker"
                )


def test_dispatcher_guards_against_an_empty_matrix() -> None:
    """A matrix that evaluates to nothing is a workflow error, not a no-op."""
    parsed = yaml.safe_load((WORKFLOWS / "aidlc-ci.yml").read_text(encoding="utf-8"))
    assert "any == 'true'" in parsed["jobs"]["build"]["if"]


def test_audit_step_is_declared_and_passed_through() -> None:
    """A step the matrix emits but the workflow does not declare is rejected
    by Actions at call time, so every StepName must exist at both ends."""
    reusable = yaml.safe_load((WORKFLOWS / "reusable-lang-ci.yml").read_text(encoding="utf-8"))
    dispatcher = yaml.safe_load((WORKFLOWS / "aidlc-ci.yml").read_text(encoding="utf-8"))

    inputs = reusable[True]["workflow_call"]["inputs"]  # `on:` parses as True
    assert "audit" in inputs
    assert dispatcher["jobs"]["build"]["with"]["audit"] == "${{ matrix.audit }}"

    step_names = [step["name"] for step in reusable["jobs"]["build"]["steps"] if "name" in step]
    assert step_names.index("test") < step_names.index("audit") < step_names.index("build")


def test_dispatcher_checks_for_drift_before_building() -> None:
    """The committed profile is an unverifiable claim without this step."""
    parsed = yaml.safe_load((WORKFLOWS / "aidlc-ci.yml").read_text(encoding="utf-8"))
    commands = [step.get("run", "") for step in parsed["jobs"]["plan"]["steps"]]

    assert any("aidlc check" in command for command in commands)
