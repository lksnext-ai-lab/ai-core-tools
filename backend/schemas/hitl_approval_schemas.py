from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

ApprovalStatusValue = Literal["pending", "deciding", "expiring", "approved", "edited", "rejected", "expired", "cancelled"]
DecisionType = Literal["approve", "edit", "reject"]


class ApprovalDecisionSchema(BaseModel):
    """A reviewer's decision on one pending action, addressed by its ``action_id``."""
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(..., min_length=1, max_length=128)
    type: DecisionType
    args: Optional[Dict[str, Any]] = Field(None, description="Replacement tool arguments ('edit' only)")
    message: Optional[str] = Field(None, max_length=2000, description="Reason shown to the agent ('reject' only)")

    @model_validator(mode="after")
    def _check_payload(self) -> "ApprovalDecisionSchema":
        if self.type == "edit" and self.args is None:
            raise ValueError("an 'edit' decision needs args")
        if self.type != "edit" and self.args is not None:
            raise ValueError("args is only valid for 'edit' decisions")
        if self.type != "reject" and self.message is not None:
            raise ValueError("message is only valid for 'reject' decisions")
        return self


class ApprovalDecisionsRequestSchema(BaseModel):
    """One decision for every action of the pending approval."""
    model_config = ConfigDict(extra="forbid")

    decisions: List[ApprovalDecisionSchema] = Field(..., min_length=1, max_length=50)


class ApprovalActionSchema(BaseModel):
    action_id: str
    name: str
    args: Dict[str, Any]
    description: Optional[str] = None
    allowed_decisions: List[DecisionType]
    args_schema: Optional[Dict[str, Any]] = None


class PendingApprovalSchema(BaseModel):
    """What a client needs to show and answer an approval request."""
    approval_id: str
    status: ApprovalStatusValue
    expires_at: datetime
    actions: List[ApprovalActionSchema]


class ApprovalStatusSchema(PendingApprovalSchema):
    conversation_id: int
    agent_id: int
    created_at: datetime
    decided_at: Optional[datetime] = None
    decisions: Optional[List[Dict[str, Any]]] = None
    resolution_reason: Optional[str] = None


class ApprovalResultSchema(BaseModel):
    """Outcome of answering an approval: the turn's answer, or a new approval request."""
    status: Literal["completed", "requires_approval"]
    response: Union[str, Dict[str, Any]] = ""
    conversation_id: Optional[int] = None
    pending_approval: Optional[PendingApprovalSchema] = None
