"""
Integration tests for the human-approval endpoints that do not need a model run:

  - GET  /internal/approvals/{id}, /cancel, /decisions/stream (validation errors)
  - GET  /public/v1/app/{app_id}/approvals/{id}, /decisions, /decisions/stream (validation errors)

Only the requester (same user / same API key) can see or answer an approval; anyone
else gets 404. Invalid decisions are rejected with 422 before any run starts.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from models.conversation import Conversation
from models.hitl_approval import ApprovalStatus, HITLApproval
from utils.security import hash_api_key

pytestmark = pytest.mark.integration

ACTION = {"action_id": "call_1", "name": "search", "args": {"q": "s3"}, "allowed_decisions": ["approve", "reject"]}


@pytest.fixture
def conversation(db, fake_agent):
    conv = Conversation(agent_id=fake_agent.agent_id, session_id=f"conv_{fake_agent.agent_id}_{uuid.uuid4()}")
    db.add(conv)
    db.flush()
    return conv


def add_approval(db, conversation, *, channel="playground", user_id=None, api_key=None,
                 status=ApprovalStatus.PENDING, expires_in=3600) -> HITLApproval:
    now = datetime.now(timezone.utc)
    approval = HITLApproval(
        id=str(uuid.uuid4()),
        app_id=conversation.agent.app_id,
        agent_id=conversation.agent_id,
        conversation_id=conversation.conversation_id,
        thread_id=f"thread_{conversation.agent_id}_{conversation.session_id}",
        interrupt_id=uuid.uuid4().hex,
        channel=channel,
        status=status.value,
        actions=[dict(ACTION)],
        requested_by_user_id=user_id,
        requested_by_api_key_hash=hash_api_key(api_key) if api_key else None,
        created_at=now,
        expires_at=now + timedelta(seconds=expires_in),
    )
    db.add(approval)
    db.flush()
    return approval


def decisions(action_id="call_1", decision="approve") -> dict:
    return {"decisions": [{"action_id": action_id, "type": decision}]}


class TestInternalApprovals:
    def test_requester_sees_the_pending_approval(self, client, db, conversation, fake_user, owner_headers):
        approval = add_approval(db, conversation, user_id=fake_user.user_id)

        response = client.get(f"/internal/approvals/{approval.id}", headers=owner_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "pending"
        assert [a["action_id"] for a in body["actions"]] == ["call_1"]

    def test_another_users_approval_is_not_found(self, client, db, conversation, owner_headers):
        approval = add_approval(db, conversation, user_id=None, api_key="someone-elses-key")

        response = client.get(f"/internal/approvals/{approval.id}", headers=owner_headers)

        assert response.status_code == 404

    def test_expired_approval_is_reported_as_expired(self, client, db, conversation, fake_user, owner_headers):
        approval = add_approval(db, conversation, user_id=fake_user.user_id, expires_in=-5)

        response = client.get(f"/internal/approvals/{approval.id}", headers=owner_headers)

        assert response.json()["status"] == "expired"

    def test_decision_for_an_unknown_action_is_rejected(self, client, db, conversation, fake_user, owner_headers):
        approval = add_approval(db, conversation, user_id=fake_user.user_id)

        response = client.post(
            f"/internal/approvals/{approval.id}/decisions/stream",
            json=decisions(action_id="call_unknown"),
            headers=owner_headers,
        )

        assert response.status_code == 422
        db.refresh(approval)
        assert approval.status == ApprovalStatus.PENDING.value

    def test_decision_type_not_allowed_is_rejected(self, client, db, conversation, fake_user, owner_headers):
        approval = add_approval(db, conversation, user_id=fake_user.user_id)

        response = client.post(
            f"/internal/approvals/{approval.id}/decisions/stream",
            json={"decisions": [{"action_id": "call_1", "type": "edit", "args": {"q": "ec2"}}]},
            headers=owner_headers,
        )

        assert response.status_code == 422

    def test_an_answered_approval_cannot_be_cancelled(self, client, db, conversation, fake_user, owner_headers):
        approval = add_approval(db, conversation, user_id=fake_user.user_id, status=ApprovalStatus.APPROVED)

        response = client.post(f"/internal/approvals/{approval.id}/cancel", headers=owner_headers)

        assert response.status_code == 409


class TestPublicApprovals:
    def test_requester_key_sees_the_approval(self, client, db, conversation, fake_app, fake_api_key):
        approval = add_approval(db, conversation, channel="public_api", api_key=fake_api_key.key)

        response = client.get(
            f"/public/v1/app/{fake_app.app_id}/approvals/{approval.id}",
            headers={"X-API-KEY": fake_api_key.key},
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "pending"

    def test_another_keys_approval_is_not_found(self, client, db, conversation, fake_app, fake_api_key):
        approval = add_approval(db, conversation, channel="public_api", api_key="another-api-key")

        response = client.get(
            f"/public/v1/app/{fake_app.app_id}/approvals/{approval.id}",
            headers={"X-API-KEY": fake_api_key.key},
        )

        assert response.status_code == 404

    def test_invalid_decision_is_rejected(self, client, db, conversation, fake_app, fake_api_key):
        approval = add_approval(db, conversation, channel="public_api", api_key=fake_api_key.key)

        response = client.post(
            f"/public/v1/app/{fake_app.app_id}/approvals/{approval.id}/decisions",
            json=decisions(action_id="call_unknown"),
            headers={"X-API-KEY": fake_api_key.key},
        )

        assert response.status_code == 422
        db.refresh(approval)
        assert approval.status == ApprovalStatus.PENDING.value

    def test_streaming_invalid_decision_is_rejected(self, client, db, conversation, fake_app, fake_api_key):
        approval = add_approval(db, conversation, channel="public_api", api_key=fake_api_key.key)

        response = client.post(
            f"/public/v1/app/{fake_app.app_id}/approvals/{approval.id}/decisions/stream",
            json=decisions(decision="edit"),
            headers={"X-API-KEY": fake_api_key.key},
        )

        assert response.status_code == 422
