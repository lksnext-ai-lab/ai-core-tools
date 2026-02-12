from typing import Optional, List
from models.skill import Skill
from repositories.skill_repository import SkillRepository
from sqlalchemy.orm import Session
from datetime import datetime
from schemas.skill_schemas import SkillListItemSchema, SkillDetailSchema, CreateUpdateSkillSchema
from utils.logger import get_logger

logger = get_logger(__name__)


class SkillService:
    @staticmethod
    def list_skills(db: Session, app_id: int) -> List[SkillListItemSchema]:
        """Get all skills for a specific app as list items"""
        skills = SkillRepository.get_all_by_app_id(db, app_id)

        result = []
        for skill in skills:
            result.append(SkillListItemSchema(
                skill_id=skill.skill_id,
                name=skill.name,
                description=skill.description or "",
                created_at=skill.create_date
            ))

        return result

    @staticmethod
    def get_skill_detail(db: Session, app_id: int, skill_id: int) -> Optional[SkillDetailSchema]:
        """Get detailed information about a specific skill"""
        if skill_id == 0:
            # New skill
            return SkillDetailSchema(
                skill_id=0,
                name="",
                description="",
                content="",
                created_at=None
            )

        # Existing skill
        skill = SkillRepository.get_by_id_and_app_id(db, skill_id, app_id)

        if not skill:
            return None

        return SkillDetailSchema(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description or "",
            content=skill.content or "",
            created_at=skill.create_date
        )

    @staticmethod
    def create_or_update_skill(
        db: Session,
        app_id: int,
        skill_id: int,
        skill_data: CreateUpdateSkillSchema
    ) -> Optional[Skill]:
        """Create a new skill or update an existing one"""
        if skill_id == 0:
            # Create new skill
            skill = Skill()
            skill.app_id = app_id
            skill.create_date = datetime.now()
        else:
            # Update existing skill
            skill = SkillRepository.get_by_id_and_app_id(db, skill_id, app_id)

            if not skill:
                return None

        # Update skill data
        skill.name = skill_data.name
        skill.description = skill_data.description
        skill.content = skill_data.content

        # Use repository to save
        if skill_id == 0:
            return SkillRepository.create(db, skill)
        else:
            return SkillRepository.update(db, skill)

    @staticmethod
    def delete_skill(db: Session, app_id: int, skill_id: int) -> bool:
        """Delete a skill"""
        return SkillRepository.delete_by_id_and_app_id(db, skill_id, app_id)
