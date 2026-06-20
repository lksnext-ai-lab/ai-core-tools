"""
Integration test: AgentExecutionEvent rows are cascade-deleted when their App
(and Agent) is deleted.

Verifies that the ON DELETE CASCADE FK constraint on agent_execution_event.app_id
(and agent_execution_event.agent_id) works correctly so that metric rows do not
become orphaned when apps or agents are removed.
"""
import uuid
import pytest
from datetime import datetime, timedelta
from sqlalchemy import text

from models.agent_execution_event import AgentExecutionEvent


# ── Helpers ────────────────────────────────────────────────────────────────


def _insert_events(db, app_id, agent_id, user_id, count=5):
    """Insert `count` AgentExecutionEvent rows for the given app/agent."""
    now = datetime.utcnow()
    for i in range(count):
        evt = AgentExecutionEvent(
            event_id=uuid.uuid4(),
            app_id=app_id,
            agent_id=agent_id,
            user_id=user_id,
            caller_type="INTERNAL_PLAYGROUND",
            parent_execution_id=None,
            started_at=now - timedelta(hours=i),
            finished_at=now - timedelta(hours=i) + timedelta(seconds=1),
            duration_ms=1000,
            status="SUCCESS",
        )
        db.add(evt)
    db.flush()


def _count_events(db, app_id):
    """Count AgentExecutionEvent rows for the given app_id."""
    result = db.execute(
        text("SELECT count(*) FROM agent_execution_event WHERE app_id = :app_id"),
        {"app_id": app_id},
    )
    return result.scalar()


# ── Tests ──────────────────────────────────────────────────────────────────


class TestAppDeleteCascadeMetrics:
    def test_cascade_on_agent_delete(self, db, fake_app, fake_agent, fake_user):
        """Deleting an Agent cascades to its AgentExecutionEvent rows."""
        _insert_events(db, fake_app.app_id, fake_agent.agent_id, fake_user.user_id, count=5)

        # Verify they were inserted
        assert _count_events(db, fake_app.app_id) == 5

        # Delete the agent directly — ON DELETE CASCADE should remove metrics rows
        db.delete(fake_agent)
        db.flush()

        assert _count_events(db, fake_app.app_id) == 0, \
            "Metrics rows must be cascade-deleted when the Agent is deleted"

    def test_cascade_on_app_delete(self, db, fake_app, fake_agent, fake_user):
        """Deleting an App cascades to its AgentExecutionEvent rows."""
        _insert_events(db, fake_app.app_id, fake_agent.agent_id, fake_user.user_id, count=5)

        assert _count_events(db, fake_app.app_id) == 5

        # Delete via AppService (which deletes agents first, then app)
        # Agents cascade metrics rows; the app deletion cascades any remaining ones.
        from services.app_service import AppService
        svc = AppService(db)
        result = svc.delete_app(fake_app.app_id)

        assert result is True, "AppService.delete_app should return True on success"
        assert _count_events(db, fake_app.app_id) == 0, \
            "Metrics rows must be gone after the App is deleted"
