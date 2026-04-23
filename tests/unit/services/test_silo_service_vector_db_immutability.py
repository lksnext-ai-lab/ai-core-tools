"""
Unit tests for the vector_db_type immutability guard in SiloService.

FR-1 (issue #142): Once a silo is created with a specific vector_db_type,
any attempt to change it via create_or_update_silo() must raise ValidationError.

SiloRepository is mocked so no database is needed.
session.add / session.commit are also replaced with no-ops.
"""

import pytest
from unittest.mock import MagicMock, patch

from services.silo_service import SiloService
from utils.error_handlers import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_silo(silo_id: int = 1, vector_db_type: str = "PGVECTOR") -> MagicMock:
    """Return a mock Silo ORM object with the given id and vector_db_type."""
    silo = MagicMock()
    silo.silo_id = silo_id
    silo.app_id = 10
    silo.vector_db_type = vector_db_type
    silo.silo_type = "CUSTOM"
    silo.metadata_definition_id = None
    silo.embedding_service_id = None
    silo.name = "Existing Silo"
    silo.description = ""
    silo.status = None
    silo.fixed_metadata = False
    return silo


def _make_silo_data(
    silo_id: int = 1,
    name: str = "Existing Silo",
    vector_db_type: str | None = None,
) -> dict:
    """Build a minimal silo_data dict as callers pass to create_or_update_silo()."""
    return {
        "silo_id": silo_id,
        "app_id": 10,
        "name": name,
        "description": "",
        "vector_db_type": vector_db_type,
    }


# ---------------------------------------------------------------------------
# Guard: changing vector_db_type on an existing silo raises ValidationError
# ---------------------------------------------------------------------------

class TestVectorDbTypeImmutabilityGuard:
    """FR-1: Immutability guard in SiloService.create_or_update_silo()."""

    def _call(self, existing_silo: MagicMock, silo_data: dict):
        """
        Invoke create_or_update_silo() with the repository mocked to return
        existing_silo and with session side-effects replaced by no-ops.
        """
        mock_db = MagicMock()
        mock_db.__bool__ = lambda self: True  # truthy so `db if db is not None` takes this branch

        with patch(
            "services.silo_service.SiloService.get_silo",
            return_value=existing_silo,
        ):
            return SiloService.create_or_update_silo(silo_data, db=mock_db)

    # ------------------------------------------------------------------
    # Rejection cases — different value supplied
    # ------------------------------------------------------------------

    def test_raises_when_changing_pgvector_to_qdrant(self):
        silo = _make_silo(vector_db_type="PGVECTOR")
        data = _make_silo_data(vector_db_type="QDRANT")

        with pytest.raises(ValidationError) as exc:
            self._call(silo, data)

        assert "vector_db_type cannot be changed" in str(exc.value)

    def test_raises_when_changing_qdrant_to_pgvector(self):
        silo = _make_silo(vector_db_type="QDRANT")
        data = _make_silo_data(vector_db_type="PGVECTOR")

        with pytest.raises(ValidationError) as exc:
            self._call(silo, data)

        assert "vector_db_type cannot be changed" in str(exc.value)

    def test_raises_regardless_of_input_case(self):
        """Guard must normalise input — lowercase 'qdrant' should also be rejected."""
        silo = _make_silo(vector_db_type="PGVECTOR")
        data = _make_silo_data(vector_db_type="qdrant")

        with pytest.raises(ValidationError):
            self._call(silo, data)

    # ------------------------------------------------------------------
    # Accepted cases — same value or omitted
    # ------------------------------------------------------------------

    def test_same_value_is_accepted(self):
        """Sending the same vector_db_type as already stored must succeed silently."""
        silo = _make_silo(vector_db_type="PGVECTOR")
        data = _make_silo_data(vector_db_type="PGVECTOR")

        # Should not raise — verifies idempotent update is allowed
        result = self._call(silo, data)
        assert result is not None

    def test_same_value_lowercase_is_accepted(self):
        """Same value in lowercase (normalised to uppercase) must succeed."""
        silo = _make_silo(vector_db_type="PGVECTOR")
        data = _make_silo_data(vector_db_type="pgvector")

        result = self._call(silo, data)
        assert result is not None

    def test_omitted_vector_db_type_is_accepted(self):
        """Omitting vector_db_type entirely (UpdateSiloSchema flow) must succeed."""
        silo = _make_silo(vector_db_type="PGVECTOR")
        data = _make_silo_data(vector_db_type=None)

        result = self._call(silo, data)
        assert result is not None

    # ------------------------------------------------------------------
    # Edge case — existing silo has NULL vector_db_type
    # ------------------------------------------------------------------

    def test_null_stored_value_skips_guard(self):
        """
        If an existing silo has no vector_db_type stored (legacy row),
        the guard must not fire — there is no type to protect.
        """
        silo = _make_silo(vector_db_type=None)
        # Even though we supply a different type, the guard should stay silent
        # because there is no existing backend to protect.
        data = _make_silo_data(vector_db_type="QDRANT")

        result = self._call(silo, data)
        assert result is not None


# ---------------------------------------------------------------------------
# Creation flow — guard must not interfere
# ---------------------------------------------------------------------------

class TestCreationFlowUnaffected:
    """Creating a new silo (silo_id absent/0) must be completely unaffected by the guard."""

    def test_create_with_pgvector_succeeds(self):
        mock_db = MagicMock()
        data = {
            "app_id": 10,
            "name": "Brand New Silo",
            "vector_db_type": "PGVECTOR",
        }

        with patch("services.silo_service.SiloService.get_silo") as mock_get:
            # get_silo should never be called for new silos
            result = SiloService.create_or_update_silo(data, db=mock_db)
            mock_get.assert_not_called()

        assert result is not None

    def test_create_with_qdrant_succeeds(self):
        mock_db = MagicMock()
        data = {
            "app_id": 10,
            "name": "Brand New Silo",
            "vector_db_type": "QDRANT",
        }

        with patch("services.silo_service.SiloService.get_silo"):
            result = SiloService.create_or_update_silo(data, db=mock_db)

        assert result is not None
