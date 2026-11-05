"""Public silo API: count, enumerate and relabel documents by metadata."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from routers.public.v1 import silos as silos_module
from routers.public.v1.schemas import (
    CountByMetadataRequestSchema,
    MetadataValuesRequestSchema,
    UpdateMetadataRequestSchema,
)
from services.silo_service import DEFAULT_METADATA_VALUES_LIMIT


@pytest.fixture(autouse=True)
def auth(mocker):
    mocker.patch.object(silos_module, "validate_api_key_for_app", return_value=None)
    mocker.patch.object(silos_module, "validate_silo_ownership", return_value=None)


@pytest.fixture
def silo_service(mocker):
    return mocker.patch.object(silos_module, "SiloService")


@pytest.fixture
def logger(mocker):
    return mocker.patch.object(silos_module, "logger")


async def _count(filter_metadata):
    return await silos_module.count_docs_by_metadata(
        app_id=1, silo_id=7, request=CountByMetadataRequestSchema(filter_metadata=filter_metadata),
        api_key="key", db=MagicMock(),
    )


async def _values(**request):
    return await silos_module.list_metadata_values(
        app_id=1, silo_id=7, request=MetadataValuesRequestSchema(**request), api_key="key", db=MagicMock(),
    )


async def _update(filter_metadata, metadata_updates, replace=False):
    return await silos_module.update_docs_metadata(
        app_id=1, silo_id=7,
        request=UpdateMetadataRequestSchema(
            filter_metadata=filter_metadata, metadata_updates=metadata_updates, replace=replace,
        ),
        api_key="key", db=MagicMock(),
    )


class TestCountDocsByMetadata:
    @pytest.mark.asyncio
    async def test_returns_the_service_count(self, silo_service):
        silo_service.count_docs_with_filter.return_value = 12

        result = await _count({"empresa": {"$eq": "ADITMAQ"}})

        assert result.count == 12
        assert silo_service.count_docs_with_filter.call_args.kwargs["filter_metadata"] == {
            "empresa": {"$eq": "ADITMAQ"}
        }

    @pytest.mark.asyncio
    async def test_empty_filter_is_rejected(self, silo_service):
        with pytest.raises(HTTPException) as exc_info:
            await _count({})

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == silos_module.FILTER_METADATA_EMPTY_MSG
        silo_service.count_docs_with_filter.assert_not_called()

    @pytest.mark.asyncio
    async def test_service_failure_hides_internals(self, silo_service, logger):
        silo_service.count_docs_with_filter.side_effect = RuntimeError("db password=secret")

        with pytest.raises(HTTPException) as exc_info:
            await _count({"empresa": "ADITMAQ"})

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Failed to count documents"
        logger.exception.assert_called_once()


class TestListMetadataValues:
    @pytest.mark.asyncio
    async def test_forwards_the_page_request(self, silo_service):
        silo_service.get_metadata_field_values.return_value = ["A", "B"]

        result = await _values(field=" empresa ", prefix="A", limit=2, after="0", filter_metadata={"x": 1})

        assert result.values == ["A", "B"]
        kwargs = silo_service.get_metadata_field_values.call_args.kwargs
        assert kwargs["field"] == "empresa"
        assert kwargs["prefix"] == "A"
        assert kwargs["limit"] == 2
        assert kwargs["after"] == "0"
        assert kwargs["filter_metadata"] == {"x": 1}
        assert kwargs["raise_errors"] is True

    @pytest.mark.asyncio
    async def test_limit_defaults_when_omitted(self, silo_service):
        silo_service.get_metadata_field_values.return_value = []

        await _values(field="empresa")

        assert silo_service.get_metadata_field_values.call_args.kwargs["limit"] == DEFAULT_METADATA_VALUES_LIMIT

    @pytest.mark.asyncio
    @pytest.mark.parametrize("field", ["", "   "])
    async def test_blank_field_is_rejected(self, silo_service, field):
        with pytest.raises(HTTPException) as exc_info:
            await _values(field=field)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "field cannot be empty"
        silo_service.get_metadata_field_values.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_field_name_is_reported(self, silo_service):
        silo_service.get_metadata_field_values.side_effect = ValueError("Invalid metadata field name: 'a;b'")

        with pytest.raises(HTTPException) as exc_info:
            await _values(field="a;b")

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid metadata field name: 'a;b'"

    @pytest.mark.asyncio
    async def test_service_failure_hides_internals(self, silo_service, logger):
        silo_service.get_metadata_field_values.side_effect = RuntimeError("connection refused")

        with pytest.raises(HTTPException) as exc_info:
            await _values(field="empresa")

        assert exc_info.value.detail == "Failed to list metadata values"
        logger.exception.assert_called_once()


class TestUpdateDocsMetadata:
    @pytest.mark.asyncio
    async def test_returns_the_updated_count(self, silo_service):
        silo_service.update_docs_metadata.return_value = 3

        result = await _update({"empresa": "OLD"}, {"empresa": "NEW"}, replace=True)

        assert result.updated == 3
        kwargs = silo_service.update_docs_metadata.call_args.kwargs
        assert kwargs["metadata_updates"] == {"empresa": "NEW"}
        assert kwargs["replace"] is True

    @pytest.mark.asyncio
    async def test_empty_filter_is_rejected(self, silo_service):
        with pytest.raises(HTTPException) as exc_info:
            await _update({}, {"empresa": "NEW"})

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == silos_module.FILTER_METADATA_EMPTY_MSG
        silo_service.update_docs_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_updates_are_rejected(self, silo_service):
        with pytest.raises(HTTPException) as exc_info:
            await _update({"empresa": "OLD"}, {})

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "metadata_updates cannot be empty"
        silo_service.update_docs_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_service_failure_hides_internals(self, silo_service, logger):
        silo_service.update_docs_metadata.side_effect = RuntimeError("boom")

        with pytest.raises(HTTPException) as exc_info:
            await _update({"empresa": "OLD"}, {"empresa": "NEW"})

        assert exc_info.value.detail == "Failed to update documents metadata"
        logger.exception.assert_called_once()
