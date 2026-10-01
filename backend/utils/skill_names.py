"""Canonical skill-name folding, shared by the repository layer (DB-side name
collision checks) and the tools layer (runtime skill resolution) so both agree
on what counts as "the same name".

Kept in ``utils`` rather than ``repositories`` to avoid ``tools`` depending on
the repository layer.
"""
import re


def fold_name(name: str) -> str:
    """Python-side name folding matching ``repositories.skill_repository._fold_col``:
    strip, whitespace runs -> '-', lowercase."""
    return re.sub(r'\s+', '-', (name or '').strip()).lower()
