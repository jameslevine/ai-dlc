"""Go, Rust and .NET adapters.

These three share a shape: a single canonical manifest, one blessed toolchain,
and a build tool that already does lint, test and build as subcommands. They
need no per-project negotiation, so they are short and live together rather
than in three near-identical files.
"""

from __future__ import annotations

import re

from aidlc.detect.adapters.base import TargetFacts, make_job
from aidlc.detect.scanner import RepoIndex
from aidlc.schemas.profile import JobSpec, SetupKind, StepName

_GO_DIRECTIVE = re.compile(r"^go\s+(\d+\.\d+)", re.MULTILINE)
_RUST_CHANNEL = re.compile(r'channel\s*=\s*"([^"]+)"')


class GoAdapter:
    id = "go"
    MARKERS = ("go.mod",)

    def detect(self, index: RepoIndex) -> list[TargetFacts]:
        results: list[TargetFacts] = []
        for directory in index.dirs_containing(*self.MARKERS):
            prefix = "" if directory == "." else directory + "/"
            text = index.read_text(prefix + "go.mod") or ""
            match = _GO_DIRECTIVE.search(text)
            facts = TargetFacts(
                path=directory,
                ecosystem=self.id,
                languages=["Go"],
                manager="go",
                versions=[match.group(1)] if match else [],
                cache_dependency_glob=prefix + "go.sum",
            )
            facts.facts = {
                # golangci-lint is only run when the repo configures it.
                # Imposing a linter no one configured produces a wall of
                # findings on the first run and gets the job disabled.
                "golangci": index.has_any(prefix + ".golangci.yml", prefix + ".golangci.yaml"),
            }
            results.append(facts)
        return results

    def job_spec(self, facts: TargetFacts) -> JobSpec:
        defaults = {
            StepName.INSTALL: "go mod download",
            StepName.LINT: "go vet ./...",
            StepName.FORMAT: 'test -z "$(gofmt -l .)"',
            StepName.TEST: "go test ./...",
        }
        if facts.facts.get("golangci"):
            defaults[StepName.LINT] = "golangci-lint run"
        return make_job(facts, SetupKind.GO, defaults)


class RustAdapter:
    id = "rust"
    MARKERS = ("Cargo.toml",)

    def detect(self, index: RepoIndex) -> list[TargetFacts]:
        results: list[TargetFacts] = []
        claimed: set[str] = set()
        for directory in index.dirs_containing(*self.MARKERS):
            # Cargo workspace members are built by the workspace root.
            if any(directory.startswith(parent + "/") for parent in claimed):
                continue
            prefix = "" if directory == "." else directory + "/"
            channel = None
            for filename in ("rust-toolchain.toml", "rust-toolchain"):
                text = index.read_text(prefix + filename)
                if text:
                    match = _RUST_CHANNEL.search(text)
                    channel = match.group(1) if match else text.strip().splitlines()[0]
                    break
            claimed.add(directory)
            facts = TargetFacts(
                path=directory,
                ecosystem=self.id,
                languages=["Rust"],
                manager="cargo",
                versions=[channel] if channel else [],
                cache_dependency_glob=prefix + "Cargo.lock",
            )
            results.append(facts)
        return results

    def job_spec(self, facts: TargetFacts) -> JobSpec:
        defaults = {
            StepName.FORMAT: "cargo fmt --check",
            StepName.LINT: "cargo clippy -- -D warnings",
            StepName.TEST: "cargo test",
        }
        return make_job(facts, SetupKind.RUST, defaults)


class DotnetAdapter:
    id = "dotnet"

    def detect(self, index: RepoIndex) -> list[TargetFacts]:
        # A solution file is the better target when present: it knows about
        # every project, so building it once beats building each .csproj.
        directories: list[str] = []
        for path in sorted(index.files):
            if path.endswith(".sln"):
                directories.append(self._dirname(path))
        if not directories:
            directories = sorted(
                {
                    self._dirname(path)
                    for path in index.files
                    if path.endswith((".csproj", ".fsproj"))
                }
            )

        results: list[TargetFacts] = []
        for directory in dict.fromkeys(directories):
            prefix = "" if directory == "." else directory + "/"
            global_json = index.read_json(prefix + "global.json") or index.read_json("global.json")
            version = (global_json.get("sdk") or {}).get("version")
            fsharp = any(p.endswith(".fsproj") for p in index.files)
            facts = TargetFacts(
                path=directory,
                ecosystem=self.id,
                languages=["F#"] if fsharp else ["C#"],
                manager="dotnet",
                versions=[str(version)] if version else [],
            )
            results.append(facts)
        return results

    @staticmethod
    def _dirname(path: str) -> str:
        return path.rsplit("/", 1)[0] if "/" in path else "."

    def job_spec(self, facts: TargetFacts) -> JobSpec:
        defaults = {
            StepName.INSTALL: "dotnet restore",
            StepName.FORMAT: "dotnet format --verify-no-changes",
            StepName.BUILD: "dotnet build --no-restore --configuration Release",
            StepName.TEST: "dotnet test --no-build --configuration Release",
        }
        return make_job(facts, SetupKind.DOTNET, defaults)
