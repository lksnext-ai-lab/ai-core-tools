"""sandbox_it1: App.sandbox_provider, Skill runtime fields, SkillFile table, Conversation.sandbox_session_id

Revision ID: sandbox_it1
Revises: crawlpol001
Create Date: 2026-05-06

Covers IT-1 of the Sandbox Provider Integration RFC:
  - App.sandbox_provider    — nullable VARCHAR(50); NULL = inherit SANDBOX_DEFAULT_PROVIDER
  - Skill.display_name      — human-readable label VARCHAR(255)
  - Skill.frontmatter       — raw YAML frontmatter Text
  - Skill.dependencies      — JSON list of pip packages Text
  - Skill.allowed_tools     — JSON list of allowed tool names Text
  - Skill.runtime           — provider runtime tag VARCHAR(50)
  - Skill.bootstrap_script_path — VARCHAR(255)
  - Skill.runtime_options   — JSON object Text
  - Skill.is_builtin        — globally-readable built-in flag Boolean
  - Skill.description       — widened to VARCHAR(1024)
  - SkillFile table         — supporting files bundled with a Skill package
  - Conversation.sandbox_session_id — VARCHAR(255); provider sandbox ID for restart recovery (Q5)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'sandbox_it1'
down_revision = 'crawlpol001'
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------ App
    op.add_column(
        'App',
        sa.Column('sandbox_provider', sa.String(50), nullable=True)
    )

    # ------------------------------------------------------------------ Skill
    op.add_column('Skill', sa.Column('display_name', sa.String(255), nullable=True))
    op.add_column('Skill', sa.Column('frontmatter', sa.Text(), nullable=True))
    op.add_column('Skill', sa.Column('dependencies', sa.Text(), nullable=True))
    op.add_column('Skill', sa.Column('allowed_tools', sa.Text(), nullable=True))
    op.add_column('Skill', sa.Column('runtime', sa.String(50), nullable=True))
    op.add_column('Skill', sa.Column('bootstrap_script_path', sa.String(255), nullable=True))
    op.add_column('Skill', sa.Column('runtime_options', sa.Text(), nullable=True))
    op.add_column(
        'Skill',
        sa.Column(
            'is_builtin',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        )
    )

    # Widen description from VARCHAR(1000) to VARCHAR(1024)
    op.alter_column(
        'Skill', 'description',
        existing_type=sa.String(1000),
        type_=sa.String(1024),
        existing_nullable=True,
    )

    # Make app_id explicitly nullable (was already, but ensure constraint is stated)
    # No change needed — already nullable=True in skills001 migration.

    # ------------------------------------------------------------------ SkillFile
    op.create_table(
        'SkillFile',
        sa.Column('file_id', sa.Integer(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.Column('path', sa.String(500), nullable=False),
        sa.Column('media_type', sa.String(100), nullable=True),
        sa.Column('content_text', sa.Text(), nullable=True),
        sa.Column('content_bytes', sa.LargeBinary(), nullable=True),
        sa.Column('checksum_sha256', sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(['skill_id'], ['Skill.skill_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('file_id'),
    )
    op.create_index('idx_skillfile_skill_id', 'SkillFile', ['skill_id'])

    # ------------------------------------------------------------------ Conversation
    op.add_column(
        'Conversation',
        sa.Column('sandbox_session_id', sa.String(255), nullable=True)
    )


def downgrade():
    # ------------------------------------------------------------------ Conversation
    op.drop_column('Conversation', 'sandbox_session_id')

    # ------------------------------------------------------------------ SkillFile
    op.drop_index('idx_skillfile_skill_id', table_name='SkillFile')
    op.drop_table('SkillFile')

    # ------------------------------------------------------------------ Skill
    op.alter_column(
        'Skill', 'description',
        existing_type=sa.String(1024),
        type_=sa.String(1000),
        existing_nullable=True,
    )
    op.drop_column('Skill', 'is_builtin')
    op.drop_column('Skill', 'runtime_options')
    op.drop_column('Skill', 'bootstrap_script_path')
    op.drop_column('Skill', 'runtime')
    op.drop_column('Skill', 'allowed_tools')
    op.drop_column('Skill', 'dependencies')
    op.drop_column('Skill', 'frontmatter')
    op.drop_column('Skill', 'display_name')

    # ------------------------------------------------------------------ App
    op.drop_column('App', 'sandbox_provider')
