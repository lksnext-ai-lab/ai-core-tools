"""Unit tests for ``tools.agentTools.prepare_agent_config`` recursion_limit.

Tests verify:
- Default value is 50 when AICT_AGENT_RECURSION_LIMIT is absent.
- Env override is honoured when the value is a valid integer.
- Non-integer value falls back to 50 and emits a WARNING.

Because AICT_AGENT_RECURSION_LIMIT is read once at module import time via
``_load_recursion_limit()``, we test that helper directly so we don't need to
reimport the module on each test.
"""

from __future__ import annotations

import importlib
import logging
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Test _load_recursion_limit directly
# ---------------------------------------------------------------------------

class TestLoadRecursionLimit:
    def test_default_is_50_when_env_absent(self):
        import tools.agentTools as at

        with patch.dict("os.environ", {}, clear=True):
            # Remove key if present
            import os
            os.environ.pop("AICT_AGENT_RECURSION_LIMIT", None)
            result = at._load_recursion_limit()

        assert result == 50

    def test_valid_integer_env_is_honoured(self):
        import tools.agentTools as at

        with patch.dict("os.environ", {"AICT_AGENT_RECURSION_LIMIT": "100"}):
            result = at._load_recursion_limit()

        assert result == 100

    def test_non_integer_env_falls_back_to_50(self, caplog):
        import tools.agentTools as at
        from unittest.mock import patch as _patch

        warning_calls: list[str] = []
        original_warning = at.logger.warning

        def _capture(msg, *args, **kwargs):
            warning_calls.append(msg % args if args else str(msg))
            return original_warning(msg, *args, **kwargs)

        with patch.dict("os.environ", {"AICT_AGENT_RECURSION_LIMIT": "not_a_number"}):
            with _patch.object(at.logger, "warning", side_effect=_capture):
                result = at._load_recursion_limit()

        assert result == 50
        assert any("not a valid integer" in w for w in warning_calls), (
            f"Expected a WARNING about invalid AICT_AGENT_RECURSION_LIMIT, got: {warning_calls}"
        )

    def test_below_one_falls_back_to_50(self):
        """LangGraph requires recursion_limit >= 1; a value < 1 (e.g. 0 or negative)
        is invalid and must clamp to the safe default rather than break every turn."""
        import tools.agentTools as at

        for bad in ("0", "-5"):
            with patch.dict("os.environ", {"AICT_AGENT_RECURSION_LIMIT": bad}):
                result = at._load_recursion_limit()
            assert result == 50


# ---------------------------------------------------------------------------
# Test prepare_agent_config uses the constant
# ---------------------------------------------------------------------------

class TestPrepareAgentConfig:
    def test_config_includes_recursion_limit(self):
        from tools.agentTools import prepare_agent_config, AICT_AGENT_RECURSION_LIMIT

        import types
        agent = types.SimpleNamespace(agent_id=42)

        config = prepare_agent_config(agent)

        assert "recursion_limit" in config
        assert config["recursion_limit"] == AICT_AGENT_RECURSION_LIMIT

    def test_config_thread_id_uses_agent_id(self):
        from tools.agentTools import prepare_agent_config

        import types
        agent = types.SimpleNamespace(agent_id=7)

        config = prepare_agent_config(agent)

        assert config["configurable"]["thread_id"] == "thread_7"
