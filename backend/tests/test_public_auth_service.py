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
