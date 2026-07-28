"""Integration test for orchestrator-level metadata dropdown chat filters.

Exercises the real Gate 1 -> Gate 2 -> Gate 3 pipeline (``create_agent`` ->
``IACTTool.create`` -> ``_resolve_and_build_retriever_tool`` ->
``resolve_search_params``) against real DB-backed Agent/Silo/OutputParser/AgentTool
rows (real lazy-loaded relationships via the ``db`` fixture's savepoint-scoped
session). No live LLM or embedding service is required or contacted:

  - ``get_llm`` / ``create_langchain_agent`` / ``MCPClientManager.get_client`` are
    mocked (pure scaffolding, no I/O).
  - ``MetadataValuesCacheService.get_distinct_values`` is mocked to ``[]`` so tool
    description/schema building never attempts a real vector store connection.
  - ``SiloService.get_silo_retriever`` (the actual vector store entry point) is
    mocked so we can assert on the filter dict it would have received — this is
    the "correct backend filter dict was constructed and would be passed to the
    vector store" scope-down called out in the test plan, since a full live
    embedding/pgvector round-trip is impractical in this suite.

Scenario: a 2-subagent orchestrator.
  - Subagent A's silo declares ``machine_model`` (a real OutputParser-backed
    metadata_definition).
  - Subagent B's silo does NOT declare ``machine_model`` at all (different
    metadata schema).
  - Orchestrator.exposed_chat_filters = ["machine_model"].

Verifies:
  - A caller filter of ``{"machine_model": "X100"}`` reaches subagent A's
    retrieval call scoped correctly (Gate 2 passes it through).
  - Subagent B's retrieval runs unaffected — not silently zeroed out by a filter
    on a field it doesn't have (Gate 2 drops it cleanly for B only, without
    erroring).
  - Subagent A's own ``rag_fixed_filters`` (when set) wins over the caller's
    selection (Gate 3 — unchanged existing precedence, reached via the new path).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixture-building helpers (real, DB-flushed ORM rows within the test's
# savepoint-scoped transaction — nothing is committed to the real DB).
# ---------------------------------------------------------------------------


def _make_output_parser(db, app_id, fields):
    from models.output_parser import OutputParser

    parser = OutputParser(name="Test Metadata Parser", fields=fields, app_id=app_id)
    db.add(parser)
    db.flush()
    return parser


def _make_silo(db, app_id, metadata_definition_id, vector_db_type="PGVECTOR"):
    from models.silo import Silo

    silo = Silo(
        name=f"Test Silo {metadata_definition_id}",
        silo_type="REPO",
        app_id=app_id,
        metadata_definition_id=metadata_definition_id,
        vector_db_type=vector_db_type,
    )
    db.add(silo)
    db.flush()
    return silo


def _make_subagent(db, app_id, silo_id, rag_fixed_filters=None, name="SubAgent"):
    from models.agent import Agent

    agent = Agent(
        name=name,
        description=f"{name} description",
        system_prompt="",
        app_id=app_id,
        silo_id=silo_id,
        is_tool=True,
        rag_fixed_filters=rag_fixed_filters,
    )
    db.add(agent)
    db.flush()
    return agent


def _make_orchestrator(db, app_id, exposed_chat_filters, sub_agents):
    from models.agent import Agent, AgentTool

    orchestrator = Agent(
        name="Orchestrator",
        description="Orchestrator description",
        system_prompt="",
        app_id=app_id,
        silo_id=None,
        has_memory=False,
        exposed_chat_filters=exposed_chat_filters,
    )
    db.add(orchestrator)
    db.flush()

    for sub in sub_agents:
        db.add(AgentTool(agent_id=orchestrator.agent_id, tool_id=sub.agent_id))
    db.flush()
    db.refresh(orchestrator)
    return orchestrator


def _retriever_tools(tools):
    """Filter a sub-agent's tool list down to the dynamic retriever tool.

    Distinguished by name convention (``search_{slug}_{silo_id}`` — see
    ``build_retriever_tool_name``), which is more robust than filtering on
    ``coroutine is not None`` alone.
    """
    return [t for t in tools if getattr(t, "name", "").startswith("search_")]


class TestOrchestratorChatFiltersIntegration:
    """2-subagent orchestrator: Gate 1 + Gate 2 (+ Gate 3) composed end-to-end."""

    @pytest.mark.asyncio
    async def test_scoped_filter_reaches_declaring_subagent_only(self, db, fake_app):
        from tools import agentTools

        parser_a = _make_output_parser(
            db, fake_app.app_id, fields=[{"name": "machine_model", "type": "str"}]
        )
        parser_b = _make_output_parser(
            db, fake_app.app_id, fields=[{"name": "other_field", "type": "str"}]
        )
        silo_a = _make_silo(db, fake_app.app_id, parser_a.parser_id)
        silo_b = _make_silo(db, fake_app.app_id, parser_b.parser_id)

        sub_a = _make_subagent(db, fake_app.app_id, silo_a.silo_id, name="SubA")
        sub_b = _make_subagent(db, fake_app.app_id, silo_b.silo_id, name="SubB")

        orchestrator = _make_orchestrator(
            db,
            fake_app.app_id,
            exposed_chat_filters=["machine_model"],
            sub_agents=[sub_a, sub_b],
        )

        fake_retriever = MagicMock()
        fake_retriever.ainvoke = AsyncMock(return_value=[])
        mock_get_silo_retriever = MagicMock(return_value=fake_retriever)

        with (
            patch("tools.agentTools.get_llm", return_value=object()),
            patch(
                "tools.agentTools.create_langchain_agent", return_value=MagicMock()
            ) as mock_create,
            patch.object(
                agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)
            ),
            patch(
                "services.silo_service.SiloService.get_silo_retriever",
                new=mock_get_silo_retriever,
            ),
            patch(
                "services.metadata_values_cache_service.MetadataValuesCacheService.get_distinct_values",
                return_value=[],
            ),
        ):
            await agentTools.create_agent(
                orchestrator, search_params={"filter": {"machine_model": "X100"}}
            )

            # tool_associations loop order == insertion order (SubA, SubB); each
            # IACTTool.create() call triggers its own create_langchain_agent call
            # before the orchestrator's own (final) call.
            sub_a_tools = mock_create.call_args_list[0].kwargs["tools"]
            sub_b_tools = mock_create.call_args_list[1].kwargs["tools"]

            retriever_tools_a = _retriever_tools(sub_a_tools)
            retriever_tools_b = _retriever_tools(sub_b_tools)
            assert len(retriever_tools_a) == 1
            assert len(retriever_tools_b) == 1

            await retriever_tools_a[0].coroutine(query="find machine")
            await retriever_tools_b[0].coroutine(query="find something")

        calls_by_silo_id = {
            call.args[0]: call.args[1] for call in mock_get_silo_retriever.call_args_list
        }

        # Subagent A: the caller's whitelisted filter reached the vector store call.
        sp_a = calls_by_silo_id[silo_a.silo_id]
        assert sp_a is not None
        assert sp_a.get("filter", {}).get("machine_model") == {"$eq": "X100"}

        # Subagent B: unaffected — Gate 2 dropped the field cleanly since silo_b
        # doesn't declare it; no filter key leaked through, retrieval still runs.
        sp_b = calls_by_silo_id[silo_b.silo_id]
        assert not (sp_b or {}).get("filter", {})

    @pytest.mark.asyncio
    async def test_subagent_fixed_filter_wins_over_caller_selection(self, db, fake_app):
        """Gate 3 (unchanged existing resolve_search_params precedence) still
        holds when reached via the new Gate 1/2 subagent path: subagent A's own
        rag_fixed_filters pins machine_model=X200, beating the caller's X100
        selection — an orchestrator caller can never loosen an admin scoping
        floor set on a specific subagent.
        """
        from tools import agentTools

        parser_a = _make_output_parser(
            db, fake_app.app_id, fields=[{"name": "machine_model", "type": "str"}]
        )
        silo_a = _make_silo(db, fake_app.app_id, parser_a.parser_id)

        sub_a = _make_subagent(
            db,
            fake_app.app_id,
            silo_a.silo_id,
            rag_fixed_filters=[{"field": "machine_model", "op": "$eq", "value": "X200"}],
            name="SubA",
        )

        orchestrator = _make_orchestrator(
            db,
            fake_app.app_id,
            exposed_chat_filters=["machine_model"],
            sub_agents=[sub_a],
        )

        fake_retriever = MagicMock()
        fake_retriever.ainvoke = AsyncMock(return_value=[])
        mock_get_silo_retriever = MagicMock(return_value=fake_retriever)

        with (
            patch("tools.agentTools.get_llm", return_value=object()),
            patch(
                "tools.agentTools.create_langchain_agent", return_value=MagicMock()
            ) as mock_create,
            patch.object(
                agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)
            ),
            patch(
                "services.silo_service.SiloService.get_silo_retriever",
                new=mock_get_silo_retriever,
            ),
            patch(
                "services.metadata_values_cache_service.MetadataValuesCacheService.get_distinct_values",
                return_value=[],
            ),
        ):
            await agentTools.create_agent(
                orchestrator, search_params={"filter": {"machine_model": "X100"}}
            )

            sub_a_tools = mock_create.call_args_list[0].kwargs["tools"]
            retriever_tools_a = _retriever_tools(sub_a_tools)
            assert len(retriever_tools_a) == 1

            await retriever_tools_a[0].coroutine(query="find machine")

        call = mock_get_silo_retriever.call_args_list[0]
        call_search_params = call.args[1]
        assert call_search_params["filter"]["machine_model"] == {"$eq": "X200"}
