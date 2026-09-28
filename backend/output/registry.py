"""Explicit allowlisted output provider registry."""

from output.contracts import OutputProvider
from output.teams_workflow import TeamsWorkflowProvider

_PROVIDERS: dict[str, OutputProvider] = {
    "teams_workflow": TeamsWorkflowProvider(),
}


def get_output_provider(provider_key: str) -> OutputProvider:
    try:
        return _PROVIDERS[provider_key]
    except KeyError as exc:
        raise ValueError(f"Unsupported output provider: {provider_key}") from exc


def list_output_providers() -> list[OutputProvider]:
    return list(_PROVIDERS.values())
