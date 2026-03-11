"""
Unit tests for SystemSettingsService.

The DB session is mocked with MagicMock so no real database is needed.
The defaults cache (class-level) is patched per-test via monkeypatch to
guarantee isolation without directly touching private class attributes.

Tests cover:
  - Type casting / validation for all supported types
  - env_var_name generation
  - load_defaults (caching, missing file, malformed YAML)
  - get_setting precedence: env > db > defaults
  - get_all_settings source resolution
  - update_setting (persist, validation, reset-on-empty-string, DB error)
  - reset_setting (delete, no-op when absent, DB error rollback)
"""

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.system_settings_service import SystemSettingsService


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

# Sample defaults dict used across tests — mirrors the YAML structure
SAMPLE_DEFAULTS = {
    "marketplace_call_quota": {
        "value": "0",
        "type": "integer",
        "category": "marketplace",
        "description": "Max API calls per user per month. 0 = unlimited.",
    },
    "feature_flag": {
        "value": "false",
        "type": "boolean",
        "category": "general",
        "description": "Enable experimental feature.",
    },
    "api_rate": {
        "value": "1.5",
        "type": "float",
        "category": "general",
        "description": "Some float setting.",
    },
    "greeting": {
        "value": "Hello",
        "type": "string",
        "category": "general",
        "description": "Greeting string.",
    },
    "allowed_origins": {
        "value": "http://a.com,http://b.com",
        "type": "string_list",
        "category": "general",
        "description": "Allowed CORS origins.",
    },
    "config_blob": {
        "value": '{"key": "val"}',
        "type": "json",
        "category": "general",
        "description": "JSON config.",
    },
}


@pytest.fixture(autouse=True)
def clear_defaults_cache(monkeypatch):
    """
    Reset the class-level defaults cache before every test so that tests
    which patch load_defaults do not bleed state into subsequent tests.
    Uses monkeypatch so cleanup is automatic even on test failure.
    """
    monkeypatch.setattr(SystemSettingsService, "_defaults_cache", None)


@pytest.fixture
def sample_defaults(monkeypatch):
    """
    Injects SAMPLE_DEFAULTS into the class-level cache via monkeypatch.
    Tests that need a controlled set of defaults should request this fixture.
    """
    monkeypatch.setattr(SystemSettingsService, "_defaults_cache", SAMPLE_DEFAULTS)
    return SAMPLE_DEFAULTS


def make_db_row(key, value=None, type_="integer", category="general", description=None):
    """Build a mock SystemSetting ORM row."""
    row = MagicMock()
    row.key = key
    row.value = value
    row.type = type_
    row.category = category
    row.description = description
    row.updated_at = None
    return row


def make_service(db=None):
    """Return a SystemSettingsService with a fresh MagicMock DB session."""
    if db is None:
        db = MagicMock()
    return SystemSettingsService(db=db)


# ---------------------------------------------------------------------------
# _env_var_name
# ---------------------------------------------------------------------------


class TestEnvVarName:
    def test_simple_key(self):
        assert SystemSettingsService._env_var_name("marketplace_call_quota") == (
            "AICT_SYSTEM_MARKETPLACE_CALL_QUOTA"
        )

    def test_uppercases_key(self):
        assert SystemSettingsService._env_var_name("feature_flag") == (
            "AICT_SYSTEM_FEATURE_FLAG"
        )

    def test_special_chars_become_underscores(self):
        # Dots, dashes, spaces → underscores
        assert SystemSettingsService._env_var_name("my.setting-name") == (
            "AICT_SYSTEM_MY_SETTING_NAME"
        )

    def test_alphanumeric_kept(self):
        result = SystemSettingsService._env_var_name("abc123")
        assert result == "AICT_SYSTEM_ABC123"


# ---------------------------------------------------------------------------
# _cast_value — type casting / validation
# ---------------------------------------------------------------------------


class TestCastString:
    def test_string_from_string(self):
        assert SystemSettingsService._cast_value("hello", "string", "k") == "hello"

    def test_none_becomes_empty_string(self):
        assert SystemSettingsService._cast_value(None, "string", "k") == ""

    def test_integer_coerced_to_string(self):
        assert SystemSettingsService._cast_value(42, "string", "k") == "42"


class TestCastInteger:
    def test_integer_string(self):
        assert SystemSettingsService._cast_value("10", "integer", "k") == 10

    def test_native_int_passthrough(self):
        assert SystemSettingsService._cast_value(7, "integer", "k") == 7

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="k"):
            SystemSettingsService._cast_value("abc", "integer", "k")

    def test_float_string_raises_value_error(self):
        with pytest.raises(ValueError):
            SystemSettingsService._cast_value("1.5", "integer", "k")


class TestCastFloat:
    def test_float_string(self):
        assert SystemSettingsService._cast_value("1.5", "float", "k") == pytest.approx(1.5)

    def test_integer_string_cast_to_float(self):
        assert SystemSettingsService._cast_value("3", "float", "k") == pytest.approx(3.0)

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="k"):
            SystemSettingsService._cast_value("bad", "float", "k")


class TestCastBoolean:
    @pytest.mark.parametrize("raw", ["true", "True", "TRUE", "1", "yes", "YES", "Yes"])
    def test_truthy_values(self, raw):
        assert SystemSettingsService._cast_value(raw, "boolean", "k") is True

    @pytest.mark.parametrize("raw", ["false", "False", "0", "no", "NO", "", None])
    def test_falsy_values(self, raw):
        assert SystemSettingsService._cast_value(raw, "boolean", "k") is False


class TestCastJson:
    def test_dict_passthrough(self):
        data = {"key": "val"}
        assert SystemSettingsService._cast_value(data, "json", "k") == data

    def test_list_passthrough(self):
        data = [1, 2, 3]
        assert SystemSettingsService._cast_value(data, "json", "k") == data

    def test_json_string_parsed(self):
        result = SystemSettingsService._cast_value('{"a": 1}', "json", "k")
        assert result == {"a": 1}

    def test_none_returns_none(self):
        assert SystemSettingsService._cast_value(None, "json", "k") is None

    def test_invalid_json_string_raises(self):
        with pytest.raises(ValueError, match="k"):
            SystemSettingsService._cast_value("{bad json", "json", "k")


class TestCastStringList:
    def test_comma_separated_string(self):
        result = SystemSettingsService._cast_value("a, b, c", "string_list", "k")
        assert result == ["a", "b", "c"]

    def test_list_passthrough(self):
        result = SystemSettingsService._cast_value(["x", "y"], "string_list", "k")
        assert result == ["x", "y"]

    def test_none_returns_empty_list(self):
        assert SystemSettingsService._cast_value(None, "string_list", "k") == []

    def test_empty_string_returns_empty_list(self):
        assert SystemSettingsService._cast_value("", "string_list", "k") == []

    def test_strips_whitespace(self):
        result = SystemSettingsService._cast_value("  a  ,  b  ", "string_list", "k")
        assert result == ["a", "b"]


class TestCastUnknownType:
    def test_unknown_type_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported"):
            SystemSettingsService._cast_value("x", "unknown_type", "k")


# ---------------------------------------------------------------------------
# load_defaults
# ---------------------------------------------------------------------------


class TestLoadDefaults:
    def test_loads_from_real_yaml_file(self):
        """The real system_defaults.yaml exists in the repo — load it."""
        svc = make_service()
        defaults = svc.load_defaults()
        assert isinstance(defaults, dict)
        # The file must have at least the canonical setting
        assert "marketplace_call_quota" in defaults

    def test_result_is_cached_on_second_call(self):
        svc = make_service()
        first = svc.load_defaults()
        second = svc.load_defaults()
        assert first is second

    def test_raises_when_file_missing(self, tmp_path):
        svc = make_service()
        missing = tmp_path / "does_not_exist.yaml"
        with patch.object(type(svc), "_defaults_path", new=missing):
            with pytest.raises(RuntimeError, match="not found"):
                svc.load_defaults()

    def test_raises_on_invalid_yaml(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("settings: {bad: yaml: content:::}")
        svc = make_service()
        with patch.object(type(svc), "_defaults_path", new=bad_yaml):
            with pytest.raises(RuntimeError, match="Malformed"):
                svc.load_defaults()

    def test_raises_when_settings_key_missing(self, tmp_path):
        yaml_file = tmp_path / "no_settings.yaml"
        yaml_file.write_text("other_key:\n  foo: bar\n")
        svc = make_service()
        with patch.object(type(svc), "_defaults_path", new=yaml_file):
            with pytest.raises(RuntimeError, match="missing 'settings'"):
                svc.load_defaults()

    def test_raises_when_settings_not_a_map(self, tmp_path):
        yaml_file = tmp_path / "settings_list.yaml"
        yaml_file.write_text("settings:\n  - item1\n  - item2\n")
        svc = make_service()
        with patch.object(type(svc), "_defaults_path", new=yaml_file):
            with pytest.raises(RuntimeError, match="'settings' must be a map"):
                svc.load_defaults()


# ---------------------------------------------------------------------------
# get_setting — precedence: env > db > default
# ---------------------------------------------------------------------------


class TestGetSettingPrecedence:
    def test_env_var_overrides_db_and_default(self, sample_defaults, monkeypatch):
        db = MagicMock()
        db_row = make_db_row("marketplace_call_quota", value="5", type_="integer")
        db.query().filter().first.return_value = db_row

        monkeypatch.setenv("AICT_SYSTEM_MARKETPLACE_CALL_QUOTA", "99")
        result = make_service(db).get_setting("marketplace_call_quota")
        assert result == 99

    def test_db_used_when_no_env_var(self, sample_defaults):
        db = MagicMock()
        db_row = make_db_row("marketplace_call_quota", value="7", type_="integer")
        db.query().filter().first.return_value = db_row

        result = make_service(db).get_setting("marketplace_call_quota")
        assert result == 7

    def test_default_used_when_no_env_and_no_db_row(self, sample_defaults):
        db = MagicMock()
        db.query().filter().first.return_value = None

        result = make_service(db).get_setting("marketplace_call_quota")
        assert result == 0  # default value "0" cast to int

    def test_default_used_when_db_row_has_null_value(self, sample_defaults):
        db = MagicMock()
        db_row = make_db_row("marketplace_call_quota", value=None, type_="integer")
        db.query().filter().first.return_value = db_row

        result = make_service(db).get_setting("marketplace_call_quota")
        assert result == 0

    def test_returns_none_when_no_default_defined(self, monkeypatch):
        db = MagicMock()
        db.query().filter().first.return_value = None

        # A defaults dict where the key has no 'value'
        defaults_no_value = {
            "orphan_key": {"type": "string", "category": "general"},
        }
        monkeypatch.setattr(SystemSettingsService, "_defaults_cache", defaults_no_value)

        result = make_service(db).get_setting("orphan_key")
        assert result is None

    def test_env_var_cast_to_correct_type(self, sample_defaults, monkeypatch):
        db = MagicMock()
        db.query().filter().first.return_value = None

        monkeypatch.setenv("AICT_SYSTEM_FEATURE_FLAG", "true")
        assert make_service(db).get_setting("feature_flag") is True

    def test_db_value_cast_to_correct_type(self, sample_defaults):
        db = MagicMock()
        db_row = make_db_row("feature_flag", value="yes", type_="boolean")
        db.query().filter().first.return_value = db_row

        assert make_service(db).get_setting("feature_flag") is True


# ---------------------------------------------------------------------------
# get_all_settings — source resolution
# ---------------------------------------------------------------------------


class TestGetAllSettings:
    def test_includes_keys_from_defaults_only(self, sample_defaults):
        db = MagicMock()
        db.query().all.return_value = []

        result = make_service(db).get_all_settings()
        keys = {s["key"] for s in result}
        assert keys == set(SAMPLE_DEFAULTS.keys())

    def test_source_env_when_env_var_set(self, sample_defaults, monkeypatch):
        db = MagicMock()
        db.query().all.return_value = []

        monkeypatch.setenv("AICT_SYSTEM_GREETING", "HI")
        result = {s["key"]: s for s in make_service(db).get_all_settings()}
        assert result["greeting"]["source"] == "env"
        assert result["greeting"]["resolved_value"] == "HI"

    def test_source_db_when_db_row_exists(self, sample_defaults):
        db = MagicMock()
        db_row = make_db_row("greeting", value="Hey", type_="string")
        db.query().all.return_value = [db_row]

        result = {s["key"]: s for s in make_service(db).get_all_settings()}
        assert result["greeting"]["source"] == "db"
        assert result["greeting"]["resolved_value"] == "Hey"

    def test_source_default_when_no_override(self, sample_defaults):
        db = MagicMock()
        db.query().all.return_value = []

        result = {s["key"]: s for s in make_service(db).get_all_settings()}
        assert result["greeting"]["source"] == "default"
        assert result["greeting"]["resolved_value"] == "Hello"

    def test_db_only_key_included_in_results(self, sample_defaults):
        """A key in DB but not in defaults is still returned."""
        db = MagicMock()
        extra_row = make_db_row("legacy_key", value="old", type_="string")
        db.query().all.return_value = [extra_row]

        result = {s["key"]: s for s in make_service(db).get_all_settings()}
        assert "legacy_key" in result
        assert result["legacy_key"]["source"] == "db"

    def test_env_wins_over_db_in_get_all(self, sample_defaults, monkeypatch):
        db = MagicMock()
        db_row = make_db_row("marketplace_call_quota", value="5", type_="integer")
        db.query().all.return_value = [db_row]

        monkeypatch.setenv("AICT_SYSTEM_MARKETPLACE_CALL_QUOTA", "42")
        result = {s["key"]: s for s in make_service(db).get_all_settings()}
        assert result["marketplace_call_quota"]["source"] == "env"
        assert result["marketplace_call_quota"]["resolved_value"] == 42


# ---------------------------------------------------------------------------
# update_setting
# ---------------------------------------------------------------------------


class TestUpdateSetting:
    def test_unknown_key_raises_key_error(self, sample_defaults):
        db = MagicMock()
        with pytest.raises(KeyError, match="Unknown setting key"):
            make_service(db).update_setting("nonexistent_key", "value")

    def test_creates_new_row_when_absent(self, sample_defaults):
        db = MagicMock()
        db.query().filter().first.return_value = None

        result = make_service(db).update_setting("marketplace_call_quota", "10")
        db.add.assert_called_once()
        db.commit.assert_called_once()
        assert result.value == "10"

    def test_updates_existing_row(self, sample_defaults):
        db = MagicMock()
        existing = make_db_row("marketplace_call_quota", value="1", type_="integer")
        db.query().filter().first.return_value = existing

        make_service(db).update_setting("marketplace_call_quota", "20")
        assert existing.value == "20"
        db.commit.assert_called_once()

    def test_invalid_value_for_integer_raises(self, sample_defaults):
        db = MagicMock()
        db.query().filter().first.return_value = None

        with pytest.raises(ValueError, match="marketplace_call_quota"):
            make_service(db).update_setting("marketplace_call_quota", "not_a_number")

    def test_empty_string_triggers_reset_for_integer(self, sample_defaults):
        db = MagicMock()
        db.query().filter().first.return_value = None

        # Should call reset_setting internally — no error, returns a blank SystemSetting
        result = make_service(db).update_setting("marketplace_call_quota", "")
        assert result.value is None

    def test_empty_string_triggers_reset_for_float(self, sample_defaults):
        db = MagicMock()
        db.query().filter().first.return_value = None

        result = make_service(db).update_setting("api_rate", "")
        assert result.value is None

    def test_empty_string_triggers_reset_for_boolean(self, sample_defaults):
        db = MagicMock()
        db.query().filter().first.return_value = None

        result = make_service(db).update_setting("feature_flag", "")
        assert result.value is None

    def test_empty_string_for_string_type_is_stored(self, sample_defaults):
        """Empty string is valid for 'string' type — should NOT trigger reset."""
        db = MagicMock()
        db.query().filter().first.return_value = None

        result = make_service(db).update_setting("greeting", "")
        assert result.value == ""
        db.commit.assert_called_once()

    def test_db_error_triggers_rollback(self, sample_defaults):
        from sqlalchemy.exc import SQLAlchemyError

        db = MagicMock()
        db.query().filter().first.return_value = None
        db.commit.side_effect = SQLAlchemyError("DB down")

        with pytest.raises(SQLAlchemyError):
            make_service(db).update_setting("marketplace_call_quota", "5")

        db.rollback.assert_called_once()

    def test_stored_type_matches_declared_type(self, sample_defaults):
        db = MagicMock()
        db.query().filter().first.return_value = None

        result = make_service(db).update_setting("marketplace_call_quota", "3")
        assert result.type == "integer"
        assert result.category == "marketplace"


# ---------------------------------------------------------------------------
# reset_setting
# ---------------------------------------------------------------------------


class TestResetSetting:
    def test_unknown_key_raises_key_error(self, sample_defaults):
        db = MagicMock()
        with pytest.raises(KeyError, match="Unknown setting key"):
            make_service(db).reset_setting("no_such_key")

    def test_no_op_when_row_not_in_db(self, sample_defaults):
        db = MagicMock()
        db.query().filter().first.return_value = None

        # Should return without error and without touching the DB
        make_service(db).reset_setting("marketplace_call_quota")
        db.delete.assert_not_called()
        db.commit.assert_not_called()

    def test_deletes_existing_row(self, sample_defaults):
        db = MagicMock()
        row = make_db_row("marketplace_call_quota", value="5")
        db.query().filter().first.return_value = row

        make_service(db).reset_setting("marketplace_call_quota")
        db.delete.assert_called_once_with(row)
        db.commit.assert_called_once()

    def test_db_error_triggers_rollback(self, sample_defaults):
        from sqlalchemy.exc import SQLAlchemyError

        db = MagicMock()
        row = make_db_row("marketplace_call_quota", value="5")
        db.query().filter().first.return_value = row
        db.commit.side_effect = SQLAlchemyError("disk full")

        with pytest.raises(SQLAlchemyError):
            make_service(db).reset_setting("marketplace_call_quota")

        db.rollback.assert_called_once()
