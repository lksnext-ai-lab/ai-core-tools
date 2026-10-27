"""Apply scheduled migrations from ended AI services to their configured targets."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.ai_service import AIService
from repositories.service_usage_repository import ServiceUsageQueries
from services.service_lifecycle_service import ServiceLifecycleService
from utils.error_handlers import ValidationError as AppValidationError
from utils.logger import get_logger
from utils.service_lifecycle import to_utc

logger = get_logger(__name__)


class AIServiceAutoMigrationService:
    @staticmethod
    def process_due_migrations(db: Session, now: Optional[datetime] = None) -> int:
        """Move each due App's main-model references once, in the same transaction as clearing its schedule."""
        current = to_utc(now) or datetime.now(timezone.utc)
        due_service_ids = db.execute(
            select(AIService.service_id)
            .where(
                AIService.app_id.is_not(None),
                AIService.auto_move_to_service_id.is_not(None),
                AIService.end_of_service_at <= current,
            )
            .order_by(AIService.service_id)
        ).scalars().all()

        migrated_count = 0
        for service_id in due_service_ids:
            try:
                source = db.execute(
                    select(AIService)
                    .where(AIService.service_id == service_id)
                    .with_for_update(skip_locked=True)
                ).scalar_one_or_none()
                if (
                    source is None
                    or source.app_id is None
                    or source.auto_move_to_service_id is None
                    or to_utc(source.end_of_service_at) is None
                    or to_utc(source.end_of_service_at) > current
                ):
                    db.rollback()
                    continue

                target_service_id = source.auto_move_to_service_id
                try:
                    ServiceLifecycleService.validate_auto_move_target(
                        db,
                        source.app_id,
                        source.service_id,
                        source.end_of_service_at,
                        target_service_id,
                        now=current,
                    )
                except AppValidationError as exc:
                    logger.error(
                        "ai_service_auto_migration: service_id=%s target_service_id=%s cannot be applied: %s",
                        source.service_id,
                        target_service_id,
                        exc.message,
                    )
                    db.rollback()
                    continue

                moved_agent_ids = ServiceUsageQueries.move_agents(
                    db, source.app_id, source.service_id, target_service_id
                )
                source.auto_move_to_service_id = None
                db.commit()
                migrated_count += 1
                logger.info(
                    "ai_service_auto_migration: app_id=%s source_service_id=%s target_service_id=%s "
                    "agents_moved=%s",
                    source.app_id,
                    source.service_id,
                    target_service_id,
                    len(moved_agent_ids),
                )
            except Exception:
                db.rollback()
                logger.exception(
                    "ai_service_auto_migration: failed to process service_id=%s",
                    service_id,
                )
        return migrated_count
