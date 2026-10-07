"""Unit tests for the A2A env config module (step_009, AD-15).

Covers:
- defaults when no env vars are set;
- bool/int/float parsing, including malformed-value fallback with a warning;
- A2A_ROOT_AGENT parsing: valid 'slug/id', malformed -> None;
- public_base_url fallback order: env override, then FRONTEND_URL, then request base;
- trailing slash stripping;
- agent_rpc_url / agent_card_url construction;
- effective_max_file_bytes: app override vs env default.

No database required.
"""

from __future__ import annotations

import pytest

from utils import a2a_config


@pytest.fixture(autouse=True)
def _clear_cache_and_env(monkeypatch):
    """Ensure each test sees a fresh cache and a clean A2A/FRONTEND_URL env."""
    for name in (
        "A2A_ENABLED",
        "A2A_ENABLE_V0_3_COMPAT",
        "A2A_ROOT_AGENT",
        "A2A_PUBLIC_BASE_URL",
        "A2A_DISCOVERY_RATE_LIMIT_PER_MINUTE",
        "A2A_MAX_REQUEST_MB",
        "A2A_MAX_FILE_MB",
        "A2A_INLINE_FILE_MAX_BYTES",
        "A2A_FILE_URL_TTL_SECONDS",
        "A2A_URI_FETCH_TIMEOUT_SECONDS",
        "A2A_TASK_RETENTION_DAYS",
        "A2A_TASK_TIMEOUT_SECONDS",
        "A2A_SWEEP_INTERVAL_SECONDS",
        "A2A_EVENT_POLL_SECONDS",
        "A2A_STREAM_COALESCE_MS",
        "A2A_KEEPALIVE_SECONDS",
        "A2A_PURGE_GRACE_SECONDS",
        "A2A_STATUS_UPDATES",
        "A2A_SDK_DEBUG",
        "FRONTEND_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    a2a_config.get_a2a_config.cache_clear()
    yield
    a2a_config.get_a2a_config.cache_clear()


class TestDefaults:
    def test_all_defaults(self):
        config = a2a_config.get_a2a_config()
        assert config.enabled is True
        assert config.enable_v0_3_compat is True
        assert config.root_agent is None
        assert config.public_base_url is None
        assert config.discovery_rate_limit_per_minute == 60
        assert config.max_request_mb == 32
        assert config.max_file_mb == 10
        assert config.inline_file_max_bytes == 5242880
        assert config.file_url_ttl_seconds == 3600
        assert config.uri_fetch_timeout_seconds == 15
        assert config.task_retention_days == 30
        assert config.task_timeout_seconds == 900
        assert config.sweep_interval_seconds == 600
        assert config.event_poll_seconds == 0.5
        assert config.stream_coalesce_ms == 250
        assert config.keepalive_seconds == 1.0
        assert config.purge_grace_seconds == 5
        assert config.status_updates is False
        assert config.sdk_debug is False

    def test_result_is_cached(self):
        assert a2a_config.get_a2a_config() is a2a_config.get_a2a_config()


class TestBoolParsing:
    @pytest.mark.parametrize("raw", ["true", "TRUE", "1", "yes", "on"])
    def test_truthy_values(self, monkeypatch, raw):
        monkeypatch.setenv("A2A_ENABLED", raw)
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().enabled is True

    @pytest.mark.parametrize("raw", ["false", "FALSE", "0", "no", "off"])
    def test_falsy_values(self, monkeypatch, raw):
        monkeypatch.setenv("A2A_ENABLED", raw)
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().enabled is False

    def test_malformed_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("A2A_ENABLED", "maybe")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().enabled is True


class TestIntParsing:
    def test_valid_int(self, monkeypatch):
        monkeypatch.setenv("A2A_TASK_RETENTION_DAYS", "45")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().task_retention_days == 45

    def test_malformed_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("A2A_TASK_RETENTION_DAYS", "forever")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().task_retention_days == 30


class TestFloatParsing:
    def test_valid_float(self, monkeypatch):
        monkeypatch.setenv("A2A_KEEPALIVE_SECONDS", "2.5")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().keepalive_seconds == 2.5

    def test_malformed_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("A2A_KEEPALIVE_SECONDS", "slow")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().keepalive_seconds == 1.0


class TestRootAgentParsing:
    def test_valid_slug_id(self, monkeypatch):
        monkeypatch.setenv("A2A_ROOT_AGENT", "my-app/42")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().root_agent == "my-app/42"

    def test_unset_is_none(self):
        assert a2a_config.get_a2a_config().root_agent is None

    @pytest.mark.parametrize(
        "raw",
        ["no-id-here", "My-App/42", "my app/42", "my-app/", "my-app/abc", "/42"],
    )
    def test_malformed_becomes_none(self, monkeypatch, raw):
        monkeypatch.setenv("A2A_ROOT_AGENT", raw)
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().root_agent is None


class TestPublicBaseUrl:
    def test_env_override_wins(self, monkeypatch):
        monkeypatch.setenv("A2A_PUBLIC_BASE_URL", "https://ai.example.com/")
        monkeypatch.setenv("FRONTEND_URL", "https://frontend.example.com")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.public_base_url("http://request-base") == "https://ai.example.com"

    def test_frontend_url_fallback(self, monkeypatch):
        monkeypatch.setenv("FRONTEND_URL", "https://frontend.example.com/")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.public_base_url("http://request-base") == "https://frontend.example.com"

    def test_request_base_fallback(self):
        assert a2a_config.public_base_url("http://request-base/") == "http://request-base"

    def test_no_source_returns_none(self):
        assert a2a_config.public_base_url(None) is None

    def test_trailing_slash_always_stripped(self, monkeypatch):
        monkeypatch.setenv("A2A_PUBLIC_BASE_URL", "https://ai.example.com///")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.public_base_url() == "https://ai.example.com"


class TestUrlBuilders:
    def test_agent_rpc_url(self):
        url = a2a_config.agent_rpc_url("https://ai.example.com", "my-app", 7)
        assert url == "https://ai.example.com/a2a/v1/apps/my-app/agents/7"

    def test_agent_rpc_url_strips_base_trailing_slash(self):
        url = a2a_config.agent_rpc_url("https://ai.example.com/", "my-app", 7)
        assert url == "https://ai.example.com/a2a/v1/apps/my-app/agents/7"

    def test_agent_card_url(self):
        url = a2a_config.agent_card_url("https://ai.example.com", "my-app", 7)
        assert url == (
            "https://ai.example.com/a2a/v1/apps/my-app/agents/7/.well-known/agent-card.json"
        )


class TestIntMinValue:
    """Fields with min_value=1: zero/negative env values fall back to the default."""

    @pytest.mark.parametrize(
        "var,attr,default",
        [
            ("A2A_MAX_REQUEST_MB", "max_request_mb", 32),
            ("A2A_MAX_FILE_MB", "max_file_mb", 10),
            ("A2A_INLINE_FILE_MAX_BYTES", "inline_file_max_bytes", 5242880),
            ("A2A_FILE_URL_TTL_SECONDS", "file_url_ttl_seconds", 3600),
            ("A2A_URI_FETCH_TIMEOUT_SECONDS", "uri_fetch_timeout_seconds", 15),
            ("A2A_TASK_RETENTION_DAYS", "task_retention_days", 30),
            ("A2A_TASK_TIMEOUT_SECONDS", "task_timeout_seconds", 900),
            ("A2A_SWEEP_INTERVAL_SECONDS", "sweep_interval_seconds", 600),
        ],
    )
    def test_zero_falls_back_to_default(self, monkeypatch, var, attr, default):
        monkeypatch.setenv(var, "0")
        a2a_config.get_a2a_config.cache_clear()
        assert getattr(a2a_config.get_a2a_config(), attr) == default

    @pytest.mark.parametrize(
        "var,attr,default",
        [
            ("A2A_MAX_REQUEST_MB", "max_request_mb", 32),
            ("A2A_TASK_TIMEOUT_SECONDS", "task_timeout_seconds", 900),
        ],
    )
    def test_negative_falls_back_to_default(self, monkeypatch, var, attr, default):
        monkeypatch.setenv(var, "-1")
        a2a_config.get_a2a_config.cache_clear()
        assert getattr(a2a_config.get_a2a_config(), attr) == default

    def test_zero_is_allowed_for_stream_coalesce_ms(self, monkeypatch):
        """0ms is a legitimate 'coalescing disabled' value, not a parse failure."""
        monkeypatch.setenv("A2A_STREAM_COALESCE_MS", "0")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().stream_coalesce_ms == 0

    def test_zero_is_allowed_for_purge_grace_seconds(self, monkeypatch):
        """0s is a legitimate 'no grace period' value, not a parse failure."""
        monkeypatch.setenv("A2A_PURGE_GRACE_SECONDS", "0")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().purge_grace_seconds == 0

    def test_zero_is_allowed_for_discovery_rate_limit(self, monkeypatch):
        """0 means 'unlimited' for the discovery limiter, not a parse failure."""
        monkeypatch.setenv("A2A_DISCOVERY_RATE_LIMIT_PER_MINUTE", "0")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().discovery_rate_limit_per_minute == 0


class TestFloatMinValue:
    @pytest.mark.parametrize("raw", ["0", "0.0", "-1", "-0.5"])
    def test_event_poll_seconds_non_positive_falls_back(self, monkeypatch, raw):
        monkeypatch.setenv("A2A_EVENT_POLL_SECONDS", raw)
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().event_poll_seconds == 0.5

    @pytest.mark.parametrize("raw", ["0", "0.0", "-1", "-0.5"])
    def test_keepalive_seconds_non_positive_falls_back(self, monkeypatch, raw):
        monkeypatch.setenv("A2A_KEEPALIVE_SECONDS", raw)
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().keepalive_seconds == 1.0

    @pytest.mark.parametrize("raw", ["inf", "-inf", "nan"])
    def test_non_finite_falls_back(self, monkeypatch, raw):
        monkeypatch.setenv("A2A_KEEPALIVE_SECONDS", raw)
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().keepalive_seconds == 1.0


class TestPublicBaseUrlValidation:
    def test_path_is_allowed(self, monkeypatch):
        monkeypatch.setenv("A2A_PUBLIC_BASE_URL", "https://ai.example.com/mattin")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().public_base_url == "https://ai.example.com/mattin"

    def test_port_is_allowed(self, monkeypatch):
        monkeypatch.setenv("A2A_PUBLIC_BASE_URL", "https://ai.example.com:8443")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().public_base_url == "https://ai.example.com:8443"

    def test_missing_scheme_is_rejected(self, monkeypatch):
        monkeypatch.setenv("A2A_PUBLIC_BASE_URL", "ai.example.com")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().public_base_url is None

    def test_non_http_scheme_is_rejected(self, monkeypatch):
        monkeypatch.setenv("A2A_PUBLIC_BASE_URL", "ftp://ai.example.com")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().public_base_url is None

    def test_query_string_is_rejected(self, monkeypatch):
        monkeypatch.setenv("A2A_PUBLIC_BASE_URL", "https://ai.example.com?x=1")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().public_base_url is None

    def test_fragment_is_rejected(self, monkeypatch):
        monkeypatch.setenv("A2A_PUBLIC_BASE_URL", "https://ai.example.com#frag")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.get_a2a_config().public_base_url is None

    def test_rejected_value_falls_back_to_frontend_url(self, monkeypatch):
        monkeypatch.setenv("A2A_PUBLIC_BASE_URL", "not-a-url")
        monkeypatch.setenv("FRONTEND_URL", "https://frontend.example.com")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.public_base_url() == "https://frontend.example.com"


class TestStartupWarning:
    def test_warns_when_neither_base_url_nor_frontend_url_set(self, mocker):
        a2a_config.get_a2a_config.cache_clear()
        warning = mocker.patch.object(a2a_config.logger, "warning")
        a2a_config.get_a2a_config()
        assert any(
            "A2A_PUBLIC_BASE_URL" in str(call.args) and "FRONTEND_URL" in str(call.args)
            for call in warning.call_args_list
        )

    def test_no_warning_when_frontend_url_set(self, monkeypatch, mocker):
        monkeypatch.setenv("FRONTEND_URL", "https://frontend.example.com")
        a2a_config.get_a2a_config.cache_clear()
        warning = mocker.patch.object(a2a_config.logger, "warning")
        a2a_config.get_a2a_config()
        assert not any(
            "will fall back to the request's Host header" in str(call.args)
            for call in warning.call_args_list
        )


class TestEffectiveMaxFileBytes:
    def test_app_override_used_when_positive(self):
        assert a2a_config.effective_max_file_bytes(25) == 25 * 1024 * 1024

    def test_env_default_used_when_app_value_is_zero(self):
        assert a2a_config.effective_max_file_bytes(0) == 10 * 1024 * 1024

    def test_env_default_used_when_app_value_is_none(self):
        assert a2a_config.effective_max_file_bytes(None) == 10 * 1024 * 1024

    def test_env_default_can_be_overridden(self, monkeypatch):
        monkeypatch.setenv("A2A_MAX_FILE_MB", "20")
        a2a_config.get_a2a_config.cache_clear()
        assert a2a_config.effective_max_file_bytes(None) == 20 * 1024 * 1024
