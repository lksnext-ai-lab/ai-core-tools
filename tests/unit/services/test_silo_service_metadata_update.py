from unittest.mock import MagicMock, patch

import pytest

from services.silo_service import SiloService


@pytest.fixture
def vector_store():
    store = MagicMock()
    store.update_documents_metadata.return_value = 4
    with patch("services.silo_service._get_vector_store", return_value=store):
        yield store


@pytest.fixture
def cache_invalidate():
    with patch("services.metadata_values_cache_service.MetadataValuesCacheService.invalidate") as invalidate:
        yield invalidate


def _patch_silo(exists=True, silo=None):
    return (
        patch("services.silo_service.SiloService.check_silo_collection_exists", return_value=exists),
        patch("services.silo_service.SiloRepository.get_by_id", return_value=silo),
    )


class TestUpdateDocsMetadata:
    def test_updates_the_collection_and_invalidates_the_values_cache(self, vector_store, cache_invalidate):
        exists, get_by_id = _patch_silo(silo=MagicMock())
        with exists, get_by_id:
            updated = SiloService.update_docs_metadata(
                silo_id=7, filter_metadata={"empresa": "OLD"}, metadata_updates={"empresa": "NEW"},
                db=MagicMock(), replace=True,
            )

        assert updated == 4
        vector_store.update_documents_metadata.assert_called_once_with(
            "silo_7", filter_metadata={"empresa": "OLD"}, metadata_updates={"empresa": "NEW"}, replace=True,
        )
        cache_invalidate.assert_called_once_with(7)

    def test_missing_collection_updates_nothing(self, vector_store, cache_invalidate):
        exists, get_by_id = _patch_silo(exists=False, silo=MagicMock())
        with exists, get_by_id:
            updated = SiloService.update_docs_metadata(
                silo_id=7, filter_metadata={"a": 1}, metadata_updates={"a": 2}, db=MagicMock(),
            )

        assert updated == 0
        vector_store.update_documents_metadata.assert_not_called()
        cache_invalidate.assert_not_called()

    def test_missing_silo_updates_nothing(self, vector_store, cache_invalidate):
        exists, get_by_id = _patch_silo(silo=None)
        with exists, get_by_id:
            updated = SiloService.update_docs_metadata(
                silo_id=7, filter_metadata={"a": 1}, metadata_updates={"a": 2}, db=MagicMock(),
            )

        assert updated == 0
        vector_store.update_documents_metadata.assert_not_called()

    def test_cache_invalidation_failure_does_not_fail_the_update(self, vector_store, cache_invalidate):
        cache_invalidate.side_effect = RuntimeError("cache down")
        exists, get_by_id = _patch_silo(silo=MagicMock())
        with exists, get_by_id:
            updated = SiloService.update_docs_metadata(
                silo_id=7, filter_metadata={"a": 1}, metadata_updates={"a": 2}, db=MagicMock(),
            )

        assert updated == 4


class TestGetMetadataFieldValuesValidation:
    @pytest.mark.parametrize("field", ["", "empresa; DROP TABLE", "a b", "x'y"])
    def test_rejects_unsafe_field_names_before_touching_the_store(self, field):
        with patch("services.silo_service.SiloRepository.get_by_id") as get_by_id:
            with pytest.raises(ValueError, match="Invalid metadata field name"):
                SiloService.get_metadata_field_values(silo_id=7, field=field, db=MagicMock())

        get_by_id.assert_not_called()
