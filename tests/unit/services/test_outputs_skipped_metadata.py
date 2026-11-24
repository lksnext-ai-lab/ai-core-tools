"""Skipped sandbox output files are reported as structured metadata; the answer text is never touched."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from services.agent_execution_service import AgentExecutionService
from tests.unit.services.test_agent_execution_service_it4 import _base_ctx


def finalize(ctx, response):
    svc = AgentExecutionService.__new__(AgentExecutionService)
    svc.agent_service = MagicMock()
    svc.session_service = MagicMock(touch_session=AsyncMock())
    svc.agent_execution_repo = MagicMock()
    seen = {}

    def parse(resp, agent):
        seen["response"] = resp
        return resp

    with patch("services.agent_execution_service.FileManagementService") as fms, \
         patch("tools.agentTools.parse_agent_response", side_effect=parse), \
         patch.object(svc, "_update_request_count"):
        fms.return_value.sync_output_files = AsyncMock(return_value=[])
        result = asyncio.run(svc._finalize_turn(ctx, response, MagicMock()))
    return result, seen["response"]


def test_a_skipped_file_adds_a_count_to_the_metadata_and_never_touches_the_answer(tmp_path, monkeypatch):
    monkeypatch.setattr("config.SANDBOX_PULL_MAX_FILE_BYTES", 3, raising=False)
    json_answer = '{"name": "structured", "n": 1}'  # what an output-parser agent returns
    ctx = _base_ctx(str(tmp_path))
    ctx.sandbox_provider.list_files.return_value = ["/workspace/output/big.bin"]
    ctx.sandbox_provider.read_file_limited.return_value = b"1234"  # cap + 1: over the cap
    result, parsed_input = finalize(ctx, json_answer)
    assert parsed_input == json_answer  # byte-identical: structured output still parses
    assert result["metadata"]["outputs_skipped"] == 1
    assert result["response"] == json_answer


def test_without_skipped_files_the_key_is_absent_and_the_answer_is_identical(tmp_path):
    ctx = _base_ctx(str(tmp_path))
    ctx.sandbox_provider.list_files.return_value = ["/workspace/output/ok.txt"]
    ctx.sandbox_provider.read_file_limited.return_value = b"fine"
    result, parsed_input = finalize(ctx, "plain answer")
    assert parsed_input == "plain answer" and "outputs_skipped" not in result["metadata"]
    assert (tmp_path / "output" / "ok.txt").read_bytes() == b"fine"


def test_a_plain_answer_is_byte_identical_with_and_without_skipped_files(tmp_path, monkeypatch):
    monkeypatch.setattr("config.SANDBOX_PULL_MAX_FILE_BYTES", 3, raising=False)
    skipped_ctx = _base_ctx(str(tmp_path))
    skipped_ctx.sandbox_provider.list_files.return_value = ["/workspace/output/big.bin"]
    skipped_ctx.sandbox_provider.read_file_limited.return_value = b"1234"
    _, with_skip = finalize(skipped_ctx, "Here is your report.")
    _, without = finalize(_base_ctx(str(tmp_path)), "Here is your report.")
    assert with_skip == without == "Here is your report."
