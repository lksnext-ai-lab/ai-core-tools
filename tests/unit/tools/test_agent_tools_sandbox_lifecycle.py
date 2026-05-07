from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_agent():
    return SimpleNamespace(
        agent_id=7,
        ai_service=None,
        enable_code_interpreter=True,
        has_memory=False,
        memory_max_tokens=None,
        memory_max_messages=None,
        memory_summarize_threshold=None,
        output_parser_id=None,
        server_tools=[],
        tool_associations=[],
        silo_id=None,
        silo=None,
        skill_associations=[],
        mcp_associations=[],
        system_prompt="You are useful.",
    )


@pytest.mark.asyncio
async def test_create_agent_reuses_prepared_sandbox_handle(tmp_path):
    from tools.agentTools import create_agent
    from tools.sandbox.provider import SandboxHandle

    agent = _make_agent()
    handle = SandboxHandle(
        sandbox_id="prepared-001",
        working_dir=str(tmp_path),
        provider_name="opensandbox",
        metadata={},
    )
    provider = MagicMock()
    provider.create_sandbox.side_effect = AssertionError("should not create a second sandbox")

    with (
        patch("tools.agentTools.get_llm", return_value=MagicMock()),
        patch("tools.agentTools.get_output_parser", return_value=None),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()),
        patch("tools.agentTools.MCPClientManager.get_client", new=AsyncMock(return_value=None)),
        patch("tools.agentTools.resolve_provider") as resolve_provider,
    ):
        await create_agent(
            agent,
            working_dir=str(tmp_path),
            sandbox_handle=handle,
            sandbox_provider=provider,
        )

    resolve_provider.assert_not_called()
    provider.create_sandbox.assert_not_called()
