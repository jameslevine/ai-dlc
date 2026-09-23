"""Conventions for the documentation and the packs that ship from here.

These are checked rather than reviewed for because a reviewer keeps missing
them: a path that is correct on the author's machine looks correct to the
author.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: A path that starts at someone's home directory, on any of the three
#: platforms. `<path-to-this-repo>` is the accepted placeholder.
MACHINE_SPECIFIC_PATH = re.compile(r"/Users/|/home/[A-Za-z0-9_.-]+/|C:\\Users\\")


def tracked_files() -> list[Path]:
    """What `git ls-files` reports; an untracked scratch file ships nowhere."""
    listing = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True, text=True
    )
    return [ROOT / name for name in listing.stdout.split("\0") if name]


def documentation_files() -> list[Path]:
    """Every tracked Markdown file, and everything under `packs/`."""
    return [
        path
        for path in tracked_files()
        if path.suffix == ".md" or path.relative_to(ROOT).parts[0] == "packs"
    ]


def test_documentation_files_include_the_authoring_guide() -> None:
    """Guards the enumeration: an empty list would pass the check below."""
    assert ROOT / "docs" / "PACK-AUTHORING.md" in documentation_files()


def test_documentation_contains_no_machine_specific_absolute_path() -> None:
    """A path that begins at a home directory is correct on the author's
    machine and nowhere else. It survived two review passes in
    docs/QUICKSTART.md, which is why this is a test and not a checklist."""
    offenders = [
        f"{path.relative_to(ROOT)}:{number}: {line.strip()}"
        for path in documentation_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if MACHINE_SPECIFIC_PATH.search(line)
    ]
    assert not offenders, "machine-specific absolute paths:\n" + "\n".join(offenders)
