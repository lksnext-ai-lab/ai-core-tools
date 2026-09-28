"""Provider-neutral contract for scheduled-task output adapters."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderDescriptor:
    key: str
    name: str
    supports_links: bool = True
    supports_native_attachments: bool = False
    content_modes: tuple[str, ...] = ("result", "excerpt", "link_only")


class OutputProvider(Protocol):
    descriptor: ProviderDescriptor

    def validate_secret(self, value: str) -> str: ...
    async def send(self, secret: str, payload: dict[str, Any]) -> dict[str, Any]: ...
