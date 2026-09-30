"""Unit tests: SharePoint and metrics routers are part of the core internal router.

Both used to be mounted by external plugins directly on the app, which skipped
the internal router's CSRF and viewer-write guards. They now live in
routers/internal and must inherit both.
Run with: pytest tests/unit/routers/test_integrated_routers_mounting.py -v
"""

from fastapi.routing import APIRoute, RouteContext, iter_route_contexts

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


_METRICS_ENDPOINTS = ("summary", "timeseries", "breakdown/{dimension}", "tools", "errors")
EXPECTED_METRICS_PATHS = {
    f"{prefix}/{endpoint}"
    for prefix in ("/admin/metrics", "/apps/{app_id}/metrics", "/apps/{app_id}/agents/{agent_id}/metrics")
    for endpoint in _METRICS_ENDPOINTS
}


def _api_routes() -> list[RouteContext]:
    # internal_router.routes is a tree since FastAPI 0.137; walk it to get every
    # route with its effective path and inherited (router-level) dependencies.
    return [
        route for route in iter_route_contexts(internal_router.routes)
        if isinstance(route.original_route, APIRoute)
    ]


def _routes(match) -> dict[tuple[str, str], RouteContext]:
    return {
        (method, route.path): route
        for route in _api_routes()
        if match(route.path)
        for method in route.methods
    }


def _sharepoint_routes() -> dict[tuple[str, str], RouteContext]:
    return _routes(lambda path: "sharepoint" in path or "/microsoft/" in path)


def _metrics_routes() -> dict[tuple[str, str], RouteContext]:
    return _routes(lambda path: "/metrics/" in path)


def test_all_sharepoint_routes_are_mounted():
    assert set(_sharepoint_routes()) == EXPECTED_ROUTES


def test_all_metrics_routes_are_mounted_read_only():
    assert set(_metrics_routes()) == {("GET", path) for path in EXPECTED_METRICS_PATHS}


def test_integrated_routes_inherit_csrf_and_viewer_write_guards():
    routes = {**_sharepoint_routes(), **_metrics_routes()}
    # Guard against a vacuous pass if route discovery ever returns nothing.
    assert len(routes) == len(EXPECTED_ROUTES) + len(EXPECTED_METRICS_PATHS)
    for key, route in routes.items():
        guards = {dep.dependency for dep in route.dependencies}
        assert enforce_csrf in guards, key
        assert require_editor_for_writes in guards, key


def test_capabilities_endpoint_is_gone():
    routes = _api_routes()
    assert routes, "route discovery returned nothing"
    assert not any(route.path == "/capabilities" for route in routes)
