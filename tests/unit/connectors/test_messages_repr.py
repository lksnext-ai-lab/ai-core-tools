"""Secrets and task output must not leak through ``repr`` of connector messages."""

from connectors.core.messages import (
    DestinationExample,
    OutboundRequest,
    ValidatedDestination,
)

SECRET = "s3cr3t"


def _assert_clean(obj):
    assert SECRET not in repr(obj)


def test_outbound_request_repr_hides_secrets_and_payload():
    request = OutboundRequest(
        url=f"https://hooks.example.com/x?sig={SECRET}", payload={"content": {"text": f"result {SECRET}"}},
        public_config={}, credentials={"signing_secret": SECRET}, event_id="evt", attempt_number=1,
        content_type="application/json", body=SECRET.encode(), body_path=None,
    )
    _assert_clean(request)


def test_validated_destination_repr_hides_secrets():
    _assert_clean(ValidatedDestination(f"https://h.example.com/?sig={SECRET}", {}, {"signing_secret": SECRET}))


def test_destination_example_repr_hides_secrets():
    _assert_clean(DestinationExample(f"https://h.example.com/?sig={SECRET}", {}, {"signing_secret": SECRET}, None))
