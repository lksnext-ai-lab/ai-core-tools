"""Lifecycle of human-in-the-loop approvals.

LangChain's ``HumanInTheLoopMiddleware`` pauses the graph with an interrupt and the
checkpointer keeps it paused indefinitely. Each pause also gets an ``HITLApproval`` row
that records who may answer it, until when, and what was decided:

- Only the requester (same user, or same API key) can read or answer it.
- Answers are claimed with a compare-and-set on the row, so a double click, a retry or
  two replicas can never resume the same pause twice.
- Unanswered approvals expire and are resolved as *rejected* — never approved.
- Decisions are addressed by ``action_id`` (the tool call id) and converted here to
  LangChain's ordered ``{"decisions": [...]}`` resume payload.
"""
from __future__ import annotations

import hmac
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import jsonschema
from langchain_core.messages import AIMessage
from sqlalchemy.orm import Session

from models.hitl_approval import (
    INTERACTIVE_CHANNELS,
    ApprovalChannel,
    ApprovalStatus,
    HITLApproval,
)
from repositories.hitl_approval_repository import HITLApprovalRepository
from schemas.hitl_approval_schemas import (
    ApprovalActionSchema,
    ApprovalDecisionSchema,
    ApprovalStatusSchema,
    PendingApprovalSchema,
)
from schemas.middleware_schemas import DEFAULT_APPROVAL_TIMEOUT_SECONDS, HITLConfig
from utils.logger import get_logger
from utils.security import hash_api_key

logger = get_logger(__name__)

MAX_EDITED_ARGS_BYTES = 64 * 1024
# The agent reads these as the tool result: they must stop it from asking for the tool again.
_NO_RETRY = " Do not call this tool again unless the user explicitly asks for it."
EXPIRED_MESSAGE = (
    "The approval request expired before anyone answered it. The tool was not executed. "
    "Tell the user it was not done." + _NO_RETRY
)
CANCELLED_MESSAGE = "The user cancelled this request. The tool was not executed." + _NO_RETRY
NOT_INTERACTIVE_MESSAGE = (
    "This tool needs a person's approval, which cannot be requested from this channel. "
    "The tool was not executed. Tell the user it needs approval." + _NO_RETRY
)


# ==================== ERRORS ====================

class ApprovalError(Exception):
    """Base error with a stable machine-readable ``code`` and the HTTP status to map it to."""
    status_code = 409
    code = "approval_error"

    def __init__(self, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.extra = extra

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": str(self), **self.extra}


class ApprovalNotFoundError(ApprovalError):
    status_code = 404
    code = "approval_not_found"


class ApprovalPendingError(ApprovalError):
    code = "approval_pending"


class ApprovalAlreadyDecidedError(ApprovalError):
    code = "approval_already_decided"


class ApprovalExpiredError(ApprovalError):
    code = "approval_expired"


class ApprovalStaleError(ApprovalError):
    code = "approval_stale"


class ApprovalNotSupportedError(ApprovalError):
    code = "approval_not_supported_in_channel"


class ApprovalDecisionError(ApprovalError):
    status_code = 422
    code = "invalid_decision"


# ==================== IDENTITY ====================

@dataclass(frozen=True)
class Requester:
    """Who started the paused run: a platform user or an API key (stored hashed)."""
    user_id: Optional[int] = None
    api_key_hash: Optional[str] = None

    @classmethod
    def from_user_context(cls, user_context: Optional[Dict[str, Any]]) -> "Requester":
        if not user_context:
            return cls()
        identity = getattr(user_context, "identity", None)
        if identity is not None:
            return cls(user_id=int(identity.id))
        if user_context.get("api_key"):
            return cls(api_key_hash=hash_api_key(user_context["api_key"]))
        user_id = user_context.get("user_id")
        if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
            return cls(user_id=int(user_id))
        return cls()

    def owns(self, approval: HITLApproval) -> bool:
        if approval.requested_by_api_key_hash:
            return bool(self.api_key_hash) and hmac.compare_digest(
                self.api_key_hash, approval.requested_by_api_key_hash
            )
        return self.user_id is not None and approval.requested_by_user_id == self.user_id


def system_user_context(approval: HITLApproval) -> Dict[str, Any]:
    """Identity used to resolve an approval without its requester (expiry).

    ``hitl_conversation_id`` grants access to that one conversation only; it is set
    server-side and never read from a request.
    """
    return {
        "user_id": f"hitl_approval_{approval.id}",
        "app_id": approval.app_id,
        "hitl_conversation_id": approval.conversation_id,
        "billing_user_id": approval.requested_by_user_id,
        "trigger": "hitl_expiry",
    }


@dataclass
class ResumeRequest:
    """A claimed approval and how to resume and record it."""
    approval: HITLApproval
    decisions: List[Dict[str, Any]]
    final_status: ApprovalStatus
    reason: Optional[str] = None
    decided_by: Optional[Requester] = None


# ==================== GRAPH PAUSE ====================

@dataclass
class GraphPause:
    interrupt_id: str
    action_requests: List[Dict[str, Any]]
    review_configs: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


async def read_pause(agent_chain: Any, config: Dict[str, Any]) -> Optional[GraphPause]:
    """The human-in-the-loop interrupt the thread is paused on, or None."""
    state = await agent_chain.aget_state(config)
    for task in getattr(state, "tasks", None) or []:
        for intr in getattr(task, "interrupts", None) or []:
            value = getattr(intr, "value", None)
            if isinstance(value, dict) and value.get("action_requests"):
                messages = (getattr(state, "values", None) or {}).get("messages", [])
                last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
                return GraphPause(
                    interrupt_id=str(intr.id),
                    action_requests=list(value["action_requests"]),
                    review_configs=list(value.get("review_configs", [])),
                    tool_calls=list(getattr(last_ai, "tool_calls", None) or []),
                )
    return None


def _build_actions(pause: GraphPause) -> List[Dict[str, Any]]:
    """Pair each action request with its tool call id.

    LangChain builds ``action_requests`` walking the AI message's tool calls in order and
    keeping those that need review, so matching by name in order recovers the ids.
    """
    configs = {rc.get("action_name"): rc for rc in pause.review_configs}
    remaining = list(pause.tool_calls)
    actions: List[Dict[str, Any]] = []
    for index, request in enumerate(pause.action_requests):
        name = request.get("name", "")
        match = next((i for i, call in enumerate(remaining) if call.get("name") == name), None)
        call = remaining.pop(match) if match is not None else {}
        review = configs.get(name, {})
        action: Dict[str, Any] = {
            "action_id": call.get("id") or f"action_{index}",
            "name": name,
            "args": request.get("args", request.get("arguments")) or {},
            "description": request.get("description"),
            "allowed_decisions": list(review.get("allowed_decisions", [])),
        }
        if review.get("args_schema"):
            action["args_schema"] = review["args_schema"]
        actions.append(action)
    return actions


# ==================== READ ====================

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def is_expired(approval: HITLApproval) -> bool:
    return _aware(approval.expires_at) <= _now()


def effective_status(approval: HITLApproval) -> str:
    """Status as clients should see it: a pending approval past its deadline is expired."""
    if approval.status == ApprovalStatus.PENDING.value and is_expired(approval):
        return ApprovalStatus.EXPIRED.value
    return approval.status


def pending_schema(approval: HITLApproval) -> PendingApprovalSchema:
    return PendingApprovalSchema(
        approval_id=approval.id,
        status=effective_status(approval),
        expires_at=approval.expires_at,
        actions=[ApprovalActionSchema(**a) for a in approval.actions],
    )


def status_schema(approval: HITLApproval) -> ApprovalStatusSchema:
    return ApprovalStatusSchema(
        **pending_schema(approval).model_dump(),
        conversation_id=approval.conversation_id,
        agent_id=approval.agent_id,
        created_at=approval.created_at,
        decided_at=approval.decided_at,
        decisions=approval.decisions,
        resolution_reason=approval.resolution_reason,
    )


def sse_payload(approval: HITLApproval) -> Dict[str, Any]:
    """``hitl_interrupt`` event body: the approval plus LangChain's request shape."""
    payload = pending_schema(approval).model_dump(mode="json")
    payload["action_requests"] = [
        {"name": a["name"], "args": a["args"], "description": a.get("description")} for a in approval.actions
    ]
    payload["review_configs"] = [
        {"action_name": a["name"], "allowed_decisions": a["allowed_decisions"]} for a in approval.actions
    ]
    return payload


def get_for_requester(db: Session, approval_id: str, requester: Requester, app_id: Optional[int] = None) -> HITLApproval:
    """Load an approval the requester owns; anything else looks like it does not exist."""
    approval = (
        HITLApprovalRepository.get_in_app(db, approval_id, app_id)
        if app_id is not None
        else HITLApprovalRepository.get(db, approval_id)
    )
    if approval is None or not requester.owns(approval):
        raise ApprovalNotFoundError("Approval not found.")
    return approval


def get_pending_for_conversation(db: Session, conversation_id: int) -> Optional[HITLApproval]:
    return HITLApprovalRepository.get_pending_for_conversation(db, conversation_id)


def check_conversation_free(db: Session, conversation_id: int) -> Optional[HITLApproval]:
    """Gate a new message on a conversation that may be paused.

    Returns an expired approval the caller must resolve before running the message, or
    None when the conversation is free. Raises ``ApprovalPendingError`` while a person
    can still answer: a new message would silently discard the pause and leave its tool
    calls unanswered in the history.
    """
    approval = (
        HITLApprovalRepository.get_pending_for_conversation(db, conversation_id)
        or HITLApprovalRepository.get_open_for_conversation(db, conversation_id)
    )
    if approval is None:
        return None
    if approval.status == ApprovalStatus.PENDING.value and is_expired(approval):
        return approval
    raise ApprovalPendingError(
        "This conversation is waiting for a tool approval. Approve, reject or cancel it first.",
        approval_id=approval.id,
        expires_at=_aware(approval.expires_at).isoformat(),
    )


# ==================== DECISIONS ====================

def _validate_edited_args(action: Dict[str, Any], args: Dict[str, Any]) -> None:
    if len(json.dumps(args, ensure_ascii=False).encode("utf-8")) > MAX_EDITED_ARGS_BYTES:
        raise ApprovalDecisionError(f"Edited arguments for '{action['name']}' are too large.")
    schema = action.get("args_schema")
    if not schema:
        return
    try:
        jsonschema.validate(args, schema)
    except jsonschema.ValidationError as exc:
        raise ApprovalDecisionError(f"Invalid arguments for '{action['name']}': {exc.message}") from exc
    except jsonschema.SchemaError:
        logger.warning("Ignoring an invalid args_schema for tool %s", action["name"])


def prepare_decisions(approval: HITLApproval, decisions: List[ApprovalDecisionSchema]) -> List[Dict[str, Any]]:
    """Check id-keyed decisions against the approval and return LangChain's ordered list."""
    by_id: Dict[str, ApprovalDecisionSchema] = {}
    for decision in decisions:
        if decision.action_id in by_id:
            raise ApprovalDecisionError(f"More than one decision for action '{decision.action_id}'.")
        by_id[decision.action_id] = decision
    known = {a["action_id"] for a in approval.actions}
    unknown = sorted(set(by_id) - known)
    if unknown:
        raise ApprovalDecisionError(f"Unknown action_id: {', '.join(unknown)}.")

    ordered: List[Dict[str, Any]] = []
    for action in approval.actions:
        decision = by_id.get(action["action_id"])
        if decision is None:
            raise ApprovalDecisionError(f"Missing a decision for action '{action['action_id']}' ({action['name']}).")
        if decision.type not in action["allowed_decisions"]:
            raise ApprovalDecisionError(
                f"'{decision.type}' is not allowed for '{action['name']}'. "
                f"Allowed: {', '.join(action['allowed_decisions'])}."
            )
        if decision.type == "approve":
            ordered.append({"type": "approve"})
        elif decision.type == "edit":
            _validate_edited_args(action, decision.args or {})
            ordered.append({"type": "edit", "edited_action": {"name": action["name"], "args": decision.args}})
        else:
            entry: Dict[str, Any] = {"type": "reject"}
            if decision.message:
                entry["message"] = decision.message
            ordered.append(entry)
    return ordered


def reject_all(approval: HITLApproval, message: str) -> List[Dict[str, Any]]:
    return [{"type": "reject", "message": message} for _ in approval.actions]


def outcome_status(decisions: List[Dict[str, Any]]) -> ApprovalStatus:
    types = {d["type"] for d in decisions}
    if "edit" in types:
        return ApprovalStatus.EDITED
    if "approve" in types:
        return ApprovalStatus.APPROVED
    return ApprovalStatus.REJECTED


# ==================== STATE TRANSITIONS ====================

async def open_approval(
    db: Session,
    *,
    agent_chain: Any,
    config: Dict[str, Any],
    conversation_id: int,
    agent_id: int,
    app_id: int,
    channel: ApprovalChannel,
    requester: Requester,
    hitl_config: Optional[HITLConfig],
    answerable: bool = True,
) -> Optional[HITLApproval]:
    """Record the pause the run just stopped at. Idempotent for the same interrupt.

    ``answerable=False`` records a pause the caller is about to reject itself: it is
    created already claimed so nobody (history, a reload, the sweeper) ever sees it pending.
    """
    pause = await read_pause(agent_chain, config)
    if pause is None:
        return None
    existing = HITLApprovalRepository.get_pending_for_conversation(db, conversation_id)
    if existing is not None:
        if existing.interrupt_id == pause.interrupt_id:
            return existing
        # The graph moved on without this approval (e.g. state restored): it can no longer be answered.
        _set_final(existing, ApprovalStatus.CANCELLED, reason="superseded")
        db.flush()

    timeout = hitl_config.approval_timeout_seconds if hitl_config else DEFAULT_APPROVAL_TIMEOUT_SECONDS
    now = _now()
    approval = HITLApproval(
        id=str(uuid.uuid4()),
        app_id=app_id,
        agent_id=agent_id,
        conversation_id=conversation_id,
        thread_id=str(config.get("configurable", {}).get("thread_id", "")),
        interrupt_id=pause.interrupt_id,
        channel=channel.value,
        status=(ApprovalStatus.PENDING if answerable else ApprovalStatus.DECIDING).value,
        actions=_build_actions(pause),
        requested_by_user_id=requester.user_id,
        requested_by_api_key_hash=requester.api_key_hash,
        created_at=now,
        expires_at=now + timedelta(seconds=timeout),
    )
    HITLApprovalRepository.add(db, approval)
    db.commit()
    logger.info(
        "HITL approval %s opened (agent=%s conversation=%s channel=%s actions=%d)",
        approval.id, agent_id, conversation_id, channel.value, len(approval.actions),
    )
    return approval


def claim_for_decision(db: Session, approval: HITLApproval) -> None:
    """Reserve a pending, unexpired approval for one decision, or explain why not."""
    claimed = HITLApprovalRepository.claim(
        db, approval.id, ApprovalStatus.PENDING, ApprovalStatus.DECIDING, only_if_not_expired=True
    )
    db.commit()
    db.refresh(approval)
    if claimed:
        return
    if approval.status == ApprovalStatus.PENDING.value:
        raise ApprovalExpiredError("This approval request has expired; the tool was not executed.")
    raise ApprovalAlreadyDecidedError(
        f"This approval request was already answered ({effective_status(approval)}).",
        status=effective_status(approval),
    )


def prepare_resume(
    db: Session,
    approval_id: str,
    decisions: List[ApprovalDecisionSchema],
    requester: Requester,
    app_id: Optional[int] = None,
) -> ResumeRequest:
    """Load, validate and claim the requester's approval for these decisions."""
    approval = get_for_requester(db, approval_id, requester, app_id)
    ordered = prepare_decisions(approval, decisions)
    claim_for_decision(db, approval)
    return ResumeRequest(approval, ordered, outcome_status(ordered), decided_by=requester)


def prepare_cancel(db: Session, approval_id: str, requester: Requester, app_id: Optional[int] = None) -> ResumeRequest:
    """Claim the requester's approval to reject all of its actions."""
    approval = get_for_requester(db, approval_id, requester, app_id)
    claim_for_decision(db, approval)
    return ResumeRequest(
        approval, reject_all(approval, CANCELLED_MESSAGE), ApprovalStatus.CANCELLED,
        reason="user_cancelled", decided_by=requester,
    )


def claim_for_expiry(db: Session, approval_id: str) -> bool:
    claimed = HITLApprovalRepository.claim(
        db, approval_id, ApprovalStatus.PENDING, ApprovalStatus.EXPIRING, only_if_expired=True
    )
    db.commit()
    return claimed


def _set_final(
    approval: HITLApproval,
    status: ApprovalStatus,
    *,
    reason: Optional[str] = None,
    decisions: Optional[List[Dict[str, Any]]] = None,
    decided_by: Optional[Requester] = None,
    error: Optional[str] = None,
) -> None:
    approval.status = status.value
    approval.decided_at = _now()
    approval.resolution_reason = reason
    if decisions is not None:
        approval.decisions = decisions
    if decided_by is not None:
        approval.decided_by_user_id = decided_by.user_id
        approval.decided_by_api_key_hash = decided_by.api_key_hash
    if error:
        approval.last_error = error[:500]


def finish(
    db: Session,
    approval_id: str,
    status: ApprovalStatus,
    *,
    reason: Optional[str] = None,
    decisions: Optional[List[Dict[str, Any]]] = None,
    decided_by: Optional[Requester] = None,
    error: Optional[str] = None,
) -> None:
    approval = HITLApprovalRepository.get(db, approval_id)
    if approval is None:
        return
    _set_final(approval, status, reason=reason, decisions=decisions, decided_by=decided_by, error=error)
    db.commit()
    logger.info("HITL approval %s resolved as %s (%s)", approval_id, status.value, reason or "decision")


def release(db: Session, approval_id: str, error: str) -> None:
    """Give a claimed approval back (its pause is still answerable) after a failed run."""
    approval = HITLApprovalRepository.get(db, approval_id)
    if approval is None:
        return
    approval.status = ApprovalStatus.PENDING.value
    approval.last_error = error[:500]
    db.commit()


def cancel_pending_for_agents(db: Session, agent_ids: List[int], reason: str) -> int:
    """Close the agents' pending approvals after their approval rules changed.

    A resume re-runs the middleware with the *current* rules: if a tool no longer needs
    approval the decision would be ignored and the tool would run even when rejected. So
    those approvals can no longer be answered. Their paused turn is dropped by the chat's
    incomplete-checkpoint recovery on the next message. The caller commits.
    """
    approval_ids = HITLApprovalRepository.list_open_ids_for_agents(db, agent_ids)
    for approval_id in approval_ids:
        approval = HITLApprovalRepository.get(db, approval_id)
        _set_final(approval, ApprovalStatus.CANCELLED, reason=reason)
    if approval_ids:
        logger.info("Cancelled %d pending HITL approval(s) for agents %s (%s)", len(approval_ids), agent_ids, reason)
    return len(approval_ids)


def is_interactive(channel: ApprovalChannel) -> bool:
    return channel in INTERACTIVE_CHANNELS
