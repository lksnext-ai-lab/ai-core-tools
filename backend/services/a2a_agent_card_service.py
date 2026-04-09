import os
from typing import Optional

from a2a.types import (
    APIKeySecurityScheme,
    AgentCapabilities,
    AgentCard,
    AgentProvider,
    AgentSkill,
    In,
    SecurityScheme,
)
from config import CLIENT_CONFIG
from models.agent import Agent
from models.app import App


DEFAULT_INPUT_MODES = [
    "text/plain",
    "text/markdown",
    "application/json",
    "text/csv",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
]

DEFAULT_OUTPUT_MODES = [
    "text/plain",
    "application/json",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/octet-stream",
]


class A2AAgentCardService:
    """Build Agent Cards for A2A-enabled Mattin AI agents."""

    @staticmethod
    def build_agent_card(
        app: App,
        agent: Agent,
        rpc_url: str,
    ) -> AgentCard:
        display_name = agent.a2a_name_override or agent.name
        description = agent.a2a_description_override or agent.description or f"Mattin AI agent {agent.name}"
        skill_tags = agent.a2a_skill_tags or ["mattin-ai", "agent"]
        examples = agent.a2a_examples or None

        skill = AgentSkill(
            id=f"agent-{agent.agent_id}",
            name=display_name,
            description=description,
            tags=skill_tags,
            examples=examples,
            input_modes=DEFAULT_INPUT_MODES,
            output_modes=DEFAULT_OUTPUT_MODES,
            security=[{"apiKey": []}],
        )

        return AgentCard(
            name=display_name,
            description=description,
            url=rpc_url,
            version=os.getenv("APP_VERSION", "0.2.37"),
            protocol_version="0.3.0",
            preferred_transport="JSONRPC",
            skills=[skill],
            default_input_modes=DEFAULT_INPUT_MODES,
            default_output_modes=DEFAULT_OUTPUT_MODES,
            capabilities=AgentCapabilities(
                streaming=True,
                state_transition_history=True,
                push_notifications=False,
            ),
            provider=AgentProvider(
                organization=CLIENT_CONFIG.client_name or "Mattin AI",
                url=os.getenv("AICT_BASE_URL", rpc_url.rsplit("/", 1)[0]),
            ),
            security=[{"apiKey": []}],
            security_schemes={
                "apiKey": SecurityScheme(
                    root=APIKeySecurityScheme(
                        name="X-API-KEY",
                        in_=In.header,
                        description="Mattin AI app-scoped API key",
                    )
                )
            },
            supports_authenticated_extended_card=False,
        )
