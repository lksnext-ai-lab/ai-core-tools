"""add_marketplace_ratings_and_conv_count

Revision ID: a1b2c3d4e5f6
Revises: 9febd6c0d636
Create Date: 2026-03-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '9febd6c0d636'
branch_labels = None
depends_on = None


def upgrade():
    # --- 1. Add denormalized stats columns to AgentMarketplaceProfile ---
    op.add_column(
        'AgentMarketplaceProfile',
        sa.Column('conversation_count', sa.Integer(), nullable=False, server_default='0')
    )
    op.add_column(
        'AgentMarketplaceProfile',
        sa.Column('rating_avg', sa.Float(), nullable=True)
    )
    op.add_column(
        'AgentMarketplaceProfile',
        sa.Column('rating_count', sa.Integer(), nullable=False, server_default='0')
    )

    # --- 2. Create AgentMarketplaceRating table ---
    op.create_table(
        'AgentMarketplaceRating',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['profile_id'], ['AgentMarketplaceProfile.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['User.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('profile_id', 'user_id', name='uq_marketplace_rating_profile_user')
    )


def downgrade():
    op.drop_table('AgentMarketplaceRating')
    op.drop_column('AgentMarketplaceProfile', 'rating_count')
    op.drop_column('AgentMarketplaceProfile', 'rating_avg')
    op.drop_column('AgentMarketplaceProfile', 'conversation_count')
