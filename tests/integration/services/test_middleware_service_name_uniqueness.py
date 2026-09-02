"""Integration tests for Middleware name uniqueness, scoped per App."""
import pytest

from schemas.middleware_schemas import CreateUpdateMiddlewareSchema
from services.middleware_service import MiddlewareService

pytestmark = pytest.mark.integration


def _schema(name: str) -> CreateUpdateMiddlewareSchema:
    return CreateUpdateMiddlewareSchema(
        name=name,
        description="",
        middleware_type="monitoring",
        config=None,
        mcp_config_ids=[],
    )


class TestMiddlewareNameUniqueness:
    def test_creating_duplicate_name_in_same_app_is_rejected(self, db, fake_app):
        MiddlewareService.create_or_update_middleware(db, fake_app.app_id, 0, _schema("Test Monitoring"))

        with pytest.raises(ValueError, match="already exists"):
            MiddlewareService.create_or_update_middleware(db, fake_app.app_id, 0, _schema("Test Monitoring"))

    def test_renaming_to_another_middlewares_existing_name_is_rejected(self, db, fake_app):
        MiddlewareService.create_or_update_middleware(db, fake_app.app_id, 0, _schema("Alpha"))
        second = MiddlewareService.create_or_update_middleware(db, fake_app.app_id, 0, _schema("Beta"))

        with pytest.raises(ValueError, match="already exists"):
            MiddlewareService.create_or_update_middleware(
                db, fake_app.app_id, second.middleware_id, _schema("Alpha")
            )

    def test_renaming_middleware_to_its_own_current_name_is_allowed(self, db, fake_app):
        mw = MiddlewareService.create_or_update_middleware(db, fake_app.app_id, 0, _schema("Gamma"))

        result = MiddlewareService.create_or_update_middleware(
            db, fake_app.app_id, mw.middleware_id, _schema("Gamma")
        )

        assert result is not None
        assert result.name == "Gamma"
