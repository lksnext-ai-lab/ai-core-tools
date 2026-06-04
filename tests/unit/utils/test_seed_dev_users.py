"""Tests for the seed_dev_users user-resolution and mode-guard logic."""
import pytest

from utils.seed_dev_users import (
    DEV_USERS,
    SEED_USERS_ENV,
    _parse_users_spec,
    current_login_mode,
    is_seedable_mode,
    resolve_users,
)


class TestParseUsersSpec:
    """Tests for _parse_users_spec."""

    def test_empty_string_returns_empty(self):
        assert _parse_users_spec("") == []

    def test_whitespace_only_returns_empty(self):
        assert _parse_users_spec("   ,  , ") == []

    def test_single_email_with_name(self):
        assert _parse_users_spec("a@x.com:Ana") == [
            {"email": "a@x.com", "name": "Ana", "description": "Seeded dev user"}
        ]

    def test_email_without_name_falls_back_to_local_part(self):
        result = _parse_users_spec("dev@acme.com")
        assert result[0]["email"] == "dev@acme.com"
        assert result[0]["name"] == "dev"

    def test_multiple_users(self):
        result = _parse_users_spec("a@x.com:Ana, b@x.com:Bob")
        assert [u["email"] for u in result] == ["a@x.com", "b@x.com"]
        assert [u["name"] for u in result] == ["Ana", "Bob"]

    def test_name_with_spaces_is_preserved(self):
        result = _parse_users_spec("a@x.com:Ana Maria")
        assert result[0]["name"] == "Ana Maria"

    def test_blank_entries_are_skipped(self):
        result = _parse_users_spec("a@x.com:Ana,,b@x.com:Bob,")
        assert len(result) == 2

    def test_empty_email_with_colon_is_skipped(self):
        assert _parse_users_spec(":NoEmail") == []


class TestResolveUsers:
    """Tests for resolve_users precedence: CLI > env > defaults."""

    def test_cli_spec_takes_precedence(self, monkeypatch):
        monkeypatch.setenv(SEED_USERS_ENV, "env@x.com:Env")
        result = resolve_users("cli@x.com:Cli")
        assert [u["email"] for u in result] == ["cli@x.com"]

    def test_env_used_when_no_cli(self, monkeypatch):
        monkeypatch.setenv(SEED_USERS_ENV, "env@x.com:Env")
        result = resolve_users(None)
        assert [u["email"] for u in result] == ["env@x.com"]

    def test_defaults_when_no_cli_and_no_env(self, monkeypatch):
        monkeypatch.delenv(SEED_USERS_ENV, raising=False)
        assert resolve_users(None) == DEV_USERS

    def test_blank_env_falls_back_to_defaults(self, monkeypatch):
        monkeypatch.setenv(SEED_USERS_ENV, "   ")
        assert resolve_users(None) == DEV_USERS


class TestLoginModeGuard:
    """Tests for current_login_mode / is_seedable_mode."""

    def test_defaults_to_oidc_when_unset(self, monkeypatch):
        monkeypatch.delenv("AICT_LOGIN", raising=False)
        assert current_login_mode() == "OIDC"
        assert is_seedable_mode() is False

    @pytest.mark.parametrize("value", ["FAKE", "fake", " local ", "LOCAL"])
    def test_seedable_modes(self, monkeypatch, value):
        monkeypatch.setenv("AICT_LOGIN", value)
        assert is_seedable_mode() is True

    @pytest.mark.parametrize("value", ["OIDC", "oidc", "bogus"])
    def test_non_seedable_modes(self, monkeypatch, value):
        monkeypatch.setenv("AICT_LOGIN", value)
        assert is_seedable_mode() is False
