"""Pure path rules for skill package files (no database or ORM imports).

Shared by ``SkillPackageRepository`` and ``utils.safe_zip`` so both apply exactly the same rules.
"""
import re
import unicodedata
from typing import List, Tuple

MAX_PATH_LENGTH = 500
MAX_SEGMENT_BYTES = 255
SKILL_MD = 'SKILL.md'
_WINDOWS_DRIVE_RE = re.compile(r'^[A-Za-z]:')
_PERCENT_ENCODED_RE = re.compile(r'%[0-9A-Fa-f]{2}')


def canonical_path(path: str) -> str:
    """NFKC-normalise ``path`` and convert backslashes to ``/`` (no other validation)."""
    return unicodedata.normalize('NFKC', path).replace('\\', '/')


def is_absolute_or_drive(canonical: str) -> bool:
    """Return True if a canonical path starts with ``/`` or a Windows drive letter."""
    return canonical.startswith('/') or bool(_WINDOWS_DRIVE_RE.match(canonical))


def canonical_segments(path: str) -> Tuple[bool, List[str]]:
    """Return ``(is_absolute_or_drive, non-empty non-'.' segments)`` of the canonical form of ``path``."""
    canon = canonical_path(path)
    return is_absolute_or_drive(canon), [s for s in canon.split('/') if s not in ('', '.')]


def normalize_path(path: str, *, allow_root_skill_md: bool = False) -> str:
    """Normalise a package-root-relative path to POSIX form.

    The path is NFKC-normalised first so that compatibility characters (fullwidth dots and slashes,
    one-dot leaders, ...) cannot smuggle traversal sequences past validation.

    Args:
        path: Raw path.
        allow_root_skill_md: When True a root-level ``SKILL.md`` (any case) is accepted and returned as
            ``'SKILL.md'``; otherwise it is rejected because SKILL.md is stored in ``Skill.content``.

    Raises:
        ValueError: If the path is empty, absolute, has a Windows drive, contains a ``..`` segment,
            starts with ``~``, contains control/format characters or a percent-encoded octet,
            has a segment that is blank, ends with ``.``/space or exceeds 255 UTF-8 bytes,
            is longer than 500 characters, or is the reserved root-level ``SKILL.md``.
    """
    if not path or not path.strip():
        raise ValueError("Skill file path must not be empty.")
    normalized = canonical_path(path)
    for ch in normalized:
        if ord(ch) < 0x20 or ord(ch) == 0x7F or unicodedata.category(ch) == 'Cf':
            raise ValueError("Skill file path must not contain control characters.")
    if _PERCENT_ENCODED_RE.search(normalized):
        raise ValueError("Skill file path must not contain percent-encoded characters.")
    if is_absolute_or_drive(normalized):
        raise ValueError("Skill file path must be relative.")
    if normalized.startswith('~'):
        raise ValueError("Skill file path must not start with '~'.")

    segments: List[str] = []
    for raw in normalized.split('/'):
        if raw in ('', '.'):
            continue
        if not raw.strip():
            raise ValueError("Skill file path must not contain blank segments.")
        if raw != raw.strip():
            raise ValueError("Skill file path segments must not have leading or trailing whitespace.")
        seg = raw
        if seg == '..':
            raise ValueError("Skill file path must not contain '..' segments.")
        if seg.endswith('.') or seg.endswith(' '):
            raise ValueError("Skill file path segments must not end with '.' or a space.")
        if len(seg.encode('utf-8')) > MAX_SEGMENT_BYTES:
            raise ValueError(f"Skill file path segments must not exceed {MAX_SEGMENT_BYTES} bytes.")
        segments.append(seg)
    if not segments:
        raise ValueError("Skill file path must not be empty.")

    result = '/'.join(segments)
    if len(result) > MAX_PATH_LENGTH:
        raise ValueError(f"Skill file path exceeds {MAX_PATH_LENGTH} characters.")
    if len(segments) == 1 and result.lower() == 'skill.md':
        if allow_root_skill_md:
            return SKILL_MD
        raise ValueError("SKILL.md is reserved: it is stored in Skill.content, not as a package file.")
    return result
