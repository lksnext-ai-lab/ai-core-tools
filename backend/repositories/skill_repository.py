from typing import Optional, List
from sqlalchemy.orm import Session
from models.skill import Skill


class SkillRepository:
    """Repository class for Skill database operations"""

    @staticmethod
    def get_all_by_app_id(db: Session, app_id: int) -> List[Skill]:
        """Get all skills for a specific app"""
        return db.query(Skill).filter(Skill.app_id == app_id).all()

    @staticmethod
    def get_by_id_and_app_id(db: Session, skill_id: int, app_id: int) -> Optional[Skill]:
        """Get a specific skill by ID and app ID"""
        return db.query(Skill).filter(
            Skill.skill_id == skill_id,
            Skill.app_id == app_id
        ).first()

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
