from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import Response
from typing import List, Annotated
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

# Import schemas and auth
from schemas.skill_schemas import SkillListItemSchema, SkillDetailSchema, CreateUpdateSkillSchema
from .auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole

# Import database and service
from db.database import get_db
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
    """
    List all skills visible to the app (owned + global builtins).
    """
    try:
        return SkillService.list_skills(db, app_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving skills: {str(e)}"
        )


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
    """
    Get detailed information about a specific skill.
    """
    try:
        skill_detail = SkillService.get_skill_detail(db, app_id, skill_id)

        if skill_detail is None and skill_id != 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SKILL_NOT_FOUND_ERROR
            )

        return skill_detail

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving skill: {str(e)}"
        )


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
    """
    Create a new skill or update an existing one.
    Skills with a non-null ``runtime`` require ADMINISTRATOR role (enforced here).
    """
    try:
        skill = SkillService.create_or_update_skill(db, app_id, skill_id, skill_data)

        if skill is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SKILL_NOT_FOUND_ERROR
            )

        # Return updated skill (reuse the GET logic)
        return await get_skill(app_id, skill.skill_id, auth_context, db, role)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating/updating skill: {str(e)}"
        )


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
    """
    Delete a skill.  Built-in skills cannot be deleted.
    """
    try:
        success = SkillService.delete_skill(db, app_id, skill_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SKILL_NOT_FOUND_ERROR
            )

        return {"message": "Skill deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting skill: {str(e)}"
        )


# ==================== IMPORT / EXPORT (IT-3) ====================


@skills_router.get("/{skill_id}/export",
                   summary="Export skill as ZIP",
                   tags=["Skills"])
async def export_skill(
    app_id: int,
    skill_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """
    Export a skill as a ZIP archive containing SKILL.md and supporting files.
    """
    try:
        zip_bytes = SkillService.export_skill_zip(db, app_id, skill_id)
        if zip_bytes is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SKILL_NOT_FOUND_ERROR,
            )
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=skill-{skill_id}.zip"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error exporting skill: {str(e)}",
        )


@skills_router.post("/import",
                    summary="Import skill from ZIP",
                    tags=["Skills"],
                    response_model=SkillDetailSchema)
async def import_skill(
    app_id: int,
    file: Annotated[UploadFile, File(description="ZIP archive produced by skill export")],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    """
    Import a skill from a ZIP archive.  If a skill with the same name already
    exists in the app it is overwritten; built-in skills are never overwritten.
    """
    try:
        zip_bytes = await file.read()
        skill = SkillService.import_skill_zip(db, app_id, zip_bytes)
        return await get_skill(app_id, skill.skill_id, auth_context, db, role)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error importing skill: {str(e)}",
        )

