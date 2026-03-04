"""
Unit tests for APIKeyService.

The repository is mocked (pytest-mock), so no database is needed.
Tests focus on:
  - Key generation (format, uniqueness, length)
  - Service business logic (CRUD operations, toggle)
  - Edge cases (missing key, wrong app, inactive states)
"""

import pytest
import string
from datetime import datetime
from unittest.mock import MagicMock

from services.api_key_service import APIKeyService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_key_record(
    key_id=1,
    app_id=10,
    user_id=5,
    name="My Key",
    is_active=True,
    key="abcdefgh12345678",  # pragma: allowlist secret
):
    """Build a mock APIKey ORM object."""
    record = MagicMock()
    record.key_id = key_id
    record.app_id = app_id
    record.user_id = user_id
    record.name = name
    record.is_active = is_active
    record.key = key
    record.created_at = datetime(2024, 1, 1, 12, 0, 0)
    record.last_used_at = None
    return record


# ---------------------------------------------------------------------------
# generate_api_key (static method — no DB)
# ---------------------------------------------------------------------------


class TestGenerateApiKey:
    VALID_CHARS = set(string.ascii_letters + string.digits)

    def test_default_length_is_32(self):
        key = APIKeyService.generate_api_key()
        assert len(key) == 32

    def test_custom_length(self):
        key = APIKeyService.generate_api_key(length=64)
        assert len(key) == 64

    def test_only_alphanumeric_characters(self):
        key = APIKeyService.generate_api_key(length=100)
        assert all(c in self.VALID_CHARS for c in key)

    def test_keys_are_unique(self):
        keys = {APIKeyService.generate_api_key() for _ in range(50)}
        # With 32 chars of alphanumeric there should be no collision in 50 runs
        assert len(keys) == 50

    def test_minimum_length_one(self):
        key = APIKeyService.generate_api_key(length=1)
        assert len(key) == 1
        assert key in self.VALID_CHARS


# ---------------------------------------------------------------------------
# get_api_keys_list
# ---------------------------------------------------------------------------


class TestGetApiKeysList:
    def test_returns_list_items_for_each_key(self, mocker):
        repo = mocker.MagicMock()
        repo.get_by_app_id.return_value = [
            make_key_record(key_id=1, name="Key A"),
            make_key_record(key_id=2, name="Key B"),
        ]
        svc = APIKeyService(api_key_repository=repo)
        result = svc.get_api_keys_list(db=MagicMock(), app_id=10)
        assert len(result) == 2
        assert result[0].name == "Key A"
        assert result[1].name == "Key B"

    def test_key_preview_shows_first_8_chars(self, mocker):
        repo = mocker.MagicMock()
        repo.get_by_app_id.return_value = [make_key_record(key="abcdefgh12345678")]
        svc = APIKeyService(api_key_repository=repo)
        result = svc.get_api_keys_list(db=MagicMock(), app_id=10)
        assert result[0].key_preview == "abcdefgh..."

    def test_empty_list_when_no_keys(self, mocker):
        repo = mocker.MagicMock()
        repo.get_by_app_id.return_value = []
        svc = APIKeyService(api_key_repository=repo)
        result = svc.get_api_keys_list(db=MagicMock(), app_id=10)
        assert result == []


# ---------------------------------------------------------------------------
# get_api_key_detail
# ---------------------------------------------------------------------------


class TestGetApiKeyDetail:
    def test_key_id_zero_returns_empty_form(self, mocker):
        svc = APIKeyService(api_key_repository=mocker.MagicMock())
        result = svc.get_api_key_detail(db=MagicMock(), app_id=10, key_id=0)
        assert result is not None
        assert result.key_id == 0
        assert result.key_preview == "Will be generated on save"

    def test_returns_none_when_not_found(self, mocker):
        repo = mocker.MagicMock()
        repo.get_by_id_and_app.return_value = None
        svc = APIKeyService(api_key_repository=repo)
        result = svc.get_api_key_detail(db=MagicMock(), app_id=10, key_id=99)
        assert result is None

    def test_returns_detail_when_found(self, mocker):
        repo = mocker.MagicMock()
        repo.get_by_id_and_app.return_value = make_key_record(key_id=5, name="My Key")
        svc = APIKeyService(api_key_repository=repo)
        result = svc.get_api_key_detail(db=MagicMock(), app_id=10, key_id=5)
        assert result is not None
        assert result.key_id == 5
        assert result.name == "My Key"


# ---------------------------------------------------------------------------
# create_api_key
# ---------------------------------------------------------------------------


class TestCreateApiKey:
    def test_creates_key_with_correct_attributes(self, mocker):
        repo = mocker.MagicMock()
        created = make_key_record(key_id=1, name="New Key", key="generatedkey123456")
        repo.create.return_value = created

        svc = APIKeyService(api_key_repository=repo)
        result = svc.create_api_key(
            db=MagicMock(), app_id=10, user_id=5, name="New Key"
        )

        assert result.key_value == "generatedkey123456"
        assert result.name == "New Key"
        assert "won't be shown again" in result.message

    def test_key_value_is_returned_once_on_creation(self, mocker):
        repo = mocker.MagicMock()
        repo.create.return_value = make_key_record(key="secretkey1234567")

        svc = APIKeyService(api_key_repository=repo)
        result = svc.create_api_key(
            db=MagicMock(), app_id=10, user_id=5, name="Key"
        )
        assert result.key_value == "secretkey1234567"

    def test_repository_create_is_called_once(self, mocker):
        repo = mocker.MagicMock()
        repo.create.return_value = make_key_record()

        svc = APIKeyService(api_key_repository=repo)
        svc.create_api_key(db=MagicMock(), app_id=10, user_id=5, name="Key")

        repo.create.assert_called_once()

    def test_generated_key_is_alphanumeric_32_chars(self, mocker):
        """The service generates a key and passes it to the repo — verify format."""
        captured = {}

        def capture_create(db, api_key_obj):
            captured["key"] = api_key_obj.key
            return api_key_obj

        repo = mocker.MagicMock()
        repo.create.side_effect = capture_create

        svc = APIKeyService(api_key_repository=repo)
        svc.create_api_key(db=MagicMock(), app_id=10, user_id=5, name="Key")

        assert len(captured["key"]) == 32
        valid_chars = set(string.ascii_letters + string.digits)
        assert all(c in valid_chars for c in captured["key"])


# ---------------------------------------------------------------------------
# update_api_key
# ---------------------------------------------------------------------------


class TestUpdateApiKey:
    def test_returns_none_when_key_not_found(self, mocker):
        repo = mocker.MagicMock()
        repo.get_by_id_and_app.return_value = None
        svc = APIKeyService(api_key_repository=repo)
        result = svc.update_api_key(
            db=MagicMock(), app_id=10, key_id=99, name="X", is_active=True
        )
        assert result is None

    def test_updates_name_and_active_status(self, mocker):
        existing = make_key_record(key_id=1, name="Old Name", is_active=True)
        repo = mocker.MagicMock()
        repo.get_by_id_and_app.return_value = existing
        repo.update.return_value = existing

        svc = APIKeyService(api_key_repository=repo)
        svc.update_api_key(
            db=MagicMock(), app_id=10, key_id=1, name="New Name", is_active=False
        )

        assert existing.name == "New Name"
        assert existing.is_active is False

    def test_key_value_is_none_on_update(self, mocker):
        existing = make_key_record()
        repo = mocker.MagicMock()
        repo.get_by_id_and_app.return_value = existing
        repo.update.return_value = existing

        svc = APIKeyService(api_key_repository=repo)
        result = svc.update_api_key(
            db=MagicMock(), app_id=10, key_id=1, name="X", is_active=True
        )
        assert result.key_value is None


# ---------------------------------------------------------------------------
# delete_api_key
# ---------------------------------------------------------------------------


class TestDeleteApiKey:
    def test_returns_false_when_not_found(self, mocker):
        repo = mocker.MagicMock()
        repo.get_by_id_and_app.return_value = None
        svc = APIKeyService(api_key_repository=repo)
        assert svc.delete_api_key(db=MagicMock(), app_id=10, key_id=99) is False

    def test_returns_true_when_deleted(self, mocker):
        repo = mocker.MagicMock()
        repo.get_by_id_and_app.return_value = make_key_record()
        svc = APIKeyService(api_key_repository=repo)
        assert svc.delete_api_key(db=MagicMock(), app_id=10, key_id=1) is True

    def test_repository_delete_called_with_correct_object(self, mocker):
        record = make_key_record()
        repo = mocker.MagicMock()
        repo.get_by_id_and_app.return_value = record
        svc = APIKeyService(api_key_repository=repo)
        svc.delete_api_key(db=MagicMock(), app_id=10, key_id=1)
        repo.delete.assert_called_once_with(mocker.ANY, record)


# ---------------------------------------------------------------------------
# toggle_api_key
# ---------------------------------------------------------------------------


class TestToggleApiKey:
    def test_returns_none_when_not_found(self, mocker):
        repo = mocker.MagicMock()
        repo.get_by_id_and_app.return_value = None
        svc = APIKeyService(api_key_repository=repo)
        assert svc.toggle_api_key(db=MagicMock(), app_id=10, key_id=99) is None

    def test_activates_inactive_key(self, mocker):
        record = make_key_record(is_active=False)
        repo = mocker.MagicMock()
        repo.get_by_id_and_app.return_value = record
        svc = APIKeyService(api_key_repository=repo)
        result = svc.toggle_api_key(db=MagicMock(), app_id=10, key_id=1)
        assert record.is_active is True
        assert "activated" in result

    def test_deactivates_active_key(self, mocker):
        record = make_key_record(is_active=True)
        repo = mocker.MagicMock()
        repo.get_by_id_and_app.return_value = record
        svc = APIKeyService(api_key_repository=repo)
        result = svc.toggle_api_key(db=MagicMock(), app_id=10, key_id=1)
        assert record.is_active is False
        assert "deactivated" in result
