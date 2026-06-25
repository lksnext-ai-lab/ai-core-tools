"""Unit tests for utils.secret_key — AC-3.

Verifies that get_secret_key() / validate_secret_key() fail fast for:
- missing / empty SECRET_KEY
- value in the known denylist
- value shorter than 32 characters

And succeeds for a valid key.
No DB required.
"""

import os
import pytest

# Belt-and-suspenders: ensure SECRET_KEY is set before any import so that
# importing get_secret_key (which is used during auth_config load) does not
# fail while we are setting up the module under test.
os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-minimum-ok")

from utils.secret_key import _DENYLIST, _MIN_LENGTH, get_secret_key, validate_secret_key


class TestGetSecretKeyMissing:
    def test_missing_env_raises_runtime_error(self, monkeypatch):
        """Absent SECRET_KEY must raise RuntimeError (fail-fast at startup)."""
        monkeypatch.delenv("SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="SECRET_KEY environment variable is not set"):
            get_secret_key()

    def test_empty_string_raises_runtime_error(self, monkeypatch):
        """Empty string is treated the same as absent."""
        monkeypatch.setenv("SECRET_KEY", "")
        with pytest.raises(RuntimeError, match="SECRET_KEY environment variable is not set"):
            get_secret_key()

    def test_whitespace_only_raises_runtime_error(self, monkeypatch):
        """A key that strips to empty is rejected."""
        monkeypatch.setenv("SECRET_KEY", "   ")
        with pytest.raises(RuntimeError, match="SECRET_KEY environment variable is not set"):
            get_secret_key()


class TestGetSecretKeyDenylist:
    def test_each_denylist_entry_raises_runtime_error(self, monkeypatch):
        """Every known insecure default in _DENYLIST must be rejected."""
        for bad_key in _DENYLIST:
            monkeypatch.setenv("SECRET_KEY", bad_key)
            with pytest.raises(RuntimeError, match="known insecure default"):
                get_secret_key()

    def test_denylist_value_with_leading_trailing_spaces_is_still_rejected(self, monkeypatch):
        """Surrounding whitespace is stripped before denylist check."""
        first_denied = next(iter(sorted(_DENYLIST)))
        monkeypatch.setenv("SECRET_KEY", f"  {first_denied}  ")
        with pytest.raises(RuntimeError, match="known insecure default"):
            get_secret_key()


class TestGetSecretKeyTooShort:
    def test_key_one_char_below_minimum_raises_runtime_error(self, monkeypatch):
        """A key of length _MIN_LENGTH - 1 is rejected with a clear length message."""
        short = "x" * (_MIN_LENGTH - 1)
        assert short not in _DENYLIST
        monkeypatch.setenv("SECRET_KEY", short)
        with pytest.raises(RuntimeError, match="too short"):
            get_secret_key()

    def test_key_exactly_minimum_length_is_accepted(self, monkeypatch):
        """A key of exactly _MIN_LENGTH characters (not in denylist) is accepted."""
        valid = "y" * _MIN_LENGTH
        assert valid not in _DENYLIST
        monkeypatch.setenv("SECRET_KEY", valid)
        result = get_secret_key()
        assert result == valid

    def test_single_character_is_rejected(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "a")
        with pytest.raises(RuntimeError, match="too short"):
            get_secret_key()


class TestGetSecretKeyValid:
    def test_long_random_key_is_accepted(self, monkeypatch):
        """A 64-char hex key (typical production value) is accepted."""
        key = "a1b2c3d4e5f6" * 6  # 72 chars, not in denylist
        monkeypatch.setenv("SECRET_KEY", key)
        assert get_secret_key() == key

    def test_returns_stripped_value(self, monkeypatch):
        """Surrounding whitespace is stripped from the returned value."""
        key = "test-secret-key-32chars-minimum-ok"
        monkeypatch.setenv("SECRET_KEY", f"  {key}  ")
        assert get_secret_key() == key


class TestValidateSecretKey:
    def test_raises_for_missing_key(self, monkeypatch):
        """validate_secret_key() is a thin wrapper — must also raise for absent key."""
        monkeypatch.delenv("SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError):
            validate_secret_key()

    def test_passes_for_valid_key(self, monkeypatch):
        """validate_secret_key() returns None (no exception) for a valid key."""
        monkeypatch.setenv("SECRET_KEY", "test-secret-key-32chars-minimum-ok")
        validate_secret_key()  # must not raise
