"""Add execution_profile columns to AIService and Agent tables.

This migration introduces the execution profiles system that lets users
control model reasoning depth (FAST, BALANCED, DEEP, MAX) independently
of the LLM provider.

- AIService.execution_profile : SmallInteger, NOT NULL, default 1 (BALANCED)
- Agent.execution_profile     : SmallInteger, nullable (None = inherit)

Revision ID: execprof001
Revises: userdel001
Create Date: 2026-07-07
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'execprof001'
down_revision = 'userdel001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # AIService
    op.add_column(
        'AIService',
        op.Column('execution_profile', op.SmallInteger(), nullable=False, server_default='1'),
    )

    # Agent
    op.add_column(
        'Agent',
        op.Column('execution_profile', op.SmallInteger(), nullable=True),
    )

    # OCRAgent inherits from Agent so the column is automatically available.


def downgrade() -> None:
    op.drop_column('OCRAgent', 'execution_profile')
    op.drop_column('Agent', 'execution_profile')
    op.drop_column('AIService', 'execution_profile')
