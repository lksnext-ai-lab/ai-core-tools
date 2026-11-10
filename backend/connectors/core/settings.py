"""Provider-neutral base for typed destination settings (public config + credentials)."""

from abc import abstractmethod
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from connectors.core.messages import JsonDict


class DestinationSettingsBase(BaseModel):
    """Parsed, validated settings of one destination; concrete shapes live in each provider."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    @abstractmethod
    def public_config_json(self) -> JsonDict:
        """Return the public configuration exactly as it is stored."""
        raise NotImplementedError

    @abstractmethod
    def credentials_json(self) -> dict[str, str]:
        """Return the credentials exactly as they are stored (secret values included)."""
        raise NotImplementedError


def read_credentials(value: Mapping[str, str] | None) -> dict[str, str]:
    """Credentials of a stored destination as a dict: ``None`` and ``{}`` both mean "no credentials"."""
    return dict(value or {})


def normalize_credentials(value: Mapping[str, str] | None) -> dict[str, str] | None:
    """Value to persist for credentials: ``None`` when empty, otherwise a plain dict copy."""
    return dict(value) if value else None
