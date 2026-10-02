"""Human-in-the-loop helpers: decision validation and pending-approval reconstruction."""
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from types import SimpleNamespace

from schemas.middleware_schemas import HITLConfig, HITLDecisionSchema
from services.agent_execution_service import _raise_if_awaiting_approval
from services.hitl_service import (
    HITLDecisionError,
    pending_approval_from_state,
    pending_approval_from_tool_calls,
    validate_decisions,
)

PENDING = {
    "action_requests": [{"name": "search", "args": {}}, {"name": "send_email", "args": {}}],
    "review_configs": [
        {"action_name": "search", "allowed_decisions": ["approve", "reject"]},
        {"action_name": "send_email", "allowed_decisions": ["approve", "edit", "reject"]},
    ],
}


class TestValidateDecisions:
    def test_valid_decisions_pass(self):
        validate_decisions(PENDING, [
            {"type": "approve"},
            {"type": "edit", "edited_action": {"name": "send_email", "args": {"to": "a@b.c"}}},
        ])

    def test_no_pending_approval(self):
        with pytest.raises(HITLDecisionError, match="no pending approval"):
            validate_decisions(None, [{"type": "approve"}])

    def test_wrong_number_of_decisions(self):
        with pytest.raises(HITLDecisionError, match="Expected 2"):
            validate_decisions(PENDING, [{"type": "approve"}])

    def test_decision_not_allowed_for_tool(self):
        with pytest.raises(HITLDecisionError, match="not allowed for tool 'search'"):
            validate_decisions(PENDING, [
                {"type": "edit", "edited_action": {"name": "search", "args": {}}},
                {"type": "approve"},
            ])

    def test_edit_cannot_switch_tool(self):
        with pytest.raises(HITLDecisionError, match="cannot change which tool"):
            validate_decisions(PENDING, [
                {"type": "approve"},
                {"type": "edit", "edited_action": {"name": "search", "args": {}}},
            ])


class TestDecisionSchema:
    def test_edit_needs_edited_action(self):
        with pytest.raises(ValidationError):
            HITLDecisionSchema(type="edit")

    def test_unknown_type_rejected(self):
        with pytest.raises(ValidationError):
            HITLDecisionSchema(type="respond")

    def test_langchain_shape(self):
        assert HITLDecisionSchema(type="reject", message="no").to_langchain() == {"type": "reject", "message": "no"}


class TestPendingApproval:
    def test_from_state_merges_interrupts(self):
        state = SimpleNamespace(tasks=[SimpleNamespace(interrupts=[SimpleNamespace(value=PENDING)])])
        assert pending_approval_from_state(state) == PENDING

    def test_from_state_without_interrupts(self):
        assert pending_approval_from_state(SimpleNamespace(tasks=[])) is None

    def test_from_tool_calls_only_reviewed_tools(self):
        config = HITLConfig(interrupt_on={"send_email": {"allowed_decisions": ["approve", "reject"]}})
        pending = pending_approval_from_tool_calls(config, [
            {"name": "search", "args": {"q": "x"}, "id": "1"},
            {"name": "send_email", "args": {"to": "a"}, "id": "2"},
        ])
        assert [a["name"] for a in pending["action_requests"]] == ["send_email"]
        assert pending["review_configs"] == [{"action_name": "send_email", "allowed_decisions": ["approve", "reject"]}]

    def test_from_tool_calls_nothing_pending(self):
        config = HITLConfig(interrupt_on={"send_email": {"allowed_decisions": ["approve"]}})
        assert pending_approval_from_tool_calls(config, []) is None
        assert pending_approval_from_tool_calls(None, [{"name": "send_email", "args": {}}]) is None


class TestNonInteractiveRuns:
    def test_interrupted_result_raises_409(self):
        result = {"messages": [], "__interrupt__": [SimpleNamespace(value=PENDING)]}
        with pytest.raises(HTTPException) as exc:
            _raise_if_awaiting_approval(result)
        assert exc.value.status_code == 409
        assert "search, send_email" in exc.value.detail

    def test_normal_result_passes(self):
        _raise_if_awaiting_approval({"messages": []})
