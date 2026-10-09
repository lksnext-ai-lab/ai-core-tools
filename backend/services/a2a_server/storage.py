"""Builds the SDK's cluster-aware task store and event stream, bound to the
`a2a_*`-prefixed tables via the registry in `sdk_models.py` (AD-2).

This module -- specifically `_bind_models` -- is the **only** place in the
codebase that writes a2a-sdk attributes that are not part of its documented
public constructor API. Everything else about the SDK objects (the engine,
the owner resolver, the poll interval) is passed through the public
constructors.

Two steps make the override safe:

1. `_build_task_store`/`_build_event_stream` (private -- `build_bound_storage`
   is the only public entry point) pass the SDK's *default* table names
   (`'tasks'`, `'task_events'`, `'task_versions'`) so the constructors take
   the no-factory branch and never call `create_task_model` et al.
   themselves. The objects therefore come back wired to the SDK's own
   `TaskModel`/`TaskEventModel`/`TaskVersionModel` -- harmless, inert metadata
   that is never queried because `create_table=False` means the SDK never
   calls `create_all` for them either.
2. `_bind_models` then swaps those SDK model classes out for the memoized
   `a2a_*` registry classes from `sdk_models.get_sdk_models()`.

Every assignment is guarded: before writing, `_bind_models` asserts the
target attribute already exists on the instance, is a class, and is a
subclass of the SDK's own public mixin for that role. If the installed SDK
ever stops satisfying one of these, `_bind_models` raises
`A2ASdkContractError` identifying exactly which attribute broke the contract
-- at startup, never mid-request. See
`tests/unit/services/a2a_server/test_sdk_contract_static.py` (shape/version,
no DB) and `tests/integration/a2a_server/test_sdk_contract.py` (behavioural,
real DB) for the suite that exercises this on every CI run and on every SDK
version bump.
"""

from __future__ import annotations

from a2a.server import models as a2a_sdk_models
from a2a.server.cluster.database_event_stream import DatabaseTaskEventStream
from a2a.server.cluster.database_task_store import VersionedDatabaseTaskStore
from a2a.server.cluster.task_store import VersionedTaskStore
from a2a.server.context import ServerCallContext
from a2a.server.owner_resolver import OwnerResolver
from db.database import async_engine as _default_async_engine
from services.a2a_server.sdk_models import (
    A2ASdkContractError,
    A2ASdkModels,
    get_sdk_models,
)
from sqlalchemy.ext.asyncio import AsyncEngine
from utils.logger import get_logger

logger = get_logger(__name__)

# AD-3: every owner string this registry resolves must be `f"a2a:{app_id}:{agent_id}:{api_key_hash}"`.
# Enforced fail-closed in `_fail_closed_owner_resolver` so a misconfigured or
# buggy `owner_resolver` can never silently scope a task under an empty or
# non-A2A owner (AC-32: cross-key/cross-app task access must be impossible).
_OWNER_PREFIX = "a2a:"

# The SDK default table names. Constructing the store/stream with exactly
# these names means the constructors take the "default model" branch and call
# no `create_*_model` factory (see AD-2 and the module docstring above).
_SDK_DEFAULT_TASKS_TABLE = "tasks"
_SDK_DEFAULT_EVENTS_TABLE = "task_events"
_SDK_DEFAULT_VERSIONS_TABLE = "task_versions"


def _require_subclass(obj: object, *, attr_name: str, owner_repr: str, expected_mixin: type) -> type:
    """Asserts `obj` is a class that subclasses `expected_mixin`.

    Raises `A2ASdkContractError` naming `attr_name` on failure. Called before
    every attribute write in `_bind_models`, never after.
    """
    if not isinstance(obj, type):
        raise A2ASdkContractError(
            f"a2a-sdk contract changed; review services/a2a_server/storage.py before bumping "
            f"the pin: expected {owner_repr}.{attr_name} to hold a class, got {type(obj)!r}"
        )
    if not issubclass(obj, expected_mixin):
        raise A2ASdkContractError(
            f"a2a-sdk contract changed; review services/a2a_server/storage.py before bumping "
            f"the pin: expected {owner_repr}.{attr_name} to subclass {expected_mixin.__name__}, "
            f"got {obj!r}"
        )
    return obj


def _fail_closed_owner_resolver(owner_resolver: OwnerResolver) -> OwnerResolver:
    """Wraps `owner_resolver` so an invalid owner can never reach the SDK.

    AC-32 requires that a task can never be scoped under an owner that is not
    an unambiguous `f"a2a:{app_id}:{agent_id}:{api_key_hash}"` string (AD-3).
    Rather than trust every call site to pass a correct resolver, every
    resolved owner is checked here, inside the store builder, each time the
    SDK calls it: empty or missing the `"a2a:"` prefix raises `PermissionError`
    before the SDK can use it to scope a read, write or list.
    """

    def _wrapped(context: ServerCallContext) -> str:
        owner = owner_resolver(context)
        if not owner or not owner.startswith(_OWNER_PREFIX):
            raise PermissionError(
                f"owner_resolver produced an invalid owner {owner!r}; expected a "
                f"{_OWNER_PREFIX!r}-prefixed string (AD-3) -- refusing to scope an a2a-sdk "
                "task store call under it"
            )
        return owner

    return _wrapped


def _bind_models(
    store: VersionedDatabaseTaskStore,
    stream: DatabaseTaskEventStream,
    models: A2ASdkModels,
) -> None:
    """Injects the `a2a_*` registry model classes into `store` and `stream`.

    The only function in the codebase that writes a2a-sdk attributes outside
    its public constructor API. Each write is preceded by a contract check
    (see `_require_subclass`); a failing check raises `A2ASdkContractError`
    before any attribute is assigned.
    """
    task_store = store.as_task_store  # public property (AD-2 point 3)
    _require_subclass(
        task_store.task_model,
        attr_name="task_model",
        owner_repr="store.as_task_store",
        expected_mixin=a2a_sdk_models.TaskMixin,
    )
    _require_subclass(
        store._event_model,  # contract: test_sdk_contract_static.py::test_bound_storage_attributes
        attr_name="_event_model",
        owner_repr="store",
        expected_mixin=a2a_sdk_models.TaskEventMixin,
    )
    _require_subclass(
        store._version_model,  # contract: test_sdk_contract_static.py::test_bound_storage_attributes
        attr_name="_version_model",
        owner_repr="store",
        expected_mixin=a2a_sdk_models.TaskVersionMixin,
    )
    _require_subclass(
        stream._event_model,  # contract: test_sdk_contract_static.py::test_bound_storage_attributes
        attr_name="_event_model",
        owner_repr="stream",
        expected_mixin=a2a_sdk_models.TaskEventMixin,
    )

    # All four checks passed; now perform the narrow injection.
    task_store.task_model = models.task  # public name (AD-2 point 3)
    store._event_model = models.event  # contract: test_sdk_contract_static.py::test_bound_storage_attributes
    store._version_model = models.version  # contract: test_sdk_contract_static.py::test_bound_storage_attributes
    stream._event_model = models.event  # contract: test_sdk_contract_static.py::test_bound_storage_attributes

    logger.debug(
        "Bound a2a-sdk store/stream to registry models (tables=%s,%s,%s)",
        models.task.__tablename__,
        models.event.__tablename__,
        models.version.__tablename__,
    )


def _build_task_store(
    *,
    engine: AsyncEngine | None,
    owner_resolver: OwnerResolver,
    max_attempts: int | None = None,
    retry_delay_s: float | None = None,
) -> VersionedDatabaseTaskStore:
    """Builds a `VersionedDatabaseTaskStore` with the SDK's default table names.

    `create_table=False`: the SDK never calls `create_all`; only Alembic
    creates the `a2a_*` tables (FR-14). The shared async engine
    (`db.database.async_engine`) is reused by default so no second connection
    pool is created (NFR-4). `owner_resolver` is required (no default) and is
    always wrapped fail-closed (`_fail_closed_owner_resolver`) -- see AC-32.

    Private: not exported. `build_bound_storage` is the only supported way to
    get a store wired to the `a2a_*` tables (AD-2); a store built here alone
    is still bound to the SDK's own, unused, default models.
    """
    kwargs: dict = {
        "engine": engine or _default_async_engine,
        "create_table": False,
        "table_name": _SDK_DEFAULT_TASKS_TABLE,
        "owner_resolver": _fail_closed_owner_resolver(owner_resolver),
        "event_table_name": _SDK_DEFAULT_EVENTS_TABLE,
        "version_table_name": _SDK_DEFAULT_VERSIONS_TABLE,
    }
    if max_attempts is not None:
        kwargs["max_attempts"] = max_attempts
    if retry_delay_s is not None:
        kwargs["retry_delay_s"] = retry_delay_s
    return VersionedDatabaseTaskStore(**kwargs)


def _build_event_stream(
    *,
    engine: AsyncEngine | None,
    poll_interval_s: float = 0.5,
) -> DatabaseTaskEventStream:
    """Builds a `DatabaseTaskEventStream` with the SDK's default table name.

    `create_table=False`, for the same reason as `_build_task_store`. Private
    for the same reason: only `build_bound_storage` returns a stream actually
    bound to the `a2a_*` tables.
    """
    return DatabaseTaskEventStream(
        engine=engine or _default_async_engine,
        create_table=False,
        table_name=_SDK_DEFAULT_EVENTS_TABLE,
        poll_interval_s=poll_interval_s,
    )


def build_bound_storage(
    *,
    owner_resolver: OwnerResolver,
    engine: AsyncEngine | None = None,
    poll_interval_s: float = 0.5,
) -> tuple[VersionedTaskStore, DatabaseTaskEventStream]:
    """Builds a store+stream pair, bound to the `a2a_*` registry models.

    `owner_resolver` is required (keyword-only, no default): every A2A caller
    must supply AD-3's `f"a2a:{app_id}:{agent_id}:{api_key_hash}"` resolver
    explicitly, and the builder wraps it fail-closed (AC-32) regardless.

    Safe to call more than once per process (AC-33 runs two in one test
    process to simulate two uvicorn workers sharing one database): the
    registry in `sdk_models.get_sdk_models()` is memoized, so every call
    returns objects bound to the *same* model classes, never new ones.
    """
    store = _build_task_store(engine=engine, owner_resolver=owner_resolver)
    stream = _build_event_stream(engine=engine, poll_interval_s=poll_interval_s)
    _bind_models(store, stream, get_sdk_models())
    return store, stream


__all__ = [
    "build_bound_storage",
]
