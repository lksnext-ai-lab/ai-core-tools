"""Tests for secret_utils module."""
import pytest
from utils.secret_utils import mask_api_key, is_masked_key, MASKED_KEY_PREFIX


class TestMaskApiKey:
    """Tests for mask_api_key function."""

    def test_none_returns_empty(self):
        assert mask_api_key(None) == ""

    def test_empty_string_returns_empty(self):
        assert mask_api_key("") == ""

    def test_change_me_placeholder_returns_empty(self):
        assert mask_api_key("CHANGE_ME") == ""

    def test_normal_key_shows_last_four(self):
        assert mask_api_key("sk-abc123456789xyz") == "****9xyz"

    def test_short_key_returns_masked_only(self):
        assert mask_api_key("abc") == "****"

    def test_exactly_four_chars_returns_masked_only(self):
        assert mask_api_key("abcd") == "****"

    def test_five_chars_shows_last_four(self):
        assert mask_api_key("abcde") == "****bcde"

    def test_long_key(self):
        key = "sk-proj-abc123456789xyz0000"
        result = mask_api_key(key)
        assert result.startswith(MASKED_KEY_PREFIX)
        assert result.endswith(key[-4:])
        assert len(result) == len(MASKED_KEY_PREFIX) + 4

    def test_result_never_contains_full_key(self):
        key = "sk-very-secret-key-12345"
        result = mask_api_key(key)
        assert key not in result
        assert "secret" not in result


class TestIsMaskedKey:
    """Tests for is_masked_key function."""

    def test_none_is_not_masked(self):
        assert is_masked_key(None) is False

    def test_empty_is_not_masked(self):
        assert is_masked_key("") is False

    def test_normal_key_is_not_masked(self):
        assert is_masked_key("sk-abc123456789") is False

    def test_masked_key_is_detected(self):
        assert is_masked_key("****1234") is True

    def test_masked_prefix_only_is_detected(self):
        assert is_masked_key("****") is True

    def test_partial_prefix_is_not_masked(self):
        assert is_masked_key("***1234") is False
