"""Unit tests: the SharePoint router is part of the core internal router.

SharePoint used to be mounted by an external plugin directly on the app, which
skipped the internal router's CSRF and viewer-write guards. It now lives in
routers/internal and must inherit both.
Run with: pytest tests/unit/routers/test_sharepoint_router_mounting.py -v
"""

from fastapi.routing import APIRoute

from middleware.csrf import enforce_csrf
from routers.internal import internal_router
from routers.internal.auth_utils import require_editor_for_writes

EXPECTED_ROUTES = {
    ("GET", "/apps/{app_id}/sharepoint-sources"),
    ("POST", "/apps/{app_id}/sharepoint-sources"),
    ("GET", "/apps/{app_id}/sharepoint-sources/{source_id}"),
    ("PUT", "/apps/{app_id}/sharepoint-sources/{source_id}"),
    ("DELETE", "/apps/{app_id}/sharepoint-sources/{source_id}"),
    ("POST", "/apps/{app_id}/sharepoint-sources/{source_id}/sync"),
    ("GET", "/microsoft/sites"),
    ("GET", "/microsoft/resolve-site"),
    ("GET", "/microsoft/drives"),
    ("POST", "/microsoft/test-connection"),
}


def _sharepoint_routes() -> dict[tuple[str, str], APIRoute]:
    return {
        (method, route.path): route
        for route in internal_router.routes
        if isinstance(route, APIRoute) and ("sharepoint" in route.path or "/microsoft/" in route.path)
        for method in route.methods
    }


def test_all_sharepoint_routes_are_mounted():
    assert set(_sharepoint_routes()) == EXPECTED_ROUTES


def test_sharepoint_routes_inherit_csrf_and_viewer_write_guards():
    for key, route in _sharepoint_routes().items():
        guards = {dep.dependency for dep in route.dependencies}
        assert enforce_csrf in guards, key
        assert require_editor_for_writes in guards, key


def test_capabilities_endpoint_is_gone():
    assert not any(
        isinstance(route, APIRoute) and route.path == "/capabilities" for route in internal_router.routes
    )
