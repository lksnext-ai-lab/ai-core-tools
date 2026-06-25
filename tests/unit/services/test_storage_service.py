"""
Unit tests for StorageBackend implementations and the get_storage_backend() factory.

LocalStorageBackend — real temp files via tmp_path; no mocks needed.
S3StorageBackend    — boto3/botocore injected via sys.modules; asyncio.to_thread
                      replaced with a sync shim so no real threads are spun up.
get_storage_backend — singleton reset between tests; env vars controlled with
                      monkeypatch so test isolation is guaranteed.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

from services.storage_service import LocalStorageBackend, get_storage_backend
import services.storage_service as _storage_mod


# ===========================================================================
# LocalStorageBackend
# ===========================================================================

class TestLocalStorageBackendUpload:
    """upload() creates the file (and parent directories) at base_path / key."""

    @pytest.mark.asyncio
    async def test_upload_creates_file_with_correct_content(self, tmp_path):
        backend = LocalStorageBackend(base_path=str(tmp_path))
        await backend.upload("file.mp4", b"hello world", "video/mp4")
        assert (tmp_path / "file.mp4").read_bytes() == b"hello world"

    @pytest.mark.asyncio
    async def test_upload_creates_nested_parent_directories(self, tmp_path):
        backend = LocalStorageBackend(base_path=str(tmp_path))
        await backend.upload("repositories/10/42.mp4", b"data", "video/mp4")
        assert (tmp_path / "repositories" / "10" / "42.mp4").exists()

    @pytest.mark.asyncio
    async def test_upload_tolerates_none_content_type(self, tmp_path):
        backend = LocalStorageBackend(base_path=str(tmp_path))
        await backend.upload("audio.wav", b"wav data", None)
        assert (tmp_path / "audio.wav").read_bytes() == b"wav data"


class TestLocalStorageBackendStream:
    """stream() yields file content; honours byte_range; raises on missing file."""

    @pytest.mark.asyncio
    async def test_stream_yields_full_file_content(self, tmp_path):
        (tmp_path / "v.mp4").write_bytes(b"video content here")
        backend = LocalStorageBackend(base_path=str(tmp_path))

        chunks: list[bytes] = []
        async for chunk in backend.stream("v.mp4"):
            chunks.append(chunk)

        assert b"".join(chunks) == b"video content here"

    @pytest.mark.asyncio
    async def test_stream_byte_range_returns_exact_inclusive_slice(self, tmp_path):
        # bytes 2..5 inclusive = b"CDEF" (4 bytes)
        (tmp_path / "f.bin").write_bytes(b"ABCDEFGHIJ")
        backend = LocalStorageBackend(base_path=str(tmp_path))

        chunks: list[bytes] = []
        async for chunk in backend.stream("f.bin", byte_range=(2, 5)):
            chunks.append(chunk)

        assert b"".join(chunks) == b"CDEF"

    @pytest.mark.asyncio
    async def test_stream_byte_range_64_bytes(self, tmp_path):
        content = bytes(range(128))
        (tmp_path / "big.bin").write_bytes(content)
        backend = LocalStorageBackend(base_path=str(tmp_path))

        chunks: list[bytes] = []
        async for chunk in backend.stream("big.bin", byte_range=(0, 63)):
            chunks.append(chunk)

        assert b"".join(chunks) == content[:64]

    @pytest.mark.asyncio
    async def test_stream_raises_file_not_found_for_missing_key(self, tmp_path):
        backend = LocalStorageBackend(base_path=str(tmp_path))
        with pytest.raises(FileNotFoundError):
            async for _ in backend.stream("nonexistent.mp4"):
                pass


class TestLocalStorageBackendDeleteExistsSize:
    """delete(), exists(), and get_size() basic behaviour."""

    @pytest.mark.asyncio
    async def test_delete_removes_file(self, tmp_path):
        p = tmp_path / "del.bin"
        p.write_bytes(b"x")
        backend = LocalStorageBackend(base_path=str(tmp_path))
        await backend.delete("del.bin")
        assert not p.exists()

    @pytest.mark.asyncio
    async def test_delete_does_not_raise_when_file_already_missing(self, tmp_path):
        backend = LocalStorageBackend(base_path=str(tmp_path))
        await backend.delete("never_existed.bin")  # must not raise

    @pytest.mark.asyncio
    async def test_exists_returns_true_for_present_file(self, tmp_path):
        (tmp_path / "yes.bin").write_bytes(b"y")
        backend = LocalStorageBackend(base_path=str(tmp_path))
        assert await backend.exists("yes.bin") is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_absent_file(self, tmp_path):
        backend = LocalStorageBackend(base_path=str(tmp_path))
        assert await backend.exists("no.bin") is False

    @pytest.mark.asyncio
    async def test_get_size_returns_exact_byte_count(self, tmp_path):
        content = b"twelve bytes"
        (tmp_path / "sized.bin").write_bytes(content)
        backend = LocalStorageBackend(base_path=str(tmp_path))
        assert await backend.get_size("sized.bin") == len(content)


# ===========================================================================
# S3StorageBackend
# ===========================================================================

class TestS3StorageBackend:
    """
    S3StorageBackend tests with fake boto3/botocore injected via sys.modules.

    asyncio.to_thread is replaced by a shim that runs the callable synchronously,
    so assertions can be made on mock call arguments without real AWS credentials.
    """

    @pytest.fixture(autouse=True)
    def _mock_aws(self, mocker):
        """Inject fake boto3/botocore and a synchronous asyncio.to_thread shim."""
        self.mock_s3_client = mocker.MagicMock()

        class FakeClientError(Exception):
            """Minimal stand-in for botocore.exceptions.ClientError."""
            def __init__(self, error_response: dict, operation_name: str = "op"):
                self.response = error_response
                super().__init__(operation_name)

        self.FakeClientError = FakeClientError

        fake_boto3 = mocker.MagicMock()
        fake_boto3.client.return_value = self.mock_s3_client

        fake_botocore_exc = mocker.MagicMock()
        fake_botocore_exc.ClientError = FakeClientError

        mocker.patch.dict(
            "sys.modules",
            {
                "boto3": fake_boto3,
                "botocore": mocker.MagicMock(),
                "botocore.exceptions": fake_botocore_exc,
            },
        )

        # Run all to_thread callables synchronously inside the test event loop
        async def _sync_shim(func, *args, **kwargs):
            return func(*args, **kwargs)

        mocker.patch("asyncio.to_thread", side_effect=_sync_shim)

    def _make_backend(self):
        """Create S3StorageBackend after sys.modules patches are active."""
        from services.storage_service import S3StorageBackend

        backend = S3StorageBackend(
            bucket="test-bucket",
            endpoint_url=None,
            access_key="test-access",
            secret_key="test-secret",
        )
        # Use the fake exception class so except-clauses work without real botocore
        backend._ClientError = self.FakeClientError
        return backend

    # --- upload ---

    @pytest.mark.asyncio
    async def test_upload_calls_put_object_with_correct_params(self):
        backend = self._make_backend()
        await backend.upload("repositories/1/2.mp4", b"video data", "video/mp4")
        self.mock_s3_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="repositories/1/2.mp4",
            Body=b"video data",
            ContentType="video/mp4",
        )

    @pytest.mark.asyncio
    async def test_upload_uses_default_content_type_when_none_given(self):
        backend = self._make_backend()
        await backend.upload("key.bin", b"data", None)
        kwargs = self.mock_s3_client.put_object.call_args.kwargs
        assert kwargs["ContentType"] == "application/octet-stream"

    # --- stream ---

    @pytest.mark.asyncio
    async def test_stream_yields_chunks_from_response_body(self):
        backend = self._make_backend()
        mock_body = MagicMock()
        mock_body.iter_chunks.return_value = iter([b"chunk_a", b"chunk_b"])
        self.mock_s3_client.get_object.return_value = {"Body": mock_body}

        chunks: list[bytes] = []
        async for chunk in backend.stream("vid.mp4"):
            chunks.append(chunk)

        assert chunks == [b"chunk_a", b"chunk_b"]

    @pytest.mark.asyncio
    async def test_stream_passes_range_header_when_byte_range_given(self):
        backend = self._make_backend()
        mock_body = MagicMock()
        mock_body.iter_chunks.return_value = iter([b"HELLO"])
        self.mock_s3_client.get_object.return_value = {"Body": mock_body}

        async for _ in backend.stream("vid.mp4", byte_range=(0, 4)):
            pass

        call_kwargs = self.mock_s3_client.get_object.call_args.kwargs
        assert call_kwargs.get("Range") == "bytes=0-4"

    @pytest.mark.asyncio
    async def test_stream_raises_file_not_found_on_s3_404(self):
        """
        S3 404 ClientErrors should surface as FileNotFoundError.

        NOTE: This test documents the expected contract. The implementation
        must catch ClientError{"Code": "404"} in stream() and re-raise as
        FileNotFoundError for this test to pass.
        """
        backend = self._make_backend()
        self.mock_s3_client.get_object.side_effect = self.FakeClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "GetObject"
        )

        with pytest.raises(FileNotFoundError):
            async for _ in backend.stream("missing.mp4"):
                pass

    # --- delete ---

    @pytest.mark.asyncio
    async def test_delete_calls_delete_object_with_correct_params(self):
        backend = self._make_backend()
        await backend.delete("repositories/1/2.mp4")
        self.mock_s3_client.delete_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="repositories/1/2.mp4",
        )

    # --- exists ---

    @pytest.mark.asyncio
    async def test_exists_returns_true_when_head_object_succeeds(self):
        backend = self._make_backend()
        self.mock_s3_client.head_object.return_value = {"ContentLength": 100}
        assert await backend.exists("existing.mp4") is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_on_s3_404_client_error(self):
        backend = self._make_backend()
        self.mock_s3_client.head_object.side_effect = self.FakeClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
        )
        assert await backend.exists("missing.mp4") is False

    # --- get_size ---

    @pytest.mark.asyncio
    async def test_get_size_returns_content_length_from_head_object(self):
        backend = self._make_backend()
        self.mock_s3_client.head_object.return_value = {"ContentLength": 98765}
        assert await backend.get_size("big.mp4") == 98765


# ===========================================================================
# get_storage_backend() factory
# ===========================================================================

class TestGetStorageBackendFactory:
    """
    Factory function returns the correct backend type and caches the singleton.

    The module-level _backend is reset before each test so singleton state
    never leaks between tests.
    """

    @pytest.fixture(autouse=True)
    def _reset_singleton(self):
        original = _storage_mod._backend
        _storage_mod._backend = None
        yield
        _storage_mod._backend = original

    def test_returns_local_backend_by_default(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "local")
        backend = get_storage_backend()
        assert isinstance(backend, LocalStorageBackend)

    def test_returns_local_backend_when_storage_backend_env_var_absent(self, monkeypatch):
        monkeypatch.delenv("STORAGE_BACKEND", raising=False)
        backend = get_storage_backend()
        assert isinstance(backend, LocalStorageBackend)

    def test_returns_s3_backend_when_env_is_s3(self, monkeypatch, mocker):
        monkeypatch.setenv("STORAGE_BACKEND", "s3")
        monkeypatch.setenv("S3_BUCKET", "my-bucket")
        monkeypatch.setenv("S3_ACCESS_KEY", "access")
        monkeypatch.setenv("S3_SECRET_KEY", "secret")

        # Mock boto3 so no real import is needed
        fake_boto3 = mocker.MagicMock()
        mocker.patch.dict(
            "sys.modules",
            {
                "boto3": fake_boto3,
                "botocore": mocker.MagicMock(),
                "botocore.exceptions": mocker.MagicMock(),
            },
        )

        from services.storage_service import S3StorageBackend

        backend = get_storage_backend()
        assert isinstance(backend, S3StorageBackend)

    def test_raises_value_error_when_s3_vars_missing(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "s3")
        monkeypatch.delenv("S3_BUCKET", raising=False)
        monkeypatch.delenv("S3_ACCESS_KEY", raising=False)
        monkeypatch.delenv("S3_SECRET_KEY", raising=False)

        with pytest.raises(ValueError, match="S3_BUCKET|S3_ACCESS_KEY|S3_SECRET_KEY"):
            get_storage_backend()

    def test_returns_same_singleton_on_repeated_calls(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "local")
        b1 = get_storage_backend()
        b2 = get_storage_backend()
        assert b1 is b2
