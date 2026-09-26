"""Unit tests: SharePoint and metrics routers are part of the core internal router.

Both used to be mounted by external plugins directly on the app, which skipped
the internal router's CSRF and viewer-write guards. They now live in
routers/internal and must inherit both.
Run with: pytest tests/unit/routers/test_integrated_routers_mounting.py -v
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


EXPECTED_METRICS_PATHS = {
    f"/apps/{{app_id}}/metrics/{name}" for name in ("summary", "executions", "agents", "models", "users")
} | {
    f"/apps/{{app_id}}/agents/{{agent_id}}/metrics/{name}"
    for name in ("summary", "executions", "tokens", "errors", "latency", "tools", "users")
}


def _routes(match) -> dict[tuple[str, str], APIRoute]:
    return {
        (method, route.path): route
        for route in internal_router.routes
        if isinstance(route, APIRoute) and match(route.path)
        for method in route.methods
    }


def _sharepoint_routes() -> dict[tuple[str, str], APIRoute]:
    return _routes(lambda path: "sharepoint" in path or "/microsoft/" in path)


def _metrics_routes() -> dict[tuple[str, str], APIRoute]:
    return _routes(lambda path: "/metrics/" in path)


def test_all_sharepoint_routes_are_mounted():
    assert set(_sharepoint_routes()) == EXPECTED_ROUTES


def test_all_metrics_routes_are_mounted_read_only():
    assert set(_metrics_routes()) == {("GET", path) for path in EXPECTED_METRICS_PATHS}


def test_integrated_routes_inherit_csrf_and_viewer_write_guards():
    for key, route in {**_sharepoint_routes(), **_metrics_routes()}.items():
        guards = {dep.dependency for dep in route.dependencies}
        assert enforce_csrf in guards, key
        assert require_editor_for_writes in guards, key


def test_capabilities_endpoint_is_gone():
    assert not any(
        isinstance(route, APIRoute) and route.path == "/capabilities" for route in internal_router.routes
    )
