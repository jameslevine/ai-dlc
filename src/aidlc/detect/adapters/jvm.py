"""JVM adapter: Maven and Gradle, Java and Kotlin.

The awkwardness here is that the two build tools disagree about almost
everything, including where the toolchain version is declared. Both paths are
handled, and when neither declares one we say nothing rather than guessing a
Java version, because picking the wrong one fails the build outright.
"""

from __future__ import annotations

import re

from aidlc.detect.adapters.base import TargetFacts, make_job
from aidlc.detect.scanner import RepoIndex
from aidlc.schemas.profile import JobSpec, SetupKind, StepName

MARKERS = ("pom.xml", "build.gradle", "build.gradle.kts")

#: `<maven.compiler.release>21</maven.compiler.release>` and the older
#: `<java.version>` property, which many Spring Boot parents still use.
_MAVEN_RELEASE = re.compile(
    r"<(?:maven\.compiler\.release|maven\.compiler\.target|java\.version)>\s*(\d+)\s*<",
)
#: Gradle's toolchain block: `languageVersion = JavaLanguageVersion.of(21)`.
_GRADLE_TOOLCHAIN = re.compile(r"JavaLanguageVersion\.of\(\s*(\d+)\s*\)")
_VERSION_FILE = re.compile(r"(\d+)")


class JvmAdapter:
    id = "jvm"

    def detect(self, index: RepoIndex) -> list[TargetFacts]:
        results: list[TargetFacts] = []
        claimed: set[str] = set()

        for directory in index.dirs_containing(*MARKERS):
            # A Gradle multi-project build has build files in every module but
            # only one wrapper, at the root. Building each module separately
            # would run the same work repeatedly, so only the wrapper root is
            # a target.
            if any(directory.startswith(parent + "/") for parent in claimed):
                continue
            facts = self._inspect(index, directory)
            if facts is not None:
                claimed.add(directory)
                results.append(facts)
        return results

    def _inspect(self, index: RepoIndex, directory: str) -> TargetFacts | None:
        prefix = "" if directory == "." else directory + "/"
        is_maven = index.has(prefix + "pom.xml")
        gradle_file = next(
            (name for name in ("build.gradle.kts", "build.gradle") if index.has(prefix + name)),
            None,
        )

        if is_maven:
            tool, wrapper = "maven", index.has(prefix + "mvnw")
        elif gradle_file:
            tool, wrapper = "gradle", index.has(prefix + "gradlew")
            # Gradle without a wrapper in a submodule means the real root is
            # elsewhere; skip it rather than invent a build command.
            if not wrapper and directory != ".":
                return None
        else:
            return None

        kotlin = bool(gradle_file and gradle_file.endswith(".kts")) or self._has_kotlin(
            index, directory
        )

        facts = TargetFacts(
            path=directory,
            ecosystem=self.id,
            languages=["Kotlin"] if kotlin else ["Java"],
            manager=tool,
            frameworks=self._frameworks(index, prefix, is_maven, gradle_file),
            versions=self._versions(index, prefix, is_maven, gradle_file),
            cache_dependency_glob=(prefix + ("pom.xml" if is_maven else "**/*.gradle*")),
        )
        facts.facts = {"build_tool": tool, "wrapper": wrapper, "kotlin": kotlin}
        return facts

    @staticmethod
    def _has_kotlin(index: RepoIndex, directory: str) -> bool:
        prefix = "" if directory == "." else directory + "/"
        return any(path.startswith(prefix) and path.endswith(".kt") for path in index.files)

    @staticmethod
    def _frameworks(
        index: RepoIndex, prefix: str, is_maven: bool, gradle_file: str | None
    ) -> list[str]:
        source = prefix + ("pom.xml" if is_maven else (gradle_file or "build.gradle"))
        text = (index.read_text(source) or "").lower()
        hints = {
            "spring-boot": "spring-boot",
            "quarkus": "quarkus",
            "micronaut": "micronaut",
            "software.amazon.awscdk": "aws-cdk",
        }
        return sorted({label for needle, label in hints.items() if needle in text})

    @staticmethod
    def _versions(
        index: RepoIndex, prefix: str, is_maven: bool, gradle_file: str | None
    ) -> list[str]:
        for filename in (".java-version", ".sdkmanrc"):
            text = index.read_text(prefix + filename)
            if text and (match := _VERSION_FILE.search(text)):
                return [match.group(1)]

        if is_maven:
            text = index.read_text(prefix + "pom.xml") or ""
            if match := _MAVEN_RELEASE.search(text):
                return [match.group(1)]
        elif gradle_file:
            text = index.read_text(prefix + gradle_file) or ""
            if match := _GRADLE_TOOLCHAIN.search(text):
                return [match.group(1)]
        return []

    def job_spec(self, facts: TargetFacts) -> JobSpec:
        if facts.manager == "maven":
            runner = "./mvnw" if facts.facts.get("wrapper") else "mvn"
            # `-B` for non-interactive, `-ntp` to silence transfer noise that
            # otherwise dominates a CI log.
            defaults = {
                StepName.TEST: f"{runner} -B -ntp verify",
            }
        else:
            runner = "./gradlew" if facts.facts.get("wrapper") else "gradle"
            defaults = {
                StepName.TEST: f"{runner} --no-daemon build",
            }
        return make_job(facts, SetupKind.JAVA, defaults)
