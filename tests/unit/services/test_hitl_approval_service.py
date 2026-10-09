from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from models.hitl_approval import ApprovalStatus, HITLApproval
from schemas.hitl_approval_schemas import ApprovalDecisionSchema
from services import hitl_approval_service as approvals
from utils.security import hash_api_key


def _approval(**overrides) -> HITLApproval:
    now = datetime.now(timezone.utc)
    values = dict(
        id="appr-1", app_id=3, agent_id=1, conversation_id=7, thread_id="thread_1_conv_1_7",
        interrupt_id="i1", channel="public_api", status="pending",
        actions=[
            {"action_id": "c2", "name": "send_email", "args": {"to": "a"}, "description": "d",
             "allowed_decisions": ["approve", "edit", "reject"]},
            {"action_id": "c3", "name": "send_email", "args": {"to": "b"}, "description": "d",
             "allowed_decisions": ["approve", "edit", "reject"]},
        ],
        requested_by_api_key_hash=hash_api_key("key-a"), created_at=now, expires_at=now + timedelta(hours=1),
    )
    values.update(overrides)
    return HITLApproval(**values)


def _decision(action_id, type_, **kw):
    return ApprovalDecisionSchema(action_id=action_id, type=type_, **kw)


class TestRequester:
    def test_api_key_requester_owns_only_its_approvals(self):
        approval = _approval()
        assert approvals.Requester.from_user_context({"api_key": "key-a"}).owns(approval)
        assert not approvals.Requester.from_user_context({"api_key": "key-b"}).owns(approval)

    def test_user_cannot_own_an_api_key_approval(self):
        assert not approvals.Requester(user_id=5).owns(_approval())

    def test_user_requester(self):
        approval = _approval(requested_by_api_key_hash=None, requested_by_user_id=5)
        assert approvals.Requester.from_user_context({"user_id": "5"}).owns(approval)
        assert not approvals.Requester(user_id=6).owns(approval)

    def test_auth_context_requester(self):
        approval = _approval(requested_by_api_key_hash=None, requested_by_user_id=5)
        auth = SimpleNamespace(identity=SimpleNamespace(id="5"))
        assert approvals.Requester.from_user_context(auth).owns(approval)

    def test_system_and_task_contexts_own_nothing(self):
        approval = _approval(requested_by_api_key_hash=None, requested_by_user_id=None)
        assert not approvals.Requester.from_user_context({"user_id": "scheduled_task_4"}).owns(approval)


class TestReadPause:
    @pytest.mark.asyncio
    async def test_actions_get_their_tool_call_ids_in_order(self):
        state = SimpleNamespace(
            tasks=[SimpleNamespace(interrupts=[SimpleNamespace(id="i9", value={
                "action_requests": [
                    {"name": "send_email", "args": {"to": "a"}, "description": "x"},
                    {"name": "send_email", "args": {"to": "b"}, "description": "x"},
                ],
                "review_configs": [{"action_name": "send_email", "allowed_decisions": ["approve", "reject"]}],
            })])],
            values={"messages": [AIMessage(content="", tool_calls=[
                {"name": "search", "args": {"q": "x"}, "id": "c1"},
                {"name": "send_email", "args": {"to": "a"}, "id": "c2"},
                {"name": "send_email", "args": {"to": "b"}, "id": "c3"},
            ])]},
        )
        chain = SimpleNamespace(aget_state=AsyncMock(return_value=state))

        pause = await approvals.read_pause(chain, {})
        actions = approvals._build_actions(pause)

        assert pause.interrupt_id == "i9"
        assert [(a["action_id"], a["args"]["to"]) for a in actions] == [("c2", "a"), ("c3", "b")]
        assert actions[0]["allowed_decisions"] == ["approve", "reject"]

    @pytest.mark.asyncio
    async def test_no_interrupt(self):
        chain = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(tasks=[], values={})))
        assert await approvals.read_pause(chain, {}) is None


class TestPrepareDecisions:
    def test_maps_id_keyed_decisions_to_langchain_order(self):
        ordered = approvals.prepare_decisions(_approval(), [
            _decision("c3", "reject", message="no"),
            _decision("c2", "edit", args={"to": "z"}),
        ])
        assert ordered == [
            {"type": "edit", "edited_action": {"name": "send_email", "args": {"to": "z"}}},
            {"type": "reject", "message": "no"},
        ]

    @pytest.mark.parametrize("decisions, fragment", [
        ([("c2", "approve")], "Missing a decision"),
        ([("c2", "approve"), ("c3", "approve"), ("c9", "approve")], "Unknown action_id"),
        ([("c2", "approve"), ("c2", "reject")], "More than one decision"),
    ])
    def test_rejects_incomplete_or_unknown_decisions(self, decisions, fragment):
        approval, answers = _approval(), [_decision(a, t) for a, t in decisions]
        with pytest.raises(approvals.ApprovalDecisionError, match=fragment):
            approvals.prepare_decisions(approval, answers)

    def test_rejects_a_decision_type_the_tool_does_not_allow(self):
        approval = _approval()
        approval.actions[0]["allowed_decisions"] = ["approve", "reject"]
        answers = [_decision("c2", "edit", args={}), _decision("c3", "approve")]
        with pytest.raises(approvals.ApprovalDecisionError, match="not allowed"):
            approvals.prepare_decisions(approval, answers)

    def test_validates_edited_args_against_args_schema(self):
        approval = _approval()
        approval.actions[0]["args_schema"] = {
            "type": "object", "properties": {"to": {"type": "string"}}, "required": ["to"],
            "additionalProperties": False,
        }
        answers = [_decision("c2", "edit", args={"to": "x", "bcc": "attacker"}), _decision("c3", "approve")]
        with pytest.raises(approvals.ApprovalDecisionError, match="Invalid arguments"):
            approvals.prepare_decisions(approval, answers)

    def test_rejects_oversized_edited_args(self):
        approval = _approval()
        answers = [
            _decision("c2", "edit", args={"body": "x" * (approvals.MAX_EDITED_ARGS_BYTES + 1)}),
            _decision("c3", "approve"),
        ]
        with pytest.raises(approvals.ApprovalDecisionError, match="too large"):
            approvals.prepare_decisions(approval, answers)

    def test_decision_payload_must_match_its_type(self):
        with pytest.raises(ValueError):
            ApprovalDecisionSchema(action_id="c2", type="approve", args={"to": "x"})
        with pytest.raises(ValueError):
            ApprovalDecisionSchema(action_id="c2", type="edit")


class TestStatus:
    @pytest.mark.parametrize("types, expected", [
        (["approve", "reject"], ApprovalStatus.APPROVED),
        (["edit", "reject"], ApprovalStatus.EDITED),
        (["reject", "reject"], ApprovalStatus.REJECTED),
    ])
    def test_outcome(self, types, expected):
        assert approvals.outcome_status([{"type": t} for t in types]) == expected

    def test_pending_past_its_deadline_reads_as_expired(self):
        approval = _approval(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        assert approvals.effective_status(approval) == "expired"
        assert approvals.pending_schema(approval).status == "expired"

    def test_expiry_and_cancel_never_approve(self):
        assert {d["type"] for d in approvals.reject_all(_approval(), approvals.EXPIRED_MESSAGE)} == {"reject"}

    def test_sse_payload_keeps_langchain_shape(self):
        payload = approvals.sse_payload(_approval())
        assert payload["approval_id"] == "appr-1"
        assert [a["action_id"] for a in payload["actions"]] == ["c2", "c3"]
        assert payload["review_configs"][0] == {
            "action_name": "send_email", "allowed_decisions": ["approve", "edit", "reject"],
        }


class TestRejectionMessages:
    @pytest.mark.parametrize("message", [
        approvals.EXPIRED_MESSAGE, approvals.CANCELLED_MESSAGE, approvals.NOT_INTERACTIVE_MESSAGE,
    ])
    def test_tell_the_agent_not_to_retry(self, message):
        assert "Do not call this tool again" in message
