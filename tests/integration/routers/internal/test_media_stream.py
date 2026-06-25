"""
Integration tests for the media stream endpoint:

  GET /internal/apps/{app_id}/repositories/{repository_id}/media/{media_id}/stream

Endpoint contract under test:
  - 200 + Accept-Ranges: bytes   when no Range header is sent
  - 206 + Content-Range header   when Range: bytes=<start>-<end> is sent
  - 404                          when the file is not found in storage
  - 404                          when media.storage_key is None

The storage backend is mocked via unittest.mock.patch on the router-level import
so no real filesystem or S3 access happens.

NOTE (tests 3 & 4 — error handling):
  These tests document the ENDPOINT CONTRACT.  They currently fail with a 500
  because stream_media does not yet:
    a) check `if not media.storage_key` before streaming  → raise HTTPException(404)
    b) catch FileNotFoundError from the iterator          → raise HTTPException(404)
  Once those checks are added the tests will pass.  The no_raise_client fixture
  (raise_server_exceptions=False) is used so the HTTP response is returned rather
  than the unhandled exception propagating to the test runner.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Module-level fixtures — Repository and Media rows
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_repository(db, fake_app, fake_silo):
    """A Repository belonging to fake_app, backed by fake_silo."""
    from models.repository import Repository

    repo = Repository(
        name="Streaming Integration Test Repo",
        type="media",
        status="active",
        app_id=fake_app.app_id,
        silo_id=fake_silo.silo_id,
    )
    db.add(repo)
    db.flush()
    return repo


@pytest.fixture
def fake_media(db, fake_repository):
    """A fully-processed Media row with a valid storage_key."""
    from models.media import Media

    m = Media(
        name="Test Video",
        repository_id=fake_repository.repository_id,
        source_type="upload",
        status="processed",
        storage_key=f"repositories/{fake_repository.repository_id}/test.mp4",
    )
    db.add(m)
    db.flush()
    return m


@pytest.fixture
def fake_media_no_key(db, fake_repository):
    """A Media row whose storage_key is NULL (upload never completed)."""
    from models.media import Media

    m = Media(
        name="Unprocessed Video",
        repository_id=fake_repository.repository_id,
        source_type="upload",
        status="pending",
        storage_key=None,
    )
    db.add(m)
    db.flush()
    return m


@pytest.fixture
def no_raise_client(db):
    """
    TestClient with raise_server_exceptions=False.

    Use for tests that need to assert HTTP error status codes (4xx / 5xx)
    rather than having unhandled server exceptions propagate into the test.
    """
    from main import app
    from db.database import get_db

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _stream_url(app_id: int, repo_id: int, media_id: int) -> str:
    return (
        f"/internal/apps/{app_id}"
        f"/repositories/{repo_id}"
        f"/media/{media_id}/stream"
    )


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

class TestStreamMediaFullDownload:
    """GET …/stream without a Range header → 200 OK."""

    def test_returns_200_with_body_and_accept_ranges_header(
        self, client, db, fake_app, fake_repository, fake_media, owner_headers
    ):
        async def _fake_stream(key, byte_range=None):
            yield b"hello world"

        mock_backend = MagicMock()
        mock_backend.stream = _fake_stream

        with patch(
            "routers.internal.repositories.get_storage_backend",
            return_value=mock_backend,
        ):
            response = client.get(
                _stream_url(
                    fake_app.app_id,
                    fake_repository.repository_id,
                    fake_media.media_id,
                ),
                headers=owner_headers,
            )

        assert response.status_code == 200
        assert response.content == b"hello world"
        assert "accept-ranges" in response.headers
        assert response.headers["accept-ranges"] == "bytes"


class TestStreamMediaRangedRequest:
    """GET …/stream with Range header → 206 Partial Content."""

    def test_returns_206_with_content_range_header_and_sliced_body(
        self, client, db, fake_app, fake_repository, fake_media, owner_headers
    ):
        async def _fake_stream(key, byte_range=None):
            yield b"hello"

        mock_backend = MagicMock()
        mock_backend.stream = _fake_stream

        with patch(
            "routers.internal.repositories.get_storage_backend",
            return_value=mock_backend,
        ):
            response = client.get(
                _stream_url(
                    fake_app.app_id,
                    fake_repository.repository_id,
                    fake_media.media_id,
                ),
                headers={**owner_headers, "Range": "bytes=0-4"},
            )

        assert response.status_code == 206
        assert response.content == b"hello"
        assert "content-range" in response.headers
        # Endpoint sets Content-Range: bytes 0-4/*
        assert response.headers["content-range"].startswith("bytes 0-4/")
        assert "accept-ranges" in response.headers


# ---------------------------------------------------------------------------
# Error-handling tests
# ---------------------------------------------------------------------------

class TestStreamMediaErrorHandling:
    """
    404 responses for missing files and absent storage_key.

    These tests use no_raise_client (raise_server_exceptions=False) to
    convert what would be an unhandled exception into an HTTP response so
    that the status code can be asserted.

    CURRENT BEHAVIOUR: the endpoint returns 500 because stream_media does not
    yet catch FileNotFoundError or guard against None storage_key.
    EXPECTED BEHAVIOUR (this contract): 404.
    """

    def test_returns_404_when_storage_raises_file_not_found(
        self,
        no_raise_client,
        db,
        fake_app,
        fake_repository,
        fake_media,
        owner_headers,
    ):
        async def _raising_stream(key, byte_range=None):
            raise FileNotFoundError(f"key not found in storage: {key!r}")
            yield  # makes this an async generator function

        mock_backend = MagicMock()
        mock_backend.stream = _raising_stream

        with patch(
            "routers.internal.repositories.get_storage_backend",
            return_value=mock_backend,
        ):
            response = no_raise_client.get(
                _stream_url(
                    fake_app.app_id,
                    fake_repository.repository_id,
                    fake_media.media_id,
                ),
                headers=owner_headers,
            )

        assert response.status_code == 404

    def test_returns_404_when_media_has_no_storage_key(
        self,
        no_raise_client,
        db,
        fake_app,
        fake_repository,
        fake_media_no_key,
        owner_headers,
    ):
        """
        Media with storage_key=None should result in 404.

        The endpoint needs an explicit `if not media.storage_key` guard before
        attempting to call stream() for this test to pass.
        """
        async def _raising_stream(key, byte_range=None):
            raise FileNotFoundError("storage_key is None — no file to stream")
            yield

        mock_backend = MagicMock()
        mock_backend.stream = _raising_stream

        with patch(
            "routers.internal.repositories.get_storage_backend",
            return_value=mock_backend,
        ):
            response = no_raise_client.get(
                _stream_url(
                    fake_app.app_id,
                    fake_repository.repository_id,
                    fake_media_no_key.media_id,
                ),
                headers=owner_headers,
            )

        assert response.status_code == 404
