from typing import Optional, List
from sqlalchemy import func
from sqlalchemy.orm import Session
from models.skill import Skill
from models.agent import AgentSkill
from repositories.skill_package_repository import SkillPackageRepository


class SkillRepository:
    """Repository class for Skill database operations"""

    @staticmethod
    def get_all_by_app_id(db: Session, app_id: int) -> List[Skill]:
        """Get all skills for a specific app"""
        if app_id is None:
            raise ValueError("app_id is required")
        return db.query(Skill).filter(Skill.app_id == app_id).all()

    @staticmethod
    def get_by_id_and_app_id(db: Session, skill_id: int, app_id: int) -> Optional[Skill]:
        """Get a specific skill by ID and app ID"""
        if app_id is None:
            raise ValueError("app_id is required")
        return db.query(Skill).filter(
            Skill.skill_id == skill_id,
            Skill.app_id == app_id
        ).first()

    @staticmethod
    def get_system_skills(db: Session, enabled_only: bool = True) -> List[Skill]:
        """Get system (platform) skills, optionally only the enabled ones"""
        query = db.query(Skill).filter(Skill.app_id.is_(None))
        if enabled_only:
            query = query.filter(Skill.is_enabled.is_(True))
        return query.order_by(Skill.name).all()

    @staticmethod
    def get_by_id_unscoped(db: Session, skill_id: int) -> Optional[Skill]:
        """Get a skill by ID without app scoping.

        For omniadmin-guarded routes only; app-scoped code must use get_by_id_and_app_id.
        """
        return db.query(Skill).filter(Skill.skill_id == skill_id).first()

    @staticmethod
    def get_system_skill_by_id(db: Session, skill_id: int, enabled_only: bool = False) -> Optional[Skill]:
        """Get a system skill by ID.

        Defaults to enabled_only=False so admin edit paths and the seeder see disabled skills;
        runtime resolution callers should pass enabled_only=True.
        """
        query = db.query(Skill).filter(
            Skill.skill_id == skill_id,
            Skill.app_id.is_(None)
        )
        if enabled_only:
            query = query.filter(Skill.is_enabled.is_(True))
        return query.first()

    @staticmethod
    def get_system_skill_by_name(db: Session, name: str, enabled_only: bool = False) -> Optional[Skill]:
        """Get a system skill by case-insensitive name.

        Defaults to enabled_only=False so the seeder and collision checks see disabled skills.
        """
        query = db.query(Skill).filter(
            func.lower(Skill.name) == name.strip().lower(),
            Skill.app_id.is_(None)
        )
        if enabled_only:
            query = query.filter(Skill.is_enabled.is_(True))
        return query.order_by(Skill.skill_id).first()

    @staticmethod
    def create(db: Session, skill: Skill) -> Skill:
        """Create a new skill"""
        db.add(skill)
        db.commit()
        db.refresh(skill)
        return skill

    @staticmethod
    def update(db: Session, skill: Skill) -> Skill:
        """Update an existing skill"""
        db.add(skill)
        db.commit()
        db.refresh(skill)
        return skill

    @staticmethod
    def delete(db: Session, skill: Skill) -> None:
        """Delete a skill"""
        db.query(AgentSkill).filter(AgentSkill.skill_id == skill.skill_id).delete(synchronize_session=False)
        SkillPackageRepository.delete_all_for_skill(db, skill.skill_id)
        db.delete(skill)
        db.commit()

    @staticmethod
    def delete_by_id_and_app_id(db: Session, skill_id: int, app_id: int) -> bool:
        """Delete a skill by ID and app ID"""
        skill = SkillRepository.get_by_id_and_app_id(db, skill_id, app_id)
        if skill:
            SkillRepository.delete(db, skill)
            return True
        return False

    @staticmethod
    def get_valid_skill_ids_for_app(db: Session, skill_ids: set, app_id: int) -> set:
        """Get skill IDs that exist and belong to the specified app
        
        Args:
            db: Database session
            skill_ids: Set of skill IDs to validate
            app_id: App ID to check ownership against
            
        Returns:
            Set of valid skill IDs that exist and belong to the app
        """
        if not skill_ids:
            return set()
        
        # Query to find skills that exist and belong to the app
        valid_skills = db.query(Skill.skill_id).filter(
            Skill.skill_id.in_(skill_ids),
            Skill.app_id == app_id
        ).all()
        
        return {skill.skill_id for skill in valid_skills}
