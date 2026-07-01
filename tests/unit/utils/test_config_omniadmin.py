"""Regression tests for utils.config.get_omniadmins / is_omniadmin case-insensitivity.

Bug locked in: AICT_OMNIADMINS entries with mixed case or surrounding whitespace
were not matched by is_omniadmin() because both the stored value and the tested
email were compared without normalisation.  After the fix, get_omniadmins()
strips + lowercases each entry and is_omniadmin() normalises the tested address
before the lookup.

No database required.
"""

import os

import pytest

# Ensure minimum env before any backend import.
os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-minimum-ok")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")


# We import the functions at module level to avoid repeated import overhead;
# both read os.getenv() at *call* time (not at import time), so monkeypatching
# AICT_OMNIADMINS takes effect immediately.
from utils.config import get_omniadmins, is_omniadmin


# ---------------------------------------------------------------------------
# get_omniadmins — normalisation
# ---------------------------------------------------------------------------


class TestGetOmniadmins:
    def test_empty_env_returns_empty_list(self, monkeypatch):
        monkeypatch.setenv("AICT_OMNIADMINS", "")
        assert get_omniadmins() == []

    def test_unset_env_returns_empty_list(self, monkeypatch):
        monkeypatch.delenv("AICT_OMNIADMINS", raising=False)
        assert get_omniadmins() == []

    def test_single_lowercase_entry_unchanged(self, monkeypatch):
        monkeypatch.setenv("AICT_OMNIADMINS", "admin@example.com")
        result = get_omniadmins()
        assert result == ["admin@example.com"]

    def test_mixed_case_entry_lowercased(self, monkeypatch):
        monkeypatch.setenv("AICT_OMNIADMINS", "Admin@Acme.COM")
        result = get_omniadmins()
        assert result == ["admin@acme.com"]

    def test_entry_with_leading_trailing_whitespace_stripped(self, monkeypatch):
        monkeypatch.setenv("AICT_OMNIADMINS", "  admin@acme.com  ")
        result = get_omniadmins()
        assert result == ["admin@acme.com"]

    def test_multiple_entries_all_normalised(self, monkeypatch):
        """Mixed-case + whitespace + multiple entries are all canonical on return."""
        monkeypatch.setenv("AICT_OMNIADMINS", "  Admin@Acme.com , B@X.io ")
        result = get_omniadmins()
        assert result == ["admin@acme.com", "b@x.io"]

    def test_blank_comma_entries_excluded(self, monkeypatch):
        """Entries that are blank after stripping are excluded from the result."""
        monkeypatch.setenv("AICT_OMNIADMINS", "admin@acme.com, , ,b@x.io")
        result = get_omniadmins()
        assert result == ["admin@acme.com", "b@x.io"]

    def test_all_entries_already_lowercase_returned_unchanged(self, monkeypatch):
        monkeypatch.setenv("AICT_OMNIADMINS", "a@x.com,b@y.com")
        result = get_omniadmins()
        assert result == ["a@x.com", "b@y.com"]

    def test_single_whitespace_only_returns_empty(self, monkeypatch):
        monkeypatch.setenv("AICT_OMNIADMINS", "   ")
        assert get_omniadmins() == []


# ---------------------------------------------------------------------------
# is_omniadmin — case-insensitive matching (the regression being locked in)
# ---------------------------------------------------------------------------


class TestIsOmniadmin:
    def test_exact_lowercase_match_returns_true(self, monkeypatch):
        monkeypatch.setenv("AICT_OMNIADMINS", "admin@acme.com")
        assert is_omniadmin("admin@acme.com") is True

    def test_uppercase_email_argument_returns_true(self, monkeypatch):
        """Regression: is_omniadmin('ADMIN@ACME.COM') must match a lowercase entry."""
        monkeypatch.setenv("AICT_OMNIADMINS", "admin@acme.com")
        assert is_omniadmin("ADMIN@ACME.COM") is True

    def test_mixed_case_env_and_lowercase_arg_returns_true(self, monkeypatch):
        """Regression: uppercase env value + lowercase argument must still match."""
        monkeypatch.setenv("AICT_OMNIADMINS", "Admin@Acme.Com")
        assert is_omniadmin("admin@acme.com") is True

    def test_mixed_case_env_and_mixed_case_arg_returns_true(self, monkeypatch):
        """Both sides normalised independently → match is reliable."""
        monkeypatch.setenv("AICT_OMNIADMINS", "  Admin@Acme.com , B@x.io ")
        assert is_omniadmin("admin@acme.com") is True
        assert is_omniadmin(" ADMIN@acme.com ") is True

    def test_second_entry_in_list_matched(self, monkeypatch):
        monkeypatch.setenv("AICT_OMNIADMINS", "  Admin@Acme.com , B@x.io ")
        assert is_omniadmin("b@x.io") is True
        assert is_omniadmin("B@X.IO") is True

    def test_non_member_returns_false(self, monkeypatch):
        monkeypatch.setenv("AICT_OMNIADMINS", "admin@acme.com")
        assert is_omniadmin("other@acme.com") is False

    def test_empty_string_arg_returns_false(self, monkeypatch):
        monkeypatch.setenv("AICT_OMNIADMINS", "admin@acme.com")
        assert is_omniadmin("") is False

    def test_empty_omniadmins_env_always_returns_false(self, monkeypatch):
        monkeypatch.setenv("AICT_OMNIADMINS", "")
        assert is_omniadmin("admin@acme.com") is False

    def test_whitespace_only_arg_stripped_before_lookup(self, monkeypatch):
        """Argument whitespace is stripped before the lookup, matching the fix."""
        monkeypatch.setenv("AICT_OMNIADMINS", "admin@acme.com")
        # A caller who passes "  admin@acme.com  " must still match.
        assert is_omniadmin("  admin@acme.com  ") is True

    def test_case_insensitive_match_with_pytest_env_default(self, monkeypatch):
        """Verify against the AICT_OMNIADMINS=admin@test.com default set in pyproject.toml.

        The actual env var injected by pytest-env is lowercase, but this test
        confirms that even a mixed-case caller gets a match — the primary
        regression scenario.
        """
        monkeypatch.setenv("AICT_OMNIADMINS", "admin@test.com")
        assert is_omniadmin("Admin@Test.COM") is True
        assert is_omniadmin("admin@test.com") is True
