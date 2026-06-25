"""Rename Media.file_path to Media.storage_key with path prefix stripping.

Revision ID: storage001
Revises: ragcfg001
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'storage001'
down_revision = 'ragcfg001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add new nullable column
    op.add_column('Media', sa.Column('storage_key', sa.String(500), nullable=True))

    # 2. Backfill: strip absolute path prefix, keeping only the relative key
    op.execute("""
        UPDATE "Media"
        SET storage_key =
          CASE
            WHEN file_path LIKE '%repositories/%'
              THEN SUBSTRING(file_path FROM POSITION('repositories/' IN file_path))
            ELSE file_path
          END
        WHERE file_path IS NOT NULL
    """)

    # 3. Drop the old column
    op.drop_column('Media', 'file_path')


def downgrade() -> None:
    # 1. Re-add the old column
    op.add_column('Media', sa.Column('file_path', sa.String(500), nullable=True))

    # 2. Copy storage_key back to file_path
    op.execute("""
        UPDATE "Media" SET file_path = storage_key WHERE storage_key IS NOT NULL
    """)

    # 3. Drop the new column
    op.drop_column('Media', 'storage_key')
