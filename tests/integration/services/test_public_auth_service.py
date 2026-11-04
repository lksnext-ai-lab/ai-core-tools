"""Integration coverage for `services.public_auth_service.PublicAuthService` on the
real test DB (review round 2, MEDIUM-1): inactive key, key of another app,
deactivated owner, and a valid key through both the raising and non-raising
entry points, which must share one predicate (`_lookup_active_key`).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException

from models.api_key import APIKey
from services.public_auth_service import PublicAuthService


@pytest.fixture
def other_app(db, fake_user):
    from models.app import App

    app_obj = App(name="Other Workspace", slug="other-workspace-fixture", owner_id=fake_user.user_id)
    db.add(app_obj)
    db.flush()
    return app_obj


@pytest.fixture
def other_app_api_key(db, other_app, fake_user):
    key = APIKey(
        key="other-app-api-key-for-integration-tests",  # pragma: allowlist secret
        name="Other App Key",
        app_id=other_app.app_id,
        user_id=fake_user.user_id,
        is_active=True,
        created_at=datetime.now(),
    )
    db.add(key)
    db.flush()
    return key


class TestFindValidKeyForAppRealDb:
    def test_inactive_key_returns_none(self, db, fake_app, fake_api_key):
        fake_api_key.is_active = False
        db.flush()
        service = PublicAuthService()

        assert service.find_valid_key_for_app(db, fake_app.app_id, fake_api_key.key) is None

    def test_key_of_another_app_returns_none(self, db, fake_app, other_app_api_key):
        service = PublicAuthService()

        assert service.find_valid_key_for_app(db, fake_app.app_id, other_app_api_key.key) is None

    def test_deactivated_owner_returns_none(self, db, fake_app, fake_api_key, fake_user):
        fake_user.is_active = False
        db.flush()
        service = PublicAuthService()

        assert service.find_valid_key_for_app(db, fake_app.app_id, fake_api_key.key) is None

    def test_valid_key_returns_the_row_without_touching_last_used_at(self, db, fake_app, fake_api_key):
        assert fake_api_key.last_used_at is None
        service = PublicAuthService()

        result = service.find_valid_key_for_app(db, fake_app.app_id, fake_api_key.key)

        assert result is not None
        assert result.key_id == fake_api_key.key_id
        db.refresh(fake_api_key)
        assert fake_api_key.last_used_at is None


class TestValidateApiKeyForAppRealDbUnchanged:
    """`validate_api_key_for_app`'s existing raising behaviour must be unaffected
    by factoring `_fetch_active_key`/`_owner_is_active` out of it."""

    def test_inactive_key_raises_401(self, db, fake_app, fake_api_key):
        fake_api_key.is_active = False
        db.flush()
        service = PublicAuthService()

        with pytest.raises(HTTPException) as exc_info:
            service.validate_api_key_for_app(db, fake_app.app_id, fake_api_key.key)
        assert exc_info.value.status_code == 401

    def test_deactivated_owner_raises_403(self, db, fake_app, fake_api_key, fake_user):
        fake_user.is_active = False
        db.flush()
        service = PublicAuthService()

        with pytest.raises(HTTPException) as exc_info:
            service.validate_api_key_for_app(db, fake_app.app_id, fake_api_key.key)
        assert exc_info.value.status_code == 403

    def test_valid_key_updates_last_used_at_and_returns_row(self, db, fake_app, fake_api_key):
        service = PublicAuthService()

        result = service.validate_api_key_for_app(db, fake_app.app_id, fake_api_key.key)

        assert result.key_id == fake_api_key.key_id
        db.refresh(fake_api_key)
        assert fake_api_key.last_used_at is not None
