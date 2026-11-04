"""Data access for the A2A agent snapshot (step_011, FR-4/FR-5/FR-9).

Both entry points eager-load everything `services.a2a_server.snapshot.A2AAgentSnapshot`
needs in exactly one query (`selectinload` for the agent's skill associations,
`joinedload` for the single-valued `app`/`ai_service`/`output_parser` relationships),
so building a card or a catalog entry never triggers a second round trip or a
lazy-load N+1 (NFR-8).
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from models.agent import Agent, AgentSkill


def _eager_loaded_query():
    return select(Agent).options(
        joinedload(Agent.app),
        joinedload(Agent.ai_service),
        joinedload(Agent.output_parser),
        selectinload(Agent.skill_associations).joinedload(AgentSkill.skill),
    )


def get_agent_for_app(db: Session, app_id: int, agent_id: int) -> Optional[Agent]:
    """Load one `Agent` scoped to `app_id`, eager-loaded for snapshot building.

    Returns `None` if the agent does not exist or belongs to a different app --
    the visibility service (step_011) treats both the same way (NFR-1/NFR-2).
    """
    stmt = _eager_loaded_query().where(Agent.agent_id == agent_id, Agent.app_id == app_id)
    return db.execute(stmt).unique().scalar_one_or_none()


def list_enabled_agents_for_app(db: Session, app_id: int) -> List[Agent]:
    """List the A2A-enabled, non-frozen agents of one app, ordered by `agent_id` ascending.

    Used by the catalog (FR-9); ordering is part of the catalog's stable contract.
    App-level freeze/disable is checked by the caller against the app row, not here.
    """
    stmt = (
        _eager_loaded_query()
        .where(
            Agent.app_id == app_id,
            Agent.a2a_enabled.is_(True),
            Agent.is_frozen.is_(False),
        )
        .order_by(Agent.agent_id.asc())
    )
    return list(db.execute(stmt).unique().scalars().all())


__all__ = ["get_agent_for_app", "list_enabled_agents_for_app"]
