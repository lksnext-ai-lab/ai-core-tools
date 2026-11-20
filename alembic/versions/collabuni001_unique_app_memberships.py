"""prevent duplicate app memberships while preserving ownership offers

Revision ID: collabuni001
Revises: chatfiltmerge003
Create Date: 2026-07-29
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = 'collabuni001'
down_revision = 'chatfiltmerge003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM "AppCollaborator"
            WHERE role <> 'OWNER'
            GROUP BY app_id, user_id
            HAVING COUNT(*) > 1
        ) THEN
            RAISE EXCEPTION 'Duplicate regular app memberships exist; resolve them before applying collabuni001';
        END IF;
        IF EXISTS (
            SELECT 1
            FROM "AppCollaborator"
            WHERE role = 'OWNER' AND status = 'PENDING'
            GROUP BY app_id, user_id
            HAVING COUNT(*) > 1
        ) THEN
            RAISE EXCEPTION 'Duplicate pending ownership offers exist; resolve them before applying collabuni001';
        END IF;
    END $$;
    """)
    op.create_index(
        'uq_app_collaborator_app_user_membership',
        'AppCollaborator',
        ['app_id', 'user_id'],
        unique=True,
        postgresql_where=sa.text("role <> 'OWNER'"),
    )
    op.create_index(
        'uq_app_collaborator_app_user_pending_owner_offer',
        'AppCollaborator',
        ['app_id', 'user_id'],
        unique=True,
        postgresql_where=sa.text("role = 'OWNER' AND status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_app_collaborator_app_user_pending_owner_offer',
        table_name='AppCollaborator',
    )
    op.drop_index(
        'uq_app_collaborator_app_user_membership',
        table_name='AppCollaborator',
    )
