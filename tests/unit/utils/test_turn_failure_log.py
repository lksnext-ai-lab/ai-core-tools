"""Unit tests for the Chat-safe failure logging helper and the guaranteed close of a rejected approval."""
import logging
from unittest.mock import MagicMock

import pytest

from utils.turn_failure_log import chat_failure_summary, log_turn_failure, safe_traceback

SECRET = "TOPSECRET-PROMPT-TEXT"


def _raise_chained() -> BaseException:
    try:
        try:
            raise ValueError(f"inner echoes {SECRET}")
        except ValueError as inner:
            raise RuntimeError(f"outer echoes {SECRET}") from inner
    except RuntimeError as exc:
        return exc


def _rendered(caplog) -> str:
    formatter = logging.Formatter()
    return "\n".join(formatter.format(r) + repr(r.__dict__) for r in caplog.records)


class TestLogTurnFailure:
    def test_chat_turn_logs_class_names_ids_and_frames_but_no_text(self, caplog):
        exc = _raise_chained()
        with caplog.at_level(logging.DEBUG):
            correlation = log_turn_failure(
                logging.getLogger("t"), "Error executing agent chat", exc, chat_turn=True, agent_id=7, conversation_id=9
            )
        out = _rendered(caplog)
        assert SECRET not in out
        assert "RuntimeError <- ValueError" in out
        assert "agent_id=7" in out and "conversation_id=9" in out and f"correlation_id={correlation}" in out
        assert "_raise_chained" in out, "frames are kept"
        assert caplog.records[0].exc_info is None and caplog.records[0].levelno == logging.ERROR

    def test_other_turns_log_the_text_with_traceback_as_before(self, caplog):
        exc = _raise_chained()
        with caplog.at_level(logging.DEBUG):
            result = log_turn_failure(logging.getLogger("t"), "Error in streaming agent chat", exc, chat_turn=False)
        assert result is None
        record = caplog.records[0]
        assert record.getMessage() == f"Error in streaming agent chat: outer echoes {SECRET}"
        assert record.exc_info is not None and record.levelno == logging.ERROR

    def test_cyclic_chain_terminates(self):
        a, b = RuntimeError("a"), RuntimeError("b")
        a.__context__, b.__context__ = b, a
        assert "RuntimeError" in safe_traceback(a)

    def test_correlation_ids_differ(self, caplog):
        ids = {log_turn_failure(logging.getLogger("t"), "w", RuntimeError("x"), chat_turn=True) for _ in range(5)}
        assert len(ids) == 5

    def test_one_exception_keeps_one_correlation_id_across_sites(self):
        exc = RuntimeError("x")
        assert log_turn_failure(logging.getLogger("t"), "a", exc, chat_turn=True) == chat_failure_summary(exc)[-8:]

    def test_non_chat_record_points_at_the_caller_not_the_helper(self, caplog):
        with caplog.at_level(logging.DEBUG):
            log_turn_failure(logging.getLogger("t"), "w", _raise_chained(), chat_turn=False)
        record = caplog.records[0]
        assert record.funcName == "test_non_chat_record_points_at_the_caller_not_the_helper"
        assert record.pathname.endswith("test_turn_failure_log.py")

    def test_chat_record_points_at_the_caller_too(self, caplog):
        with caplog.at_level(logging.DEBUG):
            log_turn_failure(logging.getLogger("t"), "w", _raise_chained(), chat_turn=True)
        assert caplog.records[0].pathname.endswith("test_turn_failure_log.py")

    def test_never_raises_for_an_exception_with_a_raising_bool_and_str(self, caplog):
        class Nasty(Exception):
            def __bool__(self):
                raise RuntimeError("bool")

            def __str__(self):
                raise RuntimeError("str")

        try:
            raise Nasty()
        except Nasty as exc:
            nasty = exc
        with caplog.at_level(logging.DEBUG):
            assert log_turn_failure(logging.getLogger("t"), "w", nasty, chat_turn=True)
            assert log_turn_failure(logging.getLogger("t"), "w", nasty, chat_turn=False) is None
        assert "Nasty" in _rendered(caplog)
        assert chat_failure_summary(nasty).startswith("Nasty correlation_id=")

    def test_a_raising_logger_never_propagates(self):
        broken = MagicMock()
        broken.log.side_effect = RuntimeError("handler down")
        assert log_turn_failure(broken, "w", RuntimeError("x"), chat_turn=True)
        assert log_turn_failure(broken, "w", RuntimeError("x"), chat_turn=False) is None

    def test_a_very_deep_traceback_is_capped(self):
        def recurse(n):
            if n == 0:
                raise RuntimeError("deep")
            recurse(n - 1)

        try:
            recurse(400)
        except RuntimeError as exc:
            deep = exc
        assert safe_traceback(deep).count("recurse") <= 2 * 50

    def test_summary_is_class_chain_and_the_id_logged(self, caplog):
        exc = _raise_chained()
        summary = chat_failure_summary(exc)
        with caplog.at_level(logging.DEBUG):
            correlation = log_turn_failure(logging.getLogger("t"), "w", exc, chat_turn=True)
        assert summary == f"RuntimeError <- ValueError correlation_id={correlation}"
        assert SECRET not in summary
