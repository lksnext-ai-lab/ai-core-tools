from typing import List, Optional, Tuple
from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, aliased, defer, load_only
from models.skill import Skill
from models.agent import Agent, AgentSkill
from repositories.skill_package_repository import SkillPackageRepository
from utils.logger import get_logger
from utils.skill_names import fold_name

logger = get_logger(__name__)

# Namespace (first int4 key) of the per-app skill advisory lock: 'SKIL'.
_SKILL_LOCK_NAMESPACE = 0x534B494C

# Heavy Skill columns that list/picker views never render.
_LIST_DEFERRED = (Skill.content, Skill.frontmatter, Skill.runtime_options, Skill.allowed_tools)

# fold_name is re-exported here (moved to utils.skill_names) so existing
# `from repositories.skill_repository import fold_name` imports keep working.
__all__ = ["SkillRepository", "fold_name"]


def _fold_col(column):
    """SQL-side name folding used for name-collision rules: lower(trim(name)) with whitespace runs -> '-'."""
    return func.regexp_replace(func.lower(func.trim(column)), r'\s+', '-', 'g')


class SkillRepository:
    """Repository class for Skill database operations"""

    @staticmethod
    def get_all_by_app_id(db: Session, app_id: int) -> List[Skill]:
        """Get all skills for a specific app"""
        if app_id is None:
            raise ValueError("app_id is required")
        return db.query(Skill).filter(Skill.app_id == app_id).all()

    @staticmethod
    def lock_app_skills(db: Session, app_id: int) -> None:
        """Serialise skill creation/rename for one app with a transaction-scoped advisory lock.

        Must be called BEFORE the duplicate-name and quota checks; released automatically at commit/rollback.
        """
        db.execute(select(func.pg_advisory_xact_lock(_SKILL_LOCK_NAMESPACE, app_id)))

    @staticmethod
    def list_for_app(db: Session, app_id: int) -> List[Skill]:
        """List an app's skills for listing views: heavy columns deferred, ordered by name"""
        if app_id is None:
            raise ValueError("app_id is required")
        return (
            db.query(Skill)
            .options(*[defer(c) for c in _LIST_DEFERRED])
            .filter(Skill.app_id == app_id)
            .order_by(Skill.name, Skill.skill_id)
            .all()
        )

    @staticmethod
    def get_selectable_for_app(db: Session, app_id: int, agent_id: Optional[int] = None) -> List[Skill]:
        """Skills an agent form of the app may pick from.

        Own app skills (any enabled state) plus ENABLED system skills whose folded name does not collide with an
        app skill (the app skill wins). When ``agent_id`` is given, system skills already attached to that agent
        stay listed even if disabled or colliding, so the form can flag them (is_enabled=False).
        """
        if app_id is None:
            raise ValueError("app_id is required")
        app_skill = aliased(Skill)
        collides = exists().where(
            app_skill.app_id == app_id,
            _fold_col(app_skill.name) == _fold_col(Skill.name),
        )
        conditions = [
            Skill.app_id == app_id,
            and_(Skill.app_id.is_(None), Skill.is_enabled.is_(True), ~collides),
        ]
        if agent_id:
            attached = select(AgentSkill.skill_id).where(AgentSkill.agent_id == agent_id)
            conditions.append(and_(Skill.app_id.is_(None), Skill.skill_id.in_(attached)))
        return (
            db.query(Skill)
            .options(load_only(Skill.skill_id, Skill.name, Skill.description, Skill.app_id, Skill.is_enabled))
            .filter(or_(*conditions))
            .order_by(Skill.app_id.is_(None), Skill.name, Skill.skill_id)
            .all()
        )

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
    def get_system_skills(db: Session, enabled_only: bool = True, light: bool = False) -> List[Skill]:
        """Get system (platform) skills, optionally only the enabled ones.

        ``light=True`` defers the heavy columns (content, frontmatter, ...) for listing views.
        """
        query = db.query(Skill).filter(Skill.app_id.is_(None))
        if light:
            query = query.options(*[defer(c) for c in _LIST_DEFERRED])
        if enabled_only:
            query = query.filter(Skill.is_enabled.is_(True))
        return query.order_by(Skill.name, Skill.skill_id).all()

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
    def get_by_name_and_app_id(db: Session, name: str, app_id: int) -> Optional[Skill]:
        """Get an app skill by case-insensitive name (used for duplicate checks)"""
        if app_id is None:
            raise ValueError("app_id is required")
        return db.query(Skill).filter(
            _fold_col(Skill.name) == fold_name(name),
            Skill.app_id == app_id
        ).order_by(Skill.skill_id).first()

    @staticmethod
    def persist(db: Session, skill: Skill) -> Skill:
        """Add a skill and flush WITHOUT committing (caller owns the transaction, e.g. atomic import)"""
        db.add(skill)
        db.flush()
        return skill

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
        """Delete a skill (unscoped: callers must have authorised it and checked source/frozen state).

        Raises:
            RuntimeError: If the database refuses the delete; the session is rolled back first. Plain
                (not a typed SkillServiceError — the data layer never makes HTTP-status decisions; the
                caller in SkillService must catch this and translate it to SkillConflictError).
        """
        skill_id = skill.skill_id
        try:
            db.query(AgentSkill).filter(AgentSkill.skill_id == skill_id).delete(synchronize_session=False)
            SkillPackageRepository.delete_all_for_skill(db, skill_id)
            db.delete(skill)
            db.commit()
        except (IntegrityError, AssertionError, SQLAlchemyError) as exc:
            db.rollback()
            logger.error("Could not delete skill %s: %s", skill_id, type(exc).__name__)
            raise RuntimeError("skill is in use; retry") from None

    @staticmethod
    def set_enabled_for_app(db: Session, skill_id: int, app_id: int, enabled: bool) -> int:
        """Atomically set is_enabled on an app-owned skill and commit. Returns the matched row count."""
        if app_id is None:
            raise ValueError("app_id is required")
        result = db.execute(
            update(Skill).where(Skill.skill_id == skill_id, Skill.app_id == app_id).values(is_enabled=bool(enabled)),
            execution_options={'synchronize_session': 'fetch'},
        )
        db.commit()
        return result.rowcount or 0

    @staticmethod
    def set_enabled_system(db: Session, skill_id: int, enabled: bool) -> int:
        """Atomically set is_enabled on a system skill and commit. Returns the matched row count."""
        result = db.execute(
            update(Skill).where(Skill.skill_id == skill_id, Skill.app_id.is_(None)).values(is_enabled=bool(enabled)),
            execution_options={'synchronize_session': 'fetch'},
        )
        db.commit()
        return result.rowcount or 0

    @staticmethod
    def get_attachment_stats(db: Session, skill_id: int) -> Tuple[int, List[int]]:
        """Return ``(number of agents using the skill, sorted distinct app ids of those agents)``."""
        rows = (
            db.query(AgentSkill.agent_id, Agent.app_id)
            .join(Agent, Agent.agent_id == AgentSkill.agent_id)
            .filter(AgentSkill.skill_id == skill_id)
            .all()
        )
        return len(rows), sorted({r.app_id for r in rows if r.app_id is not None})

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
        """Get skill IDs that may be NEWLY attached to an agent of the given app

        Accepts the app's own skills (any enabled state) and enabled system skills whose name does not collide
        with one of the app's skills (the app skill wins).

        Args:
            db: Database session
            skill_ids: Set of skill IDs to validate
            app_id: App ID of the agent (must not be None)

        Returns:
            Set of valid skill IDs

        Raises:
            ValueError: If app_id is None (would otherwise match system skills as if they were app skills)
        """
        if app_id is None:
            raise ValueError("app_id is required")
        if not skill_ids:
            return set()

        app_skill = aliased(Skill)
        collides = exists().where(
            app_skill.app_id == app_id,
            _fold_col(app_skill.name) == _fold_col(Skill.name),
        )
        valid_skills = db.query(Skill.skill_id).filter(
            Skill.skill_id.in_(skill_ids),
            or_(
                Skill.app_id == app_id,
                and_(Skill.app_id.is_(None), Skill.is_enabled.is_(True), ~collides),
            )
        ).all()

        return {skill.skill_id for skill in valid_skills}

    @staticmethod
    def get_visible_skill_ids_for_app(db: Session, skill_ids: set, app_id: int) -> set:
        """Get skill IDs visible to the app: own skills and system skills, regardless of enabled state

        Used to KEEP existing agent associations whose skill has since been disabled.

        Raises:
            ValueError: If app_id is None
        """
        if app_id is None:
            raise ValueError("app_id is required")
        if not skill_ids:
            return set()

        rows = db.query(Skill.skill_id).filter(
            Skill.skill_id.in_(skill_ids),
            or_(Skill.app_id == app_id, Skill.app_id.is_(None))
        ).all()

        return {row.skill_id for row in rows}
