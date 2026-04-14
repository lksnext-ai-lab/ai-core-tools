from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status

from routers.public.v1 import auth as auth_module


class TestGetApiKeyAuthDependency:
    def test_get_api_key_auth_requires_header(self):
        with pytest.raises(HTTPException) as exc_info:
            auth_module.get_api_key_auth(api_key=None)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "API key required" in exc_info.value.detail


class TestValidateApiKeyForApp:
    def test_validate_api_key_for_app_delegates_and_returns_model(self, mocker):
        session = mocker.MagicMock()
        api_key_obj = mocker.MagicMock()
        api_key_obj.key_id = 42

        mocker.patch.object(auth_module, "SessionLocal", return_value=session)
        validate_mock = mocker.patch.object(
            auth_module.public_auth_service,
            "validate_api_key_for_app",
            return_value=api_key_obj,
        )

        result = auth_module.validate_api_key_for_app(app_id=10, api_key="valid")

        assert result.app_id == 10
        assert result.api_key == "valid"
        assert result.key_id == 42
        validate_mock.assert_called_once_with(session, 10, "valid")
        session.close.assert_called_once()

    def test_validate_api_key_for_app_propagates_http_error(self, mocker):
        session = mocker.MagicMock()
        mocker.patch.object(auth_module, "SessionLocal", return_value=session)
        mocker.patch.object(
            auth_module.public_auth_service,
            "validate_api_key_for_app",
            side_effect=HTTPException(status_code=401, detail="Invalid"),
        )

        with pytest.raises(HTTPException) as exc_info:
            auth_module.validate_api_key_for_app(app_id=10, api_key="invalid")

        assert exc_info.value.status_code == 401
        session.close.assert_called_once()


class TestCreateApiKeyDependency:
    def test_dependency_requires_header(self):
        dependency = auth_module.create_api_key_dependency(app_id=10)

        with pytest.raises(HTTPException) as exc_info:
            dependency(api_key=None)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "API key required" in exc_info.value.detail

    def test_dependency_delegates_and_returns_model(self, mocker):
        dependency = auth_module.create_api_key_dependency(app_id=10)
        session = mocker.MagicMock()
        api_key_obj = mocker.MagicMock()
        api_key_obj.key_id = 11

        mocker.patch.object(auth_module, "SessionLocal", return_value=session)
        validate_mock = mocker.patch.object(
            auth_module.public_auth_service,
            "validate_api_key_for_app",
            return_value=api_key_obj,
        )

        result = dependency(api_key="abc")

        assert result.app_id == 10
        assert result.api_key == "abc"
        assert result.key_id == 11
        validate_mock.assert_called_once_with(session, 10, "abc")
        session.close.assert_called_once()

    def test_dependency_closes_session_on_http_error(self, mocker):
        dependency = auth_module.create_api_key_dependency(app_id=10)
        session = mocker.MagicMock()

        mocker.patch.object(auth_module, "SessionLocal", return_value=session)
        mocker.patch.object(
            auth_module.public_auth_service,
            "validate_api_key_for_app",
            side_effect=HTTPException(status_code=403, detail="Disabled"),
        )

        with pytest.raises(HTTPException) as exc_info:
            dependency(api_key="abc")

        assert exc_info.value.status_code == 403
        session.close.assert_called_once()
