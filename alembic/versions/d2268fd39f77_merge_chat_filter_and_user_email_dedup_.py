"""Merge chat-filter and user-email-dedup migration branches

Revision ID: d2268fd39f77
Revises: chatfilt001, useremail001
Create Date: 2026-07-27 10:15:39.112865

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2268fd39f77'
down_revision = ('chatfilt001', 'useremail001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
