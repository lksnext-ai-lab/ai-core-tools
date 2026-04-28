"""Merge heads before domain crawling policies feature

NOTE: When this plan was written there were two unlinked heads (14b4c9c42164 and multimodal001).
The multimodal head was subsequently linearized onto develop in commit 7c4b0b4, so at the time
this migration was created there is already only one head (14b4c9c42164).
This file is kept as a named waypoint (crawlpol_merge_heads) so that the feature migration
crawlpol001 can reference it by a stable symbolic ID.

Revision ID: crawlpol_merge_heads
Revises: 14b4c9c42164
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'crawlpol_merge_heads'
down_revision = '14b4c9c42164'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
