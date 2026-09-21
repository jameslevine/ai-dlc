"""Pydantic models for every file aidlc reads or writes.

Each generated artifact carries a schema version. aidlc refuses to read a
version from the future rather than guessing at its meaning, because a
half-understood profile produces confidently wrong CI.
"""

from __future__ import annotations

from aidlc.schemas.config import Config, ConfigError, Strictness
from aidlc.schemas.profile import (
    Conflict,
    JobSpec,
    Profile,
    SetupKind,
    Step,
    StepName,
    StepSource,
    Target,
)

__all__ = [
    "Config",
    "ConfigError",
    "Conflict",
    "JobSpec",
    "Profile",
    "SetupKind",
    "Step",
    "StepName",
    "StepSource",
    "Strictness",
    "Target",
]
