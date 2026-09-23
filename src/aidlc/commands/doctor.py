"""``aidlc doctor`` — a read-only report on what this machine can do.

Doctor answers one question: which parts of aidlc will work here, right now?
It never installs, configures, or writes anything, and it never fails the
process just because an optional capability is absent. A machine with only git
is a perfectly valid machine for `init`, `sync` and `check`.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from aidlc import __version__, probe


class Status(StrEnum):
    """How a single capability came out.

    ``WARN`` is deliberately distinct from ``FAIL``: an absent optional tool is
    information, not a problem, and colouring it like a failure trains people
    to ignore the whole report.
    """

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


#: Glyphs chosen to read correctly in a pipe, not just a terminal.
_GLYPH = {Status.OK: "+", Status.WARN: "~", Status.FAIL: "x"}


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: Status
    detail: str
    #: Shown only when the status is not OK. One actionable sentence.
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class Capability:
    """A group of checks, plus what stops working if they fail."""

    title: str
    enables: str
    checks: tuple[Check, ...]


def _check_python() -> Check:
    v = sys.version_info
    detail = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) < (3, 12):
        return Check(
            "python",
            Status.FAIL,
            detail,
            hint="aidlc requires Python 3.12 or newer.",
        )
    return Check("python", Status.OK, detail)


def _check_binary(
    name: str,
    *,
    required: bool,
    version_args: tuple[str, ...] = ("--version",),
    hint: str,
) -> Check:
    version = probe.tool_version(name, *version_args)
    if version is None:
        return Check(
            name,
            Status.FAIL if required else Status.WARN,
            "not installed",
            hint=hint,
        )
    return Check(name, Status.OK, version)


def _check_git_identity() -> Check:
    name = probe.run(["git", "config", "--get", "user.name"])
    email = probe.run(["git", "config", "--get", "user.email"])
    if not (name.ok and email.ok):
        return Check(
            "git identity",
            Status.WARN,
            "not configured",
            hint="Set git user.name and user.email, or commits will be unattributable.",
        )
    return Check("git identity", Status.OK, f"{name.stdout} <{email.stdout}>")


def _check_gh_auth() -> Check:
    if probe.which("gh") is None:
        return Check(
            "gh auth",
            Status.WARN,
            "gh not installed",
            hint="Install the GitHub CLI to collect pull-request metrics.",
        )
    # Recent gh versions persist a telemetry device id under the state dir on
    # first run, which would make a read-only probe write to the filesystem.
    # Disabling telemetry for this one call keeps doctor's no-write promise.
    result = probe.run(["gh", "auth", "status"], env={"GH_TELEMETRY": "0"})
    if not result.ok:
        return Check(
            "gh auth",
            Status.WARN,
            "not authenticated",
            hint="Run `gh auth login` to enable pull-request metrics.",
        )
    # `gh auth status` writes its human-readable report to stderr.
    text = result.stdout or result.stderr
    account = next(
        (
            line.strip()
            for line in text.splitlines()
            if "Logged in to" in line or "account" in line.lower()
        ),
        "authenticated",
    )
    return Check("gh auth", Status.OK, account)


def _check_aws() -> Check:
    """Check for AWS credentials without making a network call.

    `sts get-caller-identity` would be authoritative but needs the network, and
    doctor must stay fast and offline. Presence of a profile or key material is
    enough to report; the eval and metrics commands surface the real error if
    the credentials turn out to be invalid.
    """
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    profile = os.environ.get("AWS_PROFILE")
    has_keys = bool(os.environ.get("AWS_ACCESS_KEY_ID"))
    has_config = (
        Path.home().joinpath(".aws", "credentials").exists()
        or Path.home().joinpath(".aws", "config").exists()
    )

    if not (profile or has_keys or has_config):
        return Check(
            "aws credentials",
            Status.WARN,
            "none found",
            hint="Optional. Needed only to publish eval results and metrics to S3.",
        )
    where = "environment" if has_keys else f"profile {profile}" if profile else "~/.aws"
    return Check("aws credentials", Status.OK, f"{where}, region {region or 'unset'}")


def _check_model_access() -> Check:
    """Report which model providers have credentials present in the environment.

    Names only; never the values. Reachability is not tested here because that
    costs a network round trip and, on some providers, money.
    """
    providers = {
        "bedrock": bool(os.environ.get("AWS_REGION") or os.environ.get("AWS_PROFILE")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "ollama": bool(os.environ.get("OLLAMA_HOST")),
    }
    available = [name for name, present in providers.items() if present]
    if not available:
        return Check(
            "model providers",
            Status.WARN,
            "none configured",
            hint="Optional. Needed only for judged evals (`aidlc eval`).",
        )
    return Check("model providers", Status.OK, ", ".join(available))


def collect() -> list[Capability]:
    """Run every check. Pure and side-effect free, so tests can call it directly."""
    return [
        Capability(
            title="Core",
            enables="init, sync, check",
            checks=(
                _check_python(),
                _check_binary(
                    "git",
                    required=True,
                    hint="Install git. aidlc reads repository state for every command.",
                ),
                _check_git_identity(),
            ),
        ),
        Capability(
            title="Continuous integration",
            enables="generated workflows, actionlint",
            checks=(
                _check_binary(
                    "uv",
                    required=False,
                    hint="Install uv to run Python targets the way CI will.",
                ),
                _check_gh_auth(),
            ),
        ),
        Capability(
            title="Quality loop",
            enables="eval, report, metrics",
            checks=(
                _check_model_access(),
                _check_aws(),
            ),
        ),
    ]


def render(capabilities: list[Capability]) -> str:
    """Format the report. Plain text, pipe-safe, no colour."""
    lines: list[str] = [f"aidlc {__version__}", ""]
    hints: list[str] = []

    for capability in capabilities:
        lines.append(f"{capability.title}  ({capability.enables})")
        width = max(len(check.name) for check in capability.checks)
        for check in capability.checks:
            glyph = _GLYPH[check.status]
            lines.append(f"  {glyph} {check.name.ljust(width)}  {check.detail}")
            if check.hint and check.status is not Status.OK:
                hints.append(f"  {check.name}: {check.hint}")
        lines.append("")

    if hints:
        lines.append("Notes")
        lines.extend(hints)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def doctor() -> int:
    """Print the environment report.

    Exit code is 1 only when a *required* capability is missing, so that
    `doctor` is usable as a CI precondition without failing on the many
    optional pieces.
    """
    capabilities = collect()
    sys.stdout.write(render(capabilities))
    failed = any(
        check.status is Status.FAIL for capability in capabilities for check in capability.checks
    )
    return 1 if failed else 0
