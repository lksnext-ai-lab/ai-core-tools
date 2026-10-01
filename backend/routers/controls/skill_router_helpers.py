"""Shared helpers for the skill routers (backend/routers/internal/skills.py and admin.py's system-skills block).

Router-local: HTTP concerns only (error mapping, header sanitisation, bounded upload reads), no business logic.
"""
import contextlib
import re
from typing import Iterator, List, NoReturn

from fastapi import HTTPException, Response, UploadFile, status

from services.skill_errors import SkillImportError, SkillServiceError
from utils.logger import get_logger

logger = get_logger(__name__)

# 1 MiB read chunks while streaming an upload into memory.
_UPLOAD_CHUNK_BYTES = 1024 * 1024


def raise_for_service_error(e: SkillServiceError) -> NoReturn:
    """Map a typed service exception to the HTTPException its class carries. Never echoes str(e)."""
    raise HTTPException(status_code=e.status_code, detail=e.detail) from None


def raise_unexpected(context: str) -> NoReturn:
    """Log the full exception server-side (from the active except block) and raise a generic 500.

    Must be called from inside an ``except`` block so ``logger.exception`` can attach the traceback.
    """
    logger.exception(context)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred",
    ) from None


def safe_header_value(value: str) -> str:
    """Defense-in-depth against header injection in Content-Disposition.

    The filename already comes from ``normalize_skill_name`` (restricted to ``[a-z0-9._-]``), so this
    is a belt-and-suspenders strip of CR/LF/quotes, never the primary control.
    """
    return re.sub(r'[\r\n"]', '', value)


def zip_download_response(filename: str, data: bytes) -> Response:
    """Build the standard attachment response for a skill package ZIP download.

    ``X-Content-Type-Options: nosniff`` plus a forced ``attachment`` disposition so a browser never
    renders package contents inline (defence against a stored-XSS SKILL.md/file being served back).
    """
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_header_value(filename)}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@contextlib.contextmanager
def skill_error_boundary(context: str) -> Iterator[None]:
    """Full error-mapping ladder for one router handler body, in one place.

    An ``HTTPException`` raised deliberately inside the boundary (e.g. a 404 after a None check that itself
    runs inside the ``with`` block) passes through unchanged; a typed ``SkillServiceError`` maps to its class's
    status code; anything else is logged and turned into a generic 500 — so a stray exception from any service
    call is never silently mishandled, on any route.
    """
    try:
        yield
    except HTTPException:
        raise
    except SkillServiceError as e:
        raise_for_service_error(e)
    except Exception:
        raise_unexpected(context)


async def read_upload_bounded(file: UploadFile, max_bytes: int, *, log_context: str) -> bytes:
    """Stream an upload into memory, rejecting before it is fully buffered if it exceeds ``max_bytes``.

    This bounds only the backend PROCESS's own heap usage while reading from Starlette's already-received
    ``UploadFile`` (Starlette/FastAPI spools the request body to a temp file *before* any dependency or route
    handler runs, so a huge upload is never rejected before it hits disk on the ASGI server itself — that is a
    separate, pre-existing gap in the framework/proxy layer, not something this function can close).

    Args:
        file: The upload to read.
        max_bytes: Maximum number of bytes to accept.
        log_context: Short description included in the rejection log line (e.g. an app id or "system").

    Raises:
        SkillImportError: The upload exceeds ``max_bytes`` (mapped to 400 by the caller).
    """
    chunks: List[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            # INFO/WARNING-level rejection logging is the caller's job (it has the full service-error context,
            # e.g. app id); this stays at DEBUG so a rejection is never logged twice at visible severity.
            logger.debug("Upload exceeded %s bytes (%s)", max_bytes, log_context)
            raise SkillImportError(f"Uploaded archive exceeds the {max_bytes}-byte limit")
        chunks.append(chunk)
    return b"".join(chunks)
