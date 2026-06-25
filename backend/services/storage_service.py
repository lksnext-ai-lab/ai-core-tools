"""
Pluggable file-storage abstraction.

Use ``get_storage_backend()`` to obtain the configured backend.

Supported backends:
  - ``local``  (default) — files written under ``REPO_BASE_FOLDER``
  - ``s3``               — AWS S3 or any S3-compatible store (MinIO, etc.)

All I/O is non-blocking: blocking calls are dispatched to a thread pool via
``asyncio.to_thread`` so the event loop is never stalled.
"""
import asyncio
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from pathlib import Path


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class StorageBackend(ABC):
    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str | None = None) -> None: ...

    @abstractmethod
    async def stream(self, key: str, byte_range: tuple[int, int] | None = None) -> AsyncGenerator[bytes, None]: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def get_size(self, key: str) -> int: ...


# ---------------------------------------------------------------------------
# Local filesystem backend
# ---------------------------------------------------------------------------

class LocalStorageBackend(StorageBackend):
    def __init__(self, base_path: str) -> None:
        self._base_path = base_path

    async def upload(self, key: str, data: bytes, content_type: str | None = None) -> None:
        full_path = Path(self._base_path) / key

        def _write() -> None:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(data)

        await asyncio.to_thread(_write)

    async def stream(self, key: str, byte_range: tuple[int, int] | None = None) -> AsyncGenerator[bytes, None]:
        full_path = Path(self._base_path) / key

        if byte_range:
            start, end = byte_range
            remaining = end - start + 1

            f = await asyncio.to_thread(open, full_path, "rb")
            try:
                await asyncio.to_thread(f.seek, start)
                while remaining > 0:
                    chunk = await asyncio.to_thread(f.read, min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
            finally:
                await asyncio.to_thread(f.close)
        else:
            f = await asyncio.to_thread(open, full_path, "rb")
            try:
                while True:
                    chunk = await asyncio.to_thread(f.read, 65536)
                    if not chunk:
                        break
                    yield chunk
            finally:
                await asyncio.to_thread(f.close)

    async def delete(self, key: str) -> None:
        full_path = Path(self._base_path) / key

        def _delete() -> None:
            try:
                full_path.unlink()
            except FileNotFoundError:
                pass

        await asyncio.to_thread(_delete)

    async def exists(self, key: str) -> bool:
        full_path = Path(self._base_path) / key
        return await asyncio.to_thread(full_path.exists)

    async def get_size(self, key: str) -> int:
        full_path = Path(self._base_path) / key
        return await asyncio.to_thread(lambda: full_path.stat().st_size)


# ---------------------------------------------------------------------------
# S3 backend (boto3 import is deferred so the module loads without boto3)
# ---------------------------------------------------------------------------

class S3StorageBackend(StorageBackend):
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> None:
        import boto3  # noqa: PLC0415 — deferred: boto3 is optional
        from botocore.exceptions import ClientError as _ClientError  # noqa: PLC0415

        self._ClientError = _ClientError
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    async def upload(self, key: str, data: bytes, content_type: str | None = None) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )

    async def stream(self, key: str, byte_range: tuple[int, int] | None = None) -> AsyncGenerator[bytes, None]:
        kwargs: dict = {"Bucket": self._bucket, "Key": key}
        if byte_range:
            kwargs["Range"] = f"bytes={byte_range[0]}-{byte_range[1]}"

        try:
            response = await asyncio.to_thread(self._client.get_object, **kwargs)
        except self._ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                raise FileNotFoundError(key) from exc
            raise
        body = response["Body"]
        sentinel = object()
        it = body.iter_chunks(chunk_size=65536)

        while True:
            chunk = await asyncio.to_thread(next, it, sentinel)
            if chunk is sentinel:
                break
            yield chunk

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self._bucket,
            Key=key,
        )

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(
                self._client.head_object,
                Bucket=self._bucket,
                Key=key,
            )
            return True
        except self._ClientError as exc:
            if exc.response["Error"]["Code"] == "404":
                return False
            raise

    async def get_size(self, key: str) -> int:
        response = await asyncio.to_thread(
            self._client.head_object,
            Bucket=self._bucket,
            Key=key,
        )
        return response["ContentLength"]


# ---------------------------------------------------------------------------
# Module-level factory (singleton, initialised on first call)
# ---------------------------------------------------------------------------

_backend: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Return the configured ``StorageBackend`` singleton.

    The backend type is resolved from the ``STORAGE_BACKEND`` environment
    variable (default: ``"local"``).  For ``"s3"``, the variables
    ``S3_BUCKET``, ``S3_ACCESS_KEY``, and ``S3_SECRET_KEY`` must all be set.
    """
    global _backend

    if _backend is not None:
        return _backend

    backend_type = os.getenv("STORAGE_BACKEND", "local")

    if backend_type == "s3":
        s3_bucket = os.getenv("S3_BUCKET")
        s3_access_key = os.getenv("S3_ACCESS_KEY")
        s3_secret_key = os.getenv("S3_SECRET_KEY")

        missing = [
            name
            for name, val in (
                ("S3_BUCKET", s3_bucket),
                ("S3_ACCESS_KEY", s3_access_key),
                ("S3_SECRET_KEY", s3_secret_key),
            )
            if not val
        ]
        if missing:
            raise ValueError(
                f"STORAGE_BACKEND=s3 requires the following environment variables to be set: "
                f"{', '.join(missing)}"
            )

        _backend = S3StorageBackend(
            bucket=s3_bucket,  # type: ignore[arg-type]  # validated non-None above
            endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
            access_key=s3_access_key,  # type: ignore[arg-type]
            secret_key=s3_secret_key,  # type: ignore[arg-type]
            region=os.getenv("S3_REGION", "us-east-1"),
        )
    else:
        _backend = LocalStorageBackend(
            base_path=os.getenv("REPO_BASE_FOLDER", "data/repositories"),
        )

    return _backend
