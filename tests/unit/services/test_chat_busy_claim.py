"""Busy-marker claim of a Chat turn: release is idempotent, synchronous, bounded and never raises."""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from services.internal_chat.chat_service import BUSY_MARKER_TTL_SECONDS, InternalChatService, TurnClaim
from services.internal_chat.errors import ChatConversationBusyError, ChatResourceNotFoundError
from tools.stream_guard import AGENT_RUN_TIMEOUT_SECONDS

REPO = "services.internal_chat.chat_service.ChatConversationStateRepository"


def _service():
    return InternalChatService(MagicMock(), {"user_id": 1})


def test_ttl_covers_the_agent_run_timeout_with_a_margin():
    assert BUSY_MARKER_TTL_SECONDS > AGENT_RUN_TIMEOUT_SECONDS


def test_release_runs_once_with_local_timeouts_and_commits():
    service, claim = _service(), TurnClaim(5, uuid.uuid4())
    with patch(REPO) as repo, patch("services.internal_chat.chat_service.set_local_timeouts") as timeouts:
        service.release_turn(claim)
        service.release_turn(claim)  # idempotent
    repo.release_busy.assert_called_once_with(service.db, 5, claim.token)
    timeouts.assert_called_once()
    service.db.commit.assert_called_once()
    assert claim.released


def test_release_without_a_claim_is_a_no_op():
    service = _service()
    service.release_turn(None)
    service.db.rollback.assert_not_called()


def test_a_failing_release_never_raises_and_rolls_back():
    service, claim = _service(), TurnClaim(5, uuid.uuid4())
    with patch(REPO) as repo, patch("services.internal_chat.chat_service.set_local_timeouts"):
        repo.release_busy.side_effect = RuntimeError("db gone")
        service.release_turn(claim)  # must not raise: it runs while an error/cancellation propagates
    assert service.db.rollback.call_count == 2


def test_release_is_synchronous():
    import inspect

    assert not inspect.iscoroutinefunction(InternalChatService.release_turn)


def test_claim_maps_a_taken_marker_to_busy_and_a_missing_row_to_not_found():
    service = _service()
    with patch(REPO) as repo, patch("services.internal_chat.chat_service.set_local_timeouts"):
        repo.claim_busy.return_value = False
        repo.exists.return_value = True
        with pytest.raises(ChatConversationBusyError) as busy:
            service._claim_conversation(5)
        repo.exists.return_value = False
        with pytest.raises(ChatResourceNotFoundError):
            service._claim_conversation(5)
    assert busy.value.error_code == "CONVERSATION_BUSY" and busy.value.status_code == 409
    assert int(busy.value.headers["Retry-After"]) > 0


def test_a_successful_claim_commits_and_returns_its_token():
    service = _service()
    with patch(REPO) as repo, patch("services.internal_chat.chat_service.set_local_timeouts"):
        repo.claim_busy.return_value = True
        claim = service._claim_conversation(5)
    assert claim.conversation_id == 5 and isinstance(claim.token, uuid.UUID)
    service.db.commit.assert_called_once()


def test_a_failed_release_leaves_the_claim_retryable_and_a_later_one_marks_it_released():
    service, claim = _service(), TurnClaim(5, uuid.uuid4())
    with patch(REPO) as repo, patch("services.internal_chat.chat_service.set_local_timeouts"):
        repo.release_busy.side_effect = [RuntimeError("db gone"), None]
        service.release_turn(claim)
        assert not claim.released  # the commit never happened: the safety net must be able to try again
        service.release_turn(claim)
    assert claim.released
    assert repo.release_busy.call_count == 2


def test_turn_scope_releases_on_success_and_on_error():
    service = _service()
    prepared = MagicMock()
    for outcome in (None, RuntimeError("boom")):
        prepared.claim = TurnClaim(5, uuid.uuid4())
        with patch(REPO) as repo, patch("services.internal_chat.chat_service.set_local_timeouts"):
            if outcome is None:
                with service.turn_scope(prepared):
                    pass
            else:
                with pytest.raises(RuntimeError):
                    with service.turn_scope(prepared):
                        raise outcome
        repo.release_busy.assert_called_once()
        assert prepared.claim.released


def test_a_lock_not_available_error_is_busy_not_a_server_error():
    from sqlalchemy.exc import OperationalError

    orig = type("PgError", (Exception,), {"pgcode": "55P03"})()
    service = _service()
    with patch(REPO) as repo, patch("services.internal_chat.chat_service.set_local_timeouts"):
        repo.claim_busy.side_effect = OperationalError("UPDATE ...", {}, orig)
        with pytest.raises(ChatConversationBusyError):
            service._claim_conversation(5)
    service.db.rollback.assert_called()


def test_another_operational_error_is_not_swallowed():
    from sqlalchemy.exc import OperationalError

    orig = type("PgError", (Exception,), {"pgcode": "57014"})()
    service = _service()
    with patch(REPO) as repo, patch("services.internal_chat.chat_service.set_local_timeouts"):
        repo.claim_busy.side_effect = OperationalError("UPDATE ...", {}, orig)
        with pytest.raises(OperationalError):
            service._claim_conversation(5)


def test_renew_pushes_the_expiry_with_the_full_ttl_and_commits():
    service, claim = _service(), TurnClaim(5, uuid.uuid4())
    with patch(REPO) as repo, patch("services.internal_chat.chat_service.set_local_timeouts"):
        service.renew_turn(claim)
    repo.renew_busy.assert_called_once_with(service.db, 5, claim.token, BUSY_MARKER_TTL_SECONDS)
    service.db.commit.assert_called_once()


def test_renew_never_raises_and_ignores_released_or_missing_claims():
    service, claim = _service(), TurnClaim(5, uuid.uuid4())
    with patch(REPO) as repo, patch("services.internal_chat.chat_service.set_local_timeouts"):
        repo.renew_busy.side_effect = RuntimeError("db gone")
        service.renew_turn(claim)  # logged, rolled back, not raised
        service.renew_turn(None)
        claim.released = True
        service.renew_turn(claim)
    assert repo.renew_busy.call_count == 1
    service.db.rollback.assert_called()


def test_the_busy_repository_statements_are_one_compare_and_set_each():
    from sqlalchemy.dialects import postgresql

    from repositories.internal_chat_repository import ChatConversationStateRepository as Repo

    statements = []
    session = MagicMock()
    session.execute.side_effect = lambda stmt: statements.append(
        str(stmt.compile(dialect=postgresql.dialect()))
    ) or MagicMock(rowcount=1)
    token = uuid.uuid4()
    assert Repo.renew_busy(session, 5, token, 660) is True
    sql = statements[0]
    assert "UPDATE chat_conversation_state SET busy_until=" in sql and "clock_timestamp()" in sql
    assert "busy_token =" in sql and "conversation_id =" in sql


def test_the_turn_summary_reads_plain_data_only():
    """``to_client_summary`` is evaluated by the router after the claim's commit expired the session's objects."""
    from services.internal_chat.resolved_config import ResolvedChatConfig

    class Expired:  # reading anything from an expired ORM object would raise like this
        def __getattribute__(self, name):
            raise AssertionError(f"ORM object touched: {name}")

    config = ResolvedChatConfig(
        app_id=1, ai_service=Expired(), ai_service_id=2, ai_service_name="m", ai_service_is_system=False,
        ai_service_provider="p", ai_service_model="g", silo=None, silo_id=None, silo_name=None, skills=(),
        skill_ids=(), skill_names=(), mcp_connections=(), mcp_config_ids=(), mcp_config_names=(), system_prompt="s",
    )

    assert config.to_client_summary()["ai_service"] == {"id": 2, "name": "m"}


def test_before_model_hook_is_run_by_the_carrier_and_a_missing_one_is_a_no_op():
    from services.agent_execution_context import notify_before_model
    from services.internal_chat.resolved_config import TurnDiagnostics

    diagnostics, calls = TurnDiagnostics(), []
    diagnostics.run_before_model()  # no hook: nothing happens
    diagnostics.before_model = lambda: calls.append(1)
    notify_before_model(MagicMock(diagnostics=diagnostics))
    notify_before_model(None)
    notify_before_model(object())  # bare test doubles
    assert calls == [1]
