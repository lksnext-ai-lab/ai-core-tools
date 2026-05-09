from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import or_
from models.skill import Skill, SkillFile
from models.agent import AgentSkill


class SkillRepository:
    """Repository class for Skill database operations"""

    @staticmethod
    def get_all_by_app_id(db: Session, app_id: int) -> List[Skill]:
        """Get all skills visible to an app: owned skills + global builtins."""
        return db.query(Skill).filter(
            or_(Skill.app_id == app_id, Skill.app_id.is_(None))
        ).all()

    @staticmethod
    def get_by_id_and_app_id(db: Session, skill_id: int, app_id: int) -> Optional[Skill]:
        """Get a specific skill by ID; must belong to the app or be a builtin."""
        return db.query(Skill).filter(
            Skill.skill_id == skill_id,
            or_(Skill.app_id == app_id, Skill.app_id.is_(None)),
        ).first()

    @staticmethod
    def get_builtin_skills(db: Session) -> List[Skill]:
        """Get all globally available built-in skills (app_id=NULL, is_builtin=True)."""
        return db.query(Skill).filter(
            Skill.app_id.is_(None),
            Skill.is_builtin.is_(True),
        ).all()

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
        db.delete(skill)
        db.commit()

    @staticmethod
    def delete_by_id_and_app_id(db: Session, skill_id: int, app_id: int) -> bool:
        """Delete a skill by ID and app ID (builtins cannot be deleted via this method)."""
        skill = db.query(Skill).filter(
            Skill.skill_id == skill_id,
            Skill.app_id == app_id,  # Strict: only owned skills may be deleted
        ).first()
        if skill:
            SkillRepository.delete(db, skill)
            return True
        return False

    @staticmethod
    def get_valid_skill_ids_for_app(db: Session, skill_ids: set, app_id: int) -> set:
        """Get skill IDs that are visible to the app (owned or builtin).

        Args:
            db: Database session
            skill_ids: Set of skill IDs to validate
            app_id: App ID to check ownership against

        Returns:
            Set of valid skill IDs that the app can use
        """
        if not skill_ids:
            return set()

        valid_skills = db.query(Skill.skill_id).filter(
            Skill.skill_id.in_(skill_ids),
            or_(Skill.app_id == app_id, Skill.app_id.is_(None)),
        ).all()

        return {skill.skill_id for skill in valid_skills}

    @staticmethod
    def get_by_ids(db: Session, app_id: int, skill_ids: list[int]) -> List[Skill]:
        """Return Skill ORM objects for the given *skill_ids* visible to *app_id*.

        Only skills owned by the app or global builtins (app_id=NULL) are
        returned.  IDs that do not exist or are not visible are silently skipped.

        Args:
            db:        Database session.
            app_id:    App id used to filter owned/builtin skills.
            skill_ids: List of skill primary-key ids to load.

        Returns:
            List of matching :class:`~models.skill.Skill` instances with their
            ``files`` relationship eagerly available (lazy loads still work).
        """
        if not skill_ids:
            return []
        return db.query(Skill).filter(
            Skill.skill_id.in_(skill_ids),
            or_(Skill.app_id == app_id, Skill.app_id.is_(None)),
        ).all()

    # ------------------------------------------------------------------
    # SkillFile operations (IT-3)
    # ------------------------------------------------------------------

    @staticmethod
    def get_skill_files(db: Session, skill_id: int) -> List[SkillFile]:
        """Get all files for a skill."""
        return db.query(SkillFile).filter(SkillFile.skill_id == skill_id).all()

    @staticmethod
    def upsert_skill_file(
        db: Session,
        skill_id: int,
        path: str,
        media_type: Optional[str],
        content_text: Optional[str],
        content_bytes: Optional[bytes],
        checksum_sha256: Optional[str],
    ) -> SkillFile:
        """Create or update a SkillFile record identified by (skill_id, path)."""
        existing = db.query(SkillFile).filter(
            SkillFile.skill_id == skill_id,
            SkillFile.path == path,
        ).first()

        if existing:
            existing.media_type = media_type
            existing.content_text = content_text
            existing.content_bytes = content_bytes
            existing.checksum_sha256 = checksum_sha256
            db.add(existing)
            db.commit()
            db.refresh(existing)
            return existing

        sf = SkillFile(
            skill_id=skill_id,
            path=path,
            media_type=media_type,
            content_text=content_text,
            content_bytes=content_bytes,
            checksum_sha256=checksum_sha256,
        )
        db.add(sf)
        db.commit()
        db.refresh(sf)
        return sf

    @staticmethod
    def delete_skill_files(db: Session, skill_id: int) -> None:
        """Delete all SkillFile records for a skill."""
        db.query(SkillFile).filter(SkillFile.skill_id == skill_id).delete(
            synchronize_session=False
        )
        db.commit()

