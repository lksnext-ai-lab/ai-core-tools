"""skill packages, system skill metadata and SkillFile table

Revision ID: skills002
Revises: 1eeb4ba697f8
Create Date: 2026-09-21 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'skills002'
down_revision = '1eeb4ba697f8'
branch_labels = None
depends_on = None


def upgrade():
    # 1. New Skill columns
    op.add_column('Skill', sa.Column('display_name', sa.String(200), nullable=True))
    op.add_column('Skill', sa.Column('frontmatter', sa.Text(), nullable=True))
    op.add_column('Skill', sa.Column('allowed_tools', sa.Text(), nullable=True))
    op.add_column('Skill', sa.Column('runtime', sa.String(50), nullable=True))
    op.add_column('Skill', sa.Column('bootstrap_script_path', sa.String(500), nullable=True))
    op.add_column('Skill', sa.Column('runtime_options', sa.Text(), nullable=True))
    op.add_column('Skill', sa.Column('source', sa.String(20), nullable=False, server_default='admin'))
    op.add_column('Skill', sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')))

    # 1b. Uniqueness guard for system skills only (app_id IS NULL), case-insensitive
    op.create_index(
        'uq_skill_system_name', 'Skill', [sa.text('lower(name)')],
        unique=True, postgresql_where=sa.text('app_id IS NULL'),
    )

    # 1c. Tenant lookups (list/detail/name checks) filter on app_id
    op.create_index('ix_skill_app_id', 'Skill', ['app_id'])

    # 2. Widen description (metadata-only on PostgreSQL)
    op.alter_column(
        'Skill', 'description',
        existing_type=sa.String(1000),
        type_=sa.String(1024),
        existing_nullable=True,
    )

    # 3. SkillFile table
    op.create_table(
        'SkillFile',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.Column('path', sa.String(500), nullable=False),
        sa.Column('media_type', sa.String(120), nullable=True),
        sa.Column('content_text', sa.Text(), nullable=True),
        sa.Column('content_bytes', sa.LargeBinary(), nullable=True),
        sa.Column('checksum_sha256', sa.String(64), nullable=False),
        sa.Column('create_date', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['skill_id'], ['Skill.skill_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('skill_id', 'path', name='uq_skillfile_skill_path'),
        sa.CheckConstraint('(content_text IS NULL) <> (content_bytes IS NULL)',
                           name='ck_skillfile_content_xor'),
    )


def downgrade():
    # WARNING: destructive. Drops every SkillFile row (package blobs are unrecoverable), resets
    # source/is_enabled/display_name etc. on re-upgrade, and truncates descriptions > 1000 chars.
    # Export skill packages before downgrading if any SkillFile rows exist.
    op.drop_index('ix_skill_app_id', table_name='Skill')
    op.drop_index('uq_skill_system_name', table_name='Skill')

    op.drop_table('SkillFile')

    op.alter_column(
        'Skill', 'description',
        existing_type=sa.String(1024),
        type_=sa.String(1000),
        existing_nullable=True,
        postgresql_using='left(description, 1000)',
    )

    for col in (
        'is_enabled', 'source', 'runtime_options', 'bootstrap_script_path',
        'runtime', 'allowed_tools', 'frontmatter', 'display_name',
    ):
        op.drop_column('Skill', col)
