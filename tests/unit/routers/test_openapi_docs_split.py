"""Unit tests: /docs/internal and /docs/public each get the OpenAPI schema of their API.

Regression: since FastAPI 0.137 ``app.routes`` is a tree, and filtering it as a
flat list by path prefix produced empty internal/public schemas.
Run with: pytest tests/unit/routers/test_openapi_docs_split.py -v
"""

import main


def _paths(schema: dict) -> set[str]:
    return set(schema["paths"])


def test_split_schemas_cover_every_internal_and_public_path():
    full = _paths(main.app.openapi())
    internal = _paths(main.get_openapi_internal())
    public = _paths(main.get_openapi_public())

    assert internal == {p for p in full if p.startswith("/internal")}
    assert public == {p for p in full if p.startswith("/public")}
    assert internal and public


def test_split_schemas_include_known_routes():
    assert "/internal/collaboration/invitations/{collaboration_id}/respond" in main.get_openapi_internal()["paths"]
    assert any(p.startswith("/public/v1/") for p in main.get_openapi_public()["paths"])
