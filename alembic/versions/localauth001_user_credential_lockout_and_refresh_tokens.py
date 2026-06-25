"""Add lockout fields to user_credentials and create refresh_tokens table.

Revision ID: localauth001
Revises: ragcfg001
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'localauth001'
down_revision = 'ragcfg001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default='0' backfills existing rows without a separate UPDATE pass.
    op.add_column(
        'user_credentials',
        sa.Column('failed_attempts', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'user_credentials',
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('jti', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('family_id', sa.String(length=64), nullable=False),
        sa.Column('token_hash', sa.String(length=128), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rotated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column('ip', sa.String(length=45), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['user_id'], ['User.user_id'],
            ondelete='CASCADE',
        ),
    )

    op.create_index('ix_refresh_tokens_jti', 'refresh_tokens', ['jti'], unique=True)
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'], unique=False)
    op.create_index('ix_refresh_tokens_family_id', 'refresh_tokens', ['family_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_refresh_tokens_family_id', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_user_id', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_jti', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_column('user_credentials', 'locked_until')
    op.drop_column('user_credentials', 'failed_attempts')
