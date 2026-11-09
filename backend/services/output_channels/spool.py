"""Spool storage for prepared request bodies and captured attachments (paths, hashing, cleanup)."""

import hashlib
import json
import os
import re
import tempfile
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from connectors.core.messages import ArtifactDict
from models.output_delivery import OutputArtifact, OutputDelivery
from services.output_channels import delivery_policy
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from utils.clock import utcnow_naive
from utils.logger import get_logger

logger = get_logger(__name__)


def spool_root() -> Path:
    from utils.config import get_app_config
    root = Path(get_app_config()["TMP_BASE_FOLDER"]).resolve() / "output-deliveries"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


class SpoolAttachmentStager:
    """Writes provider-requested attachment files under the spool root and removes them afterwards.

    root may be a callable: it is resolved on the first stage call, so a provider that never
    stages a file does not touch the filesystem.
    """

    def __init__(self, root: Path | Callable[[], Path]):
        self._root_source = root
        self._root: Path | None = None
        self._paths: list[Path] = []

    def _resolve_root(self) -> Path:
        if self._root is None:
            self._root = self._root_source() if callable(self._root_source) else self._root_source
        return self._root

    def stage(
        self, relative_name: str, data: bytes, *, file_id: str, filename: str, content_type: str, part_name: str,
    ) -> ArtifactDict:
        root = self._resolve_root()
        path = contained_spool_path(root, relative_name)
        # Registered before any write so cleanup also covers a partially written file.
        self._paths.append(path)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(data)
        return {
            "file_id": file_id, "filename": filename, "content_type": content_type,
            "size_bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "part_name": part_name, "object_key": path.relative_to(root).as_posix(),
        }

    def cleanup(self) -> None:
        """Best effort: a failing unlink is logged and never masks the caller's outcome."""
        for path in self._paths:
            remove_quietly(path)
        self._paths.clear()


def remove_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not remove output spool file (%s); the spool sweep will retry", type(exc).__name__)


def contained_spool_path(root: Path, relative_key: str) -> Path:
    """Resolve relative_key under root, rejecting absolute paths, .. and symlink escapes."""
    key = Path(relative_key)
    if key.is_absolute() or ".." in key.parts:
        raise ValueError("Invalid output spool reference")
    candidate = root / key
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise ValueError("Invalid output spool reference")
    for parent in (candidate, *candidate.parents):
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise ValueError("Invalid output spool reference")
    return candidate


def safe_spool_file(relative_key: str) -> Path:
    return contained_spool_path(spool_root(), relative_key)


def release_unneeded_bodies(db: Session) -> None:
    """Drop prepared bodies and artifact rows that no future send can use."""
    now = utcnow_naive()
    needed = and_(
        OutputDelivery.status.in_(delivery_policy.BODY_NEEDED_STATUSES),
        or_(OutputDelivery.expires_at.is_(None), OutputDelivery.expires_at > now),
    )
    db.query(OutputDelivery).filter(
        ~needed,
        or_(OutputDelivery.request_body.is_not(None), OutputDelivery.request_body_path.is_not(None)),
    ).update({OutputDelivery.request_body: None, OutputDelivery.request_body_path: None}, synchronize_session=False)
    still_needed = db.query(OutputDelivery.id).filter(OutputDelivery.run_id == OutputArtifact.run_id, needed).exists()
    db.query(OutputArtifact).filter(~still_needed).delete(synchronize_session=False)
    db.commit()


def cleanup_spool_files(db: Session, *, grace_seconds: int = 3600, max_files: int = 1000) -> int:
    """Release unneeded prepared bodies, then remove unreferenced spool objects."""
    release_unneeded_bodies(db)
    root = spool_root()
    referenced = {
        key for (key,) in db.query(OutputArtifact.object_key).all() if key
    }
    referenced.update(
        key for (key,) in db.query(OutputDelivery.request_body_path)
        .filter(OutputDelivery.request_body_path.is_not(None)).all() if key
    )
    cutoff = datetime.now(UTC).timestamp() - grace_seconds
    removed = 0
    for candidate in root.rglob("*"):
        if removed >= max_files:
            break
        if candidate.is_symlink():
            continue
        if not candidate.is_file():
            continue
        try:
            relative = candidate.relative_to(root).as_posix()
            if relative not in referenced and candidate.stat().st_mtime < cutoff:
                candidate.unlink()
                removed += 1
        except (FileNotFoundError, OSError):
            continue
    for directory in sorted((path for path in root.rglob("*") if path.is_dir() and not path.is_symlink()), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    return removed


def json_body(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(body) > 256 * 1024:
        raise ValueError("Webhook JSON event exceeds the 256 KiB limit")
    return body


def file_contains(path: Path, needle: bytes) -> bool:
    overlap = b""
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(256 * 1024), b""):
            data = overlap + chunk
            if needle in data:
                return True
            overlap = data[-(len(needle) - 1):]
    return False


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(256 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_multipart(path: Path, payload: dict[str, Any], attachments: list[dict[str, Any]]) -> tuple[str, int, str]:
    event = json_body(payload)
    spool_root()  # ensures the spool directory exists (unchanged side effect)
    while True:
        boundary = "mattin-" + uuid.uuid4().hex
        marker = boundary.encode("ascii")
        if marker not in event and not any(file_contains(safe_spool_file(item["object_key"]), marker) for item in attachments):
            break
    content_type = f"multipart/form-data; boundary={boundary}"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    size = 0
    digest = hashlib.sha256()
    fd, staging_name = tempfile.mkstemp(prefix=".request-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            def write(data: bytes) -> None:
                nonlocal size
                size += len(data)
                if size > 26 * 1024 * 1024:
                    raise ValueError("Webhook multipart request is limited to 26 MiB")
                digest.update(data)
                out.write(data)

            write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload\"\r\nContent-Type: application/json\r\n\r\n".encode("ascii"))
            write(event)
            write(b"\r\n")
            for item in attachments:
                suffix = Path(item["filename"]).suffix
                suffix = suffix if re.fullmatch(r"\.[A-Za-z0-9]{1,10}", suffix or "") else ""
                transport_name = item["part_name"] + suffix
                write((
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"{item['part_name']}\"; filename=\"{transport_name}\"\r\n"
                    f"Content-Type: {item['content_type']}\r\n\r\n"
                ).encode("ascii"))
                source_path = safe_spool_file(item["object_key"])
                if not source_path.is_file():
                    raise ValueError("A captured webhook attachment is missing")
                with source_path.open("rb") as source:
                    file_digest = hashlib.sha256()
                    file_size = 0
                    for chunk in iter(lambda: source.read(256 * 1024), b""):
                        file_digest.update(chunk)
                        file_size += len(chunk)
                        write(chunk)
                    if file_size != item["size_bytes"] or file_digest.hexdigest() != item["sha256"]:
                        raise ValueError("A captured webhook attachment failed integrity validation")
                write(b"\r\n")
            write(f"--{boundary}--\r\n".encode("ascii"))
            out.flush()
            os.fsync(out.fileno())
        os.replace(staging_name, path)
    except Exception:
        try:
            os.unlink(staging_name)
        except OSError:
            pass
        raise
    return content_type, size, digest.hexdigest()
