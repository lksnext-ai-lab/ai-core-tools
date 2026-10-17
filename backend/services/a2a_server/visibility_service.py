"""Discoverability resolution (AD-4 step 3, FR-4/FR-9/FR-10, NFR-1/NFR-2).

`resolve` is the single place that decides whether a (app_slug, agent_id)
pair is discoverable and, if so, whether the caller's optional API key makes
it *visible*. The router (step_017) calls it with a short-lived session that
it closes before dispatch (AD-4) and maps the result to the uniform 404 (no
app / no agent / agent in another app / A2A disabled / frozen / `api_key`
visibility without a valid key) or lets a visible agent through.

Every branch does only indexed PK/unique-index lookups -- no LLM or network
call on any path (NFR-2) -- so a 404 costs the same as a success and leaks
nothing about *why* a given (app_slug, agent_id) is not visible.

`reason` on `Resolution` is for structured logs only (NFR-7); the router must
never let it influence the response body or status beyond VISIBLE/NOT_FOUND,
or a timing/content side channel would reopen the enumeration the uniform
404 is meant to close.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from pydantic import SecretStr
from sqlalchemy.orm import Session

from repositories.a2a_agent_repository import get_agent_for_app, list_enabled_agents_for_app
from repositories.mcp_server_repository import AppSlugRepository
from services.a2a_server.snapshot import A2AAgentSnapshot, build_snapshot
from services.public_auth_service import PublicAuthService
from utils.a2a_config import get_a2a_config
from utils.logger import get_logger

logger = get_logger(__name__)

_auth_service = PublicAuthService()


class Outcome(Enum):
    """The only two outcomes a caller ever observes (FR-10)."""

    VISIBLE = "visible"
    NOT_FOUND = "not_found"


class Reason(Enum):
    """Internal-only, for structured logs (NFR-7). Never exposed to the caller.

    `AGENT_MISSING` covers both "no such agent id" and "that agent belongs to
    another app" (review round 2, LOW-5): distinguishing them would need an
    extra, branch-only query, which is exactly the kind of work-imbalance
    NFR-2 warns against on the 404 path. The response is NOT_FOUND either
    way, so the distinction bought nothing but a timing/query-count tell.
    """

    APP_MISSING = "app_missing"
    AGENT_MISSING = "agent_missing"
    DISABLED_GLOBAL = "disabled_global"
    DISABLED_AGENT = "disabled_agent"
    FROZEN_AGENT = "frozen_agent"
    FROZEN_APP = "frozen_app"
    OWNER_DEACTIVATED = "owner_deactivated"
    KEY_REQUIRED = "key_required"
    VISIBLE = "visible"


@dataclass(frozen=True)
class ValidKey:
    """A validated API key, carried alongside a `Resolution` for owner identity (AD-3).

    `raw` is wrapped in `SecretStr` for the same reason `A2ACallScope.api_key`
    is: so a stray `repr()`/log of this object never shows the plaintext key.
    """

    key_id: int
    key_hash: str
    raw: SecretStr


@dataclass(frozen=True)
class Resolution:
    outcome: Outcome
    reason: Reason
    snapshot: Optional[A2AAgentSnapshot]
    key: Optional[ValidKey]


def _not_found(reason: Reason) -> Resolution:
    return Resolution(outcome=Outcome.NOT_FOUND, reason=reason, snapshot=None, key=None)


def _hash_api_key(raw: str) -> str:
    from utils.security import hash_api_key  # local import: avoid any import-time cost on hot paths

    return hash_api_key(raw)


def _validate_key(db: Session, *, app_id: int, raw_api_key: Optional[str]) -> Optional[ValidKey]:
    """Looks up `raw_api_key` for `app_id` without raising and without side effects.

    A key of a different app is treated as no key (FR-10): `find_valid_key_for_app`
    is already scoped to `app_id`, so that case simply returns `None` here.
    """
    if not raw_api_key:
        return None
    api_key_obj = _auth_service.find_valid_key_for_app(db, app_id, raw_api_key)
    if api_key_obj is None:
        return None
    return ValidKey(key_id=api_key_obj.key_id, key_hash=_hash_api_key(raw_api_key), raw=SecretStr(raw_api_key))


def _owner_deactivated(app) -> bool:
    """True iff `app.owner` exists and is deactivated (review round 2, LOW-6).

    FR-4 does not literally list "owner deactivated" among its freeze/disable
    checks, but a deactivated owner is treated the same way the public API
    already treats one (`PublicAuthService._owner_is_active`): hiding is the
    safer default, so A2A mirrors it here rather than leaving the agent
    discoverable through a route the owner's account can no longer use.
    `app.owner` is a lazy relationship (`AppSlugRepository.get_by_slug` does
    not eager-load it); the extra query runs on *every* resolution,
    independent of any other branch, so it adds no per-branch timing tell.
    """
    owner = app.owner
    return bool(owner) and hasattr(owner, "is_active") and not owner.is_active


def resolve(
    db: Session, app_slug: str, agent_id: int, raw_api_key: Optional[str] = None
) -> Resolution:
    """Resolve discoverability + visibility for one (app_slug, agent_id) pair (FR-4).

    Args:
        db: Sync session; the caller (router) opens and closes it around this
            call only (AD-4), never reusing it for dispatch.
        app_slug: The app slug from the URL path.
        agent_id: The agent id from the URL path.
        raw_api_key: The caller's `X-API-KEY`, if any. Validated against
            `app_slug`'s app; a key of another app counts as no key. Looked
            up unconditionally once the app is known -- before the agent is
            even fetched -- so this call costs the same whether or not
            `agent_id` turns out to exist (review round 2, LOW-5).

    Returns:
        A `Resolution`. `outcome=NOT_FOUND` for every FR-4/FR-10 non-discoverable
        or non-visible case; `outcome=VISIBLE` otherwise, with `snapshot` always
        set and `key` set iff a valid key for this app was presented (independent
        of this agent's own visibility -- the router uses it for RPC auth, FR-10).
    """
    cfg = get_a2a_config()
    if not cfg.enabled:
        return _not_found(Reason.DISABLED_GLOBAL)

    app = AppSlugRepository.get_by_slug(db, app_slug)
    if app is None:
        return _not_found(Reason.APP_MISSING)

    if _owner_deactivated(app):
        return _not_found(Reason.OWNER_DEACTIVATED)

    # Run the key lookup before touching the agent at all: every path past this
    # point pays the same cost whether or not agent_id resolves (LOW-5).
    key = _validate_key(db, app_id=app.app_id, raw_api_key=raw_api_key)

    agent = get_agent_for_app(db, app.app_id, agent_id)
    if agent is None:
        return _not_found(Reason.AGENT_MISSING)

    if not agent.a2a_enabled:
        return _not_found(Reason.DISABLED_AGENT)

    if agent.is_frozen:
        return _not_found(Reason.FROZEN_AGENT)
    if app.is_frozen:
        return _not_found(Reason.FROZEN_APP)

    # Fail closed (LOW-3): anything other than the exact string "public"
    # requires a valid key, not just the literal "api_key" value.
    if agent.a2a_card_visibility != "public" and key is None:
        return _not_found(Reason.KEY_REQUIRED)

    snapshot = build_snapshot(agent)
    return Resolution(outcome=Outcome.VISIBLE, reason=Reason.VISIBLE, snapshot=snapshot, key=key)


def list_visible(db: Session, app_slug: str, raw_api_key: Optional[str] = None) -> List[A2AAgentSnapshot]:
    """List the agents visible to this caller for the FR-9 catalog, `agent_id` ascending.

    A missing app, a frozen app, a deactivated owner, or the global switch
    being off all yield an empty list -- the router turns an empty result
    into the FR-9 404, so no extra branching is needed here to keep that
    path uniform.
    """
    cfg = get_a2a_config()
    if not cfg.enabled:
        return []

    app = AppSlugRepository.get_by_slug(db, app_slug)
    if app is None or app.is_frozen:
        return []
    if _owner_deactivated(app):
        return []

    key = _validate_key(db, app_id=app.app_id, raw_api_key=raw_api_key)

    visible: List[A2AAgentSnapshot] = []
    for agent in list_enabled_agents_for_app(db, app.app_id):
        if agent.a2a_card_visibility != "public" and key is None:
            continue
        visible.append(build_snapshot(agent))
    return visible


def resolve_root(db: Session) -> Resolution:
    """Resolve `A2A_ROOT_AGENT` for the root `.well-known/agent-card.json` (FR-2).

    The configured agent must additionally be `public` visibility -- an
    `api_key` agent is never served at the unauthenticated root, even if it
    would otherwise be discoverable with a key.
    """
    cfg = get_a2a_config()
    if not cfg.root_agent:
        return _not_found(Reason.AGENT_MISSING)

    app_slug, _, agent_id_raw = cfg.root_agent.partition("/")
    try:
        agent_id = int(agent_id_raw)
    except ValueError:
        logger.warning("a2a.visibility.root_agent_malformed root_agent=%r", cfg.root_agent)
        return _not_found(Reason.AGENT_MISSING)

    resolution = resolve(db, app_slug, agent_id, raw_api_key=None)
    if resolution.outcome is not Outcome.VISIBLE:
        return resolution
    if resolution.snapshot is not None and resolution.snapshot.visibility != "public":
        return _not_found(Reason.KEY_REQUIRED)
    return resolution


__all__ = ["Outcome", "Reason", "ValidKey", "Resolution", "resolve", "list_visible", "resolve_root"]
