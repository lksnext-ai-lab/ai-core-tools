from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
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
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    List all skills for a specific app.
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
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
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
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Create a new skill or update an existing one.
    """
    try:
        skill = SkillService.create_or_update_skill(db, app_id, skill_id, skill_data)

        if skill is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SKILL_NOT_FOUND_ERROR
            )

        # Return updated skill (reuse the GET logic)
        return await get_skill(app_id, skill.skill_id, auth_context, role, db)

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
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Delete a skill.
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
