"""Unit tests: on_turn_completed payload and sanitize logic with mocked repositories (no DB)."""
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import datetime

import pytest

from schemas.internal_chat_schemas import ChatSelection, ChatSelectionWarning
from services.agent_execution_context import TurnCompleted
from services.internal_chat import chat_service as cs
from services.internal_chat import selection_resolver as sr
from services.internal_chat.errors import ChatResourceNotFoundError


from services.internal_chat.resolved_config import TurnDiagnostics


def _config(**kw):
    base = dict(
        app_id=3, ai_service_id=1, ai_service_name="GPT", ai_service_model="gpt-x", silo_id=4, silo_name="KB",
        skill_ids=(5,), skill_names=("sk",), mcp_config_ids=(6,), mcp_config_names=("mc",),
    )
    base.update(kw)
    base.setdefault("diagnostics", TurnDiagnostics())
    cfg = SimpleNamespace(**base)
    cfg.to_selection_dict = lambda: {
        "ai_service_id": cfg.ai_service_id, "silo_id": cfg.silo_id,
        "skill_ids": list(cfg.skill_ids), "mcp_config_ids": list(cfg.mcp_config_ids),
    }
    return cfg


def _guard(**kw):
    base = dict(
        conversation_id=8, agent_id=2, session_id="conv_2_x", generation=0,
        selection={"ai_service_id": 1, "silo_id": 4, "skill_ids": [5], "mcp_config_ids": [6, 7]},
        warnings=(ChatSelectionWarning(kind="mcp_config", id=7),),
    )
    base.update(kw)
    return cs._TurnGuard(**base)


def _event(**kw):
    base = dict(conversation_id=8, assistant_message_id="m1", user_context={"user_id": 99}, turn_config=_config())
    base.update(kw)
    return TurnCompleted(**base)


class _Patched:
    """Patches every repository call of the hook and records the order of the writes."""

    def __init__(self, lock=(0, 3, "conv_2_x")):
        self.calls = []
        self.lock = lock
        self.inserted = {}

    def __enter__(self):
        def _insert(_db, **fields):
            self.calls.append("insert")
            self.inserted.update(fields)
            return SimpleNamespace(**fields, created_at=datetime.datetime(2026, 1, 1), id=1)

        def rec(name, ret=None):
            def f(*a, **k):
                self.calls.append(name)
                return ret
            return f

        self.patches = [
            patch.object(cs, "set_local_timeouts", side_effect=rec("timeouts")),
            patch.object(cs.ChatConversationStateRepository, "lock", side_effect=rec("lock", self.lock)),
            patch.object(cs.ChatConversationStateRepository, "upsert", side_effect=rec("state_upsert")),
            patch.object(cs.ChatUserDefaultRepository, "upsert", side_effect=rec("default_upsert")),
            patch.object(cs.ConversationTurnRepository, "next_index", side_effect=rec("next_index", 4)),
            patch.object(cs.ConversationTurnRepository, "insert", side_effect=_insert),
            patch.object(cs.ChatOptionsRepository, "silo_sources", side_effect=rec("silo_sources", {4: ("repository", "R")})),
            patch.object(cs.ConversationService, "delete_thread_histories_in_background", side_effect=rec("drop_thread")),
        ]
        for p_ in self.patches:
            p_.start()
        return self

    def __exit__(self, *a):
        for p_ in self.patches:
            p_.stop()


async def test_hook_payload_is_allow_listed_and_writes_scoped_rows():
    db = MagicMock()
    service = cs.InternalChatService(db, {"user_id": 11, "email": "a@b.c"})
    with _Patched() as pt:
        payload = await service.on_turn_completed(
            _event(execution_event_id="11111111-1111-1111-1111-111111111111"), _guard()
        )
    assert set(payload) == {
        "turn_index", "ai_service_id", "ai_service_name", "ai_service_deleted", "silo_id", "silo_name",
        "silo_deleted", "skills", "mcp_configs", "created_at", "warnings",
    }
    assert payload["turn_index"] == 4
    assert payload["warnings"] == [{"kind": "mcp_config", "id": 7}]
    assert pt.inserted["user_id"] == 11 and pt.inserted["app_id"] == 3 and pt.inserted["silo_source_type"] == "repository"
    assert str(pt.inserted["execution_event_id"]) == "11111111-1111-1111-1111-111111111111"
    # lock as late as possible (after the silo lookup); user default last; timeouts first
    assert pt.calls == ["timeouts", "silo_sources", "lock", "next_index", "insert", "state_upsert", "default_upsert"]
    db.commit.assert_not_called()
    db.rollback.assert_not_called()


async def test_hook_persists_requested_selection_but_turn_row_only_what_was_used():
    service = cs.InternalChatService(MagicMock(), {"user_id": 11})
    seen = {}
    with _Patched() as pt, patch.object(
        cs.ChatUserDefaultRepository, "upsert", side_effect=lambda db, uid, app, sel: seen.update(default=sel)
    ):
        await service.on_turn_completed(_event(), _guard())
    assert seen["default"]["mcp_config_ids"] == [6, 7]  # the skipped config 7 stays in the user's choice
    assert [m["id"] for m in pt.inserted["mcp_configs"]] == [6]  # but the turn recorded only what ran


@pytest.mark.parametrize("lock,gen", [(None, 0), ((2, 3, "conv_2_rotated"), 1)])
async def test_hook_skips_when_conversation_deleted_or_reset(lock, gen):
    service = cs.InternalChatService(MagicMock(), {"user_id": 1})
    with _Patched(lock=lock) as pt:
        assert await service.on_turn_completed(_event(), _guard(generation=gen)) is None
    assert "insert" not in pt.calls and "state_upsert" not in pt.calls and "default_upsert" not in pt.calls
    assert "drop_thread" in pt.calls


async def test_hook_after_reset_drops_only_the_old_thread_and_never_the_current_one():
    service = cs.InternalChatService(MagicMock(), {"user_id": 1})
    with _Patched(lock=(2, 3, "conv_2_rotated")) as pt, patch.object(
        cs.ConversationService, "delete_thread_histories_in_background"
    ) as drop:
        assert await service.on_turn_completed(_event(), _guard(generation=1)) is None
    drop.assert_called_once_with([(2, "conv_2_x")])  # the guard's (old) thread, not the rotated one
    # defensive: if the conversation somehow still points at the guard's thread, nothing is deleted
    with _Patched(lock=(2, 3, "conv_2_x")) as pt, patch.object(
        cs.ConversationService, "delete_thread_histories_in_background"
    ) as drop:
        assert await service.on_turn_completed(_event(), _guard(generation=1)) is None
    drop.assert_not_called()


async def test_hook_rejects_foreign_conversation_and_app_mismatch_before_any_write():
    service = cs.InternalChatService(MagicMock(), {"user_id": 1})
    with _Patched() as pt:
        with pytest.raises(RuntimeError):
            await service.on_turn_completed(_event(conversation_id=99), _guard())
    assert pt.calls == []
    with _Patched(lock=(0, 99, "conv_2_x")) as pt:
        with pytest.raises(RuntimeError):
            await service.on_turn_completed(_event(), _guard())
    assert "insert" not in pt.calls


def test_turn_user_context_is_an_allow_list():
    service = cs.InternalChatService(
        MagicMock(),
        {
            "user_id": 1, "email": "e", "oauth": True, "token": "t", "api_key": "k", "hitl_conversation_id": 5,
            "billing_user_id": 9, "api_key_id": 3, "source": "x", "caller_type_override": "PUBLIC_API", "app_id": 77,
        },
    )
    ctx = service.build_turn_user_context(app_id=3)
    assert ctx == {
        "user_id": 1, "email": "e", "oauth": True, "token": "t", "app_id": 3, "caller_type_override": "INTERNAL_CHAT",
    }


@pytest.mark.parametrize("bad", [True, False, "abc", None, 1.5, "apikey_1"])
def test_user_id_must_be_a_real_integer(bad):
    assert cs.InternalChatService(MagicMock(), {"user_id": bad})._user_id is None
    assert cs.InternalChatService(MagicMock(), {"user_id": "12"})._user_id == 12


def test_non_user_context_gets_not_found():
    service = cs.InternalChatService(MagicMock(), {"user_id": "apikey_x"})
    with pytest.raises(ChatResourceNotFoundError) as exc:
        service.prepare_turn(1, ChatSelection(ai_service_id=1))
    assert exc.value.message == "Resource not found"


def _skill(i, enabled=True):
    return SimpleNamespace(skill_id=i, name=f"s{i}", is_enabled=enabled, app_id=1)


def test_sanitize_drops_invalid_entries_with_warnings():
    service_ok = SimpleNamespace(service_id=1, end_of_service_at=None, app_id=1)
    repo = sr.ChatOptionsRepository
    with patch.object(repo, "ai_service", return_value=service_ok), \
         patch.object(repo, "silos", return_value=[]), \
         patch.object(repo, "selectable_skills_by_ids", return_value=[_skill(5), _skill(6, enabled=False)]), \
         patch.object(repo, "mcp_configs", return_value=[SimpleNamespace(config_id=8)]):
        selection, warnings = sr.ChatSelectionResolver.sanitize(
            MagicMock(), 1,
            {"ai_service_id": 1, "silo_id": 4, "skill_ids": [5, 6, 7], "mcp_config_ids": [8, 9]},
        )
    assert selection == ChatSelection(ai_service_id=1, silo_id=None, skill_ids=[5], mcp_config_ids=[8])
    assert {(w.kind, w.id) for w in warnings} == {("silo", 4), ("skill", 6), ("skill", 7), ("mcp_config", 9)}


def test_sanitize_returns_none_when_ai_service_gone_or_data_garbage():
    repo = sr.ChatOptionsRepository
    with patch.object(repo, "ai_service", return_value=None):
        selection, warnings = sr.ChatSelectionResolver.sanitize(MagicMock(), 1, {"ai_service_id": 1})
    assert selection is None and [(w.kind, w.id) for w in warnings] == [("ai_service", 1)]
    assert sr.ChatSelectionResolver.sanitize(MagicMock(), 1, {"nonsense": True}) == (None, [])
    assert sr.ChatSelectionResolver.sanitize(MagicMock(), 1, None) == (None, [])


def test_sanitize_drops_retired_ai_service_and_silo_without_raising():
    from datetime import datetime, timedelta
    past = datetime.utcnow() - timedelta(days=1)
    retired = SimpleNamespace(service_id=1, end_of_service_at=past, app_id=1)
    repo = sr.ChatOptionsRepository
    silo = SimpleNamespace(silo_id=4, embedding_service=SimpleNamespace(end_of_service_at=past))
    with patch.object(repo, "ai_service", return_value=retired), patch.object(repo, "silos", return_value=[silo]):
        selection, warnings = sr.ChatSelectionResolver.sanitize(MagicMock(), 1, {"ai_service_id": 1, "silo_id": 4})
    assert selection is None
    assert {(w.kind, w.id) for w in warnings} == {("ai_service", 1), ("silo", 4)}


def test_mcp_specs_use_deep_copies_and_skip_bad_config():
    good = MagicMock(config_id=1, ssl_verify=None)
    good.name = "good"
    original = {"srv": {"url": "http://x", "headers": {"a": "b"}}}
    good.to_connection_dict.return_value = original
    bad = MagicMock(config_id=2)
    bad.to_connection_dict.side_effect = ValueError("boom")
    empty = MagicMock(config_id=3)
    empty.to_connection_dict.return_value = {}
    specs, skipped = sr.ChatSelectionResolver._build_mcp_specs([good, bad, empty])
    assert [s.config_id for s in specs] == [1] and skipped == [2, 3]
    assert specs[0].ssl_verify is True
    original["srv"]["headers"]["a"] = "mutated"
    assert specs[0].connections["srv"]["headers"]["a"] == "b"


def test_sanitize_ignores_unknown_stored_keys():
    service_ok = SimpleNamespace(service_id=1, end_of_service_at=None, app_id=1)
    with patch.object(sr.ChatOptionsRepository, "ai_service", return_value=service_ok):
        selection, warnings = sr.ChatSelectionResolver.sanitize(
            MagicMock(), 1, {"ai_service_id": 1, "future_field": {"x": 1}}
        )
    assert selection == ChatSelection(ai_service_id=1) and warnings == []
