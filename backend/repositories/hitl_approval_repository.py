from datetime import datetime
from typing import List, Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from models.hitl_approval import OPEN_APPROVAL_STATUSES, ApprovalStatus, HITLApproval


class HITLApprovalRepository:
    """Data access for HITLApproval. Callers own the transaction (commit/rollback)."""

    @staticmethod
    def add(db: Session, approval: HITLApproval) -> HITLApproval:
        db.add(approval)
        db.flush()
        return approval

    @staticmethod
    def get(db: Session, approval_id: str) -> Optional[HITLApproval]:
        return db.get(HITLApproval, approval_id)

    @staticmethod
    def get_in_app(db: Session, approval_id: str, app_id: int) -> Optional[HITLApproval]:
        return db.scalars(
            select(HITLApproval).where(HITLApproval.id == approval_id, HITLApproval.app_id == app_id)
        ).first()

    @staticmethod
    def get_open_for_conversation(db: Session, conversation_id: int) -> Optional[HITLApproval]:
        return db.scalars(
            select(HITLApproval).where(
                HITLApproval.conversation_id == conversation_id,
                HITLApproval.status.in_([s.value for s in OPEN_APPROVAL_STATUSES]),
            )
        ).first()

    @staticmethod
    def get_pending_for_conversation(db: Session, conversation_id: int) -> Optional[HITLApproval]:
        return db.scalars(
            select(HITLApproval).where(
                HITLApproval.conversation_id == conversation_id,
                HITLApproval.status == ApprovalStatus.PENDING.value,
            )
        ).first()

    @staticmethod
    def get_latest_for_conversation(db: Session, conversation_id: int) -> Optional[HITLApproval]:
        return db.scalars(
            select(HITLApproval)
            .where(HITLApproval.conversation_id == conversation_id)
            .order_by(HITLApproval.created_at.desc())
            .limit(1)
        ).first()

    @staticmethod
    def claim(
        db: Session,
        approval_id: str,
        from_status: ApprovalStatus,
        to_status: ApprovalStatus,
        *,
        only_if_not_expired: bool = False,
        only_if_expired: bool = False,
    ) -> bool:
        """Atomically move an approval between statuses; False if another caller got there first."""
        stmt = (
            update(HITLApproval)
            .where(HITLApproval.id == approval_id, HITLApproval.status == from_status.value)
            .values(status=to_status.value)
        )
        if only_if_not_expired:
            stmt = stmt.where(HITLApproval.expires_at > func.now())
        if only_if_expired:
            stmt = stmt.where(HITLApproval.expires_at <= func.now())
        return db.execute(stmt.execution_options(synchronize_session=False)).rowcount == 1

    @staticmethod
    def list_expired_pending_ids(db: Session, limit: int) -> List[str]:
        return list(db.scalars(
            select(HITLApproval.id)
            .where(HITLApproval.status == ApprovalStatus.PENDING.value, HITLApproval.expires_at <= func.now())
            .order_by(HITLApproval.expires_at)
            .limit(limit)
        ))

    @staticmethod
    def list_stuck_ids(db: Session, statuses: Sequence[ApprovalStatus], older_than: datetime, limit: int) -> List[str]:
        """Approvals left mid-transition (process died while resuming them)."""
        return list(db.scalars(
            select(HITLApproval.id)
            .where(
                HITLApproval.status.in_([s.value for s in statuses]),
                func.coalesce(HITLApproval.decided_at, HITLApproval.expires_at) < older_than,
            )
            .limit(limit)
        ))

    @staticmethod
    def count_open_for_agent(db: Session, agent_id: int) -> int:
        return db.scalar(
            select(func.count()).select_from(HITLApproval).where(
                HITLApproval.agent_id == agent_id,
                HITLApproval.status.in_([s.value for s in OPEN_APPROVAL_STATUSES]),
            )
        ) or 0

    @staticmethod
    def list_open_ids_for_agents(db: Session, agent_ids: Sequence[int]) -> List[str]:
        if not agent_ids:
            return []
        return list(db.scalars(
            select(HITLApproval.id).where(
                HITLApproval.agent_id.in_(list(agent_ids)),
                HITLApproval.status == ApprovalStatus.PENDING.value,
            )
        ))
