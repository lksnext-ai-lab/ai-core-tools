"""Typed settings for the Teams Workflow provider (it takes no public config or credentials)."""

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from connectors.core.messages import JsonDict
from connectors.core.settings import DestinationSettingsBase

_MODEL_CONFIG = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
_REJECTED = "Teams destinations do not accept webhook settings or credentials"


class TeamsWorkflowPublicConfig(BaseModel):
    model_config = _MODEL_CONFIG


class TeamsWorkflowCredentials(BaseModel):
    model_config = _MODEL_CONFIG

    def to_storage(self) -> dict[str, str]:
        return {}


class TeamsWorkflowSettings(DestinationSettingsBase):
    provider_key: Literal["teams_workflow"] = "teams_workflow"
    public_config: TeamsWorkflowPublicConfig
    credentials: TeamsWorkflowCredentials

    def public_config_json(self) -> JsonDict:
        return {}

    def credentials_json(self) -> dict[str, str]:
        return self.credentials.to_storage()


def parse_teams_workflow_settings(
    config: Mapping[str, Any] | None, credentials: Mapping[str, str] | None,
) -> TeamsWorkflowSettings:
    """Accept only empty settings; any rejection becomes the fixed message (no chaining)."""
    try:
        settings = TeamsWorkflowSettings(
            provider_key="teams_workflow",
            public_config=TeamsWorkflowPublicConfig.model_validate(dict(config or {})),
            credentials=TeamsWorkflowCredentials.model_validate(dict(credentials or {})),
        )
    except (ValueError, TypeError):  # ValidationError is a ValueError
        settings = None
    if settings is None:
        # Raised outside ``except``: no __context__ holds the error that embeds the rejected input.
        raise ValueError(_REJECTED)
    return settings
