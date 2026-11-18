"""Unit tests for AppRepository.get_slug_by_id (step_009 review fix item 2).

Uses an in-memory SQLite database (same pattern as
test_sandbox_service_repository.py) so no real PostgreSQL connection is
required. Verifies the slug-only projection matches ``get_by_id(...).slug``
without loading the full App row, and handles a missing app / null slug.
"""

from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-minimum-ok")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.database import Base
from models.app import App
from repositories.app_repository import AppRepository

_SQLITE_URL = "sqlite:///:memory:"


@pytest.fixture
def engine():
    eng = create_engine(_SQLITE_URL, connect_args={"check_same_thread": False})
    import models  # noqa: F401 — registers all ORM models with Base.metadata

    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture
def db(engine):
    """Per-test session with rollback isolation (no FOR UPDATE needed on SQLite)."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=True)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


class TestGetSlugById:
    def test_returns_slug_for_existing_app(self, db):
        app = App(name="Test App", slug="test-app-slug")
        db.add(app)
        db.flush()

        assert AppRepository(db).get_slug_by_id(app.app_id) == "test-app-slug"

    def test_returns_none_for_missing_app(self, db):
        assert AppRepository(db).get_slug_by_id(999999) is None

    def test_returns_none_when_app_has_no_slug(self, db):
        app = App(name="No Slug App", slug=None)
        db.add(app)
        db.flush()

        assert AppRepository(db).get_slug_by_id(app.app_id) is None

    def test_matches_get_by_id_slug(self, db):
        app = App(name="Another App", slug="another-slug")
        db.add(app)
        db.flush()

        repo = AppRepository(db)
        assert repo.get_slug_by_id(app.app_id) == repo.get_by_id(app.app_id).slug
