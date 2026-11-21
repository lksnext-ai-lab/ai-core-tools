"""HTTP side of the stored pictures (user avatar, App image), shared by their routers."""
from datetime import datetime

from fastapi import HTTPException, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from services.stored_image_service import StoredImageService
from utils.image_normalization import (
    MAX_UPLOAD_BYTES,
    ImageValidationError,
    normalize_square_image,
)

# A URL carrying the version (?v=<updated_at>) never changes content: the browser may keep it.
VERSIONED_CACHE_CONTROL = "private, max-age=31536000, immutable"
UNVERSIONED_CACHE_CONTROL = "private, no-cache"

IMAGE_GET_RESPONSES = {200: {"content": {"image/webp": {}}}, 404: {"description": "No image"}}
IMAGE_UPLOAD_DESCRIPTION = "PNG, JPEG, WebP or GIF up to 5 MB. Stored center-cropped as a 256x256 WebP."


class ImageUpdatedResponse(BaseModel):
    image_updated_at: datetime


def image_response(service: StoredImageService, owner_id: int, version: str | None) -> Response:
    image = service.get(owner_id)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No image")
    return Response(
        content=image.content,
        media_type=image.content_type,
        headers={
            "Cache-Control": VERSIONED_CACHE_CONTROL if version else UNVERSIONED_CACHE_CONTROL,
            "X-Content-Type-Options": "nosniff",
        },
    )


async def store_uploaded_image(service: StoredImageService, owner_id: int, file: UploadFile) -> datetime:
    """Validate + normalise off the event loop, then store. Invalid uploads -> 400 / 413 with a ``code``."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        normalized = await run_in_threadpool(normalize_square_image, data)
    except ImageValidationError as exc:
        code = (status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if exc.code == "IMAGE_TOO_LARGE"
                else status.HTTP_400_BAD_REQUEST)
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": exc.message}) from exc
    return service.save(owner_id, normalized).updated_at


def delete_image(service: StoredImageService, owner_id: int) -> Response:
    service.delete(owner_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
