"""Unit tests for backend/db/advisory_lock.py (session double, no real Postgres)."""
import logging
from unittest.mock import MagicMock

import pytest

from db.advisory_lock import _derive_lock_key, try_advisory_lock

MODULE_LOGGER = "db.advisory_lock"


def _mock_session(execute_results=None, execute_side_effect=None):
    """Build a MagicMock Session whose .execute(...).scalar() is controllable."""
    session = MagicMock()
    if execute_side_effect is not None:
        session.execute.side_effect = execute_side_effect
    else:
        results = iter(execute_results or [])

        def _execute(*args, **kwargs):
            result = MagicMock()
            result.scalar.return_value = next(results)
            return result

        session.execute.side_effect = _execute
    return session


class TestTryAdvisoryLock:
    def test_acquired_true_yields_true_and_does_not_touch_rollback(self):
        session = _mock_session(execute_results=[True])

        with try_advisory_lock(session, "some:key") as acquired:
            assert acquired is True

        assert session.execute.call_count == 1
        (lock_call,) = session.execute.call_args_list
        assert "pg_try_advisory_xact_lock" in str(lock_call.args[0])
        session.rollback.assert_not_called()

    def test_not_acquired_false_result(self):
        session = _mock_session(execute_results=[False])

        with try_advisory_lock(session, "some:key") as acquired:
            assert acquired is False

        assert session.execute.call_count == 1

    def test_acquire_raises_yields_false_without_propagating(self):
        session = _mock_session(execute_side_effect=RuntimeError("connection lost"))

        with try_advisory_lock(session, "some:key") as acquired:
            assert acquired is False

        # only the (failed) lock attempt
        assert session.execute.call_count == 1
        # session is rolled back to reset poisoned transaction state after the failure
        session.rollback.assert_called_once()

    def test_acquire_raises_and_rollback_also_raises_is_logged_and_swallowed(self, caplog):
        session = MagicMock()
        session.execute.side_effect = RuntimeError("connection lost")
        session.rollback.side_effect = RuntimeError("rollback also failed")

        module_logger = logging.getLogger(MODULE_LOGGER)
        module_logger.addHandler(caplog.handler)
        previous_level = module_logger.level
        module_logger.setLevel(logging.WARNING)
        try:
            with try_advisory_lock(session, "some:key") as acquired:
                assert acquired is False
        finally:
            module_logger.removeHandler(caplog.handler)
            module_logger.setLevel(previous_level)

        assert any("rollback also failed" in record.getMessage() for record in caplog.records)

    def test_body_exception_propagates_and_lock_call_still_happened(self):
        session = _mock_session(execute_results=[True])

        with pytest.raises(ValueError):
            with try_advisory_lock(session, "some:key") as acquired:
                assert acquired is True
                raise ValueError("boom")

        assert session.execute.call_count == 1

    def test_non_str_key_raises_type_error(self):
        session = _mock_session()

        with pytest.raises(TypeError):
            with try_advisory_lock(session, None):
                pass

        session.execute.assert_not_called()


class TestDeriveLockKey:
    def test_deterministic(self):
        assert _derive_lock_key("mattin:system_skills_seed") == _derive_lock_key(
            "mattin:system_skills_seed"
        )

    def test_different_keys_differ(self):
        assert _derive_lock_key("key-a") != _derive_lock_key("key-b")

    def test_returns_signed_64_bit_int(self):
        for key in ("mattin:system_skills_seed", "omniadmin", "x", "a much longer key string here"):
            value = _derive_lock_key(key)
            assert -(2**63) <= value <= 2**63 - 1
