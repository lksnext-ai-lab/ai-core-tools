"""Pure helpers: per-turn snapshot -> ``ChatTurnInfo``, and pairing turns with history messages.

No database access here, so everything is unit-testable with plain objects.
"""
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from schemas.internal_chat_schemas import ChatSelectionWarning, ChatTurnInfo, ChatTurnRef


def snapshot_ids(items: Optional[Iterable[Any]]) -> List[int]:
    """Ids of a ``[{id, name}]`` snapshot column, ignoring malformed entries (shared with ``_refs``)."""
    return [item["id"] for item in items or [] if isinstance(item, dict) and "id" in item]


def _refs(items: Optional[Iterable[Dict[str, Any]]], existing: Optional[Set[int]]) -> List[ChatTurnRef]:
    """``[{id, name}]`` snapshot -> refs. ``existing=None`` means "just completed": nothing is deleted."""
    out: List[ChatTurnRef] = []
    for item in items or []:
        if not isinstance(item, dict) or "id" not in item:
            continue
        out.append(
            ChatTurnRef(
                id=item["id"],
                name=str(item.get("name") or ""),
                deleted=existing is not None and item["id"] not in existing,
            )
        )
    return out


def build_turn_info(
    turn: Any,
    *,
    existing_ai_service_ids: Optional[Set[int]] = None,
    existing_silo_ids: Optional[Set[int]] = None,
    existing_skill_ids: Optional[Set[int]] = None,
    existing_mcp_config_ids: Optional[Set[int]] = None,
    warnings: Sequence[ChatSelectionWarning] = (),
) -> ChatTurnInfo:
    """Allow-listed ``ChatTurnInfo`` of a ``conversation_turn`` row (or a duck-typed equivalent).

    Fields are copied one by one; the ORM object is never dumped, so columns added to the table later
    (user_id, app_id, execution_event_id, ...) cannot leak to clients. The ``existing_*`` sets flag
    resources deleted since the turn; leave them ``None`` for a turn that has just completed.
    """
    return ChatTurnInfo(
        turn_index=turn.turn_index,
        ai_service_id=turn.ai_service_id,
        ai_service_name=turn.ai_service_name,
        ai_service_deleted=(
            existing_ai_service_ids is not None
            and turn.ai_service_id is not None
            and turn.ai_service_id not in existing_ai_service_ids
        ),
        silo_id=turn.silo_id,
        silo_name=turn.silo_name,
        silo_deleted=(
            existing_silo_ids is not None and turn.silo_id is not None and turn.silo_id not in existing_silo_ids
        ),
        skills=_refs(turn.skills, existing_skill_ids),
        mcp_configs=_refs(turn.mcp_configs, existing_mcp_config_ids),
        created_at=turn.created_at,
        warnings=list(warnings),
    )


def match_turns_to_messages(messages: Sequence[Dict[str, Any]], turns: Sequence[Any]) -> List[Optional[Any]]:
    """For each history message, the ``conversation_turn`` it belongs to (None for user messages / no match).

    1. Assistant messages (``role == "agent"``) are matched to the turn whose ``assistant_message_id``
       equals the message's ``message_id``; each turn is used at most once.
    2. Fallback for the id-less rest (assistant messages without ``message_id`` and turns saved without
       ``assistant_message_id``): paired by ordinal (by ``turn_index``), but ONLY when both counts are equal.
       A message or turn that has an id is never paired by ordinal. When they differ (e.g. summarization dropped old messages) the
       alignment is unknowable and those messages get no turn (the UI shows no badge) rather than a wrong one.
    """
    result: List[Optional[Any]] = [None] * len(messages)
    by_message_id: Dict[str, Any] = {}
    for turn in turns:
        mid = getattr(turn, "assistant_message_id", None)
        if mid and mid not in by_message_id:
            by_message_id[mid] = turn

    used: Set[int] = set()
    unmatched_positions: List[int] = []
    for pos, message in enumerate(messages):
        if message.get("role") != "agent":
            continue
        turn = by_message_id.get(message.get("message_id")) if message.get("message_id") else None
        if turn is not None and id(turn) not in used:
            result[pos] = turn
            used.add(id(turn))
        elif not message.get("message_id"):
            unmatched_positions.append(pos)

    remaining_turns = sorted(
        (t for t in turns if id(t) not in used and not getattr(t, "assistant_message_id", None)),
        key=lambda t: t.turn_index,
    )
    if unmatched_positions and len(unmatched_positions) == len(remaining_turns):
        for pos, turn in zip(unmatched_positions, remaining_turns):
            result[pos] = turn
    return result
