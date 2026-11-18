"""Harden the middleware schema.

- Align column types/nullability with the ORM model (name VARCHAR(100),
  description VARCHAR(1000), middleware_type VARCHAR(32), is_frozen NOT NULL).
- Drop the redundant index on the Middleware primary key.
- Index agent_middlewares.middleware_id (deletes / reverse lookups).
- Drop middleware_mcps: it was only read by the UI and never at execution time.
- Remove middlewares of the retired types: CUSTOM (never implemented) and
  MONITORING (duplicated the core agent metrics). Their agent associations go
  with them through the existing ON DELETE CASCADE. This data is not restored
  on downgrade.

Revision ID: mw005
Revises: bfe85f7f6ded
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = 'mw005'
down_revision = 'bfe85f7f6ded'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""DELETE FROM "Middleware" WHERE middleware_type IN ('CUSTOM', 'MONITORING')""")
    op.execute("""UPDATE "Middleware" SET is_frozen = false WHERE is_frozen IS NULL""")
    op.execute("""UPDATE "Middleware" SET name = left(name, 100), description = left(description, 1000)""")

    op.alter_column('Middleware', 'name', type_=sa.String(100), existing_nullable=False)
    op.alter_column('Middleware', 'description', type_=sa.String(1000), existing_nullable=True)
    op.alter_column('Middleware', 'middleware_type', type_=sa.String(32), existing_nullable=False)
    op.alter_column('Middleware', 'is_frozen', existing_type=sa.Boolean(), nullable=False,
                    server_default=sa.false())

    op.drop_index('ix_Middleware_middleware_id', table_name='Middleware')
    op.create_index('ix_agent_middlewares_middleware_id', 'agent_middlewares', ['middleware_id'])
    op.drop_table('middleware_mcps')


def downgrade() -> None:
    op.create_table(
        'middleware_mcps',
        sa.Column('middleware_id', sa.Integer(), nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['middleware_id'], ['Middleware.middleware_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['config_id'], ['MCPConfig.config_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('middleware_id', 'config_id'),
    )
    op.drop_index('ix_agent_middlewares_middleware_id', table_name='agent_middlewares')
    op.create_index('ix_Middleware_middleware_id', 'Middleware', ['middleware_id'], unique=False)

    op.alter_column('Middleware', 'is_frozen', existing_type=sa.Boolean(), nullable=True, server_default=None)
    op.alter_column('Middleware', 'middleware_type', type_=sa.String(), existing_nullable=False)
    op.alter_column('Middleware', 'description', type_=sa.String(), existing_nullable=True)
    op.alter_column('Middleware', 'name', type_=sa.String(), existing_nullable=False)
