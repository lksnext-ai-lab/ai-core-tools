"""Move notification content mode from task bindings to output channels.

Channels with different modes in existing bindings are split into variants so
that tasks and queued deliveries keep their previous notification behavior.
"""

from alembic import op
import sqlalchemy as sa


revision = "periodic008"
down_revision = "periodic007"
branch_labels = None
depends_on = None

MODE_LABELS = {"result": "Resultado", "excerpt": "Extracto", "link_only": "Sólo enlace"}


def _variant_name(name, mode, existing):
    counter = 1
    while True:
        suffix = f" ({MODE_LABELS[mode]}{f' {counter}' if counter > 1 else ''})"
        candidate = name[:255 - len(suffix)] + suffix
        if candidate not in existing:
            existing.add(candidate)
            return candidate
        counter += 1


def upgrade():
    op.add_column("output_destination", sa.Column("content_mode", sa.String(length=30), nullable=False, server_default="result"))
    connection = op.get_bind()
    metadata = sa.MetaData()
    destinations = sa.Table("output_destination", metadata, autoload_with=connection)
    bindings = sa.Table("scheduled_task_output_binding", metadata, autoload_with=connection)
    deliveries = sa.Table("output_delivery", metadata, autoload_with=connection)
    originals = connection.execute(sa.select(destinations).order_by(destinations.c.id)).mappings().all()
    names_by_app = {}
    for destination in originals:
        names_by_app.setdefault(destination["app_id"], set()).add(destination["name"])

    for destination in originals:
        modes = set(connection.execute(sa.select(bindings.c.content_mode).where(
            bindings.c.destination_id == destination["id"],
        )).scalars())
        if not modes:
            continue
        # Prefer keeping the original channel for its result-mode bindings.
        ordered_modes = [mode for mode in MODE_LABELS if mode in modes]
        connection.execute(destinations.update().where(destinations.c.id == destination["id"]).values(content_mode=ordered_modes[0]))
        for mode in ordered_modes[1:]:
            variant = dict(destination)
            variant.pop("id")
            variant["name"] = _variant_name(destination["name"], mode, names_by_app[destination["app_id"]])
            variant["content_mode"] = mode
            variant_id = connection.execute(destinations.insert().values(**variant)).inserted_primary_key[0]
            binding_ids = list(connection.execute(sa.select(bindings.c.id).where(
                bindings.c.destination_id == destination["id"], bindings.c.content_mode == mode,
            )).scalars())
            connection.execute(bindings.update().where(bindings.c.id.in_(binding_ids)).values(destination_id=variant_id))
            # Keep the prepared payload/snapshot immutable; use the equivalent
            # channel (same endpoint/credentials) for its future send/retries.
            connection.execute(deliveries.update().where(
                deliveries.c.binding_id.in_(binding_ids), deliveries.c.destination_id == destination["id"],
            ).values(destination_id=variant_id))
    op.drop_column("scheduled_task_output_binding", "content_mode")


def downgrade():
    op.add_column("scheduled_task_output_binding", sa.Column("content_mode", sa.String(length=30), nullable=False, server_default="result"))
    connection = op.get_bind()
    metadata = sa.MetaData()
    destinations = sa.Table("output_destination", metadata, autoload_with=connection)
    bindings = sa.Table("scheduled_task_output_binding", metadata, autoload_with=connection)
    mode = sa.select(destinations.c.content_mode).where(destinations.c.id == bindings.c.destination_id).scalar_subquery()
    connection.execute(bindings.update().values(content_mode=mode))
    # Retain variants rather than merging channels that may have been edited.
    op.drop_column("output_destination", "content_mode")
