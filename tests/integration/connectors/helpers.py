"""Helpers shared by the connectors integration tests."""

import time
from datetime import datetime, timedelta
from typing import Any

from db.database import SessionLocal
from models.output_delivery import OutputDelivery, OutputDeliveryAttempt
from sqlalchemy import text
from utils.clock import utcnow_naive


def fetch_delivery(delivery_id: int) -> dict[str, Any] | None:
    """Re-read a delivery (and its attempts) in a brand-new session."""
    with SessionLocal() as session:
        row = session.get(OutputDelivery, delivery_id)
        if row is None:
            return None
        data = {col.name: getattr(row, col.name) for col in OutputDelivery.__table__.columns}
        data["attempts"] = [
            {col.name: getattr(attempt, col.name) for col in OutputDeliveryAttempt.__table__.columns}
            for attempt in row.attempts
        ]
        return data


def past(seconds: int = 3600) -> datetime:
    return utcnow_naive() - timedelta(seconds=seconds)


def future(seconds: int = 3600) -> datetime:
    return utcnow_naive() + timedelta(seconds=seconds)


def wait_for_lock_waiter(timeout: float = 5.0) -> bool:
    """Poll until another backend of this database is WAITING on a lock.

    Raw SQL on purpose: pg_locks/pg_stat_activity are catalog views with no ORM model.
    """
    deadline = time.monotonic() + timeout
    with SessionLocal() as session:
        while time.monotonic() < deadline:
            waiting = session.execute(text(
                "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                "WHERE NOT l.granted AND a.datname = current_database() AND l.pid <> pg_backend_pid()"
            )).scalar_one()
            session.rollback()
            if waiting:
                return True
            time.sleep(0.05)
    return False
