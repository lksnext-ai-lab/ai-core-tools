"""Schema-state checks for the skills002 migration (skill packages + system skills).

Like test_migration_domain_crawling.py these assert the schema produced from the models in the test DB;
the real alembic upgrade/downgrade cycle is run by hand (see step_006 transcript).
"""
import pytest
from sqlalchemy import inspect, text

pytestmark = pytest.mark.integration

NEW_SKILL_COLUMNS = {
    "display_name", "frontmatter", "allowed_tools", "runtime",
    "bootstrap_script_path", "runtime_options", "source", "is_enabled",
}


class TestSkillFileTable:
    def test_table_and_columns(self, test_engine):
        insp = inspect(test_engine)
        assert "SkillFile" in insp.get_table_names()
        cols = {c["name"]: c for c in insp.get_columns("SkillFile")}
        assert set(cols) == {
            "id", "skill_id", "path", "media_type", "content_text", "content_bytes",
            "checksum_sha256", "create_date",
        }
        assert cols["skill_id"]["nullable"] is False
        assert cols["path"]["nullable"] is False
        assert cols["checksum_sha256"]["nullable"] is False
        assert cols["content_text"]["nullable"] is True
        assert cols["content_bytes"]["nullable"] is True

    def test_unique_skill_path(self, test_engine):
        uniques = inspect(test_engine).get_unique_constraints("SkillFile")
        match = [u for u in uniques if u["name"] == "uq_skillfile_skill_path"]
        assert match and match[0]["column_names"] == ["skill_id", "path"]

    def test_content_xor_check_constraint(self, test_engine):
        checks = inspect(test_engine).get_check_constraints("SkillFile")
        assert "ck_skillfile_content_xor" in {c["name"] for c in checks}

    def test_fk_cascades_on_delete(self, test_engine):
        fks = inspect(test_engine).get_foreign_keys("SkillFile")
        fk = [f for f in fks if f["constrained_columns"] == ["skill_id"]]
        assert fk and fk[0]["referred_table"] == "Skill"
        assert fk[0]["options"].get("ondelete", "").upper() == "CASCADE"


class TestSkillTable:
    def test_new_columns_present(self, test_engine):
        cols = {c["name"]: c for c in inspect(test_engine).get_columns("Skill")}
        assert NEW_SKILL_COLUMNS <= set(cols)
        assert cols["source"]["nullable"] is False
        assert cols["is_enabled"]["nullable"] is False

    def test_description_widened(self, test_engine):
        cols = {c["name"]: c for c in inspect(test_engine).get_columns("Skill")}
        assert cols["description"]["type"].length == 1024

    def test_system_name_partial_unique_index(self, test_engine):
        with test_engine.connect() as conn:
            row = conn.execute(text(
                "SELECT indexdef FROM pg_indexes WHERE tablename = 'Skill' AND indexname = 'uq_skill_system_name'"
            )).scalar()
        assert row is not None, "uq_skill_system_name missing"
        low = row.lower()
        assert "unique" in low
        assert "lower(" in low
        assert "app_id is null" in low
