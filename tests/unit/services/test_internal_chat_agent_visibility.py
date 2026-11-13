"""Unit tests: the hidden internal chat agent is invisible by default (AD-6 points 1, 2, 3, 10, 11).

No database: queries are built on an unbound Session and compiled (the terminal call is intercepted), and
service-level guards use mocks.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query, Session

from models.agent import AGENT_KIND_INTERNAL_CHAT, AGENT_KIND_STANDARD, Agent
from repositories.agent_repository import AgentRepository
from services.agent_service import AgentService

KIND_SQL = '"Agent".kind = '


def _compile(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


@pytest.fixture
def captured_sql():
    """Run repository code on an unbound Session, recording the SQL of every executed Query."""
    sqls: list[str] = []

    def _record(self, *a, **kw):
        sqls.append(_compile(self.statement))
        return []

    def _record_first(self, *a, **kw):
        sqls.append(_compile(self.statement))
        return None

    with patch.object(Query, "all", _record), patch.object(Query, "first", _record_first):
        yield sqls


def _agent(kind: str, **kw) -> MagicMock:
    agent = MagicMock()
    agent.kind = kind
    agent.is_internal_chat = kind == AGENT_KIND_INTERNAL_CHAT
    agent.app_id = kw.get("app_id", 1)
    return agent


class TestRepositoryFilters:
    def test_visible_clause_is_kind_standard(self):
        assert "'standard'" in _compile(AgentRepository.visible_agents_clause())

    def test_get_by_app_id_filters(self, captured_sql):
        AgentRepository.get_by_app_id(Session(), 1)
        assert f"{KIND_SQL}'{AGENT_KIND_STANDARD}'" in captured_sql[0]

    def test_get_tool_agents_filters(self, captured_sql):
        AgentRepository.get_tool_agents_by_app_id(Session(), 1)
        assert f"{KIND_SQL}'{AGENT_KIND_STANDARD}'" in captured_sql[0]

    def test_get_valid_tool_ids_filters(self):
        db = MagicMock()
        db.query.return_value.filter.return_value = []
        AgentRepository.get_valid_tool_ids(db, [1, 2], 1)
        clauses = [_compile(c) for c in db.query.return_value.filter.call_args.args]
        assert any(f"{KIND_SQL}'{AGENT_KIND_STANDARD}'" in c for c in clauses)

    @pytest.mark.parametrize("agent_type", ["basic", "agent", "any", "ocr", "ocr_agent"])
    def test_lookup_filters_in_sql_by_default(self, captured_sql, agent_type):
        AgentRepository.get_agent_by_id_and_type(Session(), 1, agent_type)
        assert captured_sql, "no query executed"
        assert all(f"{KIND_SQL}'{AGENT_KIND_STANDARD}'" in q for q in captured_sql)

    @pytest.mark.parametrize("agent_type", ["basic", "any", "ocr"])
    def test_lookup_include_internal_does_not_filter(self, captured_sql, agent_type):
        AgentRepository.get_agent_by_id_and_type(Session(), 1, agent_type, include_internal=True)
        assert captured_sql
        assert all(KIND_SQL not in q for q in captured_sql)

    def test_raw_get_by_id_unfiltered(self, captured_sql):
        AgentRepository.get_by_id(Session(), 1)
        assert KIND_SQL not in captured_sql[0]


class TestServiceGuards:
    def test_get_agent_passes_include_internal(self):
        with patch.object(AgentRepository, "get_agent_by_id_and_type", return_value=None) as m:
            AgentService().get_agent(MagicMock(), 1)
            AgentService().get_agent(MagicMock(), 1, include_internal=True)
        assert m.call_args_list[0].kwargs["include_internal"] is False
        assert m.call_args_list[1].kwargs["include_internal"] is True

    def test_ensure_not_internal(self):
        AgentService._ensure_not_internal(None)
        AgentService._ensure_not_internal(_agent(AGENT_KIND_STANDARD))
        with pytest.raises(ValueError, match="Agent not found"):
            AgentService._ensure_not_internal(_agent(AGENT_KIND_INTERNAL_CHAT))

    def test_create_or_update_rejects_internal(self):
        internal = _agent(AGENT_KIND_INTERNAL_CHAT)
        with patch.object(AgentRepository, "get_agent_by_id_and_type", return_value=internal) as m:
            with pytest.raises(ValueError, match="Agent not found"):
                AgentService().create_or_update_agent(MagicMock(), {"agent_id": 5, "app_id": 1}, "agent")
        assert m.call_args.kwargs["include_internal"] is True

    @pytest.mark.parametrize("method,arg", [
        ("update_agent_tools", []), ("update_agent_mcps", []), ("update_agent_skills", []),
    ])
    def test_association_updates_reject_internal(self, method, arg):
        db = MagicMock()
        with patch.object(AgentRepository, "get_by_id", return_value=_agent(AGENT_KIND_INTERNAL_CHAT)):
            with pytest.raises(ValueError, match="Agent not found"):
                getattr(AgentService(), method)(db, 5, arg)
        db.commit.assert_not_called()

    def test_update_middlewares_rejects_internal_via_identity_map(self):
        db = MagicMock()
        db.get.return_value = _agent(AGENT_KIND_INTERNAL_CHAT)
        with pytest.raises(ValueError, match="Agent not found"):
            AgentService().update_agent_middlewares(db, 5, [])
        db.get.assert_called_once_with(Agent, 5)
        db.query.assert_not_called()
        db.commit.assert_not_called()

    def test_prompt_playground_analytics_hide_internal(self):
        # Real lookup on a mock session whose SQL-filtered query finds nothing for the internal agent.
        db = MagicMock()
        db.query.return_value.filter.return_value.filter.return_value.first.return_value = None
        svc = AgentService()
        assert svc.update_agent_prompt(db, 5, "system", "x") is False
        assert svc.get_agent_playground_data(db, 5) is None
        assert svc.get_agent_analytics(db, 5) is None


class TestTierCount:
    @staticmethod
    def _db_counting_standard_only(standard: int, internal: int) -> MagicMock:
        """Mock session whose count query honours the compiled filter (counts internal rows only if unfiltered)."""
        db = MagicMock()

        def _filter(cond):
            q = MagicMock()
            q.scalar.return_value = standard if f"{KIND_SQL}'standard'" in _compile(cond) else standard + internal
            return q

        db.query.return_value.filter.side_effect = _filter
        return db

    def _check(self, db):
        from services.tier_enforcement_service import TierEnforcementService

        with patch("services.tier_enforcement_service.is_self_managed", return_value=False), \
             patch("services.tier_enforcement_service._get_effective_tier", return_value="free"), \
             patch("services.tier_enforcement_service.TierConfigRepository") as repo:
            repo.return_value.get_limit.return_value = 5
            TierEnforcementService.check_resource_limit(db, 1, "agents")

    def test_internal_agent_does_not_count_against_limit(self):
        # limit 5, 4 standard + 1 internal: would raise (5 >= 5) if the internal agent were counted.
        self._check(self._db_counting_standard_only(standard=4, internal=1))

    def test_standard_agents_at_limit_still_raise(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            self._check(self._db_counting_standard_only(standard=5, internal=1))
        assert exc.value.status_code == 403


class TestFreezeFilters:
    @staticmethod
    def _recording_db(seen: list[str]) -> MagicMock:
        db = MagicMock()

        def _query(model):
            q = MagicMock()

            def _filter(*conds):
                if model is Agent:
                    seen.extend(_compile(c) for c in conds)
                f = MagicMock()
                f.order_by.return_value.all.return_value = []
                f.all.return_value = []
                return f

            q.filter.side_effect = _filter
            return q

        db.query.side_effect = _query
        return db

    def test_apply_freeze_excludes_internal(self):
        from services.freeze_service import FreezeService

        seen: list[str] = []
        db = self._recording_db(seen)
        app = MagicMock(app_id=1)
        db.query.side_effect = None
        base = self._recording_db(seen).query.side_effect

        def _query(model):
            if model is App_:
                q = MagicMock()
                q.filter.return_value.order_by.return_value.all.return_value = [app]
                return q
            return base(model)

        from models.app import App as App_
        db.query.side_effect = _query
        with patch("services.freeze_service.TierConfigRepository") as repo:
            repo.return_value.get_limit.return_value = 1
            FreezeService.apply_freeze(db, 1, "free")
        assert seen and all(f"{KIND_SQL}'standard'" in c for c in seen)

    def test_recalculate_on_delete_excludes_internal(self):
        from services.freeze_service import FreezeService

        seen: list[str] = []
        db = self._recording_db(seen)
        with patch("services.freeze_service.TierConfigRepository") as repo, \
             patch("services.freeze_service._effective_tier_for_user", return_value="free"):
            repo.return_value.get_limit.return_value = 1
            FreezeService.recalculate_on_delete(db, 1, "agents", app_id=1)
        assert seen and all(f"{KIND_SQL}'standard'" in c for c in seen)


class TestImportNameLookups:
    def test_get_by_name_and_app_filters_standard(self, captured_sql):
        from services.agent_import_service import AgentImportService

        svc = AgentImportService.__new__(AgentImportService)
        svc.session = Session()
        svc.get_by_name_and_app("x", 1)
        assert f"{KIND_SQL}'standard'" in captured_sql[0]

    def test_every_agent_query_in_import_service_uses_the_shared_clause(self):
        import inspect
        import re
        from services import agent_import_service as mod

        src = inspect.getsource(mod)
        queries = re.findall(r"\.query\(Agent\)(.*?)\.first\(\)", src, flags=re.S)
        assert len(queries) == 3
        assert all("Agent.visible_clause()" in q for q in queries)


class TestServiceUsageFilters:
    @staticmethod
    def _executed(call) -> str:
        db = MagicMock()
        db.execute.return_value.scalar_one.return_value = 0
        db.execute.return_value.scalars.return_value.all.return_value = []
        db.execute.return_value.__iter__.return_value = iter([])
        call(db)
        return " ".join(_compile(c.args[0]) for c in db.execute.call_args_list)

    def test_count_agents_on_ai_service(self):
        from repositories.service_usage_repository import ServiceUsageQueries as Q

        assert f"{KIND_SQL}'standard'" in self._executed(lambda db: Q.count_agents_on_ai_service(db, 1, 2))

    def test_move_agents(self):
        from repositories.service_usage_repository import ServiceUsageQueries as Q

        assert f"{KIND_SQL}'standard'" in self._executed(lambda db: Q.move_agents(db, 1, 2, 3))

    def test_move_sandbox_usage_agent_statement(self):
        from repositories.service_usage_repository import ServiceUsageQueries as Q

        sql = self._executed(lambda db: Q.move_sandbox_usage(db, 1, 2, 3))
        assert f"{KIND_SQL}'standard'" in sql

    def test_agents_listing(self):
        from repositories.service_usage_repository import ServiceUsageQueries as Q

        sql = self._executed(lambda db: Q._agents(db, Agent.service_id == 2, 1))
        assert f"{KIND_SQL}'standard'" in sql


class TestRawLookupAllowList:
    """New `AgentRepository.get_by_id(` call sites must be a conscious decision (raw lookup includes internal)."""

    ALLOWED = {
        "repositories/agent_execution_repository.py": 1,  # request-count bump must work for the internal agent
        "services/agent_service.py": 4,  # update_agent_tools/mcps/skills (each guarded) + delete_agent (cascade)
        "repositories/agent_repository.py": 1,  # delete_by_id (cascade deletion)
    }

    def test_no_unreviewed_raw_get_by_id_callers(self):
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[3] / "backend"
        found: dict[str, int] = {}
        for path in root.rglob("*.py"):
            n = len(re.findall(r"AgentRepository\.get_by_id\(", path.read_text(encoding="utf-8")))
            if n:
                found[path.relative_to(root).as_posix()] = n
        assert found == self.ALLOWED, f"unreviewed raw AgentRepository.get_by_id callers: {found}"


class TestExportImport:
    def test_full_export_skips_internal(self):
        from services.full_app_export_service import FullAppExportService

        svc = FullAppExportService.__new__(FullAppExportService)
        svc.app_repo = MagicMock()
        std, internal = _agent(AGENT_KIND_STANDARD), _agent(AGENT_KIND_INTERNAL_CHAT)
        std.service_id = internal.service_id = 1
        std.agent_id, internal.agent_id = 1, 2
        svc.app_repo.get_agents_by_app_id.return_value = [std, internal]
        svc.agent_export = MagicMock()
        svc._export_all_agents(1)
        exported_ids = [c.args[0] for c in svc.agent_export.export_agent.call_args_list]
        assert exported_ids == [1]


class TestSingleAgentExport:
    def test_export_agent_internal_is_not_found_like_missing(self):
        from services.agent_export_service import AgentExportService

        svc = AgentExportService.__new__(AgentExportService)
        svc.session = MagicMock()
        with patch.object(AgentRepository, "get_agent_by_id_and_type", return_value=None) as lookup:
            with pytest.raises(ValueError, match="Agent with ID 7 not found"):
                svc.export_agent(agent_id=7, app_id=1, user_id=1)
        assert lookup.call_args.args[2] == "any"
        assert not lookup.call_args.kwargs.get("include_internal", False)

    def test_export_router_checks_visibility_first(self):
        import inspect
        from routers.internal import agents as mod

        src = inspect.getsource(mod.export_agent)
        assert src.index("_get_agent_or_404") < src.index("AgentExportService(")
