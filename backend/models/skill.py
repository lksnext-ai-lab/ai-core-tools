from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, LargeBinary, UniqueConstraint, CheckConstraint, Index, text
from sqlalchemy.orm import relationship, deferred
from db.database import Base
from datetime import datetime


class Skill(Base):
    """Skill model - Prompt-driven specializations for agents"""
    __tablename__ = 'Skill'
    __table_args__ = (
        Index('uq_skill_system_name', text('lower(name)'), unique=True,
              postgresql_where=text('app_id IS NULL')),
        Index('ix_skill_app_id', 'app_id'),
    )

    skill_id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(String(1024))
    content = Column(Text, nullable=False)  # Markdown instructions for the skill

    # Skill package metadata
    display_name = Column(String(200))                  # human label; falls back to name when NULL
    frontmatter = Column(Text)                          # normalised SKILL.md frontmatter, JSON-encoded
    allowed_tools = Column(Text)                        # JSON-encoded list[str] - METADATA ONLY, never enforced
    runtime = Column(String(50))                        # e.g. "python3.11"
    bootstrap_script_path = Column(String(500))         # package-root-relative
    runtime_options = Column(Text)                      # JSON-encoded object
    source = Column(String(20), nullable=False, default='admin', server_default='admin')   # 'yaml' | 'admin'
    is_enabled = Column(Boolean, nullable=False, server_default=text('true'), default=True)

    # Timestamps
    create_date = Column(DateTime, default=datetime.now)
    update_date = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_frozen = Column(Boolean, default=False, nullable=False)

    # Foreign keys and relationships
    app_id = Column(Integer, ForeignKey('App.app_id'), nullable=True)  # NULL = system/platform skill
    app = relationship('App', back_populates='skills')
    agent_associations = relationship('AgentSkill', back_populates='skill')
    files = relationship('SkillFile', back_populates='skill',
                         cascade='all, delete-orphan', passive_deletes=True, lazy='select')

    @property
    def is_system(self) -> bool:
        return self.app_id is None

    def get_associated_agents(self):
        """Retrieve all agents associated with this Skill."""
        return [association.agent for association in self.agent_associations]


class SkillFile(Base):
    """One file of a skill package (SKILL.md excluded - that stays in Skill.content)."""
    __tablename__ = 'SkillFile'

    id = Column(Integer, primary_key=True)
    skill_id = Column(Integer, ForeignKey('Skill.skill_id', ondelete='CASCADE'), nullable=False)
    path = Column(String(500), nullable=False)        # package-root-relative, POSIX separators
    media_type = Column(String(120))
    content_text = deferred(Column(Text))                       # exactly one of content_text / content_bytes is set
    content_bytes = deferred(Column(LargeBinary))
    checksum_sha256 = Column(String(64), nullable=False)
    create_date = Column(DateTime, default=datetime.now)

    skill = relationship('Skill', back_populates='files')

    __table_args__ = (
        UniqueConstraint('skill_id', 'path', name='uq_skillfile_skill_path'),
        CheckConstraint('(content_text IS NULL) <> (content_bytes IS NULL)', name='ck_skillfile_content_xor'),
    )
