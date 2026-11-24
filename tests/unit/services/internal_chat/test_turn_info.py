"""Unit tests: ChatTurnInfo building and turn <-> message pairing (no DB)."""
from datetime import datetime
from types import SimpleNamespace

from services.internal_chat.turn_info import build_turn_info, match_turns_to_messages


def _turn(index, mid=None, **kw):
    base = dict(
        turn_index=index, assistant_message_id=mid, ai_service_id=1, ai_service_name="GPT", ai_model_name="m",
        silo_id=None, silo_name=None, silo_source_type=None, skills=[], mcp_configs=[],
        created_at=datetime(2026, 1, 1), user_id=7, app_id=3, execution_event_id=None, id=99, conversation_id=5,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _msg(role, mid=None):
    return {"role": role, "content": "x", "message_id": mid}


def test_match_by_message_id_ignores_order():
    t1, t2 = _turn(1, "a"), _turn(2, "b")
    msgs = [_msg("user"), _msg("agent", "b"), _msg("user"), _msg("agent", "a")]
    assert match_turns_to_messages(msgs, [t1, t2]) == [None, t2, None, t1]


def test_ordinal_fallback_when_no_ids_and_counts_equal():
    t1, t2 = _turn(1), _turn(2)
    msgs = [_msg("user"), _msg("agent"), _msg("user"), _msg("agent")]
    assert match_turns_to_messages(msgs, [t2, t1]) == [None, t1, None, t2]


def test_ordinal_fallback_skipped_when_counts_differ():
    msgs = [_msg("user"), _msg("agent"), _msg("agent")]
    assert match_turns_to_messages(msgs, [_turn(1)]) == [None, None, None]


def test_mixed_ids_match_then_fallback_only_for_idless():
    t1, t2, t3 = _turn(1, "a"), _turn(2), _turn(3, "c")
    msgs = [_msg("agent", "a"), _msg("agent"), _msg("agent", "c")]
    assert match_turns_to_messages(msgs, [t1, t2, t3]) == [t1, t2, t3]


def test_message_with_unknown_id_never_paired_by_ordinal():
    msgs = [_msg("agent", "zzz")]
    assert match_turns_to_messages(msgs, [_turn(1, "a")]) == [None]
    assert match_turns_to_messages(msgs, [_turn(1)]) == [None]


def test_turn_is_used_once_for_duplicate_message_ids():
    t1 = _turn(1, "a")
    result = match_turns_to_messages([_msg("agent", "a"), _msg("agent", "a")], [t1])
    assert result == [t1, None]


def test_build_turn_info_is_allow_listed():
    turn = _turn(
        2, "a", silo_id=4, silo_name="KB", skills=[{"id": 1, "name": "s"}, {"id": 2, "name": "gone"}],
        mcp_configs=[{"id": 9, "name": "m"}],
    )
    info = build_turn_info(
        turn, existing_ai_service_ids={1}, existing_silo_ids=set(), existing_skill_ids={1}, existing_mcp_config_ids={9}
    )
    dumped = info.model_dump(mode="json")
    assert set(dumped) == {
        "turn_index", "ai_service_id", "ai_service_name", "ai_service_deleted", "silo_id", "silo_name",
        "silo_deleted", "skills", "mcp_configs", "created_at", "warnings",
    }
    assert dumped["silo_deleted"] is True and dumped["ai_service_deleted"] is False
    assert [(s["id"], s["deleted"]) for s in dumped["skills"]] == [(1, False), (2, True)]
    assert dumped["mcp_configs"][0]["deleted"] is False
    # private columns never leak
    assert "user_id" not in dumped and "app_id" not in dumped and "assistant_message_id" not in dumped


def test_build_turn_info_without_existence_sets_marks_nothing_deleted():
    info = build_turn_info(_turn(1, silo_id=4, silo_name="KB", skills=[{"id": 1, "name": "s"}]))
    assert not info.silo_deleted and not info.ai_service_deleted and not info.skills[0].deleted


def test_snapshot_ids_ignores_malformed_entries():
    from services.internal_chat.turn_info import snapshot_ids

    assert snapshot_ids([{"id": 1, "name": "a"}, "junk", {"name": "no id"}, None, {"id": 3}]) == [1, 3]
    assert snapshot_ids(None) == []
