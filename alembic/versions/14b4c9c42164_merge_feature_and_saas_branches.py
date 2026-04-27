"""merge_feature_and_saas_branches

Revision ID: 14b4c9c42164
Revises: a3f1b9c2d4e7, 125b5f2e52be
Create Date: 2026-04-14 11:01:20.242974

Note: down_revision was originally ('a3f1b9c2d4e7', 'saas003'). It was
re-pointed to ('a3f1b9c2d4e7', '125b5f2e52be') so the multimodal head
chains linearly after the openai/saas merge instead of producing a third
merge migration. saas003 is preserved as an ancestor through 125b5f2e52be.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '14b4c9c42164'
down_revision = ('a3f1b9c2d4e7', '125b5f2e52be')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
