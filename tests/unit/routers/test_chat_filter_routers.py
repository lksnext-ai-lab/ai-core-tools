"""Chat-time filter endpoints: Playground (internal), public API and Marketplace."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from routers.internal import agents as internal_agents
from routers.internal import marketplace
from routers.public.v1 import agents as public_agents

AGENT = SimpleNamespace(agent_id=3, app_id=1)
CONVERSATION = SimpleNamespace(conversation_id=9, agent_id=3)
CURRENT_USER = SimpleNamespace(identity=SimpleNamespace(id="5"))


class TestInternalAgentChatFilters:
    @pytest.fixture(autouse=True)
    def agent_lookup(self, mocker):
        return mocker.patch.object(internal_agents, "_get_agent_or_404", return_value=AGENT)

    @pytest.mark.asyncio
    async def test_available_fields_are_computed_from_the_candidates(self):
        service = MagicMock()
        service.get_available_chat_filter_fields.return_value = [{"name": "empresa"}]
        db = MagicMock()

        result = await internal_agents.get_available_chat_filter_fields(
            app_id=1, agent_id=0, auth_context=None, role=None, db=db, agent_service=service,
            tool_ids=[4, 5], silo_id=2,
        )

        assert result == {"fields": [{"name": "empresa"}]}
        service.get_available_chat_filter_fields.assert_called_once_with(db, [4, 5], 2)

    @pytest.mark.asyncio
    async def test_filter_values_are_scoped_to_the_app_agent(self, agent_lookup):
        service = MagicMock()
        service.get_chat_filter_values.return_value = [{"field_name": "empresa", "values": ["A"]}]
        db = MagicMock()

        result = await internal_agents.get_chat_filter_values(
            app_id=1, agent_id=3, auth_context=None, role=None, db=db, agent_service=service,
        )

        assert result == {"filters": [{"field_name": "empresa", "values": ["A"]}]}
        agent_lookup.assert_called_once_with(db, 3, 1)
        service.get_chat_filter_values.assert_called_once_with(db, AGENT)

    @pytest.mark.asyncio
    async def test_field_search_trims_the_query_and_caps_the_result(self):
        service = MagicMock()
        service.get_chat_filter_field_values.return_value = ["A", "B", "C"]
        db = MagicMock()

        result = await internal_agents.search_chat_filter_field_values(
            app_id=1, agent_id=3, field_name="empresa", auth_context=None, role=None, db=db,
            agent_service=service, q="  adit  ", limit=2,
        )

        assert result == {"values": ["A", "B"]}
        service.get_chat_filter_field_values.assert_called_once_with(
            db, AGENT, "empresa", query="adit", limit=2,
        )

    @pytest.mark.asyncio
    async def test_blank_field_search_lists_without_a_query(self):
        service = MagicMock()
        service.get_chat_filter_field_values.return_value = []

        await internal_agents.search_chat_filter_field_values(
            app_id=1, agent_id=3, field_name="empresa", auth_context=None, role=None, db=MagicMock(),
            agent_service=service, q="   ", limit=50,
        )

        assert service.get_chat_filter_field_values.call_args.kwargs["query"] is None

    @pytest.mark.asyncio
    async def test_field_not_exposed_returns_404(self):
        service = MagicMock()
        service.get_chat_filter_field_values.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await internal_agents.search_chat_filter_field_values(
                app_id=1, agent_id=3, field_name="secret", auth_context=None, role=None, db=MagicMock(),
                agent_service=service, q="", limit=50,
            )

        assert exc_info.value.status_code == 404


class TestPublicAgentChatFilterField:
    @pytest.fixture(autouse=True)
    def auth(self, mocker):
        mocker.patch.object(public_agents, "validate_api_key_for_app", return_value=None)
        return mocker.patch.object(public_agents, "validate_agent_ownership", return_value=AGENT)

    @pytest.fixture
    def service(self, mocker):
        return mocker.patch.object(public_agents, "AgentService").return_value

    @pytest.mark.asyncio
    async def test_returns_the_field_values(self, auth, service):
        service.get_chat_filter_field_values.return_value = ["A", "B"]
        db = MagicMock()

        result = await public_agents.get_chat_filter_field_values(
            app_id=1, agent_id=3, field_name="empresa", api_key="key", db=db,
        )

        assert result.field_name == "empresa"
        assert result.values == ["A", "B"]
        auth.assert_called_once_with(db, 3, 1)

    @pytest.mark.asyncio
    async def test_field_not_exposed_returns_404(self, service):
        service.get_chat_filter_field_values.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await public_agents.get_chat_filter_field_values(
                app_id=1, agent_id=3, field_name="secret", api_key="key", db=MagicMock(),
            )

        assert exc_info.value.status_code == 404


class TestMarketplaceChatFilters:
    @pytest.fixture(autouse=True)
    def guards(self, mocker):
        return SimpleNamespace(
            validate=mocker.patch.object(
                marketplace, "_validate_marketplace_conversation", return_value=(CONVERSATION, AGENT),
            ),
            quota=mocker.patch.object(marketplace, "_enforce_marketplace_quota"),
            rate_limit=mocker.patch.object(marketplace, "_apply_marketplace_agent_rate_limit"),
        )

    @pytest.fixture
    def service(self, mocker):
        return mocker.patch.object(marketplace, "AgentService").return_value

    @pytest.mark.asyncio
    async def test_filter_values_check_quota_without_consuming_rate_limit(self, guards, service):
        service.get_chat_filter_values.return_value = [{"field_name": "empresa", "values": ["A"]}]
        db = MagicMock()

        result = await marketplace.get_marketplace_chat_filter_values(
            conversation_id=9, db=db, current_user=CURRENT_USER,
        )

        assert result == {"filters": [{"field_name": "empresa", "values": ["A"]}]}
        guards.validate.assert_called_once_with(9, 5, db)
        guards.quota.assert_called_once_with(5, db)
        guards.rate_limit.assert_not_called()

    @pytest.mark.asyncio
    async def test_field_search_skips_quota_and_rate_limit(self, guards, service):
        service.get_chat_filter_field_values.return_value = ["A", "B", "C"]
        db = MagicMock()

        result = await marketplace.search_marketplace_chat_filter_values(
            conversation_id=9, field_name="empresa", db=db, current_user=CURRENT_USER, q=" adit ", limit=2,
        )

        assert result == {"values": ["A", "B"]}
        service.get_chat_filter_field_values.assert_called_once_with(
            db, AGENT, "empresa", query="adit", limit=2,
        )
        guards.quota.assert_not_called()
        guards.rate_limit.assert_not_called()

    @pytest.mark.asyncio
    async def test_field_not_exposed_returns_404(self, service):
        service.get_chat_filter_field_values.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await marketplace.search_marketplace_chat_filter_values(
                conversation_id=9, field_name="secret", db=MagicMock(), current_user=CURRENT_USER, q="", limit=50,
            )

        assert exc_info.value.status_code == 404


class TestMarketplaceSearchParamsParsing:
    @pytest.mark.parametrize("raw", [None, ""])
    def test_missing_value_is_none(self, raw):
        assert marketplace._parse_optional_json(raw, "search_params") is None

    def test_valid_json_is_decoded(self):
        assert marketplace._parse_optional_json('{"filter": {"empresa": "A"}}', "search_params") == {
            "filter": {"empresa": "A"}
        }

    def test_invalid_json_is_ignored(self, mocker):
        logger = mocker.patch.object(marketplace, "logger")

        assert marketplace._parse_optional_json("{not json", "search_params") is None
        logger.warning.assert_called_once()
