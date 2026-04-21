"""
Unit tests for the embedding_service_id immutability guard.

Once a silo or domain is created with a specific embedding_service_id, any
attempt to change it via the update path must raise ValidationError.

No database is needed — ORM objects and sessions are fully mocked.
"""

import pytest
from unittest.mock import MagicMock, patch

from utils.vector_db_immutability import assert_embedding_service_immutable
from utils.error_handlers import ValidationError


# ---------------------------------------------------------------------------
# Standalone unit tests for the guard function
# ---------------------------------------------------------------------------

class TestAssertEmbeddingServiceImmutable:
    """Direct tests for the assert_embedding_service_immutable() helper."""

    def test_raises_when_ids_differ(self):
        with pytest.raises(ValidationError) as exc:
            assert_embedding_service_immutable(1, 2, "silo")
        assert "embedding_service_id cannot be changed" in str(exc.value)
        assert "silo" in str(exc.value)

    def test_raises_for_domain_entity_name(self):
        with pytest.raises(ValidationError) as exc:
            assert_embedding_service_immutable(3, 7, "domain")
        assert "domain" in str(exc.value)

    def test_passes_when_ids_are_equal(self):
        """Idempotent update — same ID must pass through."""
        assert_embedding_service_immutable(5, 5, "silo")  # must not raise

    def test_passes_when_existing_is_none(self):
        """No service set yet — guard must not fire."""
        assert_embedding_service_immutable(None, 99, "silo")

    def test_passes_when_requested_is_none(self):
        """Caller not touching the field — pass through."""
        assert_embedding_service_immutable(1, None, "silo")

    def test_passes_when_both_none(self):
        assert_embedding_service_immutable(None, None, "silo")

    def test_int_coercion(self):
        """IDs should be compared as ints even if one arrives as a different numeric type."""
        assert_embedding_service_immutable(1, 1.0, "silo")  # must not raise

    def test_raises_with_int_coercion_on_different_values(self):
        with pytest.raises(ValidationError):
            assert_embedding_service_immutable(1, 2.0, "silo")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_silo(silo_id: int = 1, embedding_service_id: int | None = 5) -> MagicMock:
    silo = MagicMock()
    silo.silo_id = silo_id
    silo.app_id = 10
    silo.vector_db_type = "PGVECTOR"
    silo.silo_type = "CUSTOM"
    silo.embedding_service_id = embedding_service_id
    silo.metadata_definition_id = None
    silo.name = "Existing Silo"
    silo.description = ""
    silo.status = None
    silo.fixed_metadata = False
    return silo


def _make_silo_data(
    silo_id: int = 1,
    name: str = "Existing Silo",
    embedding_service_id: int | None = None,
) -> dict:
    return {
        "silo_id": silo_id,
        "app_id": 10,
        "name": name,
        "description": "",
        "vector_db_type": None,
        "embedding_service_id": embedding_service_id,
    }


# ---------------------------------------------------------------------------
# SiloService integration tests
# ---------------------------------------------------------------------------

class TestSiloServiceEmbeddingServiceGuard:
    """Guard is enforced inside SiloService.create_or_update_silo()."""

    def _call(self, existing_silo: MagicMock, silo_data: dict):
        mock_db = MagicMock()
        with patch(
            "services.silo_service.SiloService.get_silo",
            return_value=existing_silo,
        ):
            from services.silo_service import SiloService
            return SiloService.create_or_update_silo(silo_data, db=mock_db)

    def test_raises_when_changing_embedding_service(self):
        silo = _make_silo(embedding_service_id=5)
        data = _make_silo_data(embedding_service_id=99)

        with pytest.raises(ValidationError) as exc:
            self._call(silo, data)

        assert "embedding_service_id cannot be changed" in str(exc.value)

    def test_raises_when_changing_to_different_service(self):
        silo = _make_silo(embedding_service_id=10)
        data = _make_silo_data(embedding_service_id=1)

        with pytest.raises(ValidationError):
            self._call(silo, data)

    def test_same_embedding_service_is_accepted(self):
        silo = _make_silo(embedding_service_id=5)
        data = _make_silo_data(embedding_service_id=5)

        result = self._call(silo, data)
        assert result is not None

    def test_omitted_embedding_service_is_accepted(self):
        """UpdateSiloSchema does not send embedding_service_id — must pass through."""
        silo = _make_silo(embedding_service_id=5)
        data = _make_silo_data(embedding_service_id=None)

        result = self._call(silo, data)
        assert result is not None

    def test_no_existing_embedding_service_skips_guard(self):
        """Legacy silo with no embedding_service_id set — guard must not fire."""
        silo = _make_silo(embedding_service_id=None)
        data = _make_silo_data(embedding_service_id=42)

        result = self._call(silo, data)
        assert result is not None


# ---------------------------------------------------------------------------
# DomainService integration tests
# ---------------------------------------------------------------------------

class TestDomainServiceEmbeddingServiceGuard:
    """Guard is enforced inside DomainService._update_existing_domain()."""

    def _call_update(
        self,
        existing_embedding_service_id: int | None,
        requested_embedding_service_id: int | None,
    ):
        from services.domain_service import DomainService
        from repositories.domain_repository import DomainRepository
        from repositories.silo_repository import SiloRepository
        from services.silo_service import SiloService as SiloSvc

        domain = MagicMock()
        domain.domain_id = 1
        domain.app_id = 10
        domain.name = "Test Domain"
        domain.silo_id = 5

        silo = MagicMock()
        silo.vector_db_type = "PGVECTOR"
        silo.embedding_service_id = existing_embedding_service_id

        mock_db = MagicMock()

        with (
            patch.object(DomainService, "get_domain", return_value=domain),
            patch.object(DomainRepository, "update", return_value=domain),
            patch.object(SiloSvc, "get_silo", return_value=silo),
            patch.object(SiloRepository, "update", return_value=silo),
        ):
            return DomainService._update_existing_domain(
                domain_id=1,
                domain_data={
                    "description": "",
                    "base_url": "https://example.com",
                    "content_tag": "body",
                    "content_class": "",
                    "content_id": "",
                },
                embedding_service_id=requested_embedding_service_id,
                name="Test Domain",
                base_url="https://example.com",
                vector_db_type=None,
                db=mock_db,
            )

    def test_raises_when_changing_embedding_service(self):
        with pytest.raises(ValidationError) as exc:
            self._call_update(5, 99)
        assert "embedding_service_id cannot be changed" in str(exc.value)
        assert "domain" in str(exc.value)

    def test_raises_changing_to_another_service(self):
        with pytest.raises(ValidationError):
            self._call_update(10, 1)

    def test_same_embedding_service_is_accepted(self):
        result = self._call_update(5, 5)
        assert result is not None

    def test_omitted_embedding_service_is_accepted(self):
        """Update path sends None for embedding_service_id — must pass through."""
        result = self._call_update(5, None)
        assert result is not None

    def test_no_existing_embedding_service_skips_guard(self):
        """Legacy domain with no embedding_service_id stored — guard must not fire."""
        result = self._call_update(None, 42)
        assert result is not None
