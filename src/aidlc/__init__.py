"""aidlc — a versioned, tool-agnostic AI development lifecycle.

The public surface of this package is the ``aidlc`` console script. Everything
else is internal and may change between minor versions.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("aidlc")
except PackageNotFoundError:  # pragma: no cover - only when running from source
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
