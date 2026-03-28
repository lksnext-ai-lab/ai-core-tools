"""system_ai_services_refactor: make AIService.app_id nullable, drop system_ai_services table

Revision ID: saas002
Revises: saas001
Create Date: 2026-03-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'saas002'
down_revision = 'saas001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make app_id nullable in AIService — NULL means platform-level (system) service
    op.alter_column(
        'AIService',
        'app_id',
        existing_type=sa.Integer(),
        nullable=True,
    )

    # Drop the now-redundant system_ai_services table
    op.drop_table('system_ai_services')


def downgrade() -> None:
    # Recreate system_ai_services table
    op.create_table(
        'system_ai_services',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('provider', sa.String(100), nullable=False),
        sa.Column('model', sa.String(255), nullable=False),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )

    # Restore NOT NULL on app_id (will fail if NULL rows exist — acceptable per plan)
    op.alter_column(
        'AIService',
        'app_id',
        existing_type=sa.Integer(),
        nullable=False,
    )
