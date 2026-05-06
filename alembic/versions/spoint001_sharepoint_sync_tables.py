"""Add sharepoint_source and sharepoint_file tables.

Revision ID: spoint001
Revises: crawlpol001
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'spoint001'
down_revision = 'crawlpol001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create PostgreSQL enum types
    sharepoint_sync_status = postgresql.ENUM(
        'IDLE', 'RUNNING', 'SUCCESS', 'PARTIAL', 'ERROR',
        name='sharepoint_sync_status',
        create_type=True,
    )
    sharepoint_sync_status.create(op.get_bind(), checkfirst=True)

    sharepoint_file_status = postgresql.ENUM(
        'PENDING', 'INDEXED', 'ERROR',
        name='sharepoint_file_status',
        create_type=True,
    )
    sharepoint_file_status.create(op.get_bind(), checkfirst=True)

    # 2. Create sharepoint_source table
    op.create_table(
        'sharepoint_source',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('app_id', sa.Integer(), nullable=False),
        sa.Column('silo_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tenant_id', sa.String(length=255), nullable=False),
        sa.Column('client_id', sa.String(length=255), nullable=False),
        sa.Column('client_secret', sa.Text(), nullable=False),
        sa.Column('site_id', sa.String(length=255), nullable=False),
        sa.Column('site_name', sa.String(length=255), nullable=True),
        sa.Column('site_url', sa.Text(), nullable=True),
        sa.Column('drive_id', sa.String(length=255), nullable=False),
        sa.Column('drive_name', sa.String(length=255), nullable=True),
        sa.Column('file_extension_filters', sa.JSON(), nullable=True),
        sa.Column('last_delta_token', sa.Text(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column(
            'last_sync_status',
            postgresql.ENUM(
                'IDLE', 'RUNNING', 'SUCCESS', 'PARTIAL', 'ERROR',
                name='sharepoint_sync_status',
                create_type=False,
            ),
            nullable=False,
            server_default='IDLE',
        ),
        sa.Column('last_sync_error', sa.Text(), nullable=True),
        sa.Column('refresh_interval_minutes', sa.Integer(), nullable=True),
        sa.Column('next_run_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['app_id'], ['App.app_id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['silo_id'], ['Silo.silo_id'],
        ),
    )

    # 3. Create sharepoint_file table
    op.create_table(
        'sharepoint_file',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('drive_item_id', sa.String(length=512), nullable=False),
        sa.Column('name', sa.String(length=512), nullable=True),
        sa.Column('path', sa.Text(), nullable=True),
        sa.Column('web_url', sa.Text(), nullable=True),
        sa.Column('mime_type', sa.String(length=255), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('last_modified_at', sa.DateTime(), nullable=True),
        sa.Column(
            'status',
            postgresql.ENUM(
                'PENDING', 'INDEXED', 'ERROR',
                name='sharepoint_file_status',
                create_type=False,
            ),
            nullable=False,
            server_default='PENDING',
        ),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('vector_doc_ids', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['source_id'], ['sharepoint_source.id'],
            ondelete='CASCADE',
        ),
        sa.UniqueConstraint('source_id', 'drive_item_id', name='uq_spfile_source_item'),
    )


def downgrade() -> None:
    op.drop_table('sharepoint_file')
    op.drop_table('sharepoint_source')

    postgresql.ENUM(
        'PENDING', 'INDEXED', 'ERROR',
        name='sharepoint_file_status',
    ).drop(op.get_bind(), checkfirst=True)

    postgresql.ENUM(
        'IDLE', 'RUNNING', 'SUCCESS', 'PARTIAL', 'ERROR',
        name='sharepoint_sync_status',
    ).drop(op.get_bind(), checkfirst=True)
