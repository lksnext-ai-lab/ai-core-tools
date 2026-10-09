"""SystemOneAgent.system_one_service_id: ON DELETE SET NULL (a deleted service leaves its agents inoperative).

sysone001 made it RESTRICT + NOT NULL, like a hard dependency. AIService works the other way (the agent keeps
existing without a service and fails when it runs), so System One follows it.
"""

from alembic import op

revision = "sysone002"
down_revision = "sysone001"
branch_labels = None
depends_on = None

TABLE = "SystemOneAgent"
COLUMN = "system_one_service_id"
FK = "SystemOneAgent_system_one_service_id_fkey"


def _replace_fk(ondelete: str) -> None:
    op.drop_constraint(FK, TABLE, type_="foreignkey")
    op.create_foreign_key(FK, TABLE, "SystemOneService", [COLUMN], ["service_id"], ondelete=ondelete)


def upgrade():
    op.alter_column(TABLE, COLUMN, nullable=True)
    _replace_fk("SET NULL")


def downgrade():
    # NOT NULL cannot hold agents that lost their service: they are inoperative anyway, so they go (with the
    # rows that point at them), like sysone001's downgrade does for every System One agent.
    orphans = f'SELECT agent_id FROM "{TABLE}" WHERE {COLUMN} IS NULL'
    op.execute(f"DELETE FROM agent_tools WHERE agent_id IN ({orphans}) OR tool_id IN ({orphans})")
    op.execute(f"DELETE FROM agent_mcps WHERE agent_id IN ({orphans})")
    op.execute(f"DELETE FROM agent_skills WHERE agent_id IN ({orphans})")
    op.execute(
        f'WITH gone AS (DELETE FROM "{TABLE}" WHERE {COLUMN} IS NULL RETURNING agent_id) '
        'DELETE FROM "Agent" WHERE agent_id IN (SELECT agent_id FROM gone)'
    )
    _replace_fk("RESTRICT")
    op.alter_column(TABLE, COLUMN, nullable=False)
