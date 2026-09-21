"""Tier-1 checks: free, instant, and run on every commit.

These exist because of a specific finding. ETH Zurich (arXiv:2602.11988,
February 2026) tested agent context files across SWE-bench Lite and 138 tasks
from repositories with real committed instruction files. The files **did not
generally improve task success rate** and added **over 20% to token cost**.

So the default assumption has to be that a rule is costing you something and
may be earning nothing. These checks make the cost visible and catch the rules
that provably cannot be earning anything: ones that never match a file here,
ones that duplicate another rule, ones scoped so they can never load.

None of this measures whether a rule *helps*. Only an ablation can do that, and
it costs real money per run. What this does is make the cheap, certain failures
impossible to ship.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatch

from aidlc.detect.scanner import RepoIndex
from aidlc.packs.loader import Pack
from aidlc.schemas.pack import Rule

#: Tokens per character, used to estimate context cost without a tokenizer.
#: Roughly four characters per token holds for English prose across the major
#: tokenizers. It is an estimate and reported as one; the trend over time is
#: what matters, not the absolute figure.
CHARS_PER_TOKEN = 4

#: Default ceiling for the always-on portion of AGENTS.md, in estimated tokens.
#: Every turn pays this, in every session, in every tool. The number is a
#: judgement call rather than a measured threshold, chosen to be roughly two
#: screens of prose: enough for a real working agreement, small enough that
#: exceeding it is a decision rather than an accident.
DEFAULT_TOKEN_BUDGET = 1500


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Finding:
    check: str
    severity: Severity
    message: str
    subject: str = ""

    def format(self) -> str:
        where = f" [{self.subject}]" if self.subject else ""
        return f"{self.severity.value}: {self.check}{where}: {self.message}"


def estimate_tokens(text: str) -> int:
    """Approximate token count. Deliberately crude and documented as such."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def check_token_budget(rendered: str, budget: int = DEFAULT_TOKEN_BUDGET) -> list[Finding]:
    """Fail when the always-loaded context exceeds its budget.

    This is the direct answer to the cost half of the ETH result. Instructions
    accumulate: every time an agent misbehaves someone adds a line, and nobody
    ever removes one. A budget converts that drift into a decision.
    """
    estimate = estimate_tokens(rendered)
    if estimate <= budget:
        return []
    return [
        Finding(
            check="token-budget",
            severity=Severity.ERROR,
            subject="AGENTS.md",
            message=(
                f"about {estimate} tokens against a budget of {budget}. "
                "Every turn in every session pays this. Delete a rule, or raise "
                "the budget deliberately."
            ),
        )
    ]


def check_unreachable_rules(packs: list[Pack]) -> list[Finding]:
    """A rule that is neither always-on nor glob-scoped can never load."""
    findings: list[Finding] = []
    for pack in packs:
        for rule in pack.rules:
            if not rule.always and not rule.globs:
                findings.append(
                    Finding(
                        check="unreachable-rule",
                        severity=Severity.ERROR,
                        subject=f"{pack.name}:{rule.id}",
                        message=(
                            "is neither `always: true` nor scoped with `globs`, "
                            "so no tool will ever load it."
                        ),
                    )
                )
    return findings


def check_duplicate_rules(packs: list[Pack]) -> list[Finding]:
    """Two rules saying the same thing cost twice and help once."""
    findings: list[Finding] = []
    seen: dict[str, str] = {}

    for pack in packs:
        for rule in pack.rules:
            key = _normalise(rule.title)
            origin = f"{pack.name}:{rule.id}"
            if key in seen:
                findings.append(
                    Finding(
                        check="duplicate-rule",
                        severity=Severity.WARNING,
                        subject=origin,
                        message=f"repeats the title of {seen[key]}. Keep one.",
                    )
                )
            else:
                seen[key] = origin
    return findings


def check_globs_match_something(packs: list[Pack], index: RepoIndex) -> list[Finding]:
    """Flag rules whose globs match no file in this repository.

    A rule scoped to `**/*.rs` in a repository with no Rust costs authoring
    effort and context budget in the tools that index it, and can never fire.
    Reported as a warning rather than an error, because a pack is shared across
    repositories and a rule that is idle here may be essential elsewhere.
    """
    findings: list[Finding] = []
    for pack in packs:
        for rule in pack.rules:
            if rule.always or not rule.globs:
                continue
            if not any(_glob_matches(glob, index) for glob in rule.globs):
                findings.append(
                    Finding(
                        check="idle-rule",
                        severity=Severity.WARNING,
                        subject=f"{pack.name}:{rule.id}",
                        message=(
                            f"matches no file here ({', '.join(rule.globs)}). "
                            "It cannot fire in this repository."
                        ),
                    )
                )
    return findings


def _glob_matches(glob: str, index: RepoIndex) -> bool:
    # `**/*.py` should also match a file at the repository root, which plain
    # fnmatch does not do, so the bare-suffix form is tried as well.
    candidates = [glob]
    if glob.startswith("**/"):
        candidates.append(glob[3:])
    return any(fnmatch(path, candidate) for path in index.files for candidate in candidates)


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def run_all(
    packs: list[Pack],
    rendered: str,
    index: RepoIndex,
    *,
    budget: int = DEFAULT_TOKEN_BUDGET,
) -> list[Finding]:
    """Every tier-1 check, most severe first."""
    findings = [
        *check_token_budget(rendered, budget),
        *check_unreachable_rules(packs),
        *check_duplicate_rules(packs),
        *check_globs_match_something(packs, index),
    ]
    return sorted(findings, key=lambda f: (f.severity is not Severity.ERROR, f.check, f.subject))


def summarise(packs: list[Pack], rendered: str) -> dict[str, int]:
    """Numbers worth watching over time, whether or not anything failed."""
    always: list[Rule] = [r for p in packs for r in p.rules if r.always]
    conditional: list[Rule] = [p_rule for p in packs for p_rule in p.rules if not p_rule.always]
    return {
        "packs": len(packs),
        "rules_always": len(always),
        "rules_conditional": len(conditional),
        "skills": sum(len(p.skills) for p in packs),
        "agents_md_tokens": estimate_tokens(rendered),
    }
