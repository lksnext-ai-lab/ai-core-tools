from typing import Annotated, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

import config as settings
# Import schemas and auth
from schemas.skill_schemas import (
    CreateUpdateSkillSchema, SkillDetailSchema, SkillEnabledUpdateSchema, SkillFileContentSchema,
    SkillListItemSchema
)
from .auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole
from routers.controls.skill_router_helpers import (
    read_upload_bounded,
    skill_error_boundary,
    zip_download_response,
)

# Import database and services
from db.database import get_db
from services.skill_errors import SkillServiceError
from services.skill_package_service import SkillPackageService
from services.skill_service import SkillService

# Import logger
from utils.logger import get_logger

SKILL_NOT_FOUND_ERROR = "Skill not found"

logger = get_logger(__name__)

skills_router = APIRouter()


# ==================== SKILL MANAGEMENT ====================


@skills_router.get("/",
                   summary="List skills",
                   tags=["Skills"],
                   response_model=List[SkillListItemSchema])
async def list_skills(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """List the skills visible to an app: its own skills plus enabled system skills."""
    with skill_error_boundary(f"Error listing skills for app {app_id}"):
        return SkillService.list_skills(db, app_id)


@skills_router.post("/import",
                    summary="Import skill package",
                    tags=["Skills"],
                    response_model=SkillDetailSchema,
                    status_code=status.HTTP_201_CREATED)
async def import_skill(
    app_id: int,
    file: Annotated[UploadFile, File(...)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    """Import a skill package (a ZIP with ``SKILL.md`` at its root) into this app.

    The archive is fully validated and persisted atomically by ``SkillPackageService.import_package``
    (CPU-bound, run off the event loop via a threadpool).
    """
    with skill_error_boundary(f"Error importing skill package for app {app_id}"):
        try:
            with SkillPackageService.upload_admission_slot():
                data = await read_upload_bounded(
                    file, settings.SKILL_IMPORT_MAX_ARCHIVE_BYTES, log_context=f"app {app_id}"
                )
                detail = await run_in_threadpool(
                    SkillPackageService.import_package, db, app_id=app_id, data=data, source='admin'
                )
        except SkillServiceError as e:
            logger.info(
                "Skill import rejected for app %s: %s (%s) %s", app_id, e.__class__.__name__, e.status_code, e.detail
            )
            raise
        logger.info(
            "Skill import accepted for app %s: skill_id=%s bytes=%s files=%s",
            app_id, detail.skill_id, len(data), len(detail.files),
        )
        return detail


@skills_router.get("/{skill_id}/export",
                   summary="Export skill package",
                   tags=["Skills"])
async def export_skill(
    app_id: int,
    skill_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """Export an own-app skill or an enabled system skill as a ZIP package.

    Zip building is CPU-bound and runs off the event loop via a threadpool.
    """
    with skill_error_boundary(f"Error exporting skill {skill_id} for app {app_id}"):
        result = await run_in_threadpool(SkillPackageService.export_for_app, db, app_id, skill_id)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SKILL_NOT_FOUND_ERROR)

        filename, zip_bytes = result
        return zip_download_response(filename, zip_bytes)


@skills_router.patch("/{skill_id}/enabled",
                     summary="Enable or disable a skill",
                     tags=["Skills"],
                     response_model=SkillDetailSchema)
async def set_skill_enabled(
    app_id: int,
    skill_id: int,
    body: SkillEnabledUpdateSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    """Enable or disable an app-owned skill. Rejects a system skill with 403 (use the admin surface)."""
    with skill_error_boundary(f"Error toggling skill {skill_id} enabled for app {app_id}"):
        detail = SkillService.set_enabled_for_app(db, app_id, skill_id, body.is_enabled)
        if detail is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SKILL_NOT_FOUND_ERROR)
        return detail


@skills_router.get("/{skill_id}",
                   summary="Get skill details",
                   tags=["Skills"],
                   response_model=SkillDetailSchema)
async def get_skill(
    app_id: int,
    skill_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """Get detailed information about a specific skill (own-app or an enabled system skill)."""
    with skill_error_boundary(f"Error retrieving skill {skill_id} for app {app_id}"):
        skill_detail = SkillService.get_skill_detail(db, app_id, skill_id)
        if skill_detail is None and skill_id != 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SKILL_NOT_FOUND_ERROR)
        return skill_detail


@skills_router.get("/{skill_id}/files/content",
                   summary="Get the text content of one skill package file",
                   tags=["Skills"],
                   response_model=SkillFileContentSchema)
async def get_skill_file_content(
    app_id: int,
    skill_id: int,
    path: str,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """Fetch the text content of one file of an own-app skill or an enabled system skill, on demand.

    404 when the skill is not visible to this app, or when ``path`` does not resolve to a file of
    THIS skill (including a path that only exists under a different skill). A binary file, or a
    ``path`` that fails the shared path-safety validation, is rejected with 400.
    """
    with skill_error_boundary(f"Error reading skill file content for skill {skill_id} in app {app_id}"):
        content = SkillService.get_file_content_for_app(db, app_id, skill_id, path)
        if content is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill file not found")
        return content


@skills_router.post("/{skill_id}",
                    summary="Create or update skill",
                    tags=["Skills"],
                    response_model=SkillDetailSchema)
async def create_or_update_skill(
    app_id: int,
    skill_id: int,
    skill_data: CreateUpdateSkillSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    """Create a new skill or update an existing one. A system skill target is rejected with 403."""
    with skill_error_boundary(f"Error creating/updating skill {skill_id} for app {app_id}"):
        detail = SkillService.create_or_update_skill(db, app_id, skill_id, skill_data)
        if detail is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SKILL_NOT_FOUND_ERROR)
        return detail


@skills_router.delete("/{skill_id}",
                      summary="Delete skill",
                      tags=["Skills"])
async def delete_skill(
    app_id: int,
    skill_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    """Delete an app-owned skill. A system skill target is rejected with 403."""
    with skill_error_boundary(f"Error deleting skill {skill_id} for app {app_id}"):
        success = SkillService.delete_skill(db, app_id, skill_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SKILL_NOT_FOUND_ERROR)
        return {"message": "Skill deleted successfully"}
