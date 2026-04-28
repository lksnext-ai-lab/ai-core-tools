"""Domain crawling policies: add domain_url, crawl_policy, crawl_job tables; drop legacy Url table.

WARNING: This migration is NOT fully restorative. The upgrade() step drops the legacy Url table
(data loss is accepted per product decision). The downgrade() step recreates an empty Url table
but all crawled data (domain_url, crawl_policy, crawl_job rows) is permanently lost.

Revision ID: crawlpol001
Revises: crawlpol_merge_heads
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'crawlpol001'
down_revision = 'crawlpol_merge_heads'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create PostgreSQL enum types (create_type=True so .create() issues CREATE TYPE)
    domain_url_status = postgresql.ENUM(
        'PENDING', 'CRAWLING', 'INDEXED', 'SKIPPED', 'FAILED', 'REMOVED', 'EXCLUDED',
        name='domain_url_status',
        create_type=True,
    )
    domain_url_status.create(op.get_bind(), checkfirst=True)

    discovery_source = postgresql.ENUM(
        'SITEMAP', 'CRAWL', 'MANUAL',
        name='discovery_source',
        create_type=True,
    )
    discovery_source.create(op.get_bind(), checkfirst=True)

    crawl_job_status = postgresql.ENUM(
        'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED',
        name='crawl_job_status',
        create_type=True,
    )
    crawl_job_status.create(op.get_bind(), checkfirst=True)

    crawl_trigger = postgresql.ENUM(
        'MANUAL', 'SCHEDULED',
        name='crawl_trigger',
        create_type=True,
    )
    crawl_trigger.create(op.get_bind(), checkfirst=True)

    # 2. Drop legacy Url table (data loss accepted)
    op.drop_table('Url')

    # 3. Create domain_url table
    op.create_table(
        'domain_url',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('domain_id', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(length=2048), nullable=False),
        sa.Column('normalized_url', sa.String(length=2048), nullable=False),
        sa.Column(
            'status',
            postgresql.ENUM('PENDING', 'CRAWLING', 'INDEXED', 'SKIPPED', 'FAILED', 'REMOVED', 'EXCLUDED',
                             name='domain_url_status', create_type=False),
            nullable=False,
            server_default='PENDING',
        ),
        sa.Column(
            'discovered_via',
            postgresql.ENUM('SITEMAP', 'CRAWL', 'MANUAL', name='discovery_source', create_type=False),
            nullable=False,
        ),
        sa.Column('depth', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('http_etag', sa.String(length=255), nullable=True),
        sa.Column('http_last_modified', sa.String(length=64), nullable=True),
        sa.Column('sitemap_lastmod', sa.DateTime(), nullable=True),
        sa.Column('last_crawled_at', sa.DateTime(), nullable=True),
        sa.Column('last_indexed_at', sa.DateTime(), nullable=True),
        sa.Column('next_crawl_at', sa.DateTime(), nullable=True),
        sa.Column('consecutive_skips', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['domain_id'], ['Domain.domain_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('domain_id', 'normalized_url', name='uq_domain_url_normalized'),
    )
    op.create_index('ix_domain_url_domain_id', 'domain_url', ['domain_id'])
    op.create_index('ix_domain_url_domain_status', 'domain_url', ['domain_id', 'status'])
    op.create_index('ix_domain_url_domain_next_crawl', 'domain_url', ['domain_id', 'next_crawl_at'])

    # 4. Create crawl_policy table
    op.create_table(
        'crawl_policy',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('domain_id', sa.Integer(), nullable=False),
        sa.Column('seed_url', sa.String(length=2048), nullable=True),
        sa.Column('sitemap_url', sa.String(length=2048), nullable=True),
        sa.Column('manual_urls', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('max_depth', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('include_globs', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('exclude_globs', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('rate_limit_rps', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('refresh_interval_hours', sa.Integer(), nullable=False, server_default='168'),
        sa.Column('respect_robots_txt', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['domain_id'], ['Domain.domain_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('domain_id', name='uq_crawl_policy_domain'),
    )

    # 5. Create crawl_job table
    op.create_table(
        'crawl_job',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('domain_id', sa.Integer(), nullable=False),
        sa.Column(
            'status',
            postgresql.ENUM('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED',
                             name='crawl_job_status', create_type=False),
            nullable=False,
            server_default='QUEUED',
        ),
        sa.Column(
            'triggered_by',
            postgresql.ENUM('MANUAL', 'SCHEDULED', name='crawl_trigger', create_type=False),
            nullable=False,
        ),
        sa.Column('triggered_by_user_id', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('discovered_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('indexed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('skipped_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('removed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_log', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('NOW()')),
        sa.Column('worker_id', sa.String(length=64), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['domain_id'], ['Domain.domain_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['triggered_by_user_id'], ['User.user_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_crawl_job_domain_id', 'crawl_job', ['domain_id'])
    op.create_index('ix_crawl_job_created_at', 'crawl_job', ['created_at'])
    op.create_index('ix_crawl_job_status_created', 'crawl_job', ['status', 'created_at'])

    # 6. Backfill: create one crawl_policy per existing Domain (inactive by default)
    op.execute(
        """
        INSERT INTO crawl_policy (domain_id, seed_url, manual_urls, include_globs, exclude_globs, is_active, created_at, updated_at)
        SELECT domain_id, base_url, '[]', '[]', '[]', false, NOW(), NOW()
        FROM "Domain"
        """
    )


def downgrade():
    # 1. Drop new tables
    op.drop_index('ix_crawl_job_status_created', table_name='crawl_job')
    op.drop_index('ix_crawl_job_created_at', table_name='crawl_job')
    op.drop_index('ix_crawl_job_domain_id', table_name='crawl_job')
    op.drop_table('crawl_job')

    op.drop_table('crawl_policy')

    op.drop_index('ix_domain_url_domain_next_crawl', table_name='domain_url')
    op.drop_index('ix_domain_url_domain_status', table_name='domain_url')
    op.drop_index('ix_domain_url_domain_id', table_name='domain_url')
    op.drop_table('domain_url')

    # 2. Drop the four enums
    postgresql.ENUM(name='crawl_trigger', create_type=False).drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='crawl_job_status', create_type=False).drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='discovery_source', create_type=False).drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='domain_url_status', create_type=False).drop(op.get_bind(), checkfirst=True)

    # 3. Recreate empty Url table (non-restorative — all crawled data is lost)
    op.create_table(
        'Url',
        sa.Column('url_id', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(length=255), nullable=True),
        sa.Column('domain_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(['domain_id'], ['Domain.domain_id'], ),
        sa.PrimaryKeyConstraint('url_id'),
    )
