"""Persistence and dispatch helpers for scheduled-task output providers."""

import os
import re
import random
import asyncio
import hashlib
import json
import mimetypes
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.output_delivery import OutputArtifact, OutputDelivery, OutputDeliveryAttempt, OutputDestination, ScheduledTaskOutputBinding
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from output.registry import get_output_provider
from output.teams_workflow import DeliveryError, build_adaptive_card

MAX_ATTEMPTS = 5
LEASE_SECONDS = 120


def _delivery_expiry() -> datetime:
    # Keep pending deliveries inside the file cleanup worker's persistent-file
    # retention window so a card cannot be retried after its links have expired.
    persistent_ttl_days = max(1, int(os.getenv("TMP_PERSISTENT_TTL_DAYS", "7")))
    persistent_ttl_seconds = persistent_ttl_days * 86400
    return datetime.utcnow() + timedelta(seconds=min(30 * 86400, persistent_ttl_seconds - 3600))


def _base_url() -> str:
    return (os.getenv("FRONTEND_URL") or os.getenv("AICT_BASE_URL") or "http://localhost:5173").rstrip("/")


def destination_dto(destination: OutputDestination) -> dict[str, Any]:
    return {
        "id": destination.id,
        "app_id": destination.app_id,
        "name": destination.name,
        "provider_key": destination.provider_key,
        "content_mode": destination.content_mode,
        "enabled": destination.enabled,
        "has_secret": bool(destination.webhook_url),
        "public_config": destination.public_config or {},
        "has_credentials": bool(destination.credentials),
        "created_at": destination.created_at,
        "updated_at": destination.updated_at,
    }


def create_destination(
    db: Session, *, app_id: int, created_by: int, name: str, webhook_url: str,
    provider_key: str = "teams_workflow", public_config: dict[str, Any] | None = None,
    credentials: dict[str, str] | None = None,
    content_mode: str = "result",
) -> OutputDestination:
    name = name.strip()
    if not name:
        raise ValueError("Destination name is required")
    if len(name) > 255:
        raise ValueError("Destination name is too long")
    provider = get_output_provider(provider_key)
    if content_mode not in provider.descriptor.content_modes:
        raise ValueError("Unsupported output content mode")
    config = dict(public_config or {})
    if provider_key == "webhook":
        webhook_url, config = provider.validate_destination(webhook_url, config, credentials)
    else:
        webhook_url = provider.validate_secret(webhook_url)
        if config or credentials:
            raise ValueError("Teams destinations do not accept webhook settings or credentials")
    destination = OutputDestination(
        app_id=app_id, created_by=created_by, name=name,
        provider_key=provider_key, public_config=config, webhook_url=webhook_url,
        content_mode=content_mode,
        credentials=credentials,
    )
    db.add(destination)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A destination with this name already exists in the app") from exc
    db.refresh(destination)
    return destination


def update_destination(db: Session, destination: OutputDestination, changes: dict[str, Any]) -> OutputDestination:
    if "name" in changes and changes["name"] is not None:
        name = changes["name"].strip()
        if not name or len(name) > 255:
            raise ValueError("Destination name is required and must be at most 255 characters")
        destination.name = name
    if "enabled" in changes and changes["enabled"] is not None:
        destination.enabled = changes["enabled"]
    provider = get_output_provider(destination.provider_key)
    if changes.get("content_mode") is not None:
        if changes["content_mode"] not in provider.descriptor.content_modes:
            raise ValueError("Unsupported output content mode")
        destination.content_mode = changes["content_mode"]
    new_url = changes.get("webhook_url") or destination.webhook_url
    new_config = changes.get("public_config") if changes.get("public_config") is not None else dict(destination.public_config or {})
    new_credentials = dict(destination.credentials or {})
    if changes.get("clear_credentials"):
        new_credentials = {}
    if changes.get("credentials") is not None:
        new_credentials = dict(changes["credentials"])
    if destination.provider_key == "webhook":
        new_url, new_config = provider.validate_destination(new_url, new_config, new_credentials)
        if "webhook_url" in changes and changes["webhook_url"]:
            old = urlparse(destination.webhook_url)
            new = urlparse(new_url)
            if (old.scheme, old.netloc, old.path, old.query) != (new.scheme, new.netloc, new.path, new.query):
                raise ValueError("Changing a webhook endpoint requires creating a new destination")
        destination.public_config = new_config
        destination.credentials = new_credentials or None
        destination.webhook_url = new_url
    elif changes.get("webhook_url"):
        rotated_url = provider.validate_secret(changes["webhook_url"])
        current_endpoint = urlparse(destination.webhook_url)
        rotated_endpoint = urlparse(rotated_url)
        if (current_endpoint.scheme, current_endpoint.netloc, current_endpoint.path) != (
            rotated_endpoint.scheme, rotated_endpoint.netloc, rotated_endpoint.path,
        ):
            raise ValueError("Changing the Workflow or channel requires creating a new destination")
        destination.webhook_url = rotated_url
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A destination with this name already exists in the app") from exc
    db.refresh(destination)
    return destination


def get_destination(db: Session, *, app_id: int, destination_id: int) -> OutputDestination:
    destination = db.query(OutputDestination).filter(
        OutputDestination.id == destination_id, OutputDestination.app_id == app_id,
    ).one_or_none()
    if destination is None:
        raise ValueError("Output destination not found")
    return destination


def replace_task_bindings(
    db: Session, *, task: ScheduledTask, app_id: int, bindings: list[dict[str, Any]], commit: bool = True,
) -> list[dict[str, Any]]:
    desired: dict[int, dict[str, Any]] = {}
    for item in bindings:
        destination_id = int(item["destination_id"])
        if destination_id in desired:
            raise ValueError("A destination can only be selected once")
        destination = get_destination(db, app_id=app_id, destination_id=destination_id)
        if not destination.enabled or not destination.webhook_url:
            raise ValueError(f"Destination '{destination.name}' is not ready")
        desired[destination_id] = item

    existing = db.query(ScheduledTaskOutputBinding).filter_by(scheduled_task_id=task.id).all()
    by_destination = {binding.destination_id: binding for binding in existing}
    for destination_id, binding in by_destination.items():
        binding.enabled = destination_id in desired
    for destination_id, item in desired.items():
        binding = by_destination.get(destination_id)
        if binding is None:
            binding = ScheduledTaskOutputBinding(scheduled_task_id=task.id, destination_id=destination_id)
            db.add(binding)
        binding.enabled = bool(item.get("enabled", True))
        binding.event_types = ["succeeded"]
    db.commit() if commit else db.flush()
    return task_bindings(db, task=task, app_id=app_id)


def task_bindings(db: Session, *, task: ScheduledTask, app_id: int) -> list[dict[str, Any]]:
    return [
        {"destination_id": binding.destination_id, "enabled": binding.enabled,
         "destination_name": binding.destination.name,
         "provider_key": binding.destination.provider_key,
         "include_attachments": bool((binding.destination.public_config or {}).get("include_attachments", False))}
        for binding in db.query(ScheduledTaskOutputBinding).join(OutputDestination)
        .filter(ScheduledTaskOutputBinding.scheduled_task_id == task.id,
                OutputDestination.app_id == app_id, ScheduledTaskOutputBinding.enabled.is_(True))
        .order_by(OutputDestination.name).all()
    ]


def _run_payload(task: ScheduledTask, run: ScheduledTaskRun, binding: ScheduledTaskOutputBinding) -> dict[str, Any]:
    base = _base_url()
    result_url = f"{base}/apps/{task.app_id}/scheduled-tasks/{task.id}/runs/{run.id}"
    file_items = []
    for item in run.output_files or []:
        file_id = item.get("file_id")
        if not file_id:
            continue
        file_url = f"{base}/apps/{task.app_id}/scheduled-tasks/{task.id}/runs/{run.id}/files/{quote(str(file_id), safe='')}"
        file_items.append({"filename": str(item.get("filename") or "Output file"), "url": file_url})
    scheduled_time = run.scheduled_time
    if scheduled_time.tzinfo is None:
        scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
    else:
        scheduled_time = scheduled_time.astimezone(timezone.utc)
    result_text = run.output_text or ""
    for item in run.output_files or []:
        file_id = str(item.get("file_id") or "")
        filename = str(item.get("filename") or "output file")
        for identifier in (file_id, filename):
            if identifier:
                result_text = result_text.replace(f"file://{identifier}", filename)
    # Never place local sandbox/file references in a message. The card links below
    # point to the authenticated Mattin AI file route instead.
    result_text = re.sub(r"file://[^\s\])}]+", "[output file]", result_text)
    return build_adaptive_card(
        title=task.name,
        status=run.status,
        scheduled_time=scheduled_time.isoformat(),
        result=result_text,
        view_url=result_url,
        files=file_items,
        content_mode=binding.destination.content_mode,
    )


def _run_webhook_event(
    task: ScheduledTask, run: ScheduledTaskRun, binding: ScheduledTaskOutputBinding,
    event_id: str, artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    base = _base_url()
    result_url = f"{base}/apps/{task.app_id}/scheduled-tasks/{run.scheduled_task_id}/runs/{run.id}"
    files = []
    for item in (run.output_files or []):
        file_id = str(item.get("file_id") or "")
        if not file_id:
            continue
        filename = str(item.get("filename") or "Output file")
        files.append({
            "file_id": file_id,
            "filename": filename,
            "url": f"{result_url}/files/{quote(file_id, safe='')}",
        })
    text = run.output_text or ""
    for item in (run.output_files or []):
        file_id = str(item.get("file_id") or "")
        filename = str(item.get("filename") or "output file")
        for marker in (file_id, filename):
            if marker:
                text = text.replace(f"file://{marker}", filename)
    text = re.sub(r"file://[^\s\])}]+", "[output file]", text)
    mode = binding.destination.content_mode
    text_limit = 4000 if mode == "excerpt" else 100_000
    text_truncated = len(text) > text_limit
    visible_files = files[:50]
    files_truncated = len(visible_files) < len(files)
    if mode == "link_only":
        text = None
        visible_files = []
        files_truncated = False
        text_truncated = False
    else:
        text = text[:text_limit]
    occurred_at = run.finished_at or datetime.now(timezone.utc)
    scheduled_at = run.scheduled_time
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    manifest = [{key: item[key] for key in ("file_id", "filename", "content_type", "size_bytes", "sha256", "part_name")} for item in artifacts]
    return {
        "schema_version": "1",
        "event_id": event_id,
        "event_type": "task.run.succeeded",
        "occurred_at": occurred_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "app": {"id": task.app_id},
        "task": {"id": task.id, "name": task.name},
        "run": {
            "id": run.id,
            "status": run.status,
            "scheduled_at": scheduled_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "completed_at": occurred_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        "content": {
            "mode": mode,
            "text": text,
            "text_truncated": text_truncated,
            "files_truncated": files_truncated,
            "files": visible_files,
        },
        "attachments": manifest,
        "links": {"result": result_url},
    }


def _spool_root() -> Path:
    from utils.config import get_app_config
    root = Path(get_app_config()["TMP_BASE_FOLDER"]).resolve() / "output-deliveries"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def _safe_spool_file(relative_key: str) -> Path:
    root = _spool_root()
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


def cleanup_spool_files(db: Session, *, grace_seconds: int = 3600, max_files: int = 1000) -> int:
    """Remove old spool objects after their database references have expired."""
    root = _spool_root()
    referenced = {
        key for (key,) in db.query(OutputArtifact.object_key).all() if key
    }
    referenced.update(
        key for (key,) in db.query(OutputDelivery.request_body_path)
        .filter(OutputDelivery.request_body_path.is_not(None)).all() if key
    )
    cutoff = datetime.now(timezone.utc).timestamp() - grace_seconds
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


def _capture_run_files_sync(task: ScheduledTask, run: ScheduledTaskRun) -> list[dict[str, Any]]:
    from services.file_management_service import FileManagementService
    from services.scheduled_task_service import task_user_context
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
    spool_root = _spool_root()
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
        OutputDestination.provider_key == "webhook",
        OutputDestination.app_id == task.app_id,
    ).all()
    if not any((binding.destination.public_config or {}).get("include_attachments", False) for binding in requested):
        return [], None
    try:
        artifacts = await asyncio.to_thread(_capture_run_files_sync, task, run)
        return artifacts, None
    except Exception:
        return [], "Required run output files could not be captured for this webhook."


def _json_body(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(body) > 256 * 1024:
        raise ValueError("Webhook JSON event exceeds the 256 KiB limit")
    return body


def _file_contains(path: Path, needle: bytes) -> bool:
    overlap = b""
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(256 * 1024), b""):
            data = overlap + chunk
            if needle in data:
                return True
            overlap = data[-(len(needle) - 1):]
    return False


def _write_multipart(path: Path, payload: dict[str, Any], attachments: list[dict[str, Any]]) -> tuple[str, int, str]:
    event = _json_body(payload)
    root = _spool_root()
    while True:
        boundary = "mattin-" + uuid.uuid4().hex
        marker = boundary.encode("ascii")
        if marker not in event and not any(_file_contains(_safe_spool_file(item["object_key"]), marker) for item in attachments):
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
                source_path = _safe_spool_file(item["object_key"])
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


def create_deliveries_for_run(
    db: Session, *, task: ScheduledTask, run: ScheduledTaskRun,
    artifacts: list[dict[str, Any]] | None = None, attachment_error: str | None = None,
) -> list[OutputDelivery]:
    """Create immutable outbox rows in the caller's run-finalization transaction."""
    bindings = db.query(ScheduledTaskOutputBinding).join(OutputDestination).filter(
        ScheduledTaskOutputBinding.scheduled_task_id == task.id,
        ScheduledTaskOutputBinding.enabled.is_(True),
        OutputDestination.enabled.is_(True),
        OutputDestination.app_id == task.app_id,
    ).all()
    deliveries = []
    for binding in bindings:
        existing = db.query(OutputDelivery).filter_by(
            run_id=run.id, binding_id=binding.id, event_type="succeeded",
        ).one_or_none()
        if existing:
            deliveries.append(existing)
            continue
        destination = binding.destination
        config = dict(destination.public_config or {})
        snapshot = {"provider_key": destination.provider_key, "name": destination.name,
                    "content_mode": destination.content_mode}
        if destination.provider_key == "webhook":
            snapshot.update(config)
            event_id = str(uuid.uuid4())
            destination_artifacts = artifacts or [] if config.get("include_attachments") else []
            payload = _run_webhook_event(task, run, binding, event_id, destination_artifacts)
            body = None
            request_body_path = None
            request_body_size = None
            request_body_sha256 = None
            content_type = "application/json"
            status = "pending"
            error = attachment_error if config.get("include_attachments") else None
            if error:
                status = "failed"
            else:
                try:
                    body = _json_body(payload)
                    if config.get("include_attachments"):
                        key = f"deliveries/{event_id.replace('-', '')}.multipart"
                        content_type, request_body_size, request_body_sha256 = _write_multipart(
                            _safe_spool_file(key), payload, destination_artifacts,
                        )
                        request_body_path = key
                except Exception as exc:
                    status = "failed"
                    error = str(exc)[:300]
                    body = None
            snapshot["content_type"] = content_type
        else:
            payload = _run_payload(task, run, binding)
            body = None
            request_body_path = None
            request_body_size = None
            request_body_sha256 = None
            status = "pending"
            error = None
        delivery = OutputDelivery(
            run_id=run.id,
            binding_id=binding.id,
            destination_id=destination.id,
            event_type="succeeded",
            destination_snapshot=snapshot,
            payload=payload,
            request_body=body,
            request_body_path=request_body_path,
            request_body_size=request_body_size,
            request_body_sha256=request_body_sha256,
            status=status,
            error_summary=error,
            expires_at=_delivery_expiry(),
        )
        db.add(delivery)
        deliveries.append(delivery)
        if destination.provider_key == "webhook" and config.get("include_attachments") and not attachment_error:
            known = {row.file_id for row in db.query(OutputArtifact).filter_by(run_id=run.id).all()}
            for artifact in destination_artifacts:
                if artifact["file_id"] not in known:
                    db.add(OutputArtifact(
                        run_id=run.id,
                        file_id=artifact["file_id"], filename=artifact["filename"],
                        content_type=artifact["content_type"], size_bytes=artifact["size_bytes"],
                        sha256=artifact["sha256"], object_key=artifact["object_key"],
                    ))
    db.flush()
    return deliveries


def delivery_dto(delivery: OutputDelivery) -> dict[str, Any]:
    return {
        "id": delivery.id,
        "destination_name": (delivery.destination_snapshot or {}).get("name", "Output destination"),
        "provider_key": (delivery.destination_snapshot or {}).get("provider_key", "teams_workflow"),
        "event_type": delivery.event_type,
        "status": delivery.status,
        "attempt_count": delivery.attempt_count,
        "next_attempt_at": delivery.next_attempt_at,
        "receipt": delivery.receipt,
        "error_summary": delivery.error_summary,
        "created_at": delivery.created_at,
        "attempts": [{
            "attempt_number": attempt.attempt_number,
            "status": attempt.status,
            "started_at": attempt.started_at,
            "finished_at": attempt.finished_at,
            "http_status": attempt.http_status,
            "error_summary": attempt.error_summary,
        } for attempt in delivery.attempts],
    }


async def test_destination(destination: OutputDestination) -> dict[str, Any]:
    if destination.provider_key == "webhook":
        event_id = str(uuid.uuid4())
        payload = {
            "schema_version": "1", "event_id": event_id, "event_type": "destination.test",
            "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "app": {"id": destination.app_id}, "task": None, "run": None,
            "content": {"mode": destination.content_mode,
                        "text": None if destination.content_mode == "link_only" else "This is a test notification from Mattin AI.",
                        "text_truncated": False, "files_truncated": False, "files": []},
            "attachments": [], "links": {"result": _base_url()},
        }
        config = dict(destination.public_config or {})
        body = _json_body(payload)
        path = None
        content_type = "application/json"
        test_file = None
        if config.get("include_attachments"):
            root = _spool_root()
            test_file = root / "tests" / f"{event_id}.txt"
            test_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            test_file.write_bytes(b"Mattin AI webhook attachment test.\n")
            file_digest = hashlib.sha256(test_file.read_bytes()).hexdigest()
            payload["attachments"] = [{
                "file_id": "destination-test-file", "filename": "prueba.txt",
                "content_type": "text/plain", "size_bytes": test_file.stat().st_size,
                "sha256": file_digest, "part_name": "file_1",
            }]
            artifact = {"file_id": "destination-test-file", "filename": "prueba.txt", "content_type": "text/plain",
                        "size_bytes": test_file.stat().st_size, "sha256": file_digest,
                        "part_name": "file_1", "object_key": test_file.relative_to(root).as_posix()}
            path = root / "tests" / f"{event_id}.multipart"
            content_type, size, digest = _write_multipart(path, payload, [artifact])
            body = None
        try:
            return await get_output_provider(destination.provider_key).send(
                destination.webhook_url, payload, config=config, credentials=destination.credentials or {},
                event_id=event_id, attempt_number=1, content_type=content_type,
                body=body, body_path=str(path) if path else None,
            )
        finally:
            if path:
                path.unlink(missing_ok=True)
            if test_file:
                test_file.unlink(missing_ok=True)

    payload = build_adaptive_card(
        title=f"{destination.name}: connection test", status="test", scheduled_time=datetime.now(timezone.utc).isoformat(),
        result="This is a test notification from Mattin AI.", view_url=_base_url(), content_mode=destination.content_mode,
    )
    return await get_output_provider(destination.provider_key).send(destination.webhook_url, payload)


def request_retry(db: Session, delivery: OutputDelivery) -> None:
    if delivery.status not in {"failed", "unknown"}:
        raise ValueError("Only failed or uncertain deliveries can be retried manually")
    if delivery.expires_at and delivery.expires_at <= datetime.utcnow():
        raise ValueError("This delivery expired and can no longer be retried")
    delivery.dispatch_generation += 1
    delivery.status = "pending"
    delivery.next_attempt_at = None
    delivery.lease_until = None
    delivery.error_summary = None
    db.commit()


def _retry_delay(attempt: int) -> float:
    return min(3600.0, 30.0 * (2 ** max(0, attempt - 1))) * random.uniform(0.75, 1.25)


async def process_delivery(delivery_id: int, generation: int) -> None:
    """One guarded POST attempt. A recovered in-flight attempt becomes unknown, never reposted."""
    db = None
    try:
        from db.database import SessionLocal
        db = SessionLocal()
        delivery = db.query(OutputDelivery).filter(OutputDelivery.id == delivery_id).with_for_update().one_or_none()
        if delivery is None or delivery.dispatch_generation != generation:
            return
        now = datetime.utcnow()
        if delivery.status == "sending":
            if delivery.lease_until and delivery.lease_until > now:
                return
            snapshot = delivery.destination_snapshot or {}
            retry_deduplicated = (
                snapshot.get("provider_key") == "webhook"
                and snapshot.get("receiver_deduplicates") is True
                and delivery.attempt_count < MAX_ATTEMPTS
                and (not delivery.expires_at or delivery.expires_at > now)
            )
            delivery.status = "retry_wait" if retry_deduplicated else "unknown"
            delivery.error_summary = (
                "Webhook worker stopped during an idempotent request; retry scheduled."
                if retry_deduplicated else
                "Worker stopped while the external request was in flight; verify receipt before resending."
            )
            if retry_deduplicated:
                delivery.next_attempt_at = now + timedelta(seconds=30)
            delivery.lease_until = None
            if delivery.attempts:
                delivery.attempts[-1].status = delivery.status
                delivery.attempts[-1].finished_at = now
                delivery.attempts[-1].error_summary = delivery.error_summary
            db.commit()
            return
        if delivery.status != "pending":
            return
        if delivery.expires_at and delivery.expires_at <= now:
            delivery.status = "failed"
            delivery.error_summary = "Delivery expired before it was sent."
            db.commit()
            return
        if not delivery.destination or not delivery.destination.enabled:
            delivery.status = "failed"
            delivery.error_summary = "Output destination is missing or disabled."
            db.commit()
            return
        webhook_url = delivery.destination.webhook_url
        provider_key = (delivery.destination_snapshot or {}).get("provider_key", delivery.destination.provider_key)
        payload = delivery.payload
        snapshot = dict(delivery.destination_snapshot or {})
        credentials = dict(delivery.destination.credentials or {})
        request_body = delivery.request_body
        request_body_key = delivery.request_body_path
        request_body_size = delivery.request_body_size
        request_body_sha256 = delivery.request_body_sha256
        delivery.attempt_count += 1
        attempt_number = delivery.attempt_count
        attempt = OutputDeliveryAttempt(delivery_id=delivery.id, attempt_number=delivery.attempt_count, status="sending")
        db.add(attempt)
        delivery.status = "sending"
        snapshot = delivery.destination_snapshot or {}
        lease_seconds = 180 if snapshot.get("provider_key") == "webhook" and snapshot.get("include_attachments") else LEASE_SECONDS
        delivery.lease_until = now + timedelta(seconds=lease_seconds)
        delivery.error_summary = None
        db.commit()
        attempt_id = attempt.id
        db.close()
        db = None

        try:
            provider = get_output_provider(provider_key)
            if provider_key == "webhook":
                body = request_body
                body_path = None
                if request_body_key:
                    path = _safe_spool_file(request_body_key)
                    if not path.is_file() or path.stat().st_size != request_body_size:
                        raise DeliveryError("Prepared webhook request body is missing or incomplete", kind="permanent")
                    digest = hashlib.sha256()
                    with path.open("rb") as source:
                        for chunk in iter(lambda: source.read(256 * 1024), b""):
                            digest.update(chunk)
                    if digest.hexdigest() != request_body_sha256:
                        raise DeliveryError("Prepared webhook request body failed integrity validation", kind="permanent")
                    body_path = str(path)
                    body = None
                receipt = await provider.send(
                    webhook_url, payload, config={key: value for key, value in snapshot.items()
                        if key in {"schema_version", "auth_mode", "receiver_deduplicates", "include_attachments"}},
                    credentials=credentials, event_id=payload["event_id"],
                    attempt_number=attempt_number,
                    content_type=snapshot.get("content_type", "application/json"),
                    body=body, body_path=body_path,
                )
            else:
                receipt = await provider.send(webhook_url, payload)
            outcome = ("accepted", receipt, None, None, None)
        except DeliveryError as exc:
            outcome = (exc.kind, None, exc.http_status, str(exc), exc.retry_after)

        db = SessionLocal()
        delivery = db.query(OutputDelivery).filter_by(id=delivery_id).with_for_update().one_or_none()
        attempt = db.query(OutputDeliveryAttempt).filter_by(id=attempt_id).one_or_none()
        if delivery is None or attempt is None:
            return
        # A late response must not overwrite a retried generation or a lease
        # that the reconciler has already classified as uncertain.
        if delivery.dispatch_generation != generation or delivery.status != "sending" or attempt.status != "sending":
            return
        kind, receipt, http_status, message, retry_after = outcome
        now = datetime.utcnow()
        attempt.finished_at = now
        attempt.http_status = http_status or (receipt or {}).get("http_status")
        delivery.lease_until = None
        if kind == "accepted":
            attempt.status = "accepted"
            delivery.status = "accepted"
            delivery.receipt = receipt
        elif kind == "unknown":
            attempt.status = delivery.status = "unknown"
            attempt.error_summary = delivery.error_summary = message
        elif kind == "retryable" and delivery.attempt_count < MAX_ATTEMPTS:
            attempt.status = "retry_wait"
            delivery.status = "retry_wait"
            delay = retry_after if retry_after is not None else _retry_delay(delivery.attempt_count)
            delivery.next_attempt_at = now + timedelta(seconds=min(max(delay, 1), 86400))
            attempt.error_summary = delivery.error_summary = message
        else:
            attempt.status = "failed"
            delivery.status = "failed"
            attempt.error_summary = delivery.error_summary = message
        db.commit()
    except Exception:
        if db:
            db.rollback()
        raise
    finally:
        if db:
            db.close()
