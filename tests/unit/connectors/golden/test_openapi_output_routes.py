"""Snapshot of the internal OpenAPI schema for the output-channel routes.

``operationId`` values derive from the router function names, so they must
survive the refactor unchanged. Regenerate only with ``GOLDEN_UPDATE=1``.
"""

import json
import os
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "openapi_output_routes.json"
# Only paths containing one of these four markers are covered; other routes are not snapshotted.
MARKERS = ("/output-providers", "/output-destinations", "/scheduled-tasks/{task_id}/outputs", "/deliveries")


def _refs(node, found: set[str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            found.add(ref.rsplit("/", 1)[1])
        for value in node.values():
            _refs(value, found)
    elif isinstance(node, list):
        for value in node:
            _refs(value, found)


def _snapshot() -> dict:
    import main

    schema = main.get_openapi_internal()
    paths = {
        path: item for path, item in schema["paths"].items()
        if path.startswith("/internal/apps/{app_id}/") and any(marker in path for marker in MARKERS)
    }
    schemas = schema.get("components", {}).get("schemas", {})
    needed: set[str] = set()
    _refs(paths, needed)
    pending = list(needed)
    while pending:
        name = pending.pop()
        found: set[str] = set()
        _refs(schemas[name], found)
        for extra in found - needed:
            needed.add(extra)
            pending.append(extra)
    return json.loads(json.dumps(
        {"paths": paths, "schemas": {name: schemas[name] for name in sorted(needed)}}, sort_keys=True,
    ))


def test_output_routes_openapi_snapshot():
    snapshot = _snapshot()
    assert snapshot["paths"], "no output routes selected: the path filter is stale"
    if os.getenv("GOLDEN_UPDATE") == "1":
        FIXTURE.write_text(json.dumps(snapshot, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return
    assert snapshot == json.loads(FIXTURE.read_text(encoding="utf-8"))
