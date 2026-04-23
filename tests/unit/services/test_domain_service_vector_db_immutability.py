"""
Unit tests for the vector_db_type immutability guard in DomainService.

The guard is enforced inside DomainService._update_existing_domain() by
calling utils.vector_db_immutability.assert_vector_db_type_immutable().

No database is needed — ORM objects and sessions are fully mocked.
"""

import pytest
from unittest.mock import MagicMock, patch, call

from utils.vector_db_immutability import assert_vector_db_type_immutable
from utils.error_handlers import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_silo_mock(vector_db_type: str | None = "PGVECTOR") -> MagicMock:
    silo = MagicMock()
    silo.vector_db_type = vector_db_type
    silo.embedding_service_id = None
    return silo


def _make_domain_mock(silo_vector_db_type: str | None = "PGVECTOR") -> MagicMock:
    domain = MagicMock()
    domain.domain_id = 1
    domain.app_id = 10
    domain.name = "Test Domain"
    domain.description = ""
    domain.base_url = "https://example.com"
    domain.content_tag = "body"
    domain.content_class = ""
    domain.content_id = ""
    domain.silo_id = 5
    domain.silo = _make_silo_mock(silo_vector_db_type)
    return domain


# ---------------------------------------------------------------------------
# DomainService._update_existing_domain() — guard integration
# ---------------------------------------------------------------------------

class TestDomainServiceUpdateGuard:
    """Immutability guard is enforced inside DomainService._update_existing_domain()."""

    def _call_update(
        self,
        silo_vector_db_type: str | None,
        requested_vector_db_type: str | None,
        embedding_service_id: int | None = None,
    ):
        from services.domain_service import DomainService
        from repositories.domain_repository import DomainRepository
        from repositories.silo_repository import SiloRepository

        domain = _make_domain_mock(silo_vector_db_type)
        silo = domain.silo

        mock_db = MagicMock()

        with (
            patch.object(DomainService, "get_domain", return_value=domain),
            patch.object(DomainRepository, "update", return_value=domain),
            patch.object(SiloService := __import__(
                "services.silo_service", fromlist=["SiloService"]
            ).SiloService, "get_silo", return_value=silo),
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
                embedding_service_id=embedding_service_id,
                name="Test Domain",
                base_url="https://example.com",
                vector_db_type=requested_vector_db_type,
                db=mock_db,
            )

    # Rejection cases

    def test_raises_when_changing_pgvector_to_qdrant(self):
        with pytest.raises(ValidationError) as exc:
            self._call_update("PGVECTOR", "QDRANT")
        assert "vector_db_type cannot be changed" in str(exc.value)
        assert "domain" in str(exc.value)

    def test_raises_when_changing_qdrant_to_pgvector(self):
        with pytest.raises(ValidationError):
            self._call_update("QDRANT", "PGVECTOR")

    def test_raises_regardless_of_input_case(self):
        with pytest.raises(ValidationError):
            self._call_update("PGVECTOR", "qdrant")

    # Accepted cases

    def test_omitted_vector_db_type_is_accepted(self):
        """UpdateDomainSchema doesn't send vector_db_type at all — must pass through."""
        result = self._call_update("PGVECTOR", None)
        assert result is not None

    def test_null_stored_value_skips_guard(self):
        """Legacy domain with no stored vector_db_type — guard must not fire."""
        result = self._call_update(None, "QDRANT")
        assert result is not None

    def test_update_with_embedding_service_change_accepted(self):
        """Changing only the embedding service (no vector_db_type) must succeed."""
        result = self._call_update("PGVECTOR", None, embedding_service_id=42)
        assert result is not None


# ---------------------------------------------------------------------------
# _update_existing_domain with no silo — guard must not fire
# ---------------------------------------------------------------------------

class TestDomainServiceUpdateNoSilo:
    def test_no_silo_skips_guard(self):
        """Domain without a linked silo — nothing to protect."""
        from services.domain_service import DomainService
        from repositories.domain_repository import DomainRepository
        from services.silo_service import SiloService

        domain = _make_domain_mock()
        domain.silo_id = None  # no silo

        mock_db = MagicMock()

        with (
            patch.object(DomainService, "get_domain", return_value=domain),
            patch.object(DomainRepository, "update", return_value=domain),
            patch.object(SiloService, "get_silo") as mock_get_silo,
        ):
            result = DomainService._update_existing_domain(
                domain_id=1,
                domain_data={},
                embedding_service_id=None,
                name="Test",
                base_url="https://example.com",
                vector_db_type="QDRANT",
                db=mock_db,
            )
            # get_silo should never be called when there is no silo_id
            mock_get_silo.assert_not_called()
        assert result is not None
