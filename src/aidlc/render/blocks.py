"""Managed blocks: generated content inside a hand-written file.

This is the mechanism behind the promise that aidlc never clobbers your work.
A generated region is delimited by markers that carry the digest of the content
between them:

```
<!-- aidlc:begin id=core version=0.1.0 digest=sha256:ab12ef -->
...generated...
<!-- aidlc:end -->
```

Only the region between the markers is ever rewritten. If the live content
hashes differently from the digest recorded in the marker, somebody edited it
by hand, and `sync` refuses rather than silently discarding their work.

`init` may add a block to a file that has none. `sync` deliberately will not:
appending to a file aidlc did not mark would mean a stray `sync` in the wrong
directory quietly modifies unrelated documents.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum

_BEGIN = re.compile(
    r"^<!--\s*aidlc:begin\s+(?P<attrs>[^>]*?)\s*-->\s*$",
    re.MULTILINE,
)
_END = re.compile(r"^<!--\s*aidlc:end\s*-->\s*$", re.MULTILINE)
_ATTR = re.compile(r"(\w+)=([^\s]+)")


class Outcome(StrEnum):
    """What happened, or would happen, to a managed block."""

    CREATED = "created"
    """The file had no block and one was added."""

    UPDATED = "updated"
    """An existing block's content changed."""

    UNCHANGED = "unchanged"
    """The rendered content matched what was already there."""

    CONFLICT = "conflict"
    """The block was edited by hand. Refuse and report."""

    ABSENT = "absent"
    """No block, and creating one is not permitted in this mode."""


@dataclass(frozen=True, slots=True)
class Block:
    """A managed region located inside a file."""

    identifier: str
    version: str
    digest: str
    content: str
    start: int
    """Character offset of the opening marker."""
    end: int
    """Character offset just past the closing marker."""


@dataclass(frozen=True, slots=True)
class Result:
    text: str
    outcome: Outcome
    detail: str = ""


def content_digest(content: str) -> str:
    """Digest of block content, computed on normalised text.

    Normalising line endings and trailing whitespace means a checkout with
    different git autocrlf settings does not read as a hand edit.
    """
    normalised = "\n".join(line.rstrip() for line in content.replace("\r\n", "\n").split("\n"))
    return "sha256:" + hashlib.sha256(normalised.strip().encode("utf-8")).hexdigest()[:16]


def find(text: str, identifier: str) -> Block | None:
    """Locate a managed block by identifier, or None."""
    for match in _BEGIN.finditer(text):
        attrs = dict(_ATTR.findall(match.group("attrs")))
        if attrs.get("id") != identifier:
            continue
        end_match = _END.search(text, match.end())
        if end_match is None:
            # An unterminated block is corruption, not a block. Treating it as
            # absent would append a second one and make the file worse.
            return None
        return Block(
            identifier=identifier,
            version=attrs.get("version", ""),
            digest=attrs.get("digest", ""),
            content=text[match.end() : end_match.start()].strip("\n"),
            start=match.start(),
            end=end_match.end(),
        )
    return None


def render(identifier: str, version: str, content: str) -> str:
    """Wrap content in markers, with its digest recorded in the opening one."""
    digest = content_digest(content)
    return (
        f"<!-- aidlc:begin id={identifier} version={version} digest={digest} -->\n"
        f"{content.strip()}\n"
        f"<!-- aidlc:end -->"
    )


def upsert(
    text: str,
    identifier: str,
    version: str,
    content: str,
    *,
    allow_create: bool = False,
    force: bool = False,
) -> Result:
    """Insert or replace a managed block.

    ``allow_create`` is the difference between `init` and `sync`. ``force``
    overrides hand-edit protection, and exists so that the refusal is
    recoverable without editing markers by hand.
    """
    block = find(text, identifier)
    new_block = render(identifier, version, content)

    if block is None:
        if not allow_create:
            return Result(text=text, outcome=Outcome.ABSENT)
        separator = (
            "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        )
        return Result(text=f"{text}{separator}{new_block}\n", outcome=Outcome.CREATED)

    # A block whose content no longer matches its recorded digest was edited
    # in place. Overwriting it would destroy work that someone chose to do.
    live = content_digest(block.content)
    if block.digest and live != block.digest and not force:
        return Result(
            text=text,
            outcome=Outcome.CONFLICT,
            detail=(
                f"the aidlc block '{identifier}' has been edited by hand. "
                "Move your changes into a pack, or re-run with --force to discard them."
            ),
        )

    if block.content.strip() == content.strip() and block.version == version:
        return Result(text=text, outcome=Outcome.UNCHANGED)

    return Result(
        text=text[: block.start] + new_block + text[block.end :],
        outcome=Outcome.UPDATED,
    )


#: Header placed at the top of files aidlc owns outright, as opposed to a block
#: inside a file someone else owns.
GENERATED_HEADER = "# Generated by aidlc. Do not edit; run `aidlc sync` instead."


def generated_file(content: str, *, comment: str = "#") -> str:
    """Prefix whole-file output with a do-not-edit header."""
    marker = GENERATED_HEADER if comment == "#" else f"<!-- {GENERATED_HEADER.lstrip('# ')} -->"
    return f"{marker}\n{content}"
