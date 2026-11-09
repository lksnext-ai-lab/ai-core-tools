"""``ProviderRegistry`` construction invariants."""

import pytest
from connectors.core.contracts import (
    Direction,
    OutboundCapabilities,
    ProviderDescriptor,
)
from connectors.core.errors import ProviderNotFoundError
from connectors.core.registry import ProviderRegistry
from connectors.registry import get_output_provider


class _Bare:
    def __init__(self, descriptor):
        self.descriptor = descriptor


def test_key_mismatch_is_rejected():
    real = get_output_provider("webhook")
    with pytest.raises(ValueError, match="declares key"):
        ProviderRegistry({"other": real})


def test_outbound_direction_without_capabilities_is_rejected():
    bare = _Bare(ProviderDescriptor(key="x", name="X", outbound=None))
    with pytest.raises(ValueError, match="declared together"):
        ProviderRegistry({"x": bare})


def test_capabilities_without_outbound_direction_is_rejected():
    bare = _Bare(ProviderDescriptor(key="x", name="X", directions=frozenset({Direction.INBOUND}),
                                    outbound=OutboundCapabilities()))
    with pytest.raises(ValueError, match="declared together"):
        ProviderRegistry({"x": bare})


def test_non_conforming_outbound_provider_is_rejected():
    bare = _Bare(ProviderDescriptor(key="x", name="X"))
    with pytest.raises(TypeError, match="OutboundProvider"):
        ProviderRegistry({"x": bare})


def test_lookup_helpers():
    registry = ProviderRegistry({"webhook": get_output_provider("webhook")})
    assert registry.find_outbound(None) is None and registry.find_outbound("nope") is None
    with pytest.raises(ProviderNotFoundError, match="Unsupported output provider: nope"):
        registry.get_outbound("nope")
