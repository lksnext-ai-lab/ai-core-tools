"""remove skill-specific fields from A2A agent

Revision ID: a2a005
Revises: a2a004
Create Date: 2026-04-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2a005'
down_revision = 'a2a004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('A2AAgent', 'remote_skill_metadata')
    op.drop_column('A2AAgent', 'remote_skill_name')
    op.drop_column('A2AAgent', 'remote_skill_id')


def downgrade() -> None:
    op.add_column(
        'A2AAgent',
        sa.Column('remote_skill_id', sa.String(length=255), nullable=False, server_default='legacy-skill'),
    )
    op.add_column(
        'A2AAgent',
        sa.Column('remote_skill_name', sa.String(length=255), nullable=False, server_default='Legacy Skill'),
    )
    op.add_column(
        'A2AAgent',
        sa.Column('remote_skill_metadata', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.alter_column('A2AAgent', 'remote_skill_id', server_default=None)
    op.alter_column('A2AAgent', 'remote_skill_name', server_default=None)
    op.alter_column('A2AAgent', 'remote_skill_metadata', server_default=None)
