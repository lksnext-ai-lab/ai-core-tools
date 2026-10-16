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


# ---------------------------------------------------------------------------
# Indexing into the temp silo
# ---------------------------------------------------------------------------

SILO_ID = 42


def _repo(silo_id=SILO_ID):
    repo = MagicMock()
    repo.silo_id = silo_id
    return repo


def _run_indexing(tmp_path, file_path="doc.pdf", content="some text", repo=None, extract=None):
    """Run vectorize_uploaded_file with a temp repo, a real TMP_BASE_FOLDER and a mocked SiloService."""
    silo_service = MagicMock()
    if extract is not None:
        silo_service.extract_documents_from_file.side_effect = extract
    with patch.object(PlaygroundMediaService, "get_or_create_temp_repository", return_value=repo or _repo()), \
         patch("utils.config.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}), \
         patch("services.playground_media_service.SiloService", silo_service):
        result = PlaygroundMediaService.vectorize_uploaded_file(
            app_id=1,
            agent_id=10,
            session_id="conv_10_abc",
            file_id="f1",
            filename="doc.pdf",
            file_path=file_path,
            content=content,
            db=MagicMock(),
            embedding_service_id=3,
        )
    return result, silo_service


def _doc(text):
    doc = MagicMock()
    doc.page_content = text
    doc.metadata = {"page": 1}
    return doc


def test_indexes_documents_extracted_from_the_file(tmp_path):
    (tmp_path / "doc.pdf").write_bytes(b"%PDF")
    result, silo_service = _run_indexing(tmp_path, extract=lambda *_: [_doc("page one")])

    assert result is True
    silo_service.index_multiple_content.assert_called_once()
    silo_id, items, _ = silo_service.index_multiple_content.call_args.args
    assert silo_id == SILO_ID
    assert items == [{"content": "page one", "metadata": {"page": 1}}]


def test_falls_back_to_content_when_extraction_fails(tmp_path):
    (tmp_path / "doc.pdf").write_bytes(b"%PDF")

    def _boom(*_):
        raise RuntimeError("broken pdf")

    result, silo_service = _run_indexing(tmp_path, extract=_boom)

    assert result is True
    _, items, _ = silo_service.index_multiple_content.call_args.args
    assert items[0]["content"] == "some text"
    assert items[0]["metadata"]["source"] == "playground_upload"


def test_falls_back_to_content_when_extraction_returns_no_documents(tmp_path):
    (tmp_path / "doc.pdf").write_bytes(b"%PDF")
    result, silo_service = _run_indexing(tmp_path, extract=lambda *_: [])

    assert result is True
    _, items, _ = silo_service.index_multiple_content.call_args.args
    assert items[0]["content"] == "some text"


def test_falls_back_to_content_when_file_is_missing(tmp_path):
    result, silo_service = _run_indexing(tmp_path, file_path="missing.pdf")

    assert result is True
    silo_service.extract_documents_from_file.assert_not_called()
    _, items, _ = silo_service.index_multiple_content.call_args.args
    assert items[0]["content"] == "some text"


def test_returns_false_when_nothing_can_be_indexed(tmp_path):
    result, silo_service = _run_indexing(tmp_path, file_path=None, content="")

    assert result is False
    silo_service.index_multiple_content.assert_not_called()


def test_returns_false_when_temp_repository_has_no_silo(tmp_path):
    result, silo_service = _run_indexing(tmp_path, repo=_repo(silo_id=None))

    assert result is False
    silo_service.index_multiple_content.assert_not_called()
