"""add excluded_count to crawl_job

Revision ID: d3adbeef1234
Revises: 
Create Date: 2026-06-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd3adbeef1234'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('crawl_job', sa.Column('excluded_count', sa.Integer(), nullable=False, server_default='0'))
    # remove server_default to match model defaults (optional)
    op.alter_column('crawl_job', 'excluded_count', server_default=None)


def downgrade() -> None:
    op.drop_column('crawl_job', 'excluded_count')
