"""Convert audit/attribution FKs to ON DELETE SET NULL for safe user deletion.

Part of the user-deletion-and-app-transfer work. Three foreign keys that point
at ``User.user_id`` purely for attribution must NOT block deleting the user nor
force the ORM into a ``SET user_id = NULL`` it is not allowed to emit. They are
converted to ``ON DELETE SET NULL`` so the rows survive (anonymised) and the
delete proceeds:

- ``AppCollaborator.invited_by``      (also made nullable — required for SET NULL)
- ``Conversation.user_id``            (already nullable)
- ``crawl_job.triggered_by_user_id``  (already nullable)

The Class-A child tables (user_credentials, refresh_tokens, subscriptions,
usage_records, MarketplaceUsage, AgentMarketplaceRating) already carry
``ON DELETE CASCADE`` and are untouched here.

Revision ID: userdel001
Revises: localauth001
Create Date: 2026-06-05
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'userdel001'
down_revision = 'localauth001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('AppCollaborator', 'invited_by', nullable=True)
    op.drop_constraint('AppCollaborator_invited_by_fkey', 'AppCollaborator', type_='foreignkey')
    op.drop_constraint('Conversation_user_id_fkey', 'Conversation', type_='foreignkey')
    op.drop_constraint('crawl_job_triggered_by_user_id_fkey', 'crawl_job', type_='foreignkey')
    op.create_foreign_key(
        'fk_appcollaborator_invited_by_user',
        'AppCollaborator', 'User',
        ['invited_by'], ['user_id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_conversation_user_id_user',
        'Conversation', 'User',
        ['user_id'], ['user_id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_crawl_job_triggered_by_user_id_user',
        'crawl_job', 'User',
        ['triggered_by_user_id'], ['user_id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_appcollaborator_invited_by_user', 'AppCollaborator', type_='foreignkey')
    op.drop_constraint('fk_conversation_user_id_user', 'Conversation', type_='foreignkey')
    op.drop_constraint('fk_crawl_job_triggered_by_user_id_user', 'crawl_job', type_='foreignkey')
    op.create_foreign_key(
        'AppCollaborator_invited_by_fkey',
        'AppCollaborator', 'User',
        ['invited_by'], ['user_id'],
    )
    op.create_foreign_key(
        'Conversation_user_id_fkey',
        'Conversation', 'User',
        ['user_id'], ['user_id'],
    )
    op.create_foreign_key(
        'crawl_job_triggered_by_user_id_fkey',
        'crawl_job', 'User',
        ['triggered_by_user_id'], ['user_id'],
    )

    # NOTE: fails if any invited_by is NULL (nulled by SET NULL on user delete); backfill before downgrading.
    op.alter_column('AppCollaborator', 'invited_by', nullable=False)
