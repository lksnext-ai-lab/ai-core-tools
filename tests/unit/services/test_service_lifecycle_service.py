from unittest.mock import MagicMock

import pytest

from services.service_lifecycle_service import ServiceLifecycleService
from services.system_settings_service import SystemSettingsService

ENV_VAR = "AICT_SYSTEM_SERVICE_END_OF_SERVICE_WARNING_DAYS"


@pytest.fixture(autouse=True)
def _fresh_defaults(monkeypatch):
    monkeypatch.setattr(SystemSettingsService, "_defaults_cache", None)
    monkeypatch.delenv(ENV_VAR, raising=False)


def _db_without_row():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


def test_default_comes_from_yaml():
    assert ServiceLifecycleService.warning_days(_db_without_row()) == 30


def test_env_overrides(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "7")
    assert ServiceLifecycleService.warning_days(_db_without_row()) == 7


def test_negative_is_clamped(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "-3")
    assert ServiceLifecycleService.warning_days(_db_without_row()) == 0


def test_error_falls_back_to_30():
    db = MagicMock()
    db.query.side_effect = RuntimeError("db down")
    assert ServiceLifecycleService.warning_days(db) == 30
