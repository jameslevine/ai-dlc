"""Project detection: read a repository and decide what it is."""

from __future__ import annotations

from aidlc.detect.profile import detect
from aidlc.detect.scanner import RepoIndex, scan

__all__ = ["RepoIndex", "detect", "scan"]
