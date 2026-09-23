"""Detection tests, one fixture repository per path worth exercising.

These are the tests that stop a plausible-looking adapter change from silently
generating the wrong CI for a whole ecosystem.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aidlc.detect import detect, scan
from aidlc.detect.adapters import ADAPTERS
from aidlc.schemas.config import Config
from aidlc.schemas.profile import Profile, SetupKind, StepName, StepSource

FIXTURES = Path(__file__).parent / "fixtures"

#: Every fixture repository detection is run over unaided. `escape-hatch` is
#: left out: no adapter knows Zig, so it produces a target only with a config.
DETECTABLE_FIXTURES = sorted(
    path.name for path in FIXTURES.iterdir() if path.is_dir() and path.name != "escape-hatch"
)


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
    """`fastapi` brings its own pack and observability; `boto3` brings AWS."""
    profile = profile_for("python-uv")
    assert profile.targets[0].frameworks == ["aws", "fastapi"]
    assert profile.packs_selected == [
        "core",
        "rules-security",
        "rules-python",
        "rules-aws",
        "rules-observability",
        "rules-fastapi",
    ]


def test_auto_selection_skips_packs_that_are_not_installed() -> None:
    """Detection may recognise a framework whose pack is not written yet.

    Selecting one that does not exist would make detection fail on a perfectly
    valid repository, so automatic selection is filtered against what ships.
    An explicit list in config is deliberately *not* filtered: a name someone
    typed is intent, and a typo in it should fail loudly.
    """
    from aidlc.packs.loader import available_builtin

    assert "rules-spring" not in available_builtin(), "this test needs a genuinely absent pack"

    profile = profile_for("jvm-maven")
    assert "spring-boot" in profile.targets[0].frameworks, "the hint is still recorded"
    assert "rules-spring" not in profile.packs_selected
    assert set(profile.packs_selected) <= set(available_builtin())


def test_security_pack_is_selected_for_every_repository(tmp_path: Path) -> None:
    """`rules-security` declares `applies_when: always`, and detection must
    honour that flag from the manifest rather than from a table, so that a
    repository no adapter recognises still gets it."""
    for fixture in ("python-uv", "node-react", "jvm-maven", "go-mod", "sam-fastapi"):
        assert "rules-security" in profile_for(fixture).packs_selected, fixture
    assert detect(tmp_path).packs_selected == ["core", "rules-security"]


def test_universal_packs_come_right_after_core() -> None:
    profile = profile_for("node-react")
    assert profile.packs_selected[:2] == ["core", "rules-security"]


def test_react_selects_the_react_pack() -> None:
    profile = profile_for("node-react")
    assert "rules-react" in profile.packs_selected


def test_plain_react_app_does_not_get_backend_or_infra_packs() -> None:
    """A frontend with no AWS evidence must not be told how to write IAM."""
    profile = profile_for("node-react")
    assert profile.packs_selected == ["core", "rules-security", "rules-typescript", "rules-react"]
    assert "rules-aws" not in profile.packs_selected
    assert "rules-fastapi" not in profile.packs_selected
    assert "rules-observability" not in profile.packs_selected


def test_express_server_selects_the_observability_pack(tmp_path: Path) -> None:
    """A Node server is deployed and paged on like any other; the table gives
    it the observability pack even though no `rules-express` ships."""
    (tmp_path / "package.json").write_text(
        '{"name": "api", "dependencies": {"express": "^5.0.0"}}', encoding="utf-8"
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    profile = detect(tmp_path)
    assert profile.targets[0].frameworks == ["express"]
    assert profile.packs_selected == [
        "core",
        "rules-security",
        "rules-typescript",
        "rules-observability",
    ]


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


def test_uv_project_audits_its_dependencies_and_a_pip_project_does_not(tmp_path: Path) -> None:
    """`uv run --with` can run pip-audit without the project listing it. pip
    has no equivalent, so emitting an audit there would fail on a tool that
    was never installed."""
    assert step_command(profile_for("python-uv"), ".", StepName.AUDIT) == (
        "uv run --with pip-audit pip-audit"
    )

    (tmp_path / "requirements.txt").write_text("httpx\n", encoding="utf-8")
    assert step_command(detect(tmp_path), ".", StepName.AUDIT) is None


def test_audit_runs_after_test_and_before_build() -> None:
    """A known CVE in a dependency must never mask a failing test."""
    names = list(StepName)
    assert names.index(StepName.TEST) < names.index(StepName.AUDIT) < names.index(StepName.BUILD)


def test_type_checker_declared_as_a_dependency_yields_a_typecheck_step() -> None:
    """A project that installs pyright into its dev group intends to run it,
    whether or not it has written a `[tool.pyright]` table yet."""
    profile = profile_for("sam-fastapi")
    backend = next(t for t in profile.targets if t.path == "backend")

    assert backend.facts["type_checker"] == "pyright"
    assert step_command(profile, "backend", StepName.TYPECHECK) == "uv run pyright"


def test_type_checker_config_table_beats_the_dependency_list(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n'
        '[dependency-groups]\ndev = ["pyright"]\n'
        "[tool.mypy]\nstrict = true\n",
        encoding="utf-8",
    )
    assert detect(tmp_path).targets[0].facts["type_checker"] == "mypy"


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


def test_npm_project_audits_its_dependencies() -> None:
    profile = profile_for("polyglot")
    assert step_command(profile, "web", StepName.AUDIT) == "npm audit --audit-level=high"


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


# -- Infrastructure ----------------------------------------------------------


def test_sam_template_is_an_infra_target_linted_with_cfn_lint() -> None:
    profile = profile_for("sam-fastapi")
    infra = next(t for t in profile.targets if t.path == "infra")

    assert infra.ecosystem == "infra"
    assert infra.languages == ["YAML"]
    assert infra.manager is None
    assert infra.frameworks == ["aws", "sam"]
    # pipx is on the runner image, so no toolchain setup is needed.
    assert infra.job.setup is SetupKind.NONE
    assert infra.job.versions == []
    assert step_command(profile, "infra", StepName.LINT) == "pipx run cfn-lint template.yaml"


def test_sam_template_using_intrinsic_tags_is_still_recognised(tmp_path: Path) -> None:
    """Almost every real template uses `!Ref` or `!Sub`, which a general
    YAML parser rejects. The template is claimed by what it says, not by
    whether the parser happens to like it."""
    (tmp_path / "template.yml").write_text(
        "Transform: AWS::Serverless-2016-10-31\n"
        "Resources:\n  Fn:\n    Type: AWS::Serverless::Function\n"
        "    Properties:\n      Role: !GetAtt Role.Arn\n",
        encoding="utf-8",
    )
    profile = detect(tmp_path)

    assert [t.ecosystem for t in profile.targets] == ["infra"]
    assert profile.targets[0].frameworks == ["aws", "sam"]
    assert step_command(profile, ".", StepName.LINT) == "pipx run cfn-lint template.yml"


def test_plain_cloudformation_template_is_not_labelled_sam(tmp_path: Path) -> None:
    (tmp_path / "template.yaml").write_text(
        'AWSTemplateFormatVersion: "2010-09-09"\nResources:\n  B:\n    Type: AWS::S3::Bucket\n',
        encoding="utf-8",
    )
    assert detect(tmp_path).targets[0].frameworks == ["aws", "cloudformation"]


def test_terraform_directory_is_checked_with_fmt() -> None:
    profile = profile_for("terraform")
    target = profile.targets[0]

    assert target.ecosystem == "infra"
    assert target.languages == ["HCL"]
    assert target.frameworks == ["aws", "terraform"]
    assert target.job.setup is SetupKind.NONE
    assert step_command(profile, ".", StepName.LINT) == "terraform fmt -check -recursive"


def test_terraform_modules_are_covered_by_the_root_job(tmp_path: Path) -> None:
    """`terraform fmt -check -recursive` at the root already walks
    `modules/*`; a job per module would check the same files again."""
    (tmp_path / "main.tf").write_text('provider "aws" {}\n', encoding="utf-8")
    module = tmp_path / "modules" / "net"
    module.mkdir(parents=True)
    (module / "main.tf").write_text('resource "aws_vpc" "main" {}\n', encoding="utf-8")

    profile = detect(tmp_path)

    assert [t.path for t in profile.targets] == ["."]
    assert step_command(profile, ".", StepName.LINT) == "terraform fmt -check -recursive"


def test_samconfig_without_a_conventional_template_is_validated_by_sam() -> None:
    """`sam init` lets a template be called anything; the SAM CLI reads its
    name from samconfig.toml, and `--lint` runs cfn-lint without touching
    AWS."""
    profile = profile_for("sam-config-only")
    target = profile.targets[0]

    assert target.ecosystem == "infra"
    assert target.frameworks == ["aws", "sam"]
    assert target.facts["template"] is None
    assert step_command(profile, ".", StepName.LINT) == "sam validate --lint"


def test_infra_target_does_not_take_install_and_test_from_a_shared_makefile() -> None:
    """The default `sam init` layout has template.yaml, pyproject.toml and a
    Makefile at the same root. `make install` and `make test` belong to the
    Python job, which runs on a runner with uv; the infra job has no
    toolchain set up and would run the tests a second time."""
    profile = profile_for("sam-root")
    by_ecosystem = {t.ecosystem: t for t in profile.targets if t.path == "."}

    assert set(by_ecosystem) == {"infra", "python"}
    infra = by_ecosystem["infra"]
    assert infra.job.setup is SetupKind.NONE
    assert [step.name for step in infra.job.steps] == [StepName.LINT]
    assert infra.job.steps[0].command == "make lint"
    assert infra.job.steps[0].source is StepSource.PROJECT

    python = by_ecosystem["python"]
    assert python.job.setup is SetupKind.UV
    assert python.job.step(StepName.INSTALL).command == "make install"  # type: ignore[union-attr]
    assert python.job.step(StepName.TEST).command == "make test"  # type: ignore[union-attr]


def test_cdk_json_alone_is_not_an_infra_target() -> None:
    """A CDK app is a program the language adapters already build; a second
    target for it would verify nothing the first does not."""
    profile = profile_for("polyglot")
    assert "infra" not in {t.ecosystem for t in profile.targets}


def test_aws_and_fastapi_frameworks_map_to_their_packs() -> None:
    """Every pack named for AWS and FastAPI now ships, so the selection is
    asserted in full and in order.

    The order is what selection produces: `core`, the universal packs, then
    each target's ecosystem pack and its frameworks alphabetically. The
    backend target sorts before `infra`, and `aws` sorts before `fastapi`.
    """
    profile = profile_for("sam-fastapi")
    assert profile.packs_selected == [
        "core",
        "rules-security",
        "rules-python",
        "rules-aws",
        "rules-observability",
        "rules-fastapi",
    ]


def test_every_kind_of_aws_evidence_selects_the_aws_and_observability_packs(
    tmp_path: Path,
) -> None:
    """Infrastructure rules are language-independent, and there is no CDK
    pack: a CDK app, a plain CloudFormation template and a Terraform tree
    all get the same two packs a SAM template does."""
    cdk = tmp_path / "cdk"
    cdk.mkdir()
    (cdk / "pyproject.toml").write_text(
        '[project]\nname = "stack"\nversion = "0.1.0"\ndependencies = ["aws-cdk-lib>=2"]\n',
        encoding="utf-8",
    )
    cloudformation = tmp_path / "cloudformation"
    cloudformation.mkdir()
    (cloudformation / "template.yaml").write_text(
        'AWSTemplateFormatVersion: "2010-09-09"\nResources:\n  B:\n    Type: AWS::S3::Bucket\n',
        encoding="utf-8",
    )
    terraform = tmp_path / "terraform"
    terraform.mkdir()
    (terraform / "main.tf").write_text('provider "aws" {}\n', encoding="utf-8")

    assert detect(cdk).targets[0].frameworks == ["aws-cdk"]
    assert detect(cdk).packs_selected == [
        "core",
        "rules-security",
        "rules-python",
        "rules-aws",
        "rules-observability",
    ]
    for root in (cloudformation, terraform):
        profile = detect(root)
        assert profile.packs_selected == [
            "core",
            "rules-security",
            "rules-aws",
            "rules-observability",
        ], root.name


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
    assert profile.packs_selected == ["core", "rules-security"]


@pytest.mark.parametrize("fixture", DETECTABLE_FIXTURES)
def test_every_fixture_produces_a_runnable_target(fixture: str) -> None:
    """Whatever else it decides, detection must never emit a target with no
    way to verify the code. A job with no steps is a green check that means
    nothing, which is worse than no job at all."""
    profile = profile_for(fixture)
    assert profile.targets, f"{fixture} produced no targets"
    for target in profile.targets:
        assert target.job.steps, f"{fixture}:{target.path} produced a job with no steps"


def test_adapter_default_commands_are_each_produced_by_a_fixture() -> None:
    """Every default command an adapter can emit is produced by at least one
    fixture. A default no fixture produces has never been rendered by a test
    or executed on a runner; `sam validate --lint` shipped that way. The step
    must come from the adapter, not from a Makefile or script that happens to
    spell the same command."""
    produced = {
        step.command
        for fixture in DETECTABLE_FIXTURES
        for target in profile_for(fixture).targets
        for step in target.job.steps
        if step.source is StepSource.DEFAULT
    }
    for adapter in ADAPTERS:
        missing = adapter.default_commands() - produced
        assert not missing, f"{adapter.id}: no fixture produces {sorted(missing)}"
