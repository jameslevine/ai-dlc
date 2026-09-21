"""`.aidlc/aidlc.lock` — what was generated, from what, at which version.

The lockfile plays the same role `uv.lock` does. It records two things that
together make drift detectable without re-deriving anything:

* **Source identity** — each pack's name, version, digest and origin. This is
  what `aidlc check` compares against to answer "is this repo running the packs
  it thinks it is?".
* **Materialized identity** — a hash per generated output. This answers the
  different question "has anything been edited since it was generated?".

Both are needed. A pack can change without the output changing, and an output
can change without the pack changing; conflating them would hide one case or
the other.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

LOCK_SCHEMA_VERSION = 1


class PackSource(StrEnum):
    BUILTIN = "builtin"
    """Bundled inside the installed wheel."""

    PATH = "path"
    """A local checkout. How a candidate pack version is evaluated."""


class LockedPack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    version: str
    digest: str
    source: PackSource = PackSource.BUILTIN
    path: str | None = None
    """Set only for path sources."""


class LockedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    kind: str
    sha256: str
    identifier: str | None = None
    """Block id, for outputs that are a region inside a larger file."""


class Lockfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_version: int = Field(default=LOCK_SCHEMA_VERSION, alias="schema")
    aidlc: str
    profile_digest: str
    packs: list[LockedPack] = Field(default_factory=list)
    outputs: list[LockedOutput] = Field(default_factory=list)

    def output_for(self, path: str) -> LockedOutput | None:
        return next((o for o in self.outputs if o.path == path), None)

    def pack_for(self, name: str) -> LockedPack | None:
        return next((p for p in self.packs if p.name == name), None)
