"""Generic provider registry mechanism (the key -> instance map lives in ``connectors.registry``)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol, cast

from connectors.core.contracts import (
    Direction,
    OutboundCapabilities,
    OutboundProvider,
    ProviderDescriptor,
)
from connectors.core.errors import ProviderNotFoundError


class _Described(Protocol):
    descriptor: ProviderDescriptor


class ProviderRegistry:
    def __init__(self, providers: Mapping[str, _Described]):
        for key, provider in providers.items():
            descriptor = provider.descriptor
            if descriptor.key != key:
                raise ValueError(f"Provider registered as '{key}' declares key '{descriptor.key}'")
            declares_outbound = Direction.OUTBOUND in descriptor.directions
            if declares_outbound != (descriptor.outbound is not None):
                raise ValueError(
                    f"Provider '{key}': OUTBOUND direction and outbound capabilities must be declared together",
                )
            if descriptor.outbound is not None and not isinstance(provider, OutboundProvider):
                raise TypeError(f"Provider '{key}' declares outbound capabilities but does not implement OutboundProvider")
        self._providers: dict[str, _Described] = dict(providers)

    def get_outbound(self, key: str) -> OutboundProvider:
        provider = self.find_outbound(key)
        if provider is None:
            raise ProviderNotFoundError(key)
        return provider

    def find_outbound(self, key: str | None) -> OutboundProvider | None:
        if key is None:
            return None
        provider = self._providers.get(key)
        if provider is None or provider.descriptor.outbound is None:
            return None
        return cast(OutboundProvider, provider)  # conformance is checked in __init__

    def list_outbound(self) -> list[OutboundProvider]:
        return [p for p in (self.find_outbound(key) for key in self._providers) if p is not None]

    def list(self, direction: Direction | None = None) -> list[_Described]:
        return [
            p for p in self._providers.values()
            if direction is None or direction in p.descriptor.directions
        ]

    def keys(self) -> frozenset[str]:
        return frozenset(self._providers)

    def outbound_keys_where(self, predicate: Callable[[OutboundCapabilities], bool]) -> tuple[str, ...]:
        return tuple(
            key for key, p in self._providers.items()
            if p.descriptor.outbound is not None and predicate(p.descriptor.outbound)
        )
