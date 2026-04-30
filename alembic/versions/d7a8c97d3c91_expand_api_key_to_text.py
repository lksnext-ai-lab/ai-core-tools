"""expand_api_key_to_text

Revision ID: d7a8c97d3c91
Revises: multimodal001
Create Date: 2026-03-09 11:02:12.972043

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7a8c97d3c91'
down_revision = 'multimodal001'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'AIService', 'api_key',
        existing_type=sa.String(255),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        'embedding_service', 'api_key',
        existing_type=sa.String(255),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        'AIService', 'api_key',
        existing_type=sa.Text(),
        type_=sa.String(255),
        existing_nullable=True,
    )
    op.alter_column(
        'embedding_service', 'api_key',
        existing_type=sa.Text(),
        type_=sa.String(255),
        existing_nullable=True,
    )
