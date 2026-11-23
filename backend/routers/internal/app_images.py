"""App image: GET for every member, PUT/DELETE for administrators (the same rule as the App's general settings)."""
from typing import Annotated

from db.database import get_db
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from routers.controls.role_authorization import AppRole, require_min_role
from services.stored_image_service import StoredImageService
from sqlalchemy.orm import Session

from .stored_image_endpoints import (
    IMAGE_GET_RESPONSES,
    IMAGE_UPLOAD_DESCRIPTION,
    ImageUpdatedResponse,
    delete_image,
    image_response,
    store_uploaded_image,
)

app_images_router = APIRouter()  # mounted by apps_router at /{app_id}/image


# ``require_min_role`` resolves the caller's role on ``app_id`` and answers 404 for an App that does not exist.
@app_images_router.get(
    "",
    summary="Get the App image",
    description="Pass `v` (the App's `image_updated_at`) to get a response the browser may cache.",
    response_class=Response,
    responses=IMAGE_GET_RESPONSES,
)
async def get_app_image(
    app_id: int,
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    v: Annotated[str | None, Query(max_length=64)] = None,
):
    return image_response(StoredImageService.app_images(db), app_id, v)


@app_images_router.put(
    "",
    response_model=ImageUpdatedResponse,
    summary="Upload the App image",
    description=IMAGE_UPLOAD_DESCRIPTION,
)
async def upload_app_image(
    app_id: int,
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    file: Annotated[UploadFile, File(...)],
):
    updated_at = await store_uploaded_image(StoredImageService.app_images(db), app_id, file)
    return ImageUpdatedResponse(image_updated_at=updated_at)


@app_images_router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove the App image",
)
async def delete_app_image(
    app_id: int,
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    return delete_image(StoredImageService.app_images(db), app_id)
