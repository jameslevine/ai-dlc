"""Infrastructure adapter: SAM, CloudFormation and Terraform.

Infrastructure is not a language ecosystem, but it is a buildable unit in the
sense that matters here: a directory with its own lint step and its own rule
packs. Treating it as a target is what gets `rules-aws` selected for a repo
whose only AWS evidence is a template, and what gets that template linted
before it is deployed rather than after.

CDK is deliberately not claimed. A CDK app is a Python or TypeScript program
and the language adapters already build it; `cdk.json` alone adds nothing a
second target could verify.
"""

from __future__ import annotations

from aidlc.detect.adapters.base import TargetFacts, make_job, steps_from_makefile
from aidlc.detect.scanner import RepoIndex
from aidlc.schemas.profile import JobSpec, SetupKind, StepName

_TEMPLATES = ("template.yaml", "template.yml")
_SAM_CONFIG = "samconfig.toml"
_SERVERLESS = "AWS::Serverless"
_FORMAT_VERSION = "AWSTemplateFormatVersion"


class InfraAdapter:
    id = "infra"

    def detect(self, index: RepoIndex) -> list[TargetFacts]:
        candidates = set(index.dirs_containing(*_TEMPLATES, _SAM_CONFIG))
        candidates.update(self._dirname(path) for path in index.files if path.endswith(".tf"))

        # Parents before children, so that a Terraform module directory can
        # see the root that already claims it.
        ordered = sorted(candidates, key=lambda d: (0 if d == "." else d.count("/") + 1, d))

        results: list[TargetFacts] = []
        terraform_roots: list[str] = []
        for directory in ordered:
            facts = self._inspect(index, directory)
            if facts is None:
                continue
            if facts.facts.get("kind") == "terraform":
                # One job per tree: `terraform fmt -check -recursive` at the
                # root already covers `modules/*`, and a job per module would
                # check the same files as many times as there are modules.
                if any(self._is_within(directory, root) for root in terraform_roots):
                    continue
                terraform_roots.append(directory)
            results.append(facts)
        return results

    @staticmethod
    def _dirname(path: str) -> str:
        return path.rsplit("/", 1)[0] if "/" in path else "."

    @staticmethod
    def _is_within(directory: str, ancestor: str) -> bool:
        return ancestor == "." or directory.startswith(ancestor + "/")

    def _inspect(self, index: RepoIndex, directory: str) -> TargetFacts | None:
        prefix = "" if directory == "." else directory + "/"

        template, serverless = self._template(index, prefix)
        samconfig = index.has(prefix + _SAM_CONFIG)
        terraform = index.glob_names(directory, ".tf")

        if template is not None or samconfig:
            kind = "sam" if serverless or samconfig else "cloudformation"
            languages = ["YAML"]
        elif terraform:
            kind = "terraform"
            languages = ["HCL"]
        else:
            return None

        facts = TargetFacts(
            path=directory,
            ecosystem=self.id,
            languages=languages,
            frameworks=["aws", kind],
        )
        facts.facts = {
            "kind": kind,
            "template": template,
            "samconfig": samconfig,
            "terraform_files": [name.rsplit("/", 1)[-1] for name in terraform],
        }
        # `sam init` puts template.yaml, pyproject.toml and a Makefile with
        # `install:` and `test:` at the same root. Those two targets belong
        # to the language target that shares the directory: it runs them on
        # a runner with its toolchain installed, and this job has none. Only
        # `lint` is an infrastructure step.
        declared = steps_from_makefile(index, directory)
        if StepName.LINT in declared:
            facts.declared_steps = {StepName.LINT: declared[StepName.LINT]}
        return facts

    @staticmethod
    def _template(index: RepoIndex, prefix: str) -> tuple[str | None, bool]:
        """The CloudFormation template in this directory, and whether it is SAM.

        `yaml.safe_load` rejects the `!Ref` and `!Sub` tags almost every real
        template uses, so a parse failure is expected rather than exceptional.
        When the parse comes back empty the raw text is checked for the same
        two markers instead; a template is claimed by what it says, not by
        whether a general-purpose YAML parser happens to like it.
        """
        for name in _TEMPLATES:
            path = prefix + name
            if not index.has(path):
                continue
            parsed = index.read_yaml(path)
            if parsed:
                serverless = _SERVERLESS in str(parsed.get("Transform", ""))
                if serverless or _FORMAT_VERSION in parsed:
                    return name, serverless
                continue
            text = index.read_text(path) or ""
            if _SERVERLESS in text:
                return name, True
            if _FORMAT_VERSION in text:
                return name, False
        return None, False

    def job_spec(self, facts: TargetFacts) -> JobSpec:
        defaults: dict[StepName, str] = {}
        if facts.facts.get("kind") == "terraform":
            defaults[StepName.LINT] = "terraform fmt -check -recursive"
        elif template := facts.facts.get("template"):
            # pipx is on the ubuntu-latest image, so cfn-lint needs no setup
            # step and nothing is added to the project's own dependencies.
            defaults[StepName.LINT] = f"pipx run cfn-lint {template}"
        else:
            # samconfig.toml without a conventionally named template: the SAM
            # CLI reads the template path from that file, and `--lint` runs
            # cfn-lint locally without touching AWS.
            defaults[StepName.LINT] = "sam validate --lint"
        return make_job(facts, SetupKind.NONE, defaults)
