"""add_administrator_role_to_collaboration

Revision ID: 3328c4012e93
Revises: 4b456a21f90b
Create Date: 2025-10-23 16:48:25.646779

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3328c4012e93'
down_revision = '4b456a21f90b'
branch_labels = None
depends_on = None


def upgrade():
    # Add 'ADMINISTRATOR' value to the collaborationrole enum
    op.execute("ALTER TYPE collaborationrole ADD VALUE IF NOT EXISTS 'ADMINISTRATOR'")


def downgrade():
    # Note: PostgreSQL does not support removing enum values directly
    # If you need to rollback, you would need to recreate the enum type
    # For now, we'll leave this as a no-op since removing enum values is complex
    pass
