"""Helpers to build filesystem paths from untrusted input without escaping a base directory."""

import os


class UnsafePathError(ValueError):
    """Raised when a path resolves outside the directory it must stay in."""


def resolve_within(base_dir: str, *parts: str) -> str:
    """Join ``parts`` onto ``base_dir`` and return the resolved absolute path.

    Symlinks and ``..`` segments are resolved before the check, and an absolute
    part replaces everything before it (``os.path.join`` semantics), so the
    result is validated as a whole. Raises ``UnsafePathError`` if the result is
    not ``base_dir`` itself or a path inside it.
    """
    base = os.path.realpath(base_dir)
    candidate = os.path.realpath(os.path.join(base, *parts))
    if os.path.commonpath([base, candidate]) != base:
        raise UnsafePathError(f"Path escapes its base directory: {candidate}")
    return candidate
