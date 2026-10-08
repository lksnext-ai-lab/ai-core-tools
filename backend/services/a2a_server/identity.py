"""Task owner identity and per-call scope (AD-3).

Every A2A task is scoped to an **owner string**,
``f"a2a:{app_id}:{agent_id}:{api_key_hash}"`` (``owner_for``), which the
pinned a2a-sdk store/stream use verbatim as the tenant partition for every
read, write and list (AD-2/FR-15). This module is the single source of truth
for that format:

- ``owner_for``/``owner_prefix``/``parse_owner`` build and take apart the
  string. The ``:`` delimiters make a prefix match unambiguous: the purge
  queue (AD-10/step_018) matches ``f"a2a:{app_id}:"`` or
  ``f"a2a:{app_id}:{agent_id}:"`` and must never also match a different
  ``app_id``/``agent_id`` that merely shares a numeric prefix (``a2a:1:``
  must not match an owner starting ``a2a:12:``).
- ``A2ACallerUser``/``resolve_a2a_owner`` adapt that owner string to the
  SDK's ``a2a.auth.user.User`` interface and its ``OwnerResolver`` callable
  type (``services/a2a_server/storage.py`` wraps ``resolve_a2a_owner`` a
  second time, fail-closed -- this module only has to produce it, not also
  guard it; defense in depth lives in both places).
- ``A2ACallScope``/``A2ARequestLog`` carry everything the router resolves
  once (visibility, the raw key, the agent snapshot, request bookkeeping)
  through ``ServerCallContext.state["a2a"]`` (AD-3) so no downstream piece
  -- the context builders, the executor bridge -- needs its own DB round
  trip to re-derive it.
- ``context_for_owner`` builds a bare context for the maintenance worker
  (AD-10), which calls the handler directly (never through the router) to
  cancel an owner's tasks and therefore has no request to build a scope
  from.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Tuple

from a2a.auth.user import User
from a2a.server.context import ServerCallContext
from pydantic import SecretStr

if TYPE_CHECKING:
    # step_011; forward-reference only (this module never imports snapshot.py
    # at runtime -- `from __future__ import annotations` makes every
    # annotation in this file a lazy string, so the class remains usable even
    # before snapshot.py exists).
    from services.a2a_server.snapshot import A2AAgentSnapshot

# AD-3: owner = f"a2a:{app_id}:{agent_id}:{api_key_hash}", api_key_hash being
# the 64 lowercase hex characters from utils.security.hash_api_key.
_OWNER_PATTERN = re.compile(r"^a2a:(\d+):(\d+):([0-9a-f]{64})$")


def _require_owner_shape(owner: str) -> str:
    """Raises `ValueError` unless `owner` matches the exact AD-3 shape.

    The message never includes the offending `owner` value itself (fix
    round 1, item 8): it embeds the caller's `api_key_hash`, a stable
    per-key identifier, and this `ValueError` can propagate to a log line
    (or, in theory, an exception message surfaced by a layer above this
    one) in a way a plain length/shape description cannot.
    """
    if not _OWNER_PATTERN.match(owner):
        raise ValueError(
            f"owner string (length {len(owner)}) does not match the AD-3 shape "
            "'a2a:{app_id}:{agent_id}:{64-hex-char key hash}'"
        )
    return owner


def owner_for(app_id: int, agent_id: int, key_hash: str) -> str:
    """Builds the AD-3 owner string for one (app, agent, api key) triple.

    Raises `ValueError` if the result does not match `_OWNER_PATTERN` --
    e.g. a negative id, or a `key_hash` that is not exactly 64 lowercase hex
    characters -- so a caller-side bug can never silently produce an owner
    string the fail-closed resolver (`storage._fail_closed_owner_resolver`)
    would otherwise have to catch later, deeper in the SDK call stack.
    """
    return _require_owner_shape(f"a2a:{app_id}:{agent_id}:{key_hash}")


def owner_prefix(app_id: int, agent_id: Optional[int] = None) -> str:
    """Builds an unambiguous owner prefix for `LIKE`/`startswith` purge matches.

    `owner_prefix(1)` is `"a2a:1:"`, which is a prefix of every owner for app
    1 and of *no* owner for app 12 (`"a2a:12:..."`) -- the trailing `:` after
    each numeric segment is what prevents the digit-prefix collision.
    """
    if agent_id is None:
        return f"a2a:{app_id}:"
    return f"a2a:{app_id}:{agent_id}:"


def parse_owner(owner: str) -> Optional[Tuple[int, int, str]]:
    """Parses an AD-3 owner string back into `(app_id, agent_id, key_hash)`.

    Returns `None` for anything that does not match the exact shape --
    never raises, so callers that scan arbitrary rows (e.g. the orphan sweep,
    step_018) can simply skip what does not parse.
    """
    match = _OWNER_PATTERN.match(owner)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), match.group(3)


class A2ACallerUser(User):
    """Adapts an AD-3 owner string to the SDK's `a2a.auth.user.User` interface.

    Always authenticated: by the time one of these is constructed, the
    caller already holds a valid API key (visibility resolution happens
    before the context builder ever runs, AD-4).
    """

    def __init__(self, owner: str) -> None:
        self._owner = _require_owner_shape(owner)

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def user_name(self) -> str:
        return self._owner


def resolve_a2a_owner(ctx: ServerCallContext) -> str:
    """The `OwnerResolver` passed to `storage.build_bound_storage` (AD-2/AD-3).

    Defense in depth: raises if `ctx.user` is not an `A2ACallerUser`, so a
    context built by anything other than `A2AServerCallContextBuilder` (or
    `context_for_owner`) can never scope a store call. `storage.py`'s
    `_fail_closed_owner_resolver` wraps this a second time to also reject an
    empty or non-`"a2a:"`-prefixed result (AC-32) -- this function only has
    to produce the owner, not also validate its shape.
    """
    if not isinstance(ctx.user, A2ACallerUser):
        raise PermissionError(
            f"expected an A2ACallerUser, got {type(ctx.user).__name__}; refusing to "
            "resolve an a2a-sdk owner for this context"
        )
    return ctx.user.user_name


@dataclass
class A2ARequestLog:
    """Per-RPC request bookkeeping, filled in as the request progresses.

    `emit` logs exactly one structured line (never the raw key or the key
    hash -- see the module docstring and the shared conventions in plan.md).
    """

    method: str
    task_id: Optional[str] = None
    context_id: Optional[str] = None
    conversation_id: Optional[int] = None
    outcome: Optional[str] = None
    started_monotonic: float = field(default_factory=time.monotonic)

    def emit(self, logger, *, app_id: int, agent_id: int, api_key_id: int) -> None:
        """Logs exactly one structured line for this RPC.

        `app_id`/`agent_id`/`api_key_id` identify the caller (from the
        enclosing `A2ACallScope`, which the call site already holds);
        never the raw key or its hash. The fields are both interpolated
        into the human-readable message and passed via `extra=` for
        structured-log consumers.
        """
        latency_ms = round((time.monotonic() - self.started_monotonic) * 1000.0, 1)
        fields = {
            "app_id": app_id,
            "agent_id": agent_id,
            "api_key_id": api_key_id,
            "method": self.method,
            "task_id": self.task_id,
            "context_id": self.context_id,
            "conversation_id": self.conversation_id,
            "latency_ms": latency_ms,
            "outcome": self.outcome,
        }
        message = "a2a.rpc " + " ".join(f"{key}={value}" for key, value in fields.items())
        logger.info(message, extra=fields)


@dataclass(frozen=True)
class A2ACallScope:
    """Everything the router resolves once per request, carried through
    `ServerCallContext.state["a2a"]` (AD-3).

    `api_key` is wrapped in `pydantic.SecretStr` because the SDK logs
    `call_context` (which embeds this scope) at DEBUG -- `repr(scope)` and
    `str(scope)` therefore never show the raw key, only `SecretStr`'s own
    masked representation. `api_key_hash`, `snapshot` and `request_log` are
    excluded from the dataclass-generated `repr` outright (`repr=False`):
    the hash is still sensitive enough (a stable per-key identifier) to keep
    out of casual log/debugger output, and the snapshot/request_log repr
    would otherwise be large and noisy without adding safety value.
    """

    app_id: int
    app_slug: str
    agent_id: int
    api_key_id: int
    api_key_hash: str = field(repr=False)
    api_key: SecretStr = field()
    snapshot: "A2AAgentSnapshot" = field(repr=False)
    request_log: A2ARequestLog = field(repr=False)
    base_url: str = field()


def context_for_owner(owner: str) -> ServerCallContext:
    """Builds a bare `ServerCallContext` for the maintenance worker (AD-10).

    No `"a2a"` scope: the maintenance worker calls the handler directly to
    cancel an owner's tasks on shutdown/app-deletion, never through the
    router, so there is no per-request snapshot/key to attach. `state["headers"]`
    still carries `a2a-version`, because the SDK's `validate_version` reads it
    unconditionally (AD-3) and a missing header is otherwise silently treated
    as protocol version 0.3.
    """
    return ServerCallContext(user=A2ACallerUser(owner), state={"headers": {"a2a-version": "1.0"}})


__all__ = [
    "owner_for",
    "owner_prefix",
    "parse_owner",
    "A2ACallerUser",
    "resolve_a2a_owner",
    "A2ARequestLog",
    "A2ACallScope",
    "context_for_owner",
]
