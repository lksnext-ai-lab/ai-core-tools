"""Output parser (metadata definition) tenant scoping on silo create/update/delete/detail."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.silo_service import SiloService
from utils.error_handlers import ValidationError


def _parser(parser_id=5, app_id=1):
    return SimpleNamespace(parser_id=parser_id, app_id=app_id, fields=[{"name": "x"}])


class TestEnsureOutputParserOwned:
    def test_own_parser_ok(self):
        SiloService.ensure_output_parser_owned(_parser(app_id=1), 1)

    def test_foreign_and_missing_share_message(self):
        with pytest.raises(ValidationError) as foreign:
            SiloService.ensure_output_parser_owned(_parser(app_id=2), 1)
        with pytest.raises(ValidationError) as missing:
            SiloService.ensure_output_parser_owned(None, 1)
        assert str(foreign.value) == str(missing.value)

    def test_parser_without_app_rejected(self):
        with pytest.raises(ValidationError):
            SiloService.ensure_output_parser_owned(_parser(app_id=None), 1)


class TestCreateOrUpdateSiloParser:
    def _call(self, parser, key="output_parser_id"):
        db = MagicMock()
        data = {"name": "s", "app_id": 1, key: 5}
        with patch("services.silo_service.SiloRepository.get_output_parser_by_id", return_value=parser), \
                patch("services.tier_enforcement_service.TierEnforcementService.check_resource_limit"):
            return SiloService.create_or_update_silo(data, db=db), db

    @pytest.mark.parametrize("key", ["output_parser_id", "metadata_definition_id"])
    def test_foreign_parser_rejected(self, key):
        with pytest.raises(ValidationError):
            self._call(_parser(app_id=2), key)

    def test_missing_parser_rejected(self):
        with pytest.raises(ValidationError):
            self._call(None)

    def test_own_parser_assigned(self):
        silo, _ = self._call(_parser(app_id=1))
        assert silo.metadata_definition_id == 5


class TestDeleteSiloParser:
    def _delete(self, parser_app_id):
        silo = SimpleNamespace(silo_id=9, app_id=1, metadata_definition_id=5, embedding_service_id=None)
        parser = _parser(app_id=parser_app_id)
        with patch("services.silo_service.SiloRepository.get_by_id", return_value=silo), \
                patch("services.silo_service.SiloRepository.delete"), \
                patch.object(SiloService, "delete_collection"), \
                patch.object(SiloService, "remove_silo_media_files"), \
                patch("services.silo_service.OutputParserService") as ops:
            ops.return_value.get_parser_by_id.return_value = parser
            SiloService.delete_silo(9, MagicMock())
            return ops.return_value.delete_parser

    def test_foreign_parser_not_deleted(self):
        self._delete(2).assert_not_called()

    def test_own_parser_deleted(self):
        self._delete(1).assert_called_once()


class TestDeleteRepositoryParser:
    def _delete(self, parser_app_id):
        from services.repository_service import RepositoryService

        silo = SimpleNamespace(silo_id=9, app_id=1, metadata_definition_id=5)
        repo = SimpleNamespace(repository_id=3, app_id=1, silo=silo, name="r")
        db = MagicMock()
        db.get.return_value = _parser(app_id=parser_app_id)
        with patch("services.repository_service.RepositoryRepository") as rr, \
                patch("services.repository_service.SiloService.delete_collection"):
            rr.get_resources_by_repository_id.return_value = []
            RepositoryService.delete_repository(repo, db)
            return rr.delete_output_parser_by_id

    def test_foreign_parser_not_deleted(self):
        self._delete(2).assert_not_called()

    def test_own_parser_deleted(self):
        self._delete(1).assert_called_once()
