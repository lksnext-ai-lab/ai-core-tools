"""Connection test of an output destination."""

from datetime import UTC, datetime
from typing import Any

from connectors import registry as connector_registry
from connectors.core.messages import BodyEncoding, OutboundRequest, TestDeliveryContext
from connectors.core.settings import read_credentials
from models.output_delivery import OutputDestination
from services.output_channels import messages, spool


async def test_destination(destination: OutputDestination) -> dict[str, Any]:
    provider = connector_registry.get_output_provider(destination.provider_key)
    # The spool root is resolved lazily: only when a file is staged or the body is multipart.
    stager = spool.SpoolAttachmentStager(spool.spool_root)
    path = None
    try:
        prepared = provider.build_test_delivery(
            TestDeliveryContext(messages.destination_view(destination), messages.base_url(), datetime.now(UTC)),
            stager,
        )
        body = None
        content_type = "application/json"
        if prepared.body_encoding == BodyEncoding.JSON:
            body = spool.json_body(prepared.payload)
        elif prepared.body_encoding == BodyEncoding.MULTIPART:
            if not prepared.event_id:
                raise ValueError("multipart deliveries require an event_id")
            path = spool.safe_spool_file(f"tests/{prepared.event_id}.multipart")
            content_type, _size, _digest = spool.write_multipart(path, prepared.payload, list(prepared.attachments))
        return dict(await provider.send(OutboundRequest(
            url=destination.webhook_url, payload=prepared.payload,
            public_config=dict(destination.public_config or {}), credentials=read_credentials(destination.credentials),
            event_id=prepared.event_id, attempt_number=1, content_type=content_type,
            body=body, body_path=str(path) if path else None,
        )))
    finally:
        if path:
            spool.remove_quietly(path)
        stager.cleanup()
