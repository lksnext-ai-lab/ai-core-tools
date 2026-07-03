"""add extra_config to AIService and embedding_service

Adds a nullable JSON-as-text column ``extra_config`` to both service
tables. Providers whose access requires more than a single api_key
(e.g. AWS Bedrock, which needs an access key id + region alongside the
secret) store the extra parameters here.

Revision ID: bedrock001
Revises: merge001_userdel_platform_role
Create Date: 2026-06-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bedrock001'
down_revision = 'd3adbeef1234'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('AIService', sa.Column('extra_config', sa.Text(), nullable=True))
    op.add_column('embedding_service', sa.Column('extra_config', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('embedding_service', 'extra_config')
    op.drop_column('AIService', 'extra_config')
