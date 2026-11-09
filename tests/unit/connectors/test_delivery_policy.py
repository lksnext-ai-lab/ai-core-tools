"""Truth tables for the capability-driven delivery policy."""

import pytest
from services.output_channels import delivery_policy


@pytest.mark.parametrize("key, flag, expected", [
    ("webhook", True, True),
    ("webhook", False, False),
    ("webhook", "true", False),
    ("webhook", None, False),
    ("teams_workflow", True, False),
    ("carrier-pigeon", True, False),
    (None, True, False),
])
def test_receiver_can_deduplicate(key, flag, expected):
    snapshot = {} if flag is None else {"receiver_deduplicates": flag}
    assert delivery_policy.receiver_can_deduplicate(key, snapshot) is expected


@pytest.mark.parametrize("snapshot, expected", [
    ({"provider_key": "webhook", "include_attachments": True}, 180),
    ({"provider_key": "webhook", "include_attachments": False}, delivery_policy.LEASE_SECONDS),
    ({"provider_key": "webhook"}, delivery_policy.LEASE_SECONDS),
    ({"provider_key": "teams_workflow", "include_attachments": True}, delivery_policy.LEASE_SECONDS),
    ({"provider_key": "carrier-pigeon", "include_attachments": True}, delivery_policy.LEASE_SECONDS),
    ({"include_attachments": True}, delivery_policy.LEASE_SECONDS),
])
def test_lease_seconds_for(snapshot, expected):
    assert delivery_policy.lease_seconds_for(snapshot) == expected
