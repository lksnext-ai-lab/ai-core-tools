"""Spool helpers for staged delivery attachments."""

import hashlib
from pathlib import Path

from connectors.core.messages import ArtifactDict


class SpoolAttachmentStager:
    """Writes provider-requested attachment files under the spool root and removes them afterwards."""

    def __init__(self, root: Path):
        self._root = root
        self._paths: list[Path] = []

    def stage(
        self, relative_name: str, data: bytes, *, file_id: str, filename: str, content_type: str, part_name: str,
    ) -> ArtifactDict:
        path = self._root / relative_name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(data)
        self._paths.append(path)
        return {
            "file_id": file_id, "filename": filename, "content_type": content_type,
            "size_bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "part_name": part_name, "object_key": path.relative_to(self._root).as_posix(),
        }

    def cleanup(self) -> None:
        for path in self._paths:
            path.unlink(missing_ok=True)
        self._paths.clear()
