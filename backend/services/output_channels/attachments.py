"""Capture of run output files into the spool for attachment-capable destinations."""

import asyncio
import hashlib
import mimetypes
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from connectors import registry as connector_registry
from models.output_delivery import OutputDestination, ScheduledTaskOutputBinding
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from services.file_management_service import FileManagementService
from services.output_channels import spool
from services.scheduled_task_identity import task_user_context
from sqlalchemy.orm import Session


def capture_run_files_sync(task: ScheduledTask, run: ScheduledTaskRun) -> list[dict[str, Any]]:
    from utils.config import get_app_config

    outputs = [item for item in (run.output_files or []) if item.get("file_id")]
    if len(outputs) > 10:
        raise ValueError("Webhook attachment limit is 10 files")
    requested = {str(item["file_id"]): item for item in outputs}
    service = FileManagementService()
    refs = asyncio.run(service.list_attached_files(
        agent_id=task.agent_id,
        user_context=task_user_context(task),
        conversation_id=str(run.conversation_id) if run.conversation_id else None,
    ))
    by_id = {str(item.get("file_id")): item for item in refs}
    missing = requested.keys() - by_id.keys()
    if missing:
        raise ValueError("One or more run output files are unavailable for webhook attachment")

    temp_root = Path(get_app_config()["TMP_BASE_FOLDER"]).resolve()
    spool_root = spool.spool_root()
    artifacts_root = spool_root / "artifacts" / str(run.id)
    artifacts_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    total = 0
    captured: list[dict[str, Any]] = []
    for index, file_id in enumerate(sorted(requested), start=1):
        output = requested[file_id]
        ref = by_id[file_id]
        relative = ref.get("file_path")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Run output file path is unavailable")
        source = temp_root / relative
        current = temp_root
        for part in Path(relative).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Run output file path is not safe")
        source = source.resolve(strict=True)
        if not source.is_relative_to(temp_root) or not source.is_file():
            raise ValueError("Run output file path is not safe")
        digest = hashlib.sha256()
        size = 0
        object_name = hashlib.sha256(file_id.encode("utf-8")).hexdigest() + ".bin"
        target = artifacts_root / object_name
        if target.exists():
            with target.open("rb") as saved:
                for chunk in iter(lambda: saved.read(256 * 1024), b""):
                    size += len(chunk)
                    digest.update(chunk)
        else:
            fd, staging_name = tempfile.mkstemp(prefix=".capture-", dir=artifacts_root)
            try:
                with os.fdopen(fd, "wb") as staged, source.open("rb") as original:
                    for chunk in iter(lambda: original.read(256 * 1024), b""):
                        size += len(chunk)
                        if size > 10 * 1024 * 1024:
                            raise ValueError("Webhook attachments are limited to 10 MiB each")
                        digest.update(chunk)
                        staged.write(chunk)
                    staged.flush()
                    os.fsync(staged.fileno())
                os.replace(staging_name, target)
            except Exception:
                try:
                    os.unlink(staging_name)
                except OSError:
                    pass
                raise
        if size > 10 * 1024 * 1024:
            raise ValueError("Webhook attachments are limited to 10 MiB each")
        total += size
        if total > 25 * 1024 * 1024:
            raise ValueError("Webhook attachments are limited to 25 MiB per delivery")
        mime = ref.get("mime_type") or mimetypes.guess_type(str(output.get("filename") or ref.get("filename")))[0] or "application/octet-stream"
        if not isinstance(mime, str) or not re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", mime):
            mime = "application/octet-stream"
        filename = str(output.get("filename") or ref.get("filename") or "output file")[:512]
        captured.append({
            "file_id": file_id,
            "filename": filename,
            "content_type": mime[:255],
            "size_bytes": size,
            "sha256": digest.hexdigest(),
            "part_name": f"file_{index}",
            "object_key": target.relative_to(spool_root).as_posix(),
        })
    return captured


async def prepare_run_attachments(db: Session, *, task: ScheduledTask, run: ScheduledTaskRun) -> tuple[list[dict[str, Any]], str | None]:
    requested = db.query(ScheduledTaskOutputBinding).join(OutputDestination).filter(
        ScheduledTaskOutputBinding.scheduled_task_id == task.id,
        ScheduledTaskOutputBinding.enabled.is_(True),
        OutputDestination.enabled.is_(True),
        OutputDestination.provider_key.in_(connector_registry.spool_attachment_provider_keys()),
        OutputDestination.app_id == task.app_id,
    ).all()
    if not any(
        connector_registry.get_output_provider(binding.destination.provider_key).includes_attachments(
            binding.destination.public_config,
        )
        for binding in requested
    ):
        return [], None
    try:
        artifacts = await asyncio.to_thread(capture_run_files_sync, task, run)
        return artifacts, None
    except Exception:
        return [], "Required run output files could not be captured for this webhook."
