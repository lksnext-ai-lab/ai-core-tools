"""Clear Silo.metadata_definition_id links that point at another app's output parser.

Before the tenant-scoping fix, a silo could be attached to an OutputParser of a different app
(or to a parser that no longer exists). Such links let one app read, and via silo deletion
delete, another app's parser. This data migration sets the link to NULL for those rows.
Downgrade is a no-op: cleared links are not restored.
"""

from alembic import op

revision = "siloparser001"
down_revision = "svceos001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE "Silo" AS s
        SET metadata_definition_id = NULL
        WHERE s.metadata_definition_id IS NOT NULL
          AND s.metadata_definition_id <> 0
          AND NOT EXISTS (
              SELECT 1 FROM "OutputParser" AS p
              WHERE p.parser_id = s.metadata_definition_id
                AND p.app_id IS NOT DISTINCT FROM s.app_id
          )
        """
    )


def downgrade():
    # Data fix: the cleared cross-app links are intentionally not restored.
    pass
