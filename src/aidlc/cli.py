"""The ``aidlc`` console script.

This module is intentionally thin. It maps command-line verbs onto functions in
``aidlc.commands`` and does nothing else, so that the behaviour of every command
is testable without parsing arguments. Command modules are imported lazily so
that `--help` and `--version` stay fast.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from aidlc import __version__

app = App(
    name="aidlc",
    version=__version__,
    help="A versioned, tool-agnostic AI development lifecycle.",
)

PathArg = Annotated[
    Path | None,
    Parameter(help="Repository to operate on. Defaults to the current directory."),
]


@app.command(name="doctor")
def doctor_command() -> int:
    """Report what this machine can do. Read-only; writes nothing."""
    from aidlc.commands.doctor import doctor

    return doctor()


@app.command(name="init")
def init_command(
    path: PathArg = None,
    *,
    force: Annotated[
        bool, Parameter(help="Overwrite managed blocks that were edited by hand.")
    ] = False,
) -> int:
    """Detect this project and generate its agent and CI configuration."""
    from aidlc.commands.sync import init

    return init(path, force=force)


@app.command(name="sync")
def sync_command(
    path: PathArg = None,
    *,
    force: Annotated[
        bool, Parameter(help="Overwrite managed blocks that were edited by hand.")
    ] = False,
    dry_run: Annotated[bool, Parameter(help="Show what would change, write nothing.")] = False,
) -> int:
    """Regenerate after a pack, config or project change."""
    from aidlc.commands.sync import sync

    return sync(path, force=force, dry_run=dry_run)


@app.command(name="check")
def check_command(path: PathArg = None) -> int:
    """Exit non-zero if anything has drifted. Writes nothing."""
    from aidlc.commands.sync import check

    return check(path)


def main() -> int:
    """Console-script entry point.

    Cyclopts returns whatever the command returned; ``None`` is normalised to a
    success code so a command can simply fall off the end.
    """
    result = app()
    return 0 if result is None else int(result)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
