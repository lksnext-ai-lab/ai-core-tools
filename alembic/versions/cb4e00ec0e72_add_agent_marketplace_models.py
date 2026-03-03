"""add_agent_marketplace_models

Revision ID: cb4e00ec0e72
Revises: 3e9d370bd29b
Create Date: 2026-02-22 18:16:51.855697

Changes:
- Create AgentMarketplaceProfile table (1:1 with Agent)
- Add marketplace_visibility enum + column to Agent
- Add conversationsource enum + source column to Conversation
- Add USER value to collaborationrole enum (AppCollaborator)
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'cb4e00ec0e72'
down_revision = '3e9d370bd29b'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create the marketplacevisibility enum type
    marketplacevisibility = sa.Enum('UNPUBLISHED', 'PRIVATE', 'PUBLIC', name='marketplacevisibility')
    marketplacevisibility.create(op.get_bind(), checkfirst=True)

    # 2. Add marketplace_visibility column to Agent
    op.add_column('Agent', sa.Column(
        'marketplace_visibility',
        sa.Enum('UNPUBLISHED', 'PRIVATE', 'PUBLIC', name='marketplacevisibility'),
        nullable=False,
        server_default='UNPUBLISHED'
    ))

    # 3. Create AgentMarketplaceProfile table
    op.create_table('AgentMarketplaceProfile',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('short_description', sa.String(length=200), nullable=True),
        sa.Column('long_description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('icon_url', sa.String(length=500), nullable=True),
        sa.Column('cover_image_url', sa.String(length=500), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['Agent.agent_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agent_id')
    )

    # 4. Create the conversationsource enum type and add source column to Conversation
    conversationsource = sa.Enum('PLAYGROUND', 'MARKETPLACE', 'API', name='conversationsource')
    conversationsource.create(op.get_bind(), checkfirst=True)

    op.add_column('Conversation', sa.Column(
        'source',
        sa.Enum('PLAYGROUND', 'MARKETPLACE', 'API', name='conversationsource'),
        nullable=False,
        server_default='PLAYGROUND'
    ))

    # 5. Add USER value to the collaborationrole enum
    op.execute("ALTER TYPE collaborationrole ADD VALUE IF NOT EXISTS 'USER'")


def downgrade():
    # 5. Remove USER from collaborationrole enum
    #    PostgreSQL does not support removing enum values directly.
    #    We recreate the enum without 'USER' and update the column.
    op.execute("DELETE FROM \"AppCollaborator\" WHERE role = 'USER'")
    op.execute("ALTER TABLE \"AppCollaborator\" ALTER COLUMN role TYPE VARCHAR USING role::text")
    op.execute("DROP TYPE IF EXISTS collaborationrole")
    op.execute("CREATE TYPE collaborationrole AS ENUM ('OWNER', 'ADMINISTRATOR', 'EDITOR', 'VIEWER')")
    op.execute("ALTER TABLE \"AppCollaborator\" ALTER COLUMN role TYPE collaborationrole USING role::collaborationrole")

    # 4. Drop source column and conversationsource enum
    op.drop_column('Conversation', 'source')
    op.execute("DROP TYPE IF EXISTS conversationsource")

    # 3. Drop AgentMarketplaceProfile table
    op.drop_table('AgentMarketplaceProfile')

    # 2. Drop marketplace_visibility column and enum
    op.drop_column('Agent', 'marketplace_visibility')
    op.execute("DROP TYPE IF EXISTS marketplacevisibility")
