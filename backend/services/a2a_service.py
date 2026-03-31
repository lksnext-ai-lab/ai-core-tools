from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.orm import Session

from models.a2a_agent import A2AAgent
from utils.logger import get_logger

logger = get_logger(__name__)


class A2AService:
    """Shared A2A helpers for validation, persistence, and health updates."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"
    INVALID = "invalid"

    SYNCED = "synced"
    ERROR = "error"

    @staticmethod
    def is_a2a_agent(agent: Any) -> bool:
        return bool(getattr(agent, "a2a_config", None))

    @staticmethod
    def split_card_url(card_url: str) -> tuple[str, str]:
        parsed = urlsplit(card_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("A2A card URL must be an absolute http(s) URL")
        if parsed.fragment:
            raise ValueError("A2A card URL must not include a fragment")

        base_url = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        path = parsed.path or "/.well-known/agent-card.json"
        if path == "/":
            path = "/.well-known/agent-card.json"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        return base_url, path

    @staticmethod
    async def _resolve_agent_card(card_url: str):
        try:
            import httpx
            from a2a.client import A2ACardResolver
        except ImportError as exc:
            raise RuntimeError(
                "A2A support requires the optional 'a2a-sdk' dependency to be installed."
            ) from exc

        if not card_url:
            raise ValueError("A2A card URL is required")

        base_url, relative_path = A2AService.split_card_url(card_url)
        timeout = httpx.Timeout(15.0, read=20.0)
        logger.info(
            "Resolving A2A card from %s (base_url=%s, path=%s)",
            card_url,
            base_url,
            relative_path,
        )

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
        ) as httpx_client:
            resolver = A2ACardResolver(httpx_client, base_url)
            agent_card = await resolver.get_agent_card(
                relative_card_path=relative_path
            )

        logger.info(
            "Resolved A2A card from %s with %s skill(s)",
            card_url,
            len(getattr(agent_card, "skills", []) or []),
        )
        return agent_card

    @staticmethod
    async def discover_card(card_url: str) -> dict[str, Any]:
        agent_card = await A2AService._resolve_agent_card(card_url)
        card_snapshot = agent_card.model_dump(mode="json", exclude_none=True)

        return {
            "card_url": card_url,
            "remote_agent_id": agent_card.url,
            "card": card_snapshot,
            "skills": card_snapshot.get("skills", []),
            "documentation_url": getattr(agent_card, "documentation_url", None),
            "icon_url": getattr(agent_card, "icon_url", None),
        }

    @staticmethod
    async def validate_source_config(
        source_config: dict[str, Any],
    ) -> dict[str, Any]:
        card_url = source_config.get("card_url")
        selected_skill_id = source_config.get("selected_skill_id")
        if not selected_skill_id:
            raise ValueError("An A2A skill must be selected")

        agent_card = await A2AService._resolve_agent_card(card_url)
        selected_skill = next(
            (skill for skill in agent_card.skills if skill.id == selected_skill_id),
            None,
        )
        if selected_skill is None:
            raise ValueError(
                f"Selected A2A skill '{selected_skill_id}' is no longer present in the agent card"
            )

        submitted_skill_snapshot = source_config.get("skill_snapshot") or {}
        snapshot_skill_id = submitted_skill_snapshot.get("id")
        if snapshot_skill_id and snapshot_skill_id != selected_skill_id:
            raise ValueError("Submitted A2A skill snapshot does not match the selected skill")

        now = datetime.utcnow()
        card_snapshot = agent_card.model_dump(mode="json", exclude_none=True)
        skill_snapshot = selected_skill.model_dump(mode="json", exclude_none=True)

        return {
            "card_url": card_url,
            "remote_agent_id": agent_card.url,
            "remote_skill_id": selected_skill.id,
            "remote_skill_name": selected_skill.name,
            "remote_agent_metadata": card_snapshot,
            "remote_skill_metadata": skill_snapshot,
            "sync_status": A2AService.SYNCED,
            "health_status": A2AService.HEALTHY,
            "last_successful_refresh_at": now,
            "last_refresh_attempt_at": now,
            "last_refresh_error": None,
            "documentation_url": getattr(agent_card, "documentation_url", None),
            "icon_url": getattr(agent_card, "icon_url", None),
        }

    @staticmethod
    def apply_source_config(record: A2AAgent, canonical_config: dict[str, Any]) -> A2AAgent:
        record.card_url = canonical_config["card_url"]
        record.remote_agent_id = canonical_config.get("remote_agent_id")
        record.remote_skill_id = canonical_config["remote_skill_id"]
        record.remote_skill_name = canonical_config["remote_skill_name"]
        record.remote_agent_metadata = canonical_config["remote_agent_metadata"]
        record.remote_skill_metadata = canonical_config["remote_skill_metadata"]
        record.sync_status = canonical_config.get("sync_status", A2AService.SYNCED)
        record.health_status = canonical_config.get("health_status", A2AService.HEALTHY)
        record.last_successful_refresh_at = canonical_config.get("last_successful_refresh_at")
        record.last_refresh_attempt_at = canonical_config.get("last_refresh_attempt_at")
        record.last_refresh_error = canonical_config.get("last_refresh_error")
        record.documentation_url = canonical_config.get("documentation_url")
        record.icon_url = canonical_config.get("icon_url")
        return record

    @staticmethod
    def serialize_record(record: Optional[A2AAgent]) -> Optional[dict[str, Any]]:
        if not record:
            return None

        return {
            "card_url": record.card_url,
            "remote_agent_id": record.remote_agent_id,
            "remote_skill_id": record.remote_skill_id,
            "remote_skill_name": record.remote_skill_name,
            "remote_agent_metadata": record.remote_agent_metadata or {},
            "remote_skill_metadata": record.remote_skill_metadata or {},
            "sync_status": record.sync_status,
            "health_status": record.health_status,
            "last_successful_refresh_at": record.last_successful_refresh_at,
            "last_refresh_attempt_at": record.last_refresh_attempt_at,
            "last_refresh_error": record.last_refresh_error,
            "documentation_url": record.documentation_url,
            "icon_url": record.icon_url,
        }

    @staticmethod
    def update_health(
        db: Session,
        record: Optional[A2AAgent],
        *,
        healthy: bool,
        error_summary: Optional[str] = None,
    ) -> None:
        if not record:
            return

        record.last_refresh_attempt_at = datetime.utcnow()
        if healthy:
            record.health_status = A2AService.HEALTHY
            record.sync_status = A2AService.SYNCED
            record.last_successful_refresh_at = record.last_refresh_attempt_at
            record.last_refresh_error = None
        else:
            record.health_status = A2AService.UNREACHABLE
            record.sync_status = A2AService.ERROR
            record.last_refresh_error = (error_summary or "Unknown A2A error")[:1000]

        logger.info(
            "Updated A2A health for agent %s: healthy=%s sync_status=%s health_status=%s error=%s",
            record.agent_id,
            healthy,
            record.sync_status,
            record.health_status,
            record.last_refresh_error,
        )
        db.add(record)
        db.commit()
