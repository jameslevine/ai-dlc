"""Safe, read-only probes of the local environment.

Every function here obeys three rules, because they are called by ``aidlc
doctor`` and by detection, both of which must work on a machine that has none
of the tools installed:

1. **Never raise.** A missing binary, a timeout, or a non-zero exit is a
   result, not an error.
2. **Never write.** No file is created, and no command with a side effect is
   run. Callers rely on this to keep the tool non-invasive.
3. **Always bound.** Every subprocess has a timeout, so a hung credential
   helper cannot wedge the CLI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: Subprocess timeout. Generous enough for a cold `gh auth status`, short
#: enough that a hung helper does not look like a crash.
DEFAULT_TIMEOUT_S = 10.0


@dataclass(frozen=True, slots=True)
class Result:
    """The outcome of running a command, with failure modelled as data."""

    ok: bool
    stdout: str = ""
    stderr: str = ""
    #: Set when the command could not run at all, as opposed to running and
    #: failing. Distinguishing these matters: "git is not installed" and "git
    #: said no" call for different advice.
    error: str | None = None

    @property
    def missing(self) -> bool:
        """True when the executable itself was not found."""
        return self.error == "not-found"


def which(name: str) -> str | None:
    """Absolute path to an executable, or None."""
    return shutil.which(name)


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    env: dict[str, str] | None = None,
) -> Result:
    """Run a command and capture its output. Never raises."""
    if not args:
        return Result(ok=False, error="empty-command")
    if which(args[0]) is None:
        return Result(ok=False, error="not-found")

    merged_env = {**os.environ, **env} if env else None
    try:
        completed = subprocess.run(  # noqa: S603 - args are constructed, never shell
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=merged_env,
        )
    except subprocess.TimeoutExpired:
        return Result(ok=False, error="timeout")
    except OSError as exc:  # pragma: no cover - defensive
        return Result(ok=False, error=f"os-error: {exc}")

    return Result(
        ok=completed.returncode == 0,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def tool_version(name: str, *args: str) -> str | None:
    """Best-effort version string for a CLI tool, or None if unavailable."""
    result = run([name, *(args or ("--version",))])
    if not result.ok:
        return None
    # Tools disagree about which stream a version goes to.
    text = result.stdout or result.stderr
    return text.splitlines()[0].strip() if text else None


def git_toplevel(start: Path) -> Path | None:
    """The git working-tree root containing ``start``, or None."""
    result = run(["git", "-C", str(start), "rev-parse", "--show-toplevel"])
    return Path(result.stdout) if result.ok and result.stdout else None
