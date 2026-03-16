"""saas_mode: add subscription tiers, billing, local auth, freeze support

Revision ID: saas001
Revises: merge001
Create Date: 2026-03-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'saas001'
down_revision = 'merge001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── New enum types ─────────────────────────────────────────────────────────
    subscription_tier = postgresql.ENUM(
        'free', 'starter', 'pro',
        name='subscriptiontier',
        create_type=True
    )
    subscription_tier.create(op.get_bind(), checkfirst=True)

    billing_status = postgresql.ENUM(
        'active', 'trialing', 'past_due', 'cancelled', 'none',
        name='billingstatus',
        create_type=True
    )
    billing_status.create(op.get_bind(), checkfirst=True)

    # ── New tables ─────────────────────────────────────────────────────────────
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('User.user_id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('tier', sa.Enum('free', 'starter', 'pro', name='subscriptiontier', create_type=False), nullable=False, server_default='free'),
        sa.Column('stripe_customer_id', sa.String(255), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=True),
        sa.Column('billing_status', sa.Enum('active', 'trialing', 'past_due', 'cancelled', 'none', name='billingstatus', create_type=False), nullable=False, server_default='none'),
        sa.Column('trial_end', sa.DateTime(), nullable=True),
        sa.Column('admin_override_tier', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )

    op.create_table(
        'tier_configs',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tier', sa.String(50), nullable=False),
        sa.Column('resource_type', sa.String(100), nullable=False),
        sa.Column('limit_value', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('tier', 'resource_type', name='uq_tier_resource'),
    )

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

    op.create_table(
        'usage_records',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('User.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('billing_period_start', sa.Date(), nullable=False),
        sa.Column('call_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('user_id', 'billing_period_start', name='uq_usage_user_period'),
    )

    op.create_table(
        'user_credentials',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('User.user_id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('verification_token', sa.String(512), nullable=True),
        sa.Column('verification_token_expiry', sa.DateTime(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('reset_token', sa.String(512), nullable=True),
        sa.Column('reset_token_expiry', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )

    # ── New columns on existing tables ─────────────────────────────────────────
    op.add_column('App', sa.Column('is_frozen', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('Agent', sa.Column('is_frozen', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('Silo', sa.Column('is_frozen', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('Skill', sa.Column('is_frozen', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('MCPServer', sa.Column('is_frozen', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('AppCollaborator', sa.Column('is_frozen', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('User', sa.Column('auth_method', sa.String(50), nullable=True, server_default='oidc'))
    op.add_column('User', sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    # ── Remove columns from existing tables ────────────────────────────────────
    op.drop_column('User', 'email_verified')
    op.drop_column('User', 'auth_method')
    op.drop_column('AppCollaborator', 'is_frozen')
    op.drop_column('MCPServer', 'is_frozen')
    op.drop_column('Skill', 'is_frozen')
    op.drop_column('Silo', 'is_frozen')
    op.drop_column('Agent', 'is_frozen')
    op.drop_column('App', 'is_frozen')

    # ── Drop new tables ────────────────────────────────────────────────────────
    op.drop_table('user_credentials')
    op.drop_table('usage_records')
    op.drop_table('system_ai_services')
    op.drop_table('tier_configs')
    op.drop_table('subscriptions')

    # ── Drop enum types ────────────────────────────────────────────────────────
    billing_status = postgresql.ENUM(name='billingstatus', create_type=False)
    billing_status.drop(op.get_bind(), checkfirst=True)

    subscription_tier = postgresql.ENUM(name='subscriptiontier', create_type=False)
    subscription_tier.drop(op.get_bind(), checkfirst=True)
