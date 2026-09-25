"""Unit tests for the SKILL_IMPORT_* env parsing helpers in config."""
import importlib
import math

import pytest

import config

VAR = "SKILL_TEST_VAR"


class TestEnvInt:
    def test_unset_returns_default(self, monkeypatch):
        monkeypatch.delenv(VAR, raising=False)
        assert config._env_int(VAR, 7) == 7

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_blank_returns_default(self, monkeypatch, raw):
        monkeypatch.setenv(VAR, raw)
        assert config._env_int(VAR, 7) == 7

    @pytest.mark.parametrize("raw, expected", [("1", 1), ("500", 500), (" 42 ", 42)])
    def test_valid(self, monkeypatch, raw, expected):
        monkeypatch.setenv(VAR, raw)
        assert config._env_int(VAR, 7) == expected

    @pytest.mark.parametrize("raw", ["0", "-1", "-500", "abc", "1.5", "1e3", "nan", "inf", "0x10"])
    def test_invalid_raises_naming_variable(self, monkeypatch, raw):
        monkeypatch.setenv(VAR, raw)
        with pytest.raises(RuntimeError, match=VAR):
            config._env_int(VAR, 7)

    def test_custom_minimum(self, monkeypatch):
        monkeypatch.setenv(VAR, "0")
        assert config._env_int(VAR, 7, minimum=0) == 0
        monkeypatch.setenv(VAR, "-1")
        with pytest.raises(RuntimeError, match=VAR):
            config._env_int(VAR, 7, minimum=0)


class TestEnvFloat:
    def test_unset_and_blank_return_default(self, monkeypatch):
        monkeypatch.delenv(VAR, raising=False)
        assert config._env_float(VAR, 100.0, minimum=1.0) == 100.0
        monkeypatch.setenv(VAR, "  ")
        assert config._env_float(VAR, 100.0, minimum=1.0) == 100.0

    @pytest.mark.parametrize("raw, expected", [("2.5", 2.5), ("100", 100.0), (" 1.0001 ", 1.0001), ("1e2", 100.0)])
    def test_valid(self, monkeypatch, raw, expected):
        monkeypatch.setenv(VAR, raw)
        assert config._env_float(VAR, 5.0, minimum=1.0, inclusive=False) == expected

    @pytest.mark.parametrize("raw", ["nan", "NaN", "inf", "-inf", "Infinity", "0", "-1", "-0.5", "abc", "1..2"])
    def test_invalid_raises_naming_variable(self, monkeypatch, raw):
        monkeypatch.setenv(VAR, raw)
        with pytest.raises(RuntimeError, match=VAR):
            config._env_float(VAR, 5.0, minimum=1.0, inclusive=False)

    def test_exclusive_minimum_rejects_equal_value(self, monkeypatch):
        monkeypatch.setenv(VAR, "1.0")
        with pytest.raises(RuntimeError, match=VAR):
            config._env_float(VAR, 5.0, minimum=1.0, inclusive=False)

    def test_inclusive_minimum_accepts_equal_value(self, monkeypatch):
        monkeypatch.setenv(VAR, "1.0")
        assert config._env_float(VAR, 5.0, minimum=1.0) == 1.0

    def test_nan_rejected_even_when_finite_check_disabled(self, monkeypatch):
        monkeypatch.setenv(VAR, "nan")
        with pytest.raises(RuntimeError, match=VAR):
            config._env_float(VAR, 5.0, minimum=1.0, finite=False)

    def test_inf_allowed_when_finite_check_disabled(self, monkeypatch):
        monkeypatch.setenv(VAR, "inf")
        assert config._env_float(VAR, 5.0, minimum=1.0, finite=False) == math.inf


class TestModuleLevelSettings:
    @pytest.fixture
    def reload_config(self, monkeypatch):
        yield lambda: importlib.reload(config)
        monkeypatch.undo()
        importlib.reload(config)

    def test_defaults(self):
        assert config.SKILL_IMPORT_MAX_FILES >= 1
        assert config.SKILL_IMPORT_MAX_RATIO > 1.0
        assert math.isfinite(config.SKILL_IMPORT_MAX_RATIO)

    def test_valid_env_is_loaded(self, monkeypatch, reload_config):
        monkeypatch.setenv("SKILL_IMPORT_MAX_FILES", "42")
        monkeypatch.setenv("SKILL_IMPORT_MAX_RATIO", "7.5")
        reload_config()
        assert config.SKILL_IMPORT_MAX_FILES == 42
        assert config.SKILL_IMPORT_MAX_RATIO == 7.5

    @pytest.mark.parametrize("var, raw", [
        ("SKILL_IMPORT_MAX_RATIO", "nan"),
        ("SKILL_IMPORT_MAX_RATIO", "inf"),
        ("SKILL_IMPORT_MAX_RATIO", "1"),
        ("SKILL_IMPORT_MAX_FILES", "0"),
        ("SKILL_IMPORT_MAX_TOTAL_BYTES", "-5"),
        ("SKILL_IMPORT_MAX_FILE_BYTES", "garbage"),
        ("SKILL_IMPORT_MAX_ARCHIVE_BYTES", "0"),
    ])
    def test_bad_env_fails_fast_at_import(self, monkeypatch, reload_config, var, raw):
        monkeypatch.setenv(var, raw)
        with pytest.raises(RuntimeError, match=var):
            reload_config()
