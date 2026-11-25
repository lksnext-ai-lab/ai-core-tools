"""Per-silo indexing settings.

"Silo" gets ``chunk_size``, ``chunk_overlap``, ``pdf_loader`` and ``pdf_loader_options``.
Existing silos keep the chunking they had (1000/200) and the fast ``pymupdf`` loader, so
their behaviour does not change until someone edits them; new silos default to 2000/400.

Downgrade drops the columns: silos lose their indexing settings (indexing goes back to the
code defaults of the previous version). Already indexed chunks are not touched either way.

Revision ID: siloidx001
Revises: appimage001
"""

import sqlalchemy as sa

from alembic import op

revision = "siloidx001"
down_revision = "appimage001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("Silo", sa.Column("chunk_size", sa.Integer(), nullable=True))
    op.add_column("Silo", sa.Column("chunk_overlap", sa.Integer(), nullable=True))
    op.execute('UPDATE "Silo" SET chunk_size = 1000, chunk_overlap = 200')
    op.alter_column("Silo", "chunk_size", nullable=False, server_default="2000")
    op.alter_column("Silo", "chunk_overlap", nullable=False, server_default="400")
    op.add_column(
        "Silo",
        sa.Column("pdf_loader", sa.String(length=45), nullable=False, server_default="pymupdf"),
    )
    op.add_column("Silo", sa.Column("pdf_loader_options", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("Silo", "pdf_loader_options")
    op.drop_column("Silo", "pdf_loader")
    op.drop_column("Silo", "chunk_overlap")
    op.drop_column("Silo", "chunk_size")
