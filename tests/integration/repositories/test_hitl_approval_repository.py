"""HITLApprovalRepository against PostgreSQL: the compare-and-set and the partial unique index
are what keep an approval from being resolved twice."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from models.conversation import Conversation
from models.hitl_approval import ApprovalStatus, HITLApproval
from repositories.hitl_approval_repository import HITLApprovalRepository


@pytest.fixture
def conversation(db, fake_agent):
    conv = Conversation(agent_id=fake_agent.agent_id, session_id=f"conv_{fake_agent.agent_id}_{uuid.uuid4()}")
    db.add(conv)
    db.flush()
    return conv


def _approval(conversation, *, status=ApprovalStatus.PENDING, expires_in=3600) -> HITLApproval:
    now = datetime.now(timezone.utc)
    return HITLApproval(
        id=str(uuid.uuid4()),
        app_id=conversation.agent.app_id,
        agent_id=conversation.agent_id,
        conversation_id=conversation.conversation_id,
        thread_id=f"thread_{conversation.agent_id}_{conversation.session_id}",
        interrupt_id=uuid.uuid4().hex,
        channel="public_api",
        status=status.value,
        actions=[{"action_id": "c1", "name": "t", "args": {}, "allowed_decisions": ["approve"]}],
        created_at=now,
        expires_at=now + timedelta(seconds=expires_in),
    )


class TestClaim:
    def test_only_one_caller_wins(self, db, conversation):
        approval = HITLApprovalRepository.add(db, _approval(conversation))

        first = HITLApprovalRepository.claim(
            db, approval.id, ApprovalStatus.PENDING, ApprovalStatus.DECIDING, only_if_not_expired=True
        )
        second = HITLApprovalRepository.claim(
            db, approval.id, ApprovalStatus.PENDING, ApprovalStatus.DECIDING, only_if_not_expired=True
        )

        assert (first, second) == (True, False)

    def test_an_expired_approval_cannot_be_decided(self, db, conversation):
        approval = HITLApprovalRepository.add(db, _approval(conversation, expires_in=-5))

        assert not HITLApprovalRepository.claim(
            db, approval.id, ApprovalStatus.PENDING, ApprovalStatus.DECIDING, only_if_not_expired=True
        )
        assert HITLApprovalRepository.claim(
            db, approval.id, ApprovalStatus.PENDING, ApprovalStatus.EXPIRING, only_if_expired=True
        )

    def test_an_unexpired_approval_is_not_swept(self, db, conversation):
        approval = HITLApprovalRepository.add(db, _approval(conversation))

        assert approval.id not in HITLApprovalRepository.list_expired_pending_ids(db, 50)
        assert not HITLApprovalRepository.claim(
            db, approval.id, ApprovalStatus.PENDING, ApprovalStatus.EXPIRING, only_if_expired=True
        )


class TestOnePausePerConversation:
    def test_second_pending_approval_is_rejected(self, db, conversation):
        HITLApprovalRepository.add(db, _approval(conversation))
        second = _approval(conversation)

        with pytest.raises(IntegrityError):
            HITLApprovalRepository.add(db, second)
        db.rollback()

    def test_a_resolving_approval_does_not_block_the_next_pause(self, db, conversation):
        HITLApprovalRepository.add(db, _approval(conversation, status=ApprovalStatus.DECIDING))
        nxt = HITLApprovalRepository.add(db, _approval(conversation))

        assert HITLApprovalRepository.get_pending_for_conversation(db, conversation.conversation_id).id == nxt.id


def test_expired_pending_listing(db, conversation):
    expired = HITLApprovalRepository.add(db, _approval(conversation, expires_in=-5))

    assert expired.id in HITLApprovalRepository.list_expired_pending_ids(db, 50)


def test_deleting_the_conversation_removes_its_approvals(db, conversation):
    approval = HITLApprovalRepository.add(db, _approval(conversation))
    approval_id = approval.id
    db.expunge(approval)

    db.delete(conversation)
    db.flush()

    assert HITLApprovalRepository.get(db, approval_id) is None
