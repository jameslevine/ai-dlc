"""Command implementations, one module per CLI verb.

Each module exposes a plain function that returns an exit code and does its own
I/O. Keeping them free of Cyclopts decorators means they can be called directly
from tests without going through argument parsing.
"""
