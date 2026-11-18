import pytest
from fastapi.testclient import TestClient

from db.database import get_db
from routers.scim.router import scim_service
from services.scim_service import SCIMAuthenticationError


@pytest.mark.parametrize(
    ("status_code", "authenticate", "expected_challenge"),
    [(401, True, "Bearer"), (403, False, None)],
)
def test_scim_authentication_errors_return_scim_responses(
    monkeypatch, status_code, authenticate, expected_challenge
):
    from main import app

    async def reject_authentication(*_args, **_kwargs):
        raise SCIMAuthenticationError(
            status_code,
            "Invalid SCIM credentials.",
            authenticate=authenticate,
        )

    monkeypatch.setattr(scim_service, "authenticate", reject_authentication)
    previous_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: None
    try:
        response = TestClient(app, raise_server_exceptions=False).get(
            "/scim/v2/test-connection/ServiceProviderConfig"
        )
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

    assert response.status_code == status_code
    assert response.headers["content-type"].startswith("application/scim+json")
    assert response.headers.get("www-authenticate") == expected_challenge
    assert response.json() == {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
        "detail": "Invalid SCIM credentials.",
        "status": str(status_code),
    }
