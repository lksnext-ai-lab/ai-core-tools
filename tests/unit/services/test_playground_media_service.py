"""Unit tests for PlaygroundMediaService.vectorize_uploaded_file with an optional media embedding service."""

from unittest.mock import MagicMock, patch

from services.playground_media_service import PlaygroundMediaService


def _db_returning_agent(media_embedding_service_id):
    agent = MagicMock()
    agent.media_embedding_service_id = media_embedding_service_id
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = agent
    return db


def _vectorize(db, **kwargs):
    return PlaygroundMediaService.vectorize_uploaded_file(
        app_id=1,
        agent_id=10,
        session_id="conv_10_abc",
        file_id="f1",
        filename="doc.pdf",
        file_path=None,
        content="some text",
        db=db,
        **kwargs,
    )


def test_skips_without_embedding_service_and_no_temp_silo():
    db = _db_returning_agent(None)
    with patch.object(PlaygroundMediaService, "get_temp_repository", return_value=None), \
         patch.object(PlaygroundMediaService, "get_or_create_temp_repository") as get_or_create:
        assert _vectorize(db) is False
    get_or_create.assert_not_called()


def test_uses_agent_embedding_service_when_configured():
    db = _db_returning_agent(7)
    with patch.object(PlaygroundMediaService, "get_temp_repository", return_value=None), \
         patch.object(PlaygroundMediaService, "get_or_create_temp_repository", return_value=None) as get_or_create:
        assert _vectorize(db) is False
    get_or_create.assert_called_once()


def test_reuses_existing_temp_silo_without_agent_embedding_service():
    db = _db_returning_agent(None)
    with patch.object(PlaygroundMediaService, "get_temp_repository", return_value=MagicMock()), \
         patch.object(PlaygroundMediaService, "get_or_create_temp_repository", return_value=None) as get_or_create:
        _vectorize(db)
    get_or_create.assert_called_once()
    db.query.assert_not_called()


def test_explicit_embedding_service_bypasses_agent_lookup():
    db = _db_returning_agent(None)
    with patch.object(PlaygroundMediaService, "get_temp_repository") as get_temp, \
         patch.object(PlaygroundMediaService, "get_or_create_temp_repository", return_value=None) as get_or_create:
        _vectorize(db, embedding_service_id=3)
    get_temp.assert_not_called()
    get_or_create.assert_called_once()
