"""Exceptions that map to exit code 3 (tool or usage error)."""

from __future__ import annotations


class PreflightError(Exception):
    """A problem with how the tool was used or with an input it cannot read at all."""
