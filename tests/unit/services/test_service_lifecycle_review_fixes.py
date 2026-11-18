"""Unit tests: playground media ownership-before-retired, importer retired-service guards, domain options."""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from schemas.import_schemas import ConflictMode
from services.agent_import_service import AgentImportService
from services.domain_service import DomainService
from services.playground_media_service import PlaygroundMediaService
from services.silo_import_service import SiloImportService
from utils.error_handlers import ValidationError
from utils.service_lifecycle import ServiceRetiredError

PAST = datetime.now(timezone.utc) - timedelta(days=3)
FUTURE = datetime.now(timezone.utc) + timedelta(days=30)

AI_REPO = "repositories.ai_service_repository.AIServiceRepository.get_by_id"
EMB_REPO = "repositories.embedding_service_repository.EmbeddingServiceRepository.get_by_id"


def _svc(service_id, retired=False, app_id=10, notice=None, eos=None) -> MagicMock:
    s = MagicMock()
    s.service_id = service_id
    s.name = f"svc{service_id}"
    s.app_id = app_id
    s.end_of_service_at = PAST if retired else eos
    s.deprecation_notice = notice
    return s


# ---------------------------------------------------------------------------
# Item 3: ownership is validated before the retired check
# ---------------------------------------------------------------------------

class TestPlaygroundOwnershipBeforeRetired:
    def _check(self, **kwargs):
        PlaygroundMediaService._ensure_media_services_active(
            MagicMock(), 10, kwargs.get("t"), kwargs.get("v"), kwargs.get("e")
        )

    def test_foreign_retired_ai_service_gets_generic_error_without_leak(self, caplog):
        foreign = _svc(2, retired=True, app_id=99, notice="SECRET-NOTICE")
        with patch(AI_REPO, return_value=foreign), caplog.at_level(logging.WARNING):
            with pytest.raises(ValidationError) as exc:
                self._check(t=2)
        assert not isinstance(exc.value, ServiceRetiredError)
        assert "retired" not in str(exc.value).lower()
        assert "svc2" not in str(exc.value) and "SECRET-NOTICE" not in str(exc.value)
        assert "service_lifecycle.blocked" not in caplog.text

    def test_foreign_retired_video_service_generic_error(self, caplog):
        with patch(AI_REPO, return_value=_svc(3, retired=True, app_id=99)), caplog.at_level(logging.WARNING):
            with pytest.raises(ValidationError):
                self._check(v=3)
        assert "service_lifecycle.blocked" not in caplog.text

    def test_foreign_retired_embedding_generic_error(self, caplog):
        foreign = _svc(4, retired=True, app_id=99, notice="SECRET-NOTICE")
        with patch(EMB_REPO, return_value=foreign), caplog.at_level(logging.WARNING):
            with pytest.raises(ValidationError) as exc:
                self._check(e=4)
        assert not isinstance(exc.value, ServiceRetiredError)
        assert "retired" not in str(exc.value).lower()
        assert "SECRET-NOTICE" not in str(exc.value)
        assert "service_lifecycle.blocked" not in caplog.text

    def test_missing_service_gets_same_error(self):
        with patch(EMB_REPO, return_value=None):
            with pytest.raises(ValidationError):
                self._check(e=4)

    def test_own_retired_ai_service_raises_service_retired(self):
        with patch(AI_REPO, return_value=_svc(2, retired=True)):
            with pytest.raises(ServiceRetiredError):
                self._check(t=2)

    def test_own_retired_embedding_raises_service_retired(self):
        with patch(EMB_REPO, return_value=_svc(4, retired=True)):
            with pytest.raises(ServiceRetiredError):
                self._check(e=4)

    def test_system_retired_embedding_raises_service_retired(self):
        with patch(EMB_REPO, return_value=_svc(4, retired=True, app_id=None)):
            with pytest.raises(ServiceRetiredError):
                self._check(e=4)

    def test_active_own_services_pass(self):
        with patch(AI_REPO, return_value=_svc(2)), patch(EMB_REPO, return_value=_svc(4)):
            self._check(t=2, v=2, e=4)

    def test_create_branch_foreign_retired_embedding_generic_error(self):
        db = MagicMock()
        with patch.object(PlaygroundMediaService, "get_temp_repository", return_value=None), patch(
            EMB_REPO, return_value=_svc(4, retired=True, app_id=99)
        ), patch("services.playground_media_service.RepositoryService.create_repository") as create:
            with pytest.raises(ValidationError) as exc:
                PlaygroundMediaService.get_or_create_temp_repository(10, 1, "s", db, embedding_service_id=4)
        assert not isinstance(exc.value, ServiceRetiredError)
        create.assert_not_called()


# ---------------------------------------------------------------------------
# Item 5: importers reject newly assigning a retired service
# ---------------------------------------------------------------------------

def _agent_export(service_name="svc1"):
    export = MagicMock()
    export.agent.name = "A"
    export.agent.service_name = service_name
    export.ai_service = None
    return export


def _agent_importer():
    imp = AgentImportService.__new__(AgentImportService)
    imp.session = MagicMock()
    return imp


class TestAgentImportRetired:
    def _run(self, service, existing_agent, mode, selected=None):
        imp = _agent_importer()
        with patch("services.agent_import_service.validate_export_version"), patch.object(
            AgentImportService, "get_by_name_and_app", return_value=existing_agent
        ), patch(
            "services.agent_import_service.AIServiceRepository.get_by_id", return_value=service
        ):
            imp.session.query.return_value.filter.return_value.order_by.return_value.first.return_value = service
            return imp.import_agent(
                _agent_export(), 10, mode, selected_ai_service_id=selected
            )

    def test_selected_retired_service_rejected(self):
        with pytest.raises(ValueError, match="retired"):
            self._run(_svc(5, retired=True), None, ConflictMode.FAIL, selected=5)

    def test_name_fallback_retired_service_rejected(self):
        with pytest.raises(ValueError, match="retired"):
            self._run(_svc(5, retired=True), None, ConflictMode.FAIL)

    def test_override_with_different_retired_service_rejected(self):
        existing = MagicMock()
        existing.service_id = 1
        with pytest.raises(ValueError, match="retired"):
            self._run(_svc(5, retired=True), existing, ConflictMode.OVERRIDE, selected=5)

    def test_override_keeping_current_retired_service_passes_guard(self):
        existing = MagicMock()
        existing.service_id = 5
        imp = _agent_importer()
        # The guard itself must not raise; later steps are out of scope here.
        imp._ensure_ai_service_assignable(_svc(5, retired=True), existing, ConflictMode.OVERRIDE)

    def test_rename_ignores_existing_agent_service(self):
        existing = MagicMock()
        existing.service_id = 5
        with pytest.raises(ValueError, match="retired"):
            _agent_importer()._ensure_ai_service_assignable(
                _svc(5, retired=True), existing, ConflictMode.RENAME
            )


def _silo_export():
    export = MagicMock()
    export.silo.name = "S"
    export.silo.embedding_service_name = "svc1"
    export.embedding_service = None
    return export


def _silo_importer():
    imp = SiloImportService.__new__(SiloImportService)
    imp.session = MagicMock()
    return imp


class TestSiloImportRetired:
    def _run(self, service, existing_silo, mode, selected=None):
        imp = _silo_importer()
        validation = MagicMock()
        validation.requires_embedding_service_selection = False
        imp.session.query.return_value.filter.return_value.first.return_value = service
        imp.session.query.return_value.filter.return_value.order_by.return_value.first.return_value = service
        with patch.object(SiloImportService, "validate_import", return_value=validation), patch.object(
            SiloImportService, "get_by_name_and_app", return_value=existing_silo
        ):
            return imp.import_silo(_silo_export(), 10, mode, selected_embedding_service_id=selected)

    def test_selected_retired_service_rejected(self):
        with pytest.raises(ValueError, match="retired"):
            self._run(_svc(5, retired=True), None, ConflictMode.FAIL, selected=5)

    def test_name_fallback_retired_service_rejected(self):
        with pytest.raises(ValueError, match="retired"):
            self._run(_svc(5, retired=True), None, ConflictMode.FAIL)

    def test_override_with_different_retired_service_rejected(self):
        existing = MagicMock()
        existing.embedding_service_id = 1
        with pytest.raises(ValueError, match="retired"):
            self._run(_svc(5, retired=True), existing, ConflictMode.OVERRIDE, selected=5)

    def test_override_keeping_current_retired_service_passes_guard(self):
        existing = MagicMock()
        existing.embedding_service_id = 5
        with patch.object(SiloImportService, "get_by_name_and_app", return_value=existing):
            _silo_importer()._ensure_embedding_assignable(
                _svc(5, retired=True), _silo_export(), 10, ConflictMode.OVERRIDE
            )


# ---------------------------------------------------------------------------
# Item 4: domain embedding options carry lifecycle data
# ---------------------------------------------------------------------------

class TestDomainEmbeddingOptions:
    def test_options_include_lifecycle_fields(self):
        retired = _svc(1, retired=True, notice="moved")
        active = _svc(2)
        system = _svc(3, app_id=None, eos=FUTURE)
        with patch("services.domain_service.EmbeddingServiceRepository.get_by_app_id", return_value=[retired, active]), \
             patch("services.domain_service.EmbeddingServiceRepository.get_system_services", return_value=[system]), \
             patch("services.domain_service.ServiceLifecycleService.warning_days", return_value=60) as wd:
            options = DomainService.get_embedding_services_for_app(10, MagicMock())
        wd.assert_called_once()
        by_id = {o["service_id"]: o for o in options}
        assert by_id[1]["lifecycle_status"] == "retired"
        assert by_id[1]["deprecation_notice"] == "moved"
        assert by_id[1]["end_of_service_at"] is not None
        assert by_id[1]["is_system"] is False
        assert by_id[2]["lifecycle_status"] == "active"
        assert by_id[2]["end_of_service_at"] is None
        assert by_id[3]["lifecycle_status"] == "deprecated"
        assert by_id[3]["is_system"] is True
