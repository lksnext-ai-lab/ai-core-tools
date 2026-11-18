"""Lifecycle fields on AI / embedding service schemas (create/update, export)."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from schemas.ai_service_schemas import CreateUpdateAIServiceSchema
from schemas.embedding_service_schemas import CreateUpdateEmbeddingServiceSchema
from schemas.export_schemas import ExportAIServiceSchema, ExportEmbeddingServiceSchema

_BASE = {"name": "n", "provider": "OpenAI", "model_name": "m", "api_key": "k"}
_EXPORT_BASE = {"name": "n", "provider": "OpenAI", "model_name": "m"}


@pytest.mark.parametrize(
    "schema,base",
    [
        (CreateUpdateAIServiceSchema, _BASE),
        (CreateUpdateEmbeddingServiceSchema, _BASE),
        (ExportAIServiceSchema, _EXPORT_BASE),
        (ExportEmbeddingServiceSchema, _EXPORT_BASE),
    ],
)
class TestLifecycleValidators:
    def test_defaults(self, schema, base):
        obj = schema(**base)
        assert obj.end_of_service_at is None
        assert obj.deprecation_notice is None

    def test_naive_datetime_is_utc(self, schema, base):
        obj = schema(**base, end_of_service_at="2030-01-02T00:00:00")
        assert obj.end_of_service_at == datetime(2030, 1, 2, tzinfo=timezone.utc)
        assert obj.end_of_service_at.utcoffset() == timedelta(0)

    def test_aware_datetime_converted(self, schema, base):
        obj = schema(**base, end_of_service_at="2030-01-02T02:00:00+02:00")
        assert obj.end_of_service_at == datetime(2030, 1, 2, tzinfo=timezone.utc)
        assert obj.end_of_service_at.utcoffset() == timedelta(0)

    def test_notice_stripped_and_empty_is_none(self, schema, base):
        assert schema(**base, deprecation_notice="  hi  ").deprecation_notice == "hi"
        assert schema(**base, deprecation_notice="   ").deprecation_notice is None

    def test_notice_control_chars_replaced(self, schema, base):
        obj = schema(**base, deprecation_notice="ok\r\nINFO forged\x00line\t.")
        assert obj.deprecation_notice == "ok  INFO forged line ."

    def test_notice_too_long(self, schema, base):
        with pytest.raises(ValidationError):
            schema(**base, deprecation_notice="x" * 1001)


def test_lifecycle_status_ignored_on_write_schemas():
    obj = CreateUpdateAIServiceSchema(**_BASE, lifecycle_status="retired")
    assert not hasattr(obj, "lifecycle_status")
    obj = CreateUpdateEmbeddingServiceSchema(**_BASE, lifecycle_status="retired")
    assert not hasattr(obj, "lifecycle_status")


def test_old_export_files_still_parse():
    assert ExportAIServiceSchema(**_EXPORT_BASE).end_of_service_at is None
