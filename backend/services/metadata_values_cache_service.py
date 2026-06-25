"""
In-memory thread-safe cache for distinct metadata field values per silo.

Cache key: (silo_id, field). TTL configurable via
METADATA_VALUES_CACHE_TTL_SECONDS env var (default 600 s).

Multi-process contract: this cache is process-local.  ``invalidate()`` only
evicts entries in the calling process; other workers serve stale values until
their TTL expires.  A cross-process cache (Redis) is not justified for
non-critical metadata hint lists.

SiloService is imported lazily inside ``_fetch_from_vector_store`` to break the
circular dependency: silo_service → metadata_values_cache_service → silo_service.
"""

import os
import threading
import time
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_TTL_SECONDS = 600
_ENV_VAR_NAME = "METADATA_VALUES_CACHE_TTL_SECONDS"

_SAMPLING_LIMIT = 50


def _parse_ttl_from_env() -> int:
    """Read TTL from env. Falls back to ``_DEFAULT_TTL_SECONDS`` with a WARNING on invalid input."""
    raw = os.getenv(_ENV_VAR_NAME)
    if raw is None:
        return _DEFAULT_TTL_SECONDS
    try:
        value = int(raw)
        if value <= 0:
            raise ValueError(f"TTL must be positive, got {value}")
        return value
    except ValueError:
        logger.warning(
            "Invalid value for %s: %r — must be a positive integer. "
            "Using default TTL of %d seconds.",
            _ENV_VAR_NAME,
            raw,
            _DEFAULT_TTL_SECONDS,
        )
        return _DEFAULT_TTL_SECONDS


class _CacheEntry:
    __slots__ = ("values", "expires_at")

    def __init__(self, values: list[str], ttl_seconds: int) -> None:
        self.values: list[str] = values
        self.expires_at: float = time.monotonic() + ttl_seconds


class MetadataValuesCacheService:
    """Singleton in-memory cache for distinct metadata field values per silo.

    Thread-safe via a single Lock.  On a cache miss the lock is released before
    calling SiloService (I/O) to avoid holding it during blocking operations.
    Two concurrent misses for the same key both query the vector store; the
    second write overwrites the first (allow-duplicate-fetch, no deadlock).

    On error an empty list is returned and the result is NOT cached so that a
    transient error does not poison the cache for the full TTL.
    """

    _cache: dict[tuple[int, str], _CacheEntry] = {}
    _lock: threading.Lock = threading.Lock()
    _ttl_seconds: int = _parse_ttl_from_env()

    @classmethod
    def get_distinct_values(
        cls,
        silo_id: int,
        field: str,
        db,
    ) -> list[str]:
        """Return distinct values for *field* in a silo's vector collection.

        Serves from cache when valid; queries SiloService on a miss.  Returns
        an empty list on error (result not cached).
        """
        cache_key = (silo_id, field)

        with cls._lock:
            entry = cls._cache.get(cache_key)
            if entry is not None and time.monotonic() < entry.expires_at:
                logger.debug(
                    "metadata_values_cache HIT silo=%d field=%r", silo_id, field
                )
                return list(entry.values)

        logger.info(
            "metadata_values_cache MISS silo=%d field=%r — querying vector store",
            silo_id,
            field,
        )
        query_start = time.monotonic()

        values = cls._fetch_from_vector_store(silo_id, field, db)

        elapsed_ms = (time.monotonic() - query_start) * 1000

        # None signals an error; empty list is a valid "no values" result.
        if values is not None:
            logger.info(
                "metadata_values_cache: fetched %d value(s) for silo=%d field=%r in %.1f ms",
                len(values),
                silo_id,
                field,
                elapsed_ms,
            )
            with cls._lock:
                cls._cache[cache_key] = _CacheEntry(values, cls._ttl_seconds)
            return list(values)

        return []

    @classmethod
    def invalidate(cls, silo_id: int) -> None:
        """Remove all cached entries for a silo.

        Must be called from every write path that changes the vector collection.
        Callers wrap this in try/except so a cache failure never blocks the write.
        """
        with cls._lock:
            keys_to_delete = [k for k in cls._cache if k[0] == silo_id]
            for key in keys_to_delete:
                del cls._cache[key]

        if keys_to_delete:
            logger.debug(
                "metadata_values_cache: invalidated %d entry/entries for silo=%d",
                len(keys_to_delete),
                silo_id,
            )

    @classmethod
    def _fetch_from_vector_store(
        cls,
        silo_id: int,
        field: str,
        db,
    ) -> Optional[list[str]]:
        """Fetch values from SiloService. Returns None on any exception."""
        try:
            # Deferred import to avoid the circular dependency described in the module docstring.
            from services.silo_service import SiloService  # noqa: PLC0415

            return SiloService.get_metadata_field_values(
                silo_id=silo_id,
                field=field,
                prefix=None,
                limit=_SAMPLING_LIMIT,
                db=db,
            )
        except Exception as exc:
            logger.warning(
                "metadata_values_cache: error fetching values for silo=%d field=%r: %s — "
                "returning empty list (result will not be cached)",
                silo_id,
                field,
                exc,
            )
            return None

    @classmethod
    def _reset_for_testing(cls) -> None:
        """Clear all cache state and reset TTL to default. Unit tests only."""
        with cls._lock:
            cls._cache.clear()
            cls._ttl_seconds = _DEFAULT_TTL_SECONDS
