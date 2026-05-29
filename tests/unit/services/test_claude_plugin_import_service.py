import io
import json
import zipfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture()
def sqlite_db():
    import models  # noqa: F401
    from db.database import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def sqlite_app(sqlite_db):
    from models.app import App
    from models.user import User

    user = User(email="plugin-import@example.com", name="Plugin Import")
    sqlite_db.add(user)
    sqlite_db.flush()
    app = App(name="Plugin Import App", owner_id=user.user_id)
    sqlite_db.add(app)
    sqlite_db.flush()
    return app


def _make_zip(files: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, content in files.items():
            payload = content.encode("utf-8") if isinstance(content, str) else content
            zf.writestr(path, payload)
    return buf.getvalue()


def test_imports_plugin_skills_agents_and_links_required_skills(sqlite_db, sqlite_app, monkeypatch):
    from models.agent import AgentSkill
    from models.skill import Skill, SkillFile
    from services.claude_plugin_import_service import ClaudePluginImportService
    from services.tier_enforcement_service import TierEnforcementService

    monkeypatch.setattr(TierEnforcementService, "check_resource_limit", lambda *args: None)

    plugin_zip = _make_zip(
        {
            ".claude-plugin/plugin.json": json.dumps(
                {
                    "name": "research-kit",
                    "displayName": "Research Kit",
                    "version": "1.0.0",
                }
            ),
            "skills/research/SKILL.md": (
                "---\n"
                "name: research\n"
                "description: Research source material\n"
                "---\n"
                "Use careful citations."
            ),
            "skills/research/references/style.md": "# Style",
            "agents/researcher.md": (
                "---\n"
                "name: researcher\n"
                "description: Finds and summarizes material\n"
                "skills:\n"
                "  - research\n"
                "---\n"
                "You are a diligent research agent."
            ),
        }
    )

    result = ClaudePluginImportService(sqlite_db).import_plugin(sqlite_app.app_id, plugin_zip)

    assert result.plugin_name == "Research Kit"
    assert [(skill.name, skill.created) for skill in result.imported_skills] == [
        ("research", True)
    ]
    assert [(agent.name, agent.created) for agent in result.imported_agents] == [
        ("researcher", True)
    ]

    skill = sqlite_db.query(Skill).filter_by(app_id=sqlite_app.app_id, name="research").one()
    association = sqlite_db.query(AgentSkill).filter_by(skill_id=skill.skill_id).one()
    assert association.agent_id == result.imported_agents[0].agent_id
    assert result.imported_agents[0].skill_ids == [skill.skill_id]

    skill_file = sqlite_db.query(SkillFile).filter_by(skill_id=skill.skill_id).one()
    assert skill_file.path == "references/style.md"
    assert skill_file.content_text == "# Style"


def test_import_supports_zip_with_single_top_level_plugin_folder(sqlite_db, sqlite_app, monkeypatch):
    from models.agent import Agent
    from models.skill import Skill
    from services.claude_plugin_import_service import ClaudePluginImportService
    from services.tier_enforcement_service import TierEnforcementService

    monkeypatch.setattr(TierEnforcementService, "check_resource_limit", lambda *args: None)

    plugin_zip = _make_zip(
        {
            "my-plugin/skills/helper/SKILL.md": (
                "---\n"
                "name: helper\n"
                "description: Helps with work\n"
                "---\n"
                "Help."
            ),
            "my-plugin/agents/helper-agent.md": (
                "---\n"
                "name: helper-agent\n"
                "description: Uses helper\n"
                "skills: helper\n"
                "---\n"
                "Use helper."
            ),
        }
    )

    result = ClaudePluginImportService(sqlite_db).import_plugin(sqlite_app.app_id, plugin_zip)

    assert result.plugin_name == "my-plugin"
    assert sqlite_db.query(Skill).filter_by(app_id=sqlite_app.app_id, name="helper").count() == 1
    assert (
        sqlite_db.query(Agent)
        .filter_by(app_id=sqlite_app.app_id, name="helper-agent")
        .count()
        == 1
    )


def test_import_reports_missing_agent_skill_references(sqlite_db, sqlite_app, monkeypatch):
    from models.agent import AgentSkill
    from services.claude_plugin_import_service import ClaudePluginImportService
    from services.tier_enforcement_service import TierEnforcementService

    monkeypatch.setattr(TierEnforcementService, "check_resource_limit", lambda *args: None)

    plugin_zip = _make_zip(
        {
            "agents/auditor.md": (
                "---\n"
                "name: auditor\n"
                "description: Checks output\n"
                "skills:\n"
                "  - missing-skill\n"
                "---\n"
                "Audit carefully."
            )
        }
    )

    result = ClaudePluginImportService(sqlite_db).import_plugin(sqlite_app.app_id, plugin_zip)

    assert result.imported_agents[0].missing_skills == ["missing-skill"]
    assert "missing-skill" in result.warnings[0]
    assert sqlite_db.query(AgentSkill).count() == 0


def test_import_rejects_path_traversal(sqlite_db, sqlite_app):
    from services.claude_plugin_import_service import ClaudePluginImportService

    plugin_zip = _make_zip(
        {
            "../escape.md": "bad",
            "agents/auditor.md": "---\nname: auditor\n---\nAudit.",
        }
    )

    with pytest.raises(ValueError, match="Path traversal"):
        ClaudePluginImportService(sqlite_db).import_plugin(sqlite_app.app_id, plugin_zip)


def test_import_rejects_manifest_path_traversal(sqlite_db, sqlite_app):
    from services.claude_plugin_import_service import ClaudePluginImportService

    plugin_zip = _make_zip(
        {
            ".claude-plugin/plugin.json": json.dumps(
                {"name": "bad-plugin", "agents": "../agents"}
            ),
            "agents/auditor.md": "---\nname: auditor\n---\nAudit.",
        }
    )

    with pytest.raises(ValueError, match="escapes plugin root"):
        ClaudePluginImportService(sqlite_db).import_plugin(sqlite_app.app_id, plugin_zip)
