"""add skills support

Revision ID: skills001
Revises: mcpservers001
Create Date: 2026-01-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'skills001'
down_revision = 'mcpservers001'
branch_labels = None
depends_on = None


def upgrade():
    # Create Skill table
    op.create_table('Skill',
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.String(1000), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('create_date', sa.DateTime(), nullable=True),
        sa.Column('update_date', sa.DateTime(), nullable=True),
        sa.Column('app_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['app_id'], ['App.app_id'], ),
        sa.PrimaryKeyConstraint('skill_id')
    )

    # Create agent_skills junction table
    op.create_table('agent_skills',
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['Agent.agent_id'], ),
        sa.ForeignKeyConstraint(['skill_id'], ['Skill.skill_id'], ),
        sa.PrimaryKeyConstraint('agent_id', 'skill_id')
    )


def downgrade():
    op.drop_table('agent_skills')
    op.drop_table('Skill')
