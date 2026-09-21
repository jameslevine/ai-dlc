"""The consumer repository aidlc is operating on.

One place that knows where aidlc's files live, how to read them and how to
write them back. Commands share it so that `init`, `sync` and `check` cannot
drift apart in their idea of what a workspace is — which matters, because
`check` exists precisely to detect disagreement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from aidlc import __version__
from aidlc.packs.digest import digest_text
from aidlc.packs.loader import Pack, PackError, load_many
from aidlc.schemas.config import Config, ConfigError
from aidlc.schemas.config import load as load_config
from aidlc.schemas.lock import LockedPack, Lockfile, PackSource
from aidlc.schemas.profile import PROFILE_SCHEMA_VERSION, Profile

#: Everything aidlc owns in a consumer repo lives under this directory, except
#: the emitted files that tools require at fixed locations.
AIDLC_DIR = ".aidlc"
CONFIG_NAME = "config.yml"
PROFILE_NAME = "profile.json"
LOCK_NAME = "aidlc.lock"


class WorkspaceError(Exception):
    """A workspace could not be read. Message is written for a human."""


@dataclass(slots=True)
class Workspace:
    root: Path

    @property
    def aidlc_dir(self) -> Path:
        return self.root / AIDLC_DIR

    @property
    def config_path(self) -> Path:
        return self.aidlc_dir / CONFIG_NAME

    @property
    def profile_path(self) -> Path:
        return self.aidlc_dir / PROFILE_NAME

    @property
    def lock_path(self) -> Path:
        return self.aidlc_dir / LOCK_NAME

    @property
    def initialised(self) -> bool:
        return self.profile_path.exists()

    # -- reading -----------------------------------------------------------

    def config(self) -> Config:
        try:
            return load_config(self.config_path)
        except ConfigError as exc:
            raise WorkspaceError(str(exc)) from exc

    def stored_profile(self) -> Profile | None:
        if not self.profile_path.exists():
            return None
        try:
            raw = json.loads(self.profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceError(f"{self.profile_path} is not readable JSON: {exc}") from exc

        version = raw.get("schema")
        if isinstance(version, int) and version > PROFILE_SCHEMA_VERSION:
            # Guessing at a future schema produces confidently wrong CI, which
            # is worse than refusing and asking for an upgrade.
            raise WorkspaceError(
                f"{self.profile_path} uses schema {version}, but this aidlc "
                f"understands up to {PROFILE_SCHEMA_VERSION}. Upgrade aidlc."
            )
        try:
            return Profile.model_validate(raw)
        except ValidationError as exc:
            raise WorkspaceError(f"{self.profile_path} is not a valid profile:\n{exc}") from exc

    def stored_lock(self) -> Lockfile | None:
        if not self.lock_path.exists():
            return None
        try:
            raw = json.loads(self.lock_path.read_text(encoding="utf-8"))
            return Lockfile.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise WorkspaceError(f"{self.lock_path} is not a valid lockfile: {exc}") from exc

    def packs(self, names: list[str]) -> list[Pack]:
        try:
            return load_many(names)
        except PackError as exc:
            raise WorkspaceError(str(exc)) from exc

    # -- writing -----------------------------------------------------------

    def write_profile(self, profile: Profile) -> None:
        self.aidlc_dir.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(serialise_profile(profile), encoding="utf-8")

    def write_lock(self, lock: Lockfile) -> None:
        self.aidlc_dir.mkdir(parents=True, exist_ok=True)
        payload = lock.model_dump(by_alias=True, mode="json", exclude_none=True)
        self.lock_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def serialise_profile(profile: Profile) -> str:
    """Stable JSON for the profile.

    Sorted keys and a fixed indent mean an unchanged repository re-serialises
    byte-for-byte identically, which is what lets `check` treat any difference
    as real drift rather than formatting noise.
    """
    payload = profile.model_dump(by_alias=True, mode="json", exclude_none=True)
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def profile_digest(profile: Profile) -> str:
    """Hash of a profile, ignoring the fields that change on every run.

    `generated_by` carries the aidlc version, so including it would make every
    upgrade look like a change to the project itself.
    """
    payload = profile.model_dump(by_alias=True, mode="json", exclude_none=True)
    payload.pop("generated_by", None)
    return "sha256:" + digest_text([json.dumps(payload, sort_keys=True)])[:16]


def build_lock(profile: Profile, packs: list[Pack], outputs: list) -> Lockfile:
    """Assemble a lockfile from the pieces a run produced."""
    return Lockfile(
        aidlc=__version__,
        profile_digest=profile_digest(profile),
        packs=[
            LockedPack(
                name=pack.name,
                version=pack.version,
                digest="sha256:" + pack.digest[:32],
                source=PackSource.PATH if pack.source.startswith("path:") else PackSource.BUILTIN,
                path=pack.source.removeprefix("path:") if pack.source.startswith("path:") else None,
            )
            for pack in sorted(packs, key=lambda p: p.name)
        ],
        outputs=outputs,
    )


def find_root(start: Path) -> Path:
    """The repository root containing ``start``.

    Prefers the git toplevel, because that is what a person means by "this
    project". Falls back to the directory itself so that aidlc works on a
    directory that is not a git repository yet.
    """
    from aidlc import probe

    toplevel = probe.git_toplevel(start)
    return toplevel if toplevel is not None else start.resolve()
