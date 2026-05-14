"""Helpers for bundling Skill files before sandbox upload."""

from __future__ import annotations

import io
import posixpath
import tarfile
from typing import Any


def skill_archive_name(skill: Any) -> str:
    raw_name = str(getattr(skill, "name", "skill"))
    safe_name = "".join(
        char if char.isalnum() or char in "._-" else "_"
        for char in raw_name
    ).strip("._-")
    safe_name = safe_name or "skill"
    skill_id = getattr(skill, "skill_id", None)
    if skill_id is not None:
        return f"{skill_id}_{safe_name}.tar.gz"
    return f"{safe_name}.tar.gz"


def build_skill_archive(skill: Any) -> tuple[bytes, int]:
    buffer = io.BytesIO()
    file_count = 0
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for skill_file in skill.files:
            if str(skill_file.path).endswith("/"):
                continue
            content = _skill_file_content(skill_file)
            info = tarfile.TarInfo(_archive_member_path(skill_file.path))
            info.size = len(content)
            info.mode = 0o644
            info.mtime = 0
            archive.addfile(info, io.BytesIO(content))
            file_count += 1
    return buffer.getvalue(), file_count


def _skill_file_content(skill_file: Any) -> bytes:
    if skill_file.content_bytes is not None:
        return bytes(skill_file.content_bytes)
    if skill_file.content_text is not None:
        return skill_file.content_text.encode("utf-8")
    return b""


def _archive_member_path(path: str) -> str:
    raw_path = str(path)
    if "\x00" in raw_path:
        raise ValueError(f"Skill file path contains NUL byte: {raw_path!r}")
    normalized = posixpath.normpath(raw_path)
    if (
        not normalized
        or normalized == "."
        or normalized == ".."
        or normalized.startswith("../")
        or normalized.startswith("/")
    ):
        raise ValueError(f"Skill file path must be package-relative: {raw_path!r}")
    return normalized
