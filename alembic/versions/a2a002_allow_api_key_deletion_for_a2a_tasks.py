"""allow api key deletion for a2a tasks

Revision ID: a2a002
Revises: a2a001
Create Date: 2026-04-09 18:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2a002'
down_revision = 'a2a001'
branch_labels = None
depends_on = None


def _drop_api_key_fk() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys('A2ATask'):
        constrained_columns = fk.get('constrained_columns') or []
        referred_table = fk.get('referred_table')
        if constrained_columns == ['api_key_id'] and referred_table == 'APIKey':
            op.drop_constraint(fk['name'], 'A2ATask', type_='foreignkey')
            return
    raise RuntimeError("Could not find A2ATask.api_key_id foreign key")


def upgrade() -> None:
    _drop_api_key_fk()
    op.create_foreign_key(
        'A2ATask_api_key_id_fkey',
        'A2ATask',
        'APIKey',
        ['api_key_id'],
        ['key_id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    _drop_api_key_fk()
    op.create_foreign_key(
        'A2ATask_api_key_id_fkey',
        'A2ATask',
        'APIKey',
        ['api_key_id'],
        ['key_id'],
    )
