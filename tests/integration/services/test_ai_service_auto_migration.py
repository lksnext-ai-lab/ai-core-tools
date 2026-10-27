"""Automatic main-model migration for App AI services."""

from datetime import datetime, timedelta, timezone

import pytest

from models.ai_service import AIService
from services.ai_service_auto_migration_service import AIServiceAutoMigrationService
from services.ai_service_service import AIServiceMigrationTargetError, AIServiceService
from services.service_lifecycle_service import ServiceLifecycleService
from utils.error_handlers import ValidationError as AppValidationError

pytestmark = pytest.mark.integration


def test_due_ai_service_migration_moves_agents_and_clears_schedule(
    db, fake_app, fake_ai_service, fake_agent
):
    now = datetime.now(timezone.utc)
    target = AIService(
        name="migration-target",
        provider="OpenAI",
        api_key="test-key",  # pragma: allowlist secret
        app_id=fake_app.app_id,
    )
    db.add(target)
    db.flush()

    fake_ai_service.end_of_service_at = now - timedelta(minutes=1)
    fake_ai_service.auto_move_to_service_id = target.service_id
    db.flush()

    processed = AIServiceAutoMigrationService.process_due_migrations(db, now=now)

    db.refresh(fake_ai_service)
    db.refresh(fake_agent)
    assert processed == 1
    assert fake_agent.service_id == target.service_id
    assert fake_ai_service.auto_move_to_service_id is None


def test_future_ai_service_migration_is_not_applied(db, fake_ai_service, fake_agent):
    now = datetime.now(timezone.utc)
    target = AIService(
        name="future-migration-target",
        provider="OpenAI",
        api_key="test-key",  # pragma: allowlist secret
        app_id=fake_ai_service.app_id,
    )
    db.add(target)
    db.flush()
    fake_ai_service.end_of_service_at = now + timedelta(days=1)
    fake_ai_service.auto_move_to_service_id = target.service_id
    db.flush()

    processed = AIServiceAutoMigrationService.process_due_migrations(db, now=now)

    db.refresh(fake_ai_service)
    db.refresh(fake_agent)
    assert processed == 0
    assert fake_agent.service_id == fake_ai_service.service_id
    assert fake_ai_service.auto_move_to_service_id == target.service_id


def test_due_ai_service_keeps_schedule_when_target_is_already_retired(
    db, fake_app, fake_ai_service, fake_agent
):
    now = datetime.now(timezone.utc)
    target = AIService(
        name="retired-migration-target",
        provider="OpenAI",
        api_key="test-key",  # pragma: allowlist secret
        app_id=fake_app.app_id,
        end_of_service_at=now - timedelta(days=2),
    )
    db.add(target)
    db.flush()
    fake_ai_service.end_of_service_at = now - timedelta(days=1)
    fake_ai_service.auto_move_to_service_id = target.service_id
    db.flush()

    processed = AIServiceAutoMigrationService.process_due_migrations(db, now=now)

    db.refresh(fake_ai_service)
    db.refresh(fake_agent)
    assert processed == 0
    assert fake_agent.service_id == fake_ai_service.service_id
    assert fake_ai_service.auto_move_to_service_id == target.service_id


def test_scheduled_migration_target_cannot_be_deleted(db, fake_app, fake_ai_service):
    target = AIService(
        name="protected-migration-target",
        provider="OpenAI",
        api_key="test-key",  # pragma: allowlist secret
        app_id=fake_app.app_id,
    )
    db.add(target)
    db.flush()
    fake_ai_service.end_of_service_at = datetime.now(timezone.utc) + timedelta(days=1)
    fake_ai_service.auto_move_to_service_id = target.service_id
    db.flush()

    with pytest.raises(AIServiceMigrationTargetError):
        AIServiceService.ensure_not_auto_migration_target(db, target.service_id)


def test_migration_target_must_outlive_source_service(db, fake_app):
    now = datetime.now(timezone.utc)
    target = AIService(
        name="short-lived-target",
        provider="OpenAI",
        api_key="test-key",  # pragma: allowlist secret
        app_id=fake_app.app_id,
        end_of_service_at=now + timedelta(days=1),
    )
    db.add(target)
    db.flush()

    with pytest.raises(AppValidationError, match="remain active"):
        ServiceLifecycleService.validate_auto_move_target(
            db,
            fake_app.app_id,
            source_service_id=None,
            end_of_service_at=now + timedelta(days=2),
            target_service_id=target.service_id,
            now=now,
        )


def test_migration_target_cannot_be_retired_while_migrations_are_pending(
    db, fake_app, fake_ai_service
):
    now = datetime.now(timezone.utc)
    target = AIService(
        name="pending-migration-target",
        provider="OpenAI",
        api_key="test-key",  # pragma: allowlist secret
        app_id=fake_app.app_id,
    )
    db.add(target)
    db.flush()
    fake_ai_service.end_of_service_at = now + timedelta(days=1)
    fake_ai_service.auto_move_to_service_id = target.service_id
    db.flush()

    with pytest.raises(AppValidationError, match="destination of scheduled migrations"):
        ServiceLifecycleService.validate_auto_move_dependents(
            db, target.service_id, now - timedelta(minutes=1)
        )
