"""Unit tests for SkillService JSON helpers and CreateUpdateSkillSchema semantics (no database)."""
import json
import logging
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from schemas.skill_schemas import CreateUpdateSkillSchema
from services.skill_service import SkillService, logger as merge_logger
from utils.skill_json import dump_json, load_json, logger as service_logger


@pytest.fixture
def log_records():
    """Capture records from the skill service logger regardless of propagation settings."""
    records = []

    class _H(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _H(level=logging.DEBUG)
    loggers = [service_logger, merge_logger]
    old_levels = [lg.level for lg in loggers]
    for lg in loggers:
        lg.addHandler(handler)
        lg.setLevel(logging.DEBUG)
    yield records
    for lg, level in zip(loggers, old_levels):
        lg.removeHandler(handler)
        lg.setLevel(level)


class TestLoadJson:
    def test_malformed_returns_default_and_logs_without_value(self, log_records):
        secret = "SECRET-VALUE-{not json"
        assert load_json(secret, [], skill_id=7, column='allowed_tools') == []
        warnings = [r for r in log_records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        msg = warnings[0].getMessage()
        assert "SECRET-VALUE" not in msg
        assert "7" in msg and "allowed_tools" in msg

    def test_valid_list_round_trip(self):
        dumped = dump_json(["a", "b"])
        assert load_json(dumped, []) == ["a", "b"]

    def test_valid_dict_round_trip(self):
        dumped = dump_json({"k": {"n": 1}})
        assert load_json(dumped, {}) == {"k": {"n": 1}}

    @pytest.mark.parametrize("default", [[], {}])
    def test_none_returns_default(self, default):
        assert load_json(None, default) is default

    def test_empty_string_returns_default(self):
        assert load_json('', {}) == {}

    @pytest.mark.parametrize("stored, default", [
        ('{"a": 1}', []),     # object where list expected
        ('["a"]', {}),        # list where object expected
        ('"text"', []),
        ('42', {}),
        ('null', []),
    ])
    def test_wrong_container_type_returns_default(self, stored, default, log_records):
        assert load_json(stored, default) == default
        assert any(r.levelno == logging.WARNING for r in log_records)

    def test_non_string_list_elements_filtered(self, log_records):
        assert load_json('["a", 1, null, {"x": 1}, "b"]', []) == ["a", "b"]
        assert any(r.levelno == logging.WARNING for r in log_records)

    def test_non_string_list_log_does_not_contain_values(self, log_records):
        load_json('["a", "leaky-value", 5]', [], skill_id=1, column='c')
        assert all("leaky-value" not in r.getMessage() for r in log_records)


class TestDumpJson:
    def test_none_stays_none(self):
        assert dump_json(None) is None

    def test_empty_containers_are_dumped(self):
        assert dump_json([]) == "[]"
        assert dump_json({}) == "{}"

    def test_non_ascii_not_escaped(self):
        assert dump_json({"k": "ñ"}) == '{"k": "ñ"}'


class TestMergeWhenToUse:
    @staticmethod
    def _skill(frontmatter):
        return SimpleNamespace(skill_id=3, frontmatter=frontmatter)

    def test_adds_key_when_no_frontmatter(self):
        skill = self._skill(None)
        SkillService._merge_when_to_use(skill, "when needed")
        assert json.loads(skill.frontmatter) == {"when_to_use": "when needed"}

    def test_adds_key_preserving_others(self):
        skill = self._skill(json.dumps({"name": "x"}))
        SkillService._merge_when_to_use(skill, "when needed")
        assert json.loads(skill.frontmatter) == {"name": "x", "when_to_use": "when needed"}

    def test_replaces_existing_key(self):
        skill = self._skill(json.dumps({"when_to_use": "old"}))
        SkillService._merge_when_to_use(skill, "new")
        assert json.loads(skill.frontmatter) == {"when_to_use": "new"}

    @pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
    def test_blank_removes_key(self, blank):
        skill = self._skill(json.dumps({"name": "x", "when_to_use": "old"}))
        SkillService._merge_when_to_use(skill, blank)
        assert json.loads(skill.frontmatter) == {"name": "x"}

    @pytest.mark.parametrize("stored", ["{not json", '["a"]', '"str"', "42", "null"])
    def test_unreadable_stored_frontmatter_is_reset_and_written(self, stored, log_records):
        skill = self._skill(stored)
        SkillService._merge_when_to_use(skill, "when needed")  # must not raise
        assert json.loads(skill.frontmatter) == {"when_to_use": "when needed"}
        warnings = [r for r in log_records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "3" in warnings[0].getMessage()
        assert "not json" not in warnings[0].getMessage()

    @pytest.mark.parametrize("stored", ["{not json", '["a"]', '"str"', "42", "null"])
    def test_unreadable_stored_frontmatter_blank_when_to_use_resets_to_empty(self, stored):
        skill = self._skill(stored)
        SkillService._merge_when_to_use(skill, "  ")
        assert json.loads(skill.frontmatter) == {}


class TestCreateUpdateSkillSchema:
    BASE = {"name": "n", "content": "c"}

    def test_omitted_fields_not_in_fields_set(self):
        s = CreateUpdateSkillSchema(**self.BASE)
        for f in ("display_name", "runtime", "bootstrap_script_path", "allowed_tools", "runtime_options"):
            assert f not in s.model_fields_set
            assert getattr(s, f) is None

    def test_explicit_null_is_in_fields_set(self):
        s = CreateUpdateSkillSchema(**self.BASE, display_name=None, allowed_tools=None, runtime_options=None)
        assert {"display_name", "allowed_tools", "runtime_options"} <= s.model_fields_set
        assert "runtime" not in s.model_fields_set

    def test_explicit_empty_list_distinguishable_from_omitted(self):
        s = CreateUpdateSkillSchema(**self.BASE, allowed_tools=[])
        assert "allowed_tools" in s.model_fields_set
        assert s.allowed_tools == []

    @pytest.mark.parametrize("field, limit", [
        ("display_name", 200), ("runtime", 50), ("bootstrap_script_path", 500),
    ])
    def test_max_length_bounds(self, field, limit):
        assert getattr(CreateUpdateSkillSchema(**self.BASE, **{field: "a" * limit}), field) == "a" * limit
        with pytest.raises(ValidationError):
            CreateUpdateSkillSchema(**self.BASE, **{field: "a" * (limit + 1)})
