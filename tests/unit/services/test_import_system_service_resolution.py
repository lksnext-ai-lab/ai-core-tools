"""Import resolves AI / embedding services by name or id, falling back to system services (app_id NULL)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from schemas.import_schemas import ConflictMode
from services.agent_import_service import AgentImportService
from services.silo_import_service import SiloImportService

APP = 10
PAST = datetime.now(timezone.utc) - timedelta(days=3)


class _StopImport(Exception):
    """Raised right after service resolution to stop the (mocked) import."""


def _svc(service_id, app_id, retired=False, name="gpt-5.4") -> MagicMock:
    s = MagicMock()
    s.service_id = service_id
    s.name = name
    s.app_id = app_id
    s.end_of_service_at = PAST if retired else None
    s.deprecation_notice = None
    return s


def _agent_export(service_name="gpt-5.4") -> MagicMock:
    export = MagicMock()
    export.agent.name = "A"
    export.agent.service_name = service_name
    export.ai_service = None
    return export


def _agent_importer(name_results=()):
    """Importer whose name lookup yields ``name_results`` in order (app scope first, then system)."""
    imp = AgentImportService.__new__(AgentImportService)
    imp.session = MagicMock()
    imp.session.query.return_value.filter.return_value.order_by.return_value.first.side_effect = list(name_results)
    return imp


class TestFindAiServiceByName:
    def test_app_service_preferred_over_system(self):
        app_svc = _svc(1, APP)
        imp = _agent_importer([app_svc])
        assert imp._find_ai_service_by_name("gpt-5.4", APP) is app_svc
        # system scope never consulted once the app has one
        assert imp.session.query.return_value.filter.return_value.order_by.return_value.first.call_count == 1

    def test_system_fallback_when_app_has_none(self):
        system_svc = _svc(2, None)
        imp = _agent_importer([None, system_svc])
        assert imp._find_ai_service_by_name("gpt-5.4", APP) is system_svc

    def test_none_when_neither_exists(self):
        imp = _agent_importer([None, None])
        assert imp._find_ai_service_by_name("gpt-5.4", APP) is None

    def test_lookup_is_deterministic_and_scoped(self):
        """Queries are ordered by service_id and only ever scoped to the app or to NULL."""
        imp = _agent_importer([None, None])
        imp._find_ai_service_by_name("gpt-5.4", APP)
        query = imp.session.query.return_value
        assert query.filter.call_count == 2
        query.filter.return_value.order_by.assert_called()
        scopes = [str(c.args[1].compile(compile_kwargs={"literal_binds": True})) for c in query.filter.call_args_list]
        assert scopes[0].endswith(f"= {APP}")
        assert "IS NULL" in scopes[1]


class TestAgentImportNameResolution:
    def test_system_service_resolved_by_name(self):
        system_svc = _svc(2, None)
        imp = _agent_importer([None, system_svc])
        with patch("services.agent_import_service.validate_export_version"), patch.object(
            AgentImportService, "get_by_name_and_app", return_value=None
        ), patch.object(imp, "_ensure_ai_service_assignable", side_effect=_StopImport) as guard:
            try:
                imp.import_agent(_agent_export(), APP, ConflictMode.FAIL)
            except _StopImport:
                pass
        guard.assert_called_once()
        assert guard.call_args.args[0] is system_svc

    def test_not_found_error_when_neither_exists(self):
        imp = _agent_importer([None, None])
        with patch("services.agent_import_service.validate_export_version"), patch.object(
            AgentImportService, "get_by_name_and_app", return_value=None
        ):
            with pytest.raises(ValueError, match="AI service 'gpt-5.4' not found"):
                imp.import_agent(_agent_export(), APP, ConflictMode.FAIL)

    def test_other_apps_service_never_matched(self):
        # The queries only match app == APP or NULL; another app's service is never returned.
        imp = _agent_importer([None, None])
        with patch("services.agent_import_service.validate_export_version"), patch.object(
            AgentImportService, "get_by_name_and_app", return_value=None
        ):
            with pytest.raises(ValueError, match="not found"):
                imp.import_agent(_agent_export(), APP, ConflictMode.FAIL)

    def test_retired_system_service_by_name_rejected_in_rename(self):
        imp = _agent_importer([None, _svc(2, None, retired=True)])
        existing = MagicMock()
        existing.service_id = 2
        with patch("services.agent_import_service.validate_export_version"), patch.object(
            AgentImportService, "get_by_name_and_app", side_effect=[existing, existing, None]
        ):
            with pytest.raises(ValueError, match="retired"):
                imp.import_agent(_agent_export(), APP, ConflictMode.RENAME)


class TestAgentImportSelectedId:
    def _run(self, selected_service):
        imp = _agent_importer()
        with patch("services.agent_import_service.validate_export_version"), patch.object(
            AgentImportService, "get_by_name_and_app", return_value=None
        ), patch("services.agent_import_service.AIServiceRepository.get_by_id", return_value=selected_service), patch.object(
            imp, "_ensure_ai_service_assignable", side_effect=_StopImport
        ) as guard:
            try:
                imp.import_agent(_agent_export(), APP, ConflictMode.FAIL, selected_ai_service_id=5)
            except _StopImport:
                pass
        return guard

    def test_selected_system_service_accepted(self):
        system_svc = _svc(5, None)
        guard = self._run(system_svc)
        guard.assert_called_once()
        assert guard.call_args.args[0] is system_svc

    def test_selected_own_service_accepted(self):
        assert self._run(_svc(5, APP)).call_count == 1

    def test_selected_other_apps_service_rejected(self):
        imp = _agent_importer()
        with patch("services.agent_import_service.validate_export_version"), patch.object(
            AgentImportService, "get_by_name_and_app", return_value=None
        ), patch("services.agent_import_service.AIServiceRepository.get_by_id", return_value=_svc(5, 99)):
            with pytest.raises(ValueError, match="Selected AI service 5 not found"):
                imp.import_agent(_agent_export(), APP, ConflictMode.FAIL, selected_ai_service_id=5)

    def test_selected_missing_service_rejected(self):
        imp = _agent_importer()
        with patch("services.agent_import_service.validate_export_version"), patch.object(
            AgentImportService, "get_by_name_and_app", return_value=None
        ), patch("services.agent_import_service.AIServiceRepository.get_by_id", return_value=None):
            with pytest.raises(ValueError, match="not found"):
                imp.import_agent(_agent_export(), APP, ConflictMode.FAIL, selected_ai_service_id=5)


class TestAgentImportMapFallThrough:
    def test_name_missing_from_map_falls_through_to_system_lookup(self):
        system_svc = _svc(2, None)
        imp = _agent_importer([None, system_svc])
        with patch("services.agent_import_service.validate_export_version"), patch.object(
            AgentImportService, "get_by_name_and_app", return_value=None
        ), patch.object(imp, "_ensure_ai_service_assignable", side_effect=_StopImport) as guard:
            try:
                imp.import_agent(_agent_export(), APP, ConflictMode.FAIL, ai_service_id_map={"other": 7})
            except _StopImport:
                pass
        assert guard.call_args.args[0] is system_svc


def _silo_export() -> MagicMock:
    export = MagicMock()
    export.silo.name = "S"
    export.silo.embedding_service_name = "emb"
    export.embedding_service = None
    return export


class TestSiloImportEmbeddingByName:
    def _importer(self, name_results):
        imp = SiloImportService.__new__(SiloImportService)
        imp.session = MagicMock()
        imp.session.query.return_value.filter.return_value.order_by.return_value.first.side_effect = list(name_results)
        return imp

    def test_find_prefers_app_service(self):
        app_svc = _svc(1, APP, name="emb")
        imp = self._importer([app_svc])
        assert imp._find_embedding_service_by_name("emb", APP) is app_svc

    def test_find_falls_back_to_system(self):
        system_svc = _svc(2, None, name="emb")
        imp = self._importer([None, system_svc])
        assert imp._find_embedding_service_by_name("emb", APP) is system_svc

    def test_import_silo_resolves_system_embedding_by_name_without_selection(self):
        system_svc = _svc(2, None, name="emb")
        # find is called by the "selection required" check and again by the name step
        imp = self._importer([None, system_svc, None, system_svc])
        validation = MagicMock()
        validation.requires_embedding_service_selection = True
        with patch.object(SiloImportService, "validate_import", return_value=validation), patch.object(
            SiloImportService, "get_by_name_and_app", return_value=None
        ), patch.object(imp, "_ensure_embedding_assignable", side_effect=_StopImport) as guard:
            try:
                imp.import_silo(_silo_export(), APP, ConflictMode.FAIL)
            except _StopImport:
                pass
        guard.assert_called_once()
        assert guard.call_args.args[0] is system_svc

    def test_import_silo_still_requires_selection_when_unresolvable(self):
        imp = self._importer([None, None])
        validation = MagicMock()
        validation.requires_embedding_service_selection = True
        with patch.object(SiloImportService, "validate_import", return_value=validation):
            with pytest.raises(ValueError, match="selection required"):
                imp.import_silo(_silo_export(), APP, ConflictMode.FAIL)
