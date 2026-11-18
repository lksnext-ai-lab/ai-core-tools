from datetime import datetime
from unittest.mock import MagicMock

from repositories.agent_execution_repository import AgentExecutionRepository


def test_update_agent_request_count_updates_last_used_date(mocker):
    agent = MagicMock(request_count=2, last_used_date=None)
    db = MagicMock()
    mocker.patch(
        "repositories.agent_execution_repository.AgentRepository.get_by_id",
        return_value=agent,
    )

    before_update = datetime.now()
    result = AgentExecutionRepository.update_agent_request_count(db, agent_id=123)
    after_update = datetime.now()

    assert result is True
    assert agent.request_count == 3
    assert before_update <= agent.last_used_date <= after_update
    db.commit.assert_called_once_with()
    db.rollback.assert_not_called()
