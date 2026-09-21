"""Detection tests, one fixture repository per path worth exercising.

These are the tests that stop a plausible-looking adapter change from silently
generating the wrong CI for a whole ecosystem.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aidlc.detect import detect, scan
from aidlc.schemas.config import Config
from aidlc.schemas.profile import Profile, SetupKind, StepName, StepSource

FIXTURES = Path(__file__).parent / "fixtures"


def profile_for(name: str, config: Config | None = None) -> Profile:
    return detect(FIXTURES / name, config)


def step_command(profile: Profile, path: str, step: StepName) -> str | None:
    target = next(t for t in profile.targets if t.path == path)
    found = target.job.step(step)
    return found.command if found else None


# -- the scanner -------------------------------------------------------------


def test_scanner_prunes_dependency_directories() -> None:
    index = scan(FIXTURES / "python-uv")
    assert index.has("pyproject.toml")
    assert not any("node_modules" in path for path in index.files)
    assert not any(".venv" in path for path in index.files)


def test_scanner_prunes_conventional_test_data_directories(tmp_path: Path) -> None:
    """A repository's own fixtures must not become CI targets.

    Without this, running aidlc on any project with test data generates jobs
    that build synthetic manifests, verifying nothing. `testdata` is ignored by
    the Go toolchain itself, so pruning it by default is uncontroversial.
    """
    for directory in ("testdata", "__fixtures__", "__mocks__"):
        nested = tmp_path / directory / "sample"
        nested.mkdir(parents=True)
        (nested / "go.mod").write_text("module x\n\ngo 1.24\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module real\n\ngo 1.24\n", encoding="utf-8")

    profile = detect(tmp_path)
    assert [t.path for t in profile.targets] == ["."]


def test_scanner_prunes_agent_tooling_directories(tmp_path: Path) -> None:
    """A skill's bundled example project is not a target of the host repo.

    Found on a real repository: a skill shipping an example Next.js app under
    .agents/skills/<name>/templates/ was detected as a second Node target.
    """
    template = tmp_path / ".agents/skills/some-skill/templates/example"
    template.mkdir(parents=True)
    (template / "package.json").write_text('{"name": "example"}', encoding="utf-8")
    (tmp_path / "go.mod").write_text("module real\n\ngo 1.24\n", encoding="utf-8")

    profile = detect(tmp_path)
    assert [t.path for t in profile.targets] == ["."]


def test_detect_ignore_prunes_a_project_specific_directory(tmp_path: Path) -> None:
    """The escape hatch for conventions too local to prune by default."""
    nested = tmp_path / "fixtures" / "sample"
    nested.mkdir(parents=True)
    (nested / "go.mod").write_text("module x\n\ngo 1.24\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module real\n\ngo 1.24\n", encoding="utf-8")

    assert len(detect(tmp_path).targets) == 2

    config = Config.model_validate({"schema": 1, "detect": {"ignore": ["fixtures"]}})
    assert [t.path for t in detect(tmp_path, config).targets] == ["."]


def test_scanner_tolerates_a_malformed_manifest(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("this is not [ valid toml", encoding="utf-8")
    index = scan(tmp_path)
    # A broken manifest yields an empty mapping, never an exception.
    assert index.read_toml("pyproject.toml") == {}


def test_scanner_does_not_follow_symlinked_directories(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "go.mod").write_text("module x\n", encoding="utf-8")
    (tmp_path / "link").symlink_to(real, target_is_directory=True)

    index = scan(tmp_path)
    assert index.has("real/go.mod")
    assert not index.has("link/go.mod")


# -- Python ------------------------------------------------------------------


def test_python_uv_project() -> None:
    profile = profile_for("python-uv")
    target = profile.targets[0]

    assert target.ecosystem == "python"
    assert target.manager == "uv"
    assert target.job.setup is SetupKind.UV
    assert target.job.versions == ["3.12"]
    assert target.job.cache_dependency_glob == "uv.lock"
    assert step_command(profile, ".", StepName.INSTALL) == "uv sync --locked"
    assert step_command(profile, ".", StepName.TYPECHECK) == "uv run pyright"
    assert step_command(profile, ".", StepName.TEST) == "uv run pytest"


def test_python_frameworks_select_rule_packs() -> None:
    profile = profile_for("python-uv")
    assert "fastapi" in profile.targets[0].frameworks
    assert "rules-python" in profile.packs_selected
    assert "core" in profile.packs_selected


def test_auto_selection_skips_packs_that_are_not_installed() -> None:
    """The framework table names packs that may not be written yet.

    Selecting one that does not exist would make detection fail on a perfectly
    valid repository, so automatic selection is filtered against what ships.
    An explicit list in config is deliberately *not* filtered: a name someone
    typed is intent, and a typo in it should fail loudly.
    """
    from aidlc.packs.loader import available_builtin

    profile = profile_for("python-uv")
    installed = set(available_builtin())

    assert set(profile.packs_selected) <= installed
    assert "fastapi" in profile.targets[0].frameworks, "the hint is still recorded"


def test_react_selects_the_react_pack() -> None:
    profile = profile_for("node-react")
    assert "rules-react" in profile.packs_selected


def test_jvm_selects_the_java_pack() -> None:
    profile = profile_for("jvm-maven")
    assert "rules-java" in profile.packs_selected


def test_pip_project_without_requirements_does_not_reference_one(tmp_path: Path) -> None:
    """Emitting `-r requirements.txt` for a project that has none produces CI
    that fails on its first step, which is worse than generating no CI."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\nrequires-python = ">=3.12"\n',
        encoding="utf-8",
    )
    profile = detect(tmp_path)
    install = step_command(profile, ".", StepName.INSTALL)

    assert install == "python -m pip install -e ."


def test_pip_project_with_requirements_uses_it(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("httpx\n", encoding="utf-8")
    profile = detect(tmp_path)

    assert step_command(profile, ".", StepName.INSTALL) == (
        "python -m pip install -r requirements.txt"
    )


def test_python_poetry_project_uses_poetry_commands() -> None:
    profile = profile_for("python-poetry")
    target = profile.targets[0]

    assert target.manager == "poetry"
    # Poetry has no first-party setup action, so the generic workflow installs
    # nothing and the commands carry their own runner.
    assert target.job.setup is SetupKind.NONE
    assert step_command(profile, ".", StepName.INSTALL) == "poetry install --no-interaction"
    assert step_command(profile, ".", StepName.TYPECHECK) == "poetry run mypy"
    # No ruff configured, so no lint step is invented.
    assert step_command(profile, ".", StepName.LINT) is None


# -- Node --------------------------------------------------------------------


def test_node_react_uses_declared_scripts() -> None:
    profile = profile_for("node-react")
    target = profile.targets[0]

    assert target.ecosystem == "node"
    assert target.languages == ["TypeScript"]
    assert target.manager == "pnpm"
    assert "react" in target.frameworks
    assert target.job.versions == ["22"]
    assert step_command(profile, ".", StepName.INSTALL) == "pnpm install --frozen-lockfile"


def test_node_project_scripts_beat_adapter_defaults() -> None:
    """The governing precedence rule, tested where it actually matters.

    This project lints with Biome and typechecks with its own script. aidlc
    must run those, not substitute its own opinion.
    """
    profile = profile_for("node-react")
    target = profile.targets[0]

    lint = target.job.step(StepName.LINT)
    assert lint is not None
    assert lint.command == "pnpm run lint"
    assert lint.source is StepSource.PROJECT

    typecheck = target.job.step(StepName.TYPECHECK)
    assert typecheck is not None
    assert typecheck.source is StepSource.PROJECT, "a declared script must win over tsc --noEmit"


def test_node_without_scripts_falls_back_to_defaults() -> None:
    profile = profile_for("node-plain")
    target = profile.targets[0]

    assert target.languages == ["JavaScript"]
    # No lockfile, so `npm ci` would fail; the adapter must not emit it.
    assert step_command(profile, ".", StepName.INSTALL) == "npm install"
    assert target.job.cache_dependency_glob is None
    # Not TypeScript, so no typecheck is invented.
    assert step_command(profile, ".", StepName.TYPECHECK) is None


# -- JVM ---------------------------------------------------------------------


def test_maven_project() -> None:
    profile = profile_for("jvm-maven")
    target = profile.targets[0]

    assert target.ecosystem == "jvm"
    assert target.languages == ["Java"]
    assert target.manager == "maven"
    assert target.job.versions == ["21"]
    assert "spring-boot" in target.frameworks
    assert step_command(profile, ".", StepName.TEST) == "./mvnw -B -ntp verify"


def test_gradle_kotlin_project() -> None:
    profile = profile_for("jvm-gradle")
    target = profile.targets[0]

    assert target.languages == ["Kotlin"]
    assert target.manager == "gradle"
    assert target.job.versions == ["21"], "toolchain block is the version source"
    assert step_command(profile, ".", StepName.TEST) == "./gradlew --no-daemon build"


# -- Go, Rust, .NET ----------------------------------------------------------


def test_go_project() -> None:
    profile = profile_for("go-mod")
    target = profile.targets[0]

    assert target.job.setup is SetupKind.GO
    assert target.job.versions == ["1.24"]
    assert step_command(profile, ".", StepName.TEST) == "go test ./..."
    # golangci-lint is not configured here, so go vet is the linter.
    assert step_command(profile, ".", StepName.LINT) == "go vet ./..."


def test_rust_project() -> None:
    profile = profile_for("rust-cargo")
    target = profile.targets[0]

    assert target.job.setup is SetupKind.RUST
    assert target.job.versions == ["1.84.0"]
    assert step_command(profile, ".", StepName.FORMAT) == "cargo fmt --check"


def test_dotnet_project_prefers_the_solution() -> None:
    profile = profile_for("dotnet-sln")
    target = profile.targets[0]

    assert target.job.setup is SetupKind.DOTNET
    assert target.job.versions == ["9.0.100"]
    assert target.path == ".", "the solution at the root wins over the nested csproj"


# -- Monorepo, conflicts, escape hatch ---------------------------------------


def test_polyglot_repo_yields_one_target_per_unit() -> None:
    profile = profile_for("polyglot")
    by_path = {t.path: t for t in profile.targets}

    assert set(by_path) == {"api", "web"}
    assert by_path["api"].ecosystem == "python"
    assert by_path["web"].ecosystem == "node"
    assert by_path["api"].job.working_directory == "api"


def test_polyglot_repo_selects_packs_for_every_ecosystem() -> None:
    profile = profile_for("polyglot")
    assert {"rules-python", "rules-typescript", "rules-react"} <= set(profile.packs_selected)


def test_existing_workflows_are_reported_never_touched() -> None:
    profile = profile_for("polyglot")
    conflicts = [c for c in profile.conflicts if c.kind == "existing_workflow"]

    assert len(conflicts) == 1
    assert conflicts[0].path == ".github/workflows/deploy.yml"
    assert "will not modify" in conflicts[0].note


def test_escape_hatch_makes_an_unknown_language_buildable() -> None:
    """No adapter knows Zig, and it does not need to.

    An explicit target in config is a first-class target, which is what keeps
    the claim "no language is ever unsupported" honest.
    """
    config = Config.model_validate(
        {
            "schema": 1,
            "targets": [
                {
                    "path": ".",
                    "setup": "none",
                    "steps": {"test": "zig build test", "build": "zig build"},
                }
            ],
        }
    )
    profile = profile_for("escape-hatch", config)
    target = profile.targets[0]

    assert target.ecosystem == "custom"
    assert target.job.setup is SetupKind.NONE
    assert step_command(profile, ".", StepName.TEST) == "zig build test"
    assert target.job.step(StepName.TEST).source is StepSource.CONFIG  # type: ignore[union-attr]


def test_makefile_targets_are_treated_as_project_declarations() -> None:
    profile = profile_for("makefile-python")

    lint = next(t for t in profile.targets if t.path == ".").job.step(StepName.LINT)
    assert lint is not None
    assert lint.command == "make lint", "a Makefile lint target beats the ruff default"
    assert lint.source is StepSource.PROJECT


def test_config_override_beats_everything() -> None:
    config = Config.model_validate(
        {"schema": 1, "targets": [{"path": ".", "steps": {"test": "pytest -x --ff"}}]}
    )
    profile = profile_for("python-uv", config)
    test = next(t for t in profile.targets if t.path == ".").job.step(StepName.TEST)

    assert test is not None
    assert test.command == "pytest -x --ff"
    assert test.source is StepSource.CONFIG


def test_empty_command_in_config_disables_a_step() -> None:
    config = Config.model_validate(
        {"schema": 1, "targets": [{"path": ".", "steps": {"typecheck": ""}}]}
    )
    profile = profile_for("python-uv", config)
    assert step_command(profile, ".", StepName.TYPECHECK) is None


def test_explicit_pack_list_replaces_detection() -> None:
    config = Config.model_validate({"schema": 1, "packs": ["core"]})
    profile = profile_for("python-uv", config)
    assert profile.packs_selected == ["core"]


def test_detect_on_an_empty_directory_is_not_an_error(tmp_path: Path) -> None:
    profile = detect(tmp_path)
    assert profile.targets == []
    assert profile.packs_selected == ["core"]


@pytest.mark.parametrize(
    "fixture",
    [
        "python-uv",
        "python-poetry",
        "node-react",
        "node-plain",
        "jvm-maven",
        "jvm-gradle",
        "go-mod",
        "rust-cargo",
        "dotnet-sln",
        "polyglot",
    ],
)
def test_every_fixture_produces_a_runnable_target(fixture: str) -> None:
    """Whatever else it decides, detection must never emit a target with no
    way to verify the code. A job with no steps is a green check that means
    nothing, which is worse than no job at all."""
    profile = profile_for(fixture)
    assert profile.targets, f"{fixture} produced no targets"
    for target in profile.targets:
        assert target.job.steps, f"{fixture}:{target.path} produced a job with no steps"
