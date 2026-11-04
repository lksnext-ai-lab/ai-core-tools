"""Add last used date to agents.

Revision ID: agentlast001
Revises: siloparser001
Create Date: 2026-10-27
"""

from alembic import op
import sqlalchemy as sa


revision = "agentlast001"
down_revision = "siloparser001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("Agent", sa.Column("last_used_date", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("Agent", "last_used_date")
