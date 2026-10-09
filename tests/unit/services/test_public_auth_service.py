from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status

from services.public_auth_service import PublicAuthService


def make_api_key_record(*, key_id: int = 1, owner_active: bool = True):
    owner = MagicMock()
    owner.is_active = owner_active

    app = MagicMock()
    app.owner = owner

    api_key_obj = MagicMock()
    api_key_obj.key_id = key_id
    api_key_obj.app = app
    return api_key_obj


class TestValidateApiKeyForApp:
    def test_raises_401_when_api_key_is_invalid(self, mocker):
        repo = mocker.MagicMock()
        repo.get_active_by_app_and_key.return_value = None
        service = PublicAuthService(api_key_repository=repo)

        with pytest.raises(HTTPException) as exc_info:
            service.validate_api_key_for_app(db=MagicMock(), app_id=10, api_key="invalid")

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Invalid or inactive API key for this app"
        repo.update_last_used_at.assert_not_called()

    def test_raises_403_when_owner_is_deactivated(self, mocker):
        repo = mocker.MagicMock()
        repo.get_active_by_app_and_key.return_value = make_api_key_record(owner_active=False)
        service = PublicAuthService(api_key_repository=repo)

        with pytest.raises(HTTPException) as exc_info:
            service.validate_api_key_for_app(db=MagicMock(), app_id=10, api_key="valid")

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc_info.value.detail == "This API key belongs to a deactivated account"
        repo.update_last_used_at.assert_not_called()

    def test_updates_last_used_and_returns_api_key_when_valid(self, mocker):
        api_key_obj = make_api_key_record(key_id=99, owner_active=True)
        repo = mocker.MagicMock()
        repo.get_active_by_app_and_key.return_value = api_key_obj
        service = PublicAuthService(api_key_repository=repo)

        result = service.validate_api_key_for_app(db=MagicMock(), app_id=10, api_key="valid")

        assert result is api_key_obj
        repo.update_last_used_at.assert_called_once()
        repo.get_active_by_app_and_key.assert_called_once()


class TestFindValidKeyForApp:
    """`find_valid_key_for_app` (A2A visibility, step_011) shares the exact
    predicate `validate_api_key_for_app` is built from (`_lookup_active_key`),
    but never raises and never touches `last_used_at`."""

    def test_returns_none_when_api_key_is_invalid(self, mocker):
        repo = mocker.MagicMock()
        repo.get_active_by_app_and_key.return_value = None
        service = PublicAuthService(api_key_repository=repo)

        result = service.find_valid_key_for_app(db=MagicMock(), app_id=10, api_key="invalid")

        assert result is None
        repo.update_last_used_at.assert_not_called()

    def test_returns_none_when_owner_is_deactivated(self, mocker):
        repo = mocker.MagicMock()
        repo.get_active_by_app_and_key.return_value = make_api_key_record(owner_active=False)
        service = PublicAuthService(api_key_repository=repo)

        result = service.find_valid_key_for_app(db=MagicMock(), app_id=10, api_key="valid")

        assert result is None
        repo.update_last_used_at.assert_not_called()

    def test_returns_the_row_when_valid_and_never_touches_last_used_at(self, mocker):
        api_key_obj = make_api_key_record(key_id=99, owner_active=True)
        repo = mocker.MagicMock()
        repo.get_active_by_app_and_key.return_value = api_key_obj
        service = PublicAuthService(api_key_repository=repo)

        result = service.find_valid_key_for_app(db=MagicMock(), app_id=10, api_key="valid")

        assert result is api_key_obj
        repo.update_last_used_at.assert_not_called()

    def test_key_of_another_app_is_none(self, mocker):
        # get_active_by_app_and_key is itself app_id-scoped; a key belonging to a
        # different app simply never matches, which the repository already encodes
        # by filtering on app_id -- this asserts find_valid_key_for_app surfaces
        # that as None rather than finding it some other way.
        repo = mocker.MagicMock()
        repo.get_active_by_app_and_key.return_value = None
        service = PublicAuthService(api_key_repository=repo)

        result = service.find_valid_key_for_app(db=MagicMock(), app_id=10, api_key="other-apps-key")

        assert result is None
