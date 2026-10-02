"""Human-in-the-loop helpers shared by the streaming chat, resume and history endpoints.

Payloads follow LangChain's ``HumanInTheLoopMiddleware`` interrupt format::

    {"action_requests": [{"name", "args", "description"}],
     "review_configs": [{"action_name", "allowed_decisions"}]}

Decisions must come in the same order as ``action_requests`` and each decision type
must be allowed for its action — LangChain raises otherwise, and because the resume
value is stored in the checkpoint an invalid decision would wedge the conversation.
That is why decisions are validated here before ``Command(resume=...)`` is sent.
"""
from typing import Any, Optional

from schemas.middleware_schemas import HITLConfig


class HITLDecisionError(ValueError):
    """The decisions do not match the pending approval (shown to the user as-is)."""


def pending_approval_from_state(state: Any) -> Optional[dict]:
    """Extract the pending HITL request from a LangGraph ``StateSnapshot``."""
    action_requests: list = []
    review_configs: list = []
    for task in getattr(state, "tasks", None) or []:
        for intr in getattr(task, "interrupts", None) or []:
            value = getattr(intr, "value", None)
            if isinstance(value, dict):
                action_requests.extend(value.get("action_requests", []))
                review_configs.extend(value.get("review_configs", []))
    if not action_requests:
        return None
    return {"action_requests": action_requests, "review_configs": review_configs}


def pending_approval_from_tool_calls(config: Optional[HITLConfig], tool_calls: list) -> Optional[dict]:
    """Rebuild the pending request from the unanswered tool calls in the checkpoint.

    Used to restore the approval card after a page reload without touching LangGraph
    internals: the interrupted state is the last AI message's tool calls that need review.
    """
    if config is None or not tool_calls:
        return None
    action_requests, review_configs = [], []
    for call in tool_calls:
        rule = config.interrupt_on.get(call.get("name"))
        if rule is None:
            continue
        action_requests.append({
            "name": call["name"],
            "args": call.get("args") or {},
            "description": f"{config.description_prefix}\n\nTool: {call['name']}",
        })
        review_configs.append({"action_name": call["name"], "allowed_decisions": rule.allowed_decisions})
    if not action_requests:
        return None
    return {"action_requests": action_requests, "review_configs": review_configs}


def validate_decisions(pending: Optional[dict], decisions: list[dict]) -> None:
    """Raise HITLDecisionError unless ``decisions`` answer ``pending`` exactly."""
    if not pending:
        raise HITLDecisionError("There is no pending approval in this conversation.")
    actions = pending["action_requests"]
    if len(decisions) != len(actions):
        raise HITLDecisionError(f"Expected {len(actions)} decision(s), received {len(decisions)}.")
    allowed_by_tool = {rc["action_name"]: rc["allowed_decisions"] for rc in pending["review_configs"]}
    for action, decision in zip(actions, decisions):
        allowed = allowed_by_tool.get(action["name"], [])
        if decision["type"] not in allowed:
            raise HITLDecisionError(
                f"'{decision['type']}' is not allowed for tool '{action['name']}'. Allowed: {', '.join(allowed)}."
            )
        if decision["type"] == "edit" and decision["edited_action"]["name"] != action["name"]:
            raise HITLDecisionError("An edit cannot change which tool is called.")
