"""A System One evaluation must not keep its database connection while it waits for a slot or for the server."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.system_one_agent import SystemOneAgent
from services.agent_execution_service import AgentExecutionService

pytestmark = pytest.mark.asyncio


async def test_the_database_session_is_released_before_the_evaluation_starts():
    db = MagicMock()
    seen = {}
    agent = SystemOneAgent(agent_id=3, app_id=9, name="Triage", system_one_service_id=1, questions=[], is_tool=True)

    async def evaluate(*args, **kwargs):
        seen["released_when_evaluating"] = db.commit.called
        return MagicMock()

    service = AgentExecutionService()
    with patch.object(service.agent_service, "get_agent", return_value=agent), \
         patch("services.agent_execution_service.SystemOneEvaluator.snapshot", return_value=MagicMock()), \
         patch("services.agent_execution_service.SystemOneEvaluator.evaluate", AsyncMock(side_effect=evaluate)), \
         patch.object(AgentExecutionService, "_update_request_count"):
        await service.execute_agent_system_one(3, "text", None, {}, db, app_id=9)

    assert seen["released_when_evaluating"] is True
