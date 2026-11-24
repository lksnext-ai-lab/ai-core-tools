"""GET /chat/options -> attachment_indexing (the App's default embedding service), in its three states."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import event

from models.app import App
from models.embedding_service import EmbeddingService
from tests.integration.internal_chat._chat_support import base

URL = lambda world: base(world["app_id"]) + "/options"  # noqa: E731


def _options(client, world):
    response = client.get(URL(world), headers=world["alice"])
    assert response.status_code == 200, response.text
    return response.json()


def _count_queries(db, client, world) -> int:
    statements = []

    def capture(conn, cursor, statement, *a):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        _options(client, world)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    return len(statements)


def test_no_default_embedding_service(client, world):
    assert _options(client, world)["attachment_indexing"] == {"enabled": False, "reason": "no_default_embedding_service"}


def test_an_active_default_enables_indexing(client, db, world):
    db.get(App, world["app_id"]).default_embedding_service_id = world["emb"]
    db.commit()
    assert _options(client, world)["attachment_indexing"] == {"enabled": True, "reason": None}


def test_a_deprecated_default_still_enables_indexing(client, db, world):
    db.get(App, world["app_id"]).default_embedding_service_id = world["emb"]
    db.get(EmbeddingService, world["emb"]).end_of_service_at = datetime.now(timezone.utc) + timedelta(days=5)
    db.commit()
    assert _options(client, world)["attachment_indexing"] == {"enabled": True, "reason": None}


def test_a_retired_default_disables_indexing_with_its_reason(client, db, world):
    db.get(App, world["app_id"]).default_embedding_service_id = world["emb"]
    db.get(EmbeddingService, world["emb"]).end_of_service_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    assert _options(client, world)["attachment_indexing"] == {"enabled": False, "reason": "embedding_service_retired"}


def test_the_query_count_does_not_depend_on_the_state(client, db, world):
    without = _count_queries(db, client, world)
    db.get(App, world["app_id"]).default_embedding_service_id = world["emb"]
    db.commit()
    assert _count_queries(db, client, world) == without
    db.get(EmbeddingService, world["emb"]).end_of_service_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    assert _count_queries(db, client, world) == without
