"""Content digests: the second identity a pack carries.

A pack has two identities because they answer different questions.

**Version** (``rules-python@1.3.0``) is *intent*. It is what a consumer pins,
what a promotion moves, and what a rollback reverts to. It is chosen by a human
and it lies whenever someone edits a pack without bumping it.

**Digest** (``sha256:a7f3c9e1…``) is *identity*. It is computed from the bytes
and cannot lie. It catches the edit-without-bump case, and — the reason it
exists — it stops two eval runs labelled `1.3.0` with different content from
being silently averaged into one meaningless number.

Every eval record carries both, as ``rules-python@1.3.0+a7f3c9e12b04``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping

#: How much of the hex digest to show. Twelve characters is ~48 bits, which is
#: far beyond collision risk for the number of pack versions one person will
#: ever produce, and short enough to read in a table.
SHORT_LENGTH = 12


def digest_files(files: Mapping[str, bytes]) -> str:
    """Hash a mapping of relative path to file content.

    Canonicalisation matters more than the hash function here. Paths are sorted
    so that filesystem iteration order cannot change the result, and each entry
    is length-prefixed so that a file named ``ab/c`` cannot hash the same as one
    named ``a/bc`` with shifted content.
    """
    hasher = hashlib.sha256()
    for path in sorted(files):
        content = files[path]
        encoded = path.encode("utf-8")
        hasher.update(len(encoded).to_bytes(4, "big"))
        hasher.update(encoded)
        hasher.update(len(content).to_bytes(8, "big"))
        hasher.update(content)
    return hasher.hexdigest()


def short(full_digest: str) -> str:
    """Truncate a digest for display, tolerating an ``sha256:`` prefix."""
    return full_digest.removeprefix("sha256:")[:SHORT_LENGTH]


def qualified(name: str, version: str, full_digest: str) -> str:
    """The canonical way a pack is named in a record: ``name@version+digest``."""
    return f"{name}@{version}+{short(full_digest)}"


def digest_text(chunks: Iterable[str]) -> str:
    """Hash rendered output, for drift detection on generated files."""
    hasher = hashlib.sha256()
    for chunk in chunks:
        encoded = chunk.encode("utf-8")
        hasher.update(len(encoded).to_bytes(8, "big"))
        hasher.update(encoded)
    return hasher.hexdigest()
