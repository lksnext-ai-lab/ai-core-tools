"""Unit tests: require_editor_for_writes blocks viewer writes, exempting only the
collaboration invitation-respond route (matched by route template, not by URL suffix).

A small FastAPI app mounts the guard the same way routers/internal/__init__.py does,
with auth and DB dependencies overridden — no DB required.
Run with: pytest tests/unit/routers/test_require_editor_for_writes.py -v
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from db.database import get_db
from routers.internal import auth_utils
from routers.internal.auth_utils import get_current_user_oauth, require_editor_for_writes
from routers.internal import internal_router

VIEWER_EMAIL = "viewer@example.com"


def _build_client() -> TestClient:
    collaboration = APIRouter()
    collaboration.add_api_route(
        "/invitations/{collaboration_id}/respond", lambda collaboration_id: {"ok": True}, methods=["POST"]
    )
    collaboration.add_api_route("/invitations", lambda: {"ok": True}, methods=["POST"])

    apps = APIRouter()
    # Decoy: a write route that also ends in "/respond" must NOT be exempted.
    apps.add_api_route("/{app_id}/respond", lambda app_id: {"ok": True}, methods=["POST"])
    apps.add_api_route("/{app_id}", lambda app_id: {"ok": True}, methods=["GET"])

    internal = APIRouter()
    internal.include_router(apps, prefix="/apps", dependencies=[Depends(require_editor_for_writes)])
    internal.include_router(
        collaboration, prefix="/collaboration", dependencies=[Depends(require_editor_for_writes)]
    )

    app = FastAPI()
    app.include_router(internal, prefix="/internal")
    app.dependency_overrides[get_current_user_oauth] = lambda: SimpleNamespace(
        identity=SimpleNamespace(email=VIEWER_EMAIL)
    )
    app.dependency_overrides[get_db] = lambda: MagicMock()
    return TestClient(app)


@pytest.fixture
def client(mocker):
    mocker.patch.object(auth_utils, "_is_omniadmin", return_value=False)
    mocker.patch.object(
        auth_utils.UserService, "get_user_by_email", return_value=SimpleNamespace(platform_role="viewer")
    )
    return _build_client()


def test_viewer_can_read(client):
    assert client.get("/internal/apps/1").status_code == 200


def test_viewer_can_respond_to_invitation(client):
    assert client.post("/internal/collaboration/invitations/7/respond").status_code == 200


def test_viewer_cannot_write_other_routes(client):
    assert client.post("/internal/collaboration/invitations").status_code == 403


def test_viewer_cannot_write_unrelated_route_ending_in_respond(client):
    assert client.post("/internal/apps/1/respond").status_code == 403


def test_non_viewer_can_write(mocker):
    mocker.patch.object(auth_utils, "_is_omniadmin", return_value=False)
    mocker.patch.object(
        auth_utils.UserService, "get_user_by_email", return_value=SimpleNamespace(platform_role="user")
    )
    assert _build_client().post("/internal/apps/1/respond").status_code == 200


def test_exemption_matches_real_collaboration_respond_route():
    """Renaming the real route's path would silently lock viewers out of invitations."""
    exempted = [
        route.path for route in internal_router.routes
        if route.path.endswith(auth_utils._VIEWER_WRITABLE_ROUTE_SUFFIXES)
    ]
    assert exempted == ["/collaboration/invitations/{collaboration_id}/respond"]
