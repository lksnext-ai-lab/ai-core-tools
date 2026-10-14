"""Async data access for the pinned a2a-sdk tables (step_018/AD-10, RB-11).

Uses only the registry models from `services.a2a_server.sdk_models.get_sdk_models()` (never the SDK's
unprefixed defaults) on the shared `db.database.async_engine`. Owner prefixes are built by the caller
(`identity.owner_prefix`); this module only matches them with an escaped `LIKE`. All timestamps are
naive UTC, matching the SDK `DateTime` columns.

Every batched loop selects primary keys with an `ORDER BY` + `LIMIT`, deletes exactly those rows and
commits, so each iteration removes the rows it selected and the loop always makes progress.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from a2a.types.a2a_pb2 import TaskState
from sqlalchemy import BigInteger, and_, case, cast, delete, exists, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import async_sessionmaker

from db.database import async_engine
from services.a2a_server.sdk_models import get_sdk_models
from services.a2a_server.task_states import TERMINAL_TASK_STATES

# Names as persisted in `status['state']` (a2a-sdk writes the protobuf enum name via MessageToDict).
TERMINAL_STATE_NAMES: Tuple[str, ...] = tuple(sorted(TaskState.Name(state) for state in TERMINAL_TASK_STATES))

_AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)

_DEFAULT_BATCH = 500
_DEFAULT_OWNER_PAGE = 1000
# Owners whose app/agent segments are numeric (AD-3 shape prefix); anything else is ignored.
_OWNER_IDS_REGEX = r"^a2a:[0-9]{1,18}:[0-9]{1,18}:"


def _escape_like(value: str) -> str:
    """Escapes `%`, `_` and backslash so `value` matches literally as a `LIKE` prefix."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _state_name():
    return get_sdk_models().task.status["state"].as_string()


class A2ATaskRepository:
    """Async data access for `a2a_tasks`/`a2a_task_events`/`a2a_task_versions`."""

    @staticmethod
    async def list_nonterminal_by_prefix(prefix: str) -> List[Tuple[str, str]]:
        """Returns `(task_id, owner)` for every non-terminal task whose owner starts with `prefix`."""
        task = get_sdk_models().task
        async with _AsyncSessionLocal() as session:
            stmt = (
                select(task.id, task.owner)
                .where(
                    task.owner.like(f"{_escape_like(prefix)}%", escape="\\"),
                    _state_name().not_in(TERMINAL_STATE_NAMES),
                )
                .order_by(task.id)
            )
            return [(row[0], row[1]) for row in (await session.execute(stmt)).all()]

    @staticmethod
    async def purge_prefix(prefix: str, batch: int = _DEFAULT_BATCH) -> int:
        """Deletes every task, event and version whose owner starts with `prefix`.

        Tasks are deleted in batches together with their events/versions (one transaction per
        batch); then any remaining owner-scoped events/versions (e.g. rows whose task row was
        already gone) are deleted by PK batches.

        Returns:
            Number of task rows deleted.
        """
        models = get_sdk_models()
        pattern = f"{_escape_like(prefix)}%"
        total = 0
        async with _AsyncSessionLocal() as session:
            while True:
                ids = (
                    await session.execute(
                        select(models.task.id)
                        .where(models.task.owner.like(pattern, escape="\\"))
                        .order_by(models.task.id)
                        .limit(batch)
                    )
                ).scalars().all()
                if not ids:
                    break
                await session.execute(delete(models.event).where(models.event.task_id.in_(ids)))
                await session.execute(delete(models.version).where(models.version.task_id.in_(ids)))
                result = await session.execute(delete(models.task).where(models.task.id.in_(ids)))
                await session.commit()
                total += result.rowcount or 0

            while True:
                seqs = (
                    await session.execute(
                        select(models.event.seq)
                        .where(models.event.owner.like(pattern, escape="\\"))
                        .order_by(models.event.seq)
                        .limit(batch)
                    )
                ).scalars().all()
                if not seqs:
                    break
                await session.execute(delete(models.event).where(models.event.seq.in_(seqs)))
                await session.commit()

            while True:
                version_ids = (
                    await session.execute(
                        select(models.version.task_id)
                        .where(models.version.owner.like(pattern, escape="\\"))
                        .order_by(models.version.task_id)
                        .limit(batch)
                    )
                ).scalars().all()
                if not version_ids:
                    break
                await session.execute(delete(models.version).where(models.version.task_id.in_(version_ids)))
                await session.commit()
        return total

    @staticmethod
    async def list_stale_nonterminal(cutoff: datetime, limit: int) -> List[Tuple[str, str]]:
        """Returns up to `limit` `(task_id, owner)` non-terminal tasks with `last_updated < cutoff`."""
        task = get_sdk_models().task
        async with _AsyncSessionLocal() as session:
            stmt = (
                select(task.id, task.owner)
                .where(
                    task.last_updated.isnot(None),
                    task.last_updated < cutoff,
                    _state_name().not_in(TERMINAL_STATE_NAMES),
                )
                .order_by(task.last_updated, task.id)
                .limit(limit)
            )
            return [(row[0], row[1]) for row in (await session.execute(stmt)).all()]

    @staticmethod
    async def purge_older_than(cutoff: datetime, batch: int = _DEFAULT_BATCH) -> int:
        """Deletes tasks older than `cutoff`, with their events and versions in the same transaction.

        Purged: `last_updated < cutoff`, plus `last_updated IS NULL` tasks that have no version row
        (incomplete writes). A NULL-timestamp task that still has a version row is kept.

        Returns:
            Number of task rows deleted.
        """
        models = get_sdk_models()
        task = models.task
        has_version = exists(select(models.version.task_id).where(models.version.task_id == task.id))
        total = 0
        async with _AsyncSessionLocal() as session:
            while True:
                ids = (
                    await session.execute(
                        select(task.id)
                        .where(
                            or_(
                                and_(task.last_updated.isnot(None), task.last_updated < cutoff),
                                and_(task.last_updated.is_(None), ~has_version),
                            )
                        )
                        .order_by(task.id)
                        .limit(batch)
                    )
                ).scalars().all()
                if not ids:
                    break
                await session.execute(delete(models.event).where(models.event.task_id.in_(ids)))
                await session.execute(delete(models.version).where(models.version.task_id.in_(ids)))
                result = await session.execute(delete(task).where(task.id.in_(ids)))
                await session.commit()
                total += result.rowcount or 0
        return total

    @staticmethod
    async def purge_terminal_events_older_than(cutoff: datetime, batch: int = _DEFAULT_BATCH) -> int:
        """RB-6: deletes events of terminal tasks whose `last_updated < cutoff` (tasks/versions kept).

        Driven from the events side: each batch selects event PKs (joined to their task) and deletes
        exactly those, so the loop ends once no matching event remains.

        Returns:
            Number of event rows deleted.
        """
        models = get_sdk_models()
        event, task = models.event, models.task
        total = 0
        async with _AsyncSessionLocal() as session:
            while True:
                seqs = (
                    await session.execute(
                        select(event.seq)
                        .join(task, task.id == event.task_id)
                        .where(
                            task.last_updated.isnot(None),
                            task.last_updated < cutoff,
                            _state_name().in_(TERMINAL_STATE_NAMES),
                        )
                        .order_by(event.seq)
                        .limit(batch)
                    )
                ).scalars().all()
                if not seqs:
                    break
                result = await session.execute(delete(event).where(event.seq.in_(seqs)))
                await session.commit()
                total += result.rowcount or 0
        return total

    @staticmethod
    async def list_owner_agent_ids(
        after: Optional[Tuple[int, int]] = None, limit: int = _DEFAULT_OWNER_PAGE
    ) -> List[Tuple[int, int]]:
        """One keyset page of distinct `(app_id, agent_id)` pairs parsed from task owners in SQL.

        Args:
            after: The last pair of the previous page (exclusive), or None for the first page.
            limit: Page size.

        Returns:
            Pairs in ascending `(app_id, agent_id)` order; owners not shaped `a2a:{int}:{int}:` are skipped.
        """
        task = get_sdk_models().task
        well_formed = task.owner.regexp_match(_OWNER_IDS_REGEX)
        # CASE guards the casts: Postgres does not guarantee WHERE predicate evaluation order.
        app_id = case((well_formed, cast(func.split_part(task.owner, ":", 2), BigInteger)), else_=None)
        agent_id = case((well_formed, cast(func.split_part(task.owner, ":", 3), BigInteger)), else_=None)
        stmt = select(app_id, agent_id).where(well_formed).distinct()
        if after is not None:
            stmt = stmt.where(tuple_(app_id, agent_id) > tuple_(after[0], after[1]))
        stmt = stmt.order_by(app_id, agent_id).limit(limit)
        async with _AsyncSessionLocal() as session:
            return [(int(row[0]), int(row[1])) for row in (await session.execute(stmt)).all()]


__all__ = ["A2ATaskRepository", "TERMINAL_STATE_NAMES"]
