from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, LargeBinary
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime


class Skill(Base):
    """Skill model - Prompt-driven specializations for agents"""
    __tablename__ = 'Skill'

    skill_id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(String(1024))
    content = Column(Text, nullable=False)  # Markdown instructions for the skill

    # Runtime capability fields (IT-1)
    display_name = Column(String(255), nullable=True)          # Human-readable label
    frontmatter = Column(Text, nullable=True)                  # Raw YAML frontmatter from SKILL.md
    # DEPRECATED in v2: dependencies is retained in DB for backward compatibility but
    # is no longer exposed via API schemas. Do not use in new code.
    dependencies = Column(Text, nullable=True)                 # JSON list of pip packages
    allowed_tools = Column(Text, nullable=True)                # JSON list of allowed tool names
    runtime = Column(String(50), nullable=True)                # e.g. 'python', None = prompt-only
    bootstrap_script_path = Column(String(255), nullable=True) # Path to bootstrap .py inside SkillFile
    runtime_options = Column(Text, nullable=True)              # JSON object for provider-specific opts
    is_builtin = Column(Boolean, default=False, nullable=False, server_default='false')
    # is_builtin=True + app_id=NULL → globally readable; apps can clone and customise (Q1)

    # Timestamps
    create_date = Column(DateTime, default=datetime.now)
    update_date = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_frozen = Column(Boolean, default=False, nullable=False)

    # Foreign keys and relationships
    app_id = Column(Integer, ForeignKey('App.app_id'), nullable=True)
    app = relationship('App', back_populates='skills')
    agent_associations = relationship('AgentSkill', back_populates='skill')
    files = relationship('SkillFile', back_populates='skill', cascade='all, delete-orphan')

    def get_associated_agents(self):
        """Retrieve all agents associated with this Skill."""
        return [association.agent for association in self.agent_associations]


class SkillFile(Base):
    """Supporting file bundled with a Skill package (scripts, templates, assets).

    path: Package-root-relative path such as 'scripts/setup.py',
          'references/api.md', or 'assets/logo.png'.
          Must never be absolute, start with '..', or normalize
          outside the package root (e.g., '../escape.py').
          Validated at the repository layer before persistence.
    """
    __tablename__ = 'SkillFile'

    file_id = Column(Integer, primary_key=True)
    skill_id = Column(Integer, ForeignKey('Skill.skill_id'), nullable=False)

    # Package-root-relative path, e.g. "scripts/setup.py" or "templates/report.docx"
    path = Column(String(500), nullable=False)  # package-root-relative
    media_type = Column(String(100), nullable=True)  # MIME type

    # Exactly one of content_text / content_bytes should be set
    content_text = Column(Text, nullable=True)
    content_bytes = Column(LargeBinary, nullable=True)

    # SHA-256 hex digest for integrity verification
    checksum_sha256 = Column(String(64), nullable=True)

    skill = relationship('Skill', back_populates='files')
