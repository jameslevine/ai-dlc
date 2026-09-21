"""The ``aidlc`` console script.

This module is intentionally thin. It maps command-line verbs onto functions in
``aidlc.commands`` and does nothing else, so that the behaviour of every command
is testable without parsing arguments.
"""

from __future__ import annotations

import sys

from cyclopts import App

from aidlc import __version__

app = App(
    name="aidlc",
    version=__version__,
    help="A versioned, tool-agnostic AI development lifecycle.",
)


@app.command(name="doctor")
def doctor_command() -> int:
    """Report what this machine can do. Read-only; writes nothing."""
    from aidlc.commands.doctor import doctor

    return doctor()


def main() -> int:
    """Console-script entry point.

    Cyclopts returns whatever the command returned; we normalise ``None`` to a
    success exit code so commands can simply fall off the end.
    """
    result = app()
    code = 0 if result is None else int(result)
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
