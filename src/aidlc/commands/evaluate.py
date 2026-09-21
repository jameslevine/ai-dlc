"""`aidlc eval` — check whether the rule set is earning its keep.

Tier 1 is deterministic, free and runs on every commit. Tier 2, which puts a
model in the loop, is not implemented yet; the command already takes `--tier`
so that adding it does not change the interface people have learned.
"""

from __future__ import annotations

import sys
from pathlib import Path

from aidlc.detect import detect, scan
from aidlc.evals.deterministic import DEFAULT_TOKEN_BUDGET, Severity, run_all, summarise
from aidlc.render.emitters import agents_md_content
from aidlc.workspace import Workspace, WorkspaceError, find_root


def evaluate(
    path: Path | None = None,
    *,
    tier: int = 1,
    budget: int = DEFAULT_TOKEN_BUDGET,
) -> int:
    """Run the eval suite. Exit 1 if any check reports an error."""
    if tier != 1:
        print(
            f"tier {tier} evals are not implemented yet. "
            "Tier 2 puts a model in the loop and is planned; tier 1 is deterministic.",
            file=sys.stderr,
        )
        return 2

    root = find_root(path or Path.cwd())
    workspace = Workspace(root=root)

    try:
        config = workspace.config()
        profile = workspace.stored_profile() or detect(root, config)
        packs = workspace.packs(profile.packs_selected)
    except WorkspaceError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    index = scan(root, extra_ignores=frozenset(config.detect.ignore))
    rendered = agents_md_content(packs, profile)

    stats = summarise(packs, rendered)
    print("Context cost")
    print(f"  packs                {stats['packs']}")
    print(f"  always-on rules      {stats['rules_always']}")
    print(f"  conditional rules    {stats['rules_conditional']}")
    print(f"  skills               {stats['skills']}")
    print(f"  AGENTS.md            ~{stats['agents_md_tokens']} tokens (estimate)")
    print()

    findings = run_all(packs, rendered, index, budget=budget)
    if not findings:
        print("No findings.")
        return 0

    for finding in findings:
        print(finding.format())

    errors = sum(1 for finding in findings if finding.severity is Severity.ERROR)
    warnings = len(findings) - errors
    print()
    print(f"{errors} error(s), {warnings} warning(s).")

    # Warnings are informational on purpose. An idle rule is a candidate for
    # deletion, not a broken build, and failing on it would train people to
    # ignore the whole command.
    return 1 if errors else 0
