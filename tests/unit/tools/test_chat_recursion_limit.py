"""AICT_CHAT_RECURSION_LIMIT: the App Chat's own graph step limit; agents keep AICT_AGENT_RECURSION_LIMIT."""
from unittest.mock import patch

import pytest

import tools.agentTools as at


def test_chat_default_is_100_and_agent_default_stays_50():
    with patch.dict("os.environ", {}, clear=True):
        assert at._load_recursion_limit("AICT_CHAT_RECURSION_LIMIT", at._DEFAULT_CHAT_RECURSION_LIMIT) == 100
        assert at._load_recursion_limit() == 50


@pytest.mark.parametrize("bad", ["nope", "0", "-3", ""])
def test_invalid_chat_value_falls_back_to_100_with_a_warning(bad):
    seen = []
    with patch.dict("os.environ", {"AICT_CHAT_RECURSION_LIMIT": bad}), \
         patch.object(at.logger, "warning", side_effect=lambda m, *a: seen.append(m % a)):
        assert at._load_recursion_limit("AICT_CHAT_RECURSION_LIMIT", 100) == 100
    assert any("AICT_CHAT_RECURSION_LIMIT" in line for line in seen)


def test_the_chat_config_uses_the_chat_limit_and_agents_the_agent_limit(monkeypatch):
    monkeypatch.setattr(at, "AICT_CHAT_RECURSION_LIMIT", 123)
    monkeypatch.setattr(at, "AICT_AGENT_RECURSION_LIMIT", 45)
    agent = type("A", (), {"agent_id": 1})()
    with patch.object(at, "compute_thread_id", return_value="t"):
        assert at.prepare_agent_config(agent, chat_turn=True)["recursion_limit"] == 123
        assert at.prepare_agent_config(agent)["recursion_limit"] == 45
