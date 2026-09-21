"""The adapter registry.

Order matters only for presentation; adapters do not compete for targets,
because each claims directories by its own marker files. A directory holding
both `pyproject.toml` and `package.json` legitimately produces two targets, and
generating CI for both is the correct answer.
"""

from __future__ import annotations

from aidlc.detect.adapters.base import EcosystemAdapter, TargetFacts
from aidlc.detect.adapters.jvm import JvmAdapter
from aidlc.detect.adapters.node import NodeAdapter
from aidlc.detect.adapters.python import PythonAdapter
from aidlc.detect.adapters.simple import DotnetAdapter, GoAdapter, RustAdapter

#: Every tier-1 ecosystem. Adding one is this line plus an adapter module.
ADAPTERS: tuple[EcosystemAdapter, ...] = (
    PythonAdapter(),
    NodeAdapter(),
    JvmAdapter(),
    GoAdapter(),
    RustAdapter(),
    DotnetAdapter(),
)


def by_id(ecosystem: str) -> EcosystemAdapter | None:
    return next((a for a in ADAPTERS if a.id == ecosystem), None)


__all__ = ["ADAPTERS", "EcosystemAdapter", "TargetFacts", "by_id"]
