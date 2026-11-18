"""add unique constraint on middleware name per app

Revision ID: mw004
Revises: 02ce79e497e6
Create Date: 2026-07-28 10:15:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'mw004'
down_revision = '02ce79e497e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint('uq_middleware_app_name', 'Middleware', ['app_id', 'name'])


def downgrade():
    op.drop_constraint('uq_middleware_app_name', 'Middleware', type_='unique')
