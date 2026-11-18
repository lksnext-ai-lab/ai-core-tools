"""Per-pool sizing and pg_stat_activity tagging of every Postgres connection pool."""

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from scheduling import periodic_agent_task
from services import agent_cache_service
from services.agent_cache_service import CheckpointerCacheService

DATABASE_MODULE_PATH = Path(__file__).resolve().parents[3] / "backend" / "db" / "database.py"
POSTGRES_URL = "postgresql://user:pass@db:5432/app"

POOL_ENV_VARS = (
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_ASYNC_POOL_SIZE",
    "DB_ASYNC_MAX_OVERFLOW",
)


def _load_database_module(monkeypatch, **env):
    """Execute db/database.py in isolation, capturing the engine kwargs instead of connecting."""
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", POSTGRES_URL)
    for name in POOL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    create_engine = MagicMock(name="create_engine")
    create_async_engine = MagicMock(name="create_async_engine")
    monkeypatch.setattr("sqlalchemy.create_engine", create_engine)
    monkeypatch.setattr("sqlalchemy.ext.asyncio.create_async_engine", create_async_engine)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

    spec = importlib.util.spec_from_file_location("database_under_test", DATABASE_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return create_engine.call_args.kwargs, create_async_engine.call_args.kwargs


class TestSqlAlchemyPools:
    def test_defaults_keep_sync_pool_and_size_async_pool_separately(self, monkeypatch):
        sync_kwargs, async_kwargs = _load_database_module(monkeypatch)

        assert (sync_kwargs["pool_size"], sync_kwargs["max_overflow"]) == (20, 10)
        assert (async_kwargs["pool_size"], async_kwargs["max_overflow"]) == (5, 5)

    def test_async_pool_no_longer_follows_the_sync_pool_settings(self, monkeypatch):
        sync_kwargs, async_kwargs = _load_database_module(
            monkeypatch,
            DB_POOL_SIZE="10",
            DB_MAX_OVERFLOW="10",
            DB_ASYNC_POOL_SIZE="2",
            DB_ASYNC_MAX_OVERFLOW="3",
        )

        assert (sync_kwargs["pool_size"], sync_kwargs["max_overflow"]) == (10, 10)
        assert (async_kwargs["pool_size"], async_kwargs["max_overflow"]) == (2, 3)

    def test_each_engine_tags_its_connections(self, monkeypatch):
        sync_kwargs, async_kwargs = _load_database_module(monkeypatch)

        assert sync_kwargs["connect_args"]["application_name"] == "mattin-api"
        assert async_kwargs["connect_args"]["application_name"] == "mattin-api-async"


class TestCheckpointerPool:
    async def test_pool_uses_configured_size_and_tags_its_connections(self, monkeypatch):
        pool = MagicMock()
        pool.open = AsyncMock()
        pool_class = MagicMock(return_value=pool)
        saver = MagicMock()
        saver.setup = AsyncMock()
        monkeypatch.setattr(agent_cache_service, "AsyncConnectionPool", pool_class)
        monkeypatch.setattr(agent_cache_service, "AsyncPostgresSaver", MagicMock(return_value=saver))
        monkeypatch.setattr(agent_cache_service, "CHECKPOINTER_POOL_MIN", 1)
        monkeypatch.setattr(agent_cache_service, "CHECKPOINTER_POOL_MAX", 5)
        monkeypatch.setattr(CheckpointerCacheService, "_db_uri", POSTGRES_URL)
        monkeypatch.setattr(CheckpointerCacheService, "_pool", None)
        monkeypatch.setattr(CheckpointerCacheService, "_checkpointer", None)
        monkeypatch.setattr(CheckpointerCacheService, "_is_setup_done", False)

        await CheckpointerCacheService.initialize_pool()

        kwargs = pool_class.call_args.kwargs
        assert (kwargs["min_size"], kwargs["max_size"]) == (1, 5)
        assert kwargs["kwargs"]["application_name"] == "mattin-checkpointer"
        assert kwargs["kwargs"]["autocommit"] is True

    def test_defaults_match_previous_hardcoded_sizes(self):
        assert (agent_cache_service.CHECKPOINTER_POOL_MIN, agent_cache_service.CHECKPOINTER_POOL_MAX) == (2, 10)


class TestDbosSystemPool:
    def test_unset_keeps_the_dbos_default(self, monkeypatch):
        monkeypatch.delenv("DBOS_SYS_DB_POOL_SIZE", raising=False)
        assert periodic_agent_task._sys_db_pool_size() is None

    def test_configured_size_is_used(self, monkeypatch):
        monkeypatch.setenv("DBOS_SYS_DB_POOL_SIZE", "10")
        assert periodic_agent_task._sys_db_pool_size() == 10

    def test_size_below_dbos_minimum_fails_at_startup(self, monkeypatch):
        monkeypatch.setenv("DBOS_SYS_DB_POOL_SIZE", "4")
        with pytest.raises(ValueError, match="at least 5"):
            periodic_agent_task._sys_db_pool_size()
