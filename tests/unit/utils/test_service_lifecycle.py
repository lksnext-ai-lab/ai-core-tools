import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from utils.service_lifecycle import (
    LifecycleStatus,
    RetiredServiceAssignmentError,
    ServiceRetiredError,
    compute_lifecycle_status,
    ensure_assignable,
    ensure_service_active,
    get_service_call_context,
    is_retired,
    service_call_context,
    set_service_call_context,
    to_utc,
)

@pytest.fixture
def lifecycle_caplog(caplog):
    """The project logger does not propagate to root, so attach caplog's handler directly."""
    from utils import service_lifecycle

    service_lifecycle.logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG)
    yield caplog
    service_lifecycle.logger.removeHandler(caplog.handler)


NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
N = 30


def _service(eos, notice=None, service_id=7, app_id=3, name="gpt-old"):
    return SimpleNamespace(
        service_id=service_id, app_id=app_id, name=name, end_of_service_at=eos, deprecation_notice=notice
    )


@pytest.mark.parametrize("eos, expected", [
    (None, LifecycleStatus.ACTIVE),
    (NOW + timedelta(days=N + 1), LifecycleStatus.ACTIVE),
    (NOW + timedelta(days=N), LifecycleStatus.DEPRECATED),
    (NOW + timedelta(minutes=1), LifecycleStatus.DEPRECATED),
    (NOW, LifecycleStatus.RETIRED),
    (NOW - timedelta(days=5), LifecycleStatus.RETIRED),
])
def test_status_table(eos, expected):
    assert compute_lifecycle_status(eos, N, now=NOW) is expected


def test_zero_warning_days_has_no_deprecated_phase():
    assert compute_lifecycle_status(NOW + timedelta(minutes=1), 0, now=NOW) is LifecycleStatus.ACTIVE
    assert compute_lifecycle_status(NOW, 0, now=NOW) is LifecycleStatus.RETIRED


def test_negative_warning_days_behave_like_zero():
    assert compute_lifecycle_status(NOW + timedelta(days=1), -5, now=NOW) is LifecycleStatus.ACTIVE


def test_naive_and_aware_inputs():
    naive = datetime(2026, 10, 18, 11, 0)
    aware = datetime(2026, 10, 18, 14, 0, tzinfo=timezone(timedelta(hours=2)))  # 12:00 UTC
    assert to_utc(naive) == datetime(2026, 10, 18, 11, 0, tzinfo=timezone.utc)
    assert to_utc(aware) == NOW
    assert to_utc(None) is None
    assert compute_lifecycle_status(naive, N, now=NOW) is LifecycleStatus.RETIRED
    assert compute_lifecycle_status(aware, N, now=NOW) is LifecycleStatus.RETIRED


def test_default_now_is_current_time():
    assert compute_lifecycle_status(datetime.now(timezone.utc) - timedelta(seconds=1), N) is LifecycleStatus.RETIRED


def test_is_retired():
    assert is_retired(_service(NOW - timedelta(days=1)), now=NOW)
    assert not is_retired(_service(NOW + timedelta(days=1)), now=NOW)
    assert not is_retired(_service(None), now=NOW)
    assert not is_retired(SimpleNamespace(name="mock"), now=NOW)


def test_message_formats():
    eos = datetime(2026, 9, 1, tzinfo=timezone.utc)
    ai = ServiceRetiredError(_service(eos), "ai").message
    assert ai == "Service gpt-old was retired on 2026-09-01."
    with_notice = ServiceRetiredError(_service(eos, notice="Use gpt-new."), "ai").message
    assert with_notice == "Service gpt-old was retired on 2026-09-01. Use gpt-new."
    emb = ServiceRetiredError(_service(eos), "embedding").message
    assert emb == (
        "Service gpt-old was retired on 2026-09-01. "
        "Silos using it must be re-indexed with another embedding service."
    )
    assert ServiceRetiredError(_service(eos, notice="Note."), "embedding").message.endswith(" Note.")
    sandbox = ServiceRetiredError(_service(eos), "sandbox").message
    assert sandbox == (
        "Service gpt-old was retired on 2026-09-01. "
        "The code interpreter is disabled until another sandbox service is selected."
    )


def test_error_attributes():
    eos = datetime(2026, 9, 1, tzinfo=timezone.utc)
    exc = ServiceRetiredError(_service(eos, notice="n"), "ai")
    assert exc.status_code == 409
    assert exc.error_code == "SERVICE_RETIRED"
    assert (exc.service_id, exc.service_name, exc.kind) == (7, "gpt-old", "ai")
    assert exc.end_of_service_at == eos
    assert exc.deprecation_notice == "n"


def test_ensure_service_active_passes_for_active_none_and_mock():
    ensure_service_active(None, "ai")
    ensure_service_active(_service(None), "ai")
    ensure_service_active(_service(datetime.now(timezone.utc) + timedelta(days=1)), "ai")
    ensure_service_active(SimpleNamespace(name="mock"), "ai")


def test_ensure_service_active_logs_one_warning_and_raises(lifecycle_caplog):
    caplog = lifecycle_caplog
    set_service_call_context(channel="chat", app_id=42, resource_type="agent", resource_id=9)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ServiceRetiredError) as info:
            ensure_service_active(_service(NOW - timedelta(days=1)), "embedding")
    assert info.value.status_code == 409
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    text = warnings[0].getMessage()
    for expected in ("service_id=7", "service_app_id=3", "kind=embedding", "app_id=42", "channel=chat",
                     "resource_type=agent", "resource_id=9"):
        assert expected in text


def test_missing_context_logs_unknown(lifecycle_caplog):
    caplog = lifecycle_caplog
    with service_call_context(channel="x"):
        pass  # reset restores "no context"
    set_service_call_context(channel="chat")
    import contextvars
    ctx = contextvars.Context()

    def run():
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ServiceRetiredError):
                ensure_service_active(_service(NOW - timedelta(days=1)), "ai")

    ctx.run(run)
    text = [r for r in caplog.records if r.levelno == logging.WARNING][0].getMessage()
    assert "channel=unknown" in text and "app_id=unknown" in text and "resource_id=unknown" in text


def test_call_context_manager_restores_previous():
    set_service_call_context(channel="outer")
    with service_call_context(channel="inner", app_id=1):
        assert get_service_call_context()["channel"] == "inner"
    assert get_service_call_context()["channel"] == "outer"


def test_ensure_assignable():
    retired = _service(NOW - timedelta(days=1), service_id=5)
    ensure_assignable(retired, 5, "Agent LLM", "ai")  # unchanged
    ensure_assignable(_service(None, service_id=6), 1, "Agent LLM", "ai")  # active
    ensure_assignable(None, 1, "Agent LLM", "ai")
    with pytest.raises(RetiredServiceAssignmentError, match="Agent LLM: service gpt-old was retired on"):
        ensure_assignable(retired, 1, "Agent LLM", "ai")
    with pytest.raises(RetiredServiceAssignmentError):
        ensure_assignable(retired, None, "Agent LLM", "ai")


class TestNormalizeDeprecationNotice:
    def test_none_and_empty(self):
        from utils.service_lifecycle import normalize_deprecation_notice

        assert normalize_deprecation_notice(None) is None
        assert normalize_deprecation_notice("") is None
        assert normalize_deprecation_notice("  \n\t ") is None

    def test_strips(self):
        from utils.service_lifecycle import normalize_deprecation_notice

        assert normalize_deprecation_notice("  use model X  ") == "use model X"

    def test_control_characters_become_spaces(self):
        from utils.service_lifecycle import normalize_deprecation_notice

        cleaned = normalize_deprecation_notice("line1\r\nFAKE LOG\x00tab\there")
        assert cleaned == "line1  FAKE LOG tab here"
        assert not any(c in cleaned for c in "\r\n\t\x00")

    def test_max_length(self):
        import pytest
        from utils.service_lifecycle import normalize_deprecation_notice

        assert normalize_deprecation_notice("a" * 1000) == "a" * 1000
        with pytest.raises(ValueError):
            normalize_deprecation_notice("a" * 1001)

    def test_format_and_separator_characters_replaced(self):
        from utils.service_lifecycle import normalize_deprecation_notice

        assert normalize_deprecation_notice("a\u202eb\u2028c\u2029d\u200be") == "a b c d e"
