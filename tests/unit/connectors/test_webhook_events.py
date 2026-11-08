"""The webhook attachment manifest never exposes internal storage keys."""

from connectors.providers.webhook.events import attachment_manifest


def test_attachment_manifest_exposes_only_public_keys():
    artifact = {
        "file_id": "f-1", "filename": "report.pdf", "content_type": "application/pdf",
        "size_bytes": 10, "sha256": "ab" * 32, "part_name": "file_0",
        "object_key": "apps/1/internal/report.pdf",
    }

    manifest = attachment_manifest([artifact])

    assert manifest == [{key: value for key, value in artifact.items() if key != "object_key"}]
    assert "object_key" not in manifest[0]
