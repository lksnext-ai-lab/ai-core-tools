"""How "no credentials" is physically stored in ``output_destination.credentials``.

The column is ``JSON, nullable=True`` without ``none_as_null=True``. This file
records what PostgreSQL really holds for: explicit ``None``, ``{}`` and an
omitted attribute. The result decides how AC-20 is verified in step_011.
"""

import pytest
from models.output_delivery import OutputDestination
from sqlalchemy import Text, cast, func, select

pytestmark = pytest.mark.integration


def _destination(app_id, name, **extra) -> OutputDestination:
    return OutputDestination(app_id=app_id, name=name, provider_key="webhook", webhook_url="https://hooks.example.com/c", **extra)


def _is_sql_null(db, destination_id) -> bool:
    return db.execute(
        select(OutputDestination.id).where(OutputDestination.id == destination_id, OutputDestination.credentials.is_(None))
    ).first() is not None


def _json_typeof(db, destination_id):
    """Physical JSON type via the catalog functions (None = SQL NULL)."""
    return db.execute(
        select(func.json_typeof(OutputDestination.credentials)).where(OutputDestination.id == destination_id)
    ).scalar_one()


class TestCredentialsRepresentation:
    def test_explicit_none(self, db, fake_app):
        dest = _destination(fake_app.app_id, "explicit-none")
        dest.credentials = None
        db.add(dest)
        db.flush()
        db.expire_all()
        assert db.get(OutputDestination, dest.id).credentials is None
        # Real behavior (SQLAlchemy 2.x, JSON without none_as_null): an explicit
        # None is stored as JSON 'null', which is NOT SQL NULL.
        assert _json_typeof(db, dest.id) == "null"
        assert _is_sql_null(db, dest.id) is False

    def test_empty_dict(self, db, fake_app):
        dest = _destination(fake_app.app_id, "empty-dict")
        dest.credentials = {}
        db.add(dest)
        db.flush()
        db.expire_all()
        assert db.get(OutputDestination, dest.id).credentials == {}
        assert _json_typeof(db, dest.id) == "object"
        assert _is_sql_null(db, dest.id) is False

    def test_omitted(self, db, fake_app):
        dest = _destination(fake_app.app_id, "omitted")
        db.add(dest)
        db.flush()
        db.expire_all()
        assert db.get(OutputDestination, dest.id).credentials is None
        # Omitted attribute: no value is bound, the column is SQL NULL.
        assert _json_typeof(db, dest.id) is None
        assert _is_sql_null(db, dest.id) is True

    def test_raw_values_for_the_three_cases(self, db, fake_app):
        """Same facts via the textual JSON cast, to make the physical form explicit."""
        explicit = _destination(fake_app.app_id, "raw-none")
        explicit.credentials = None
        empty = _destination(fake_app.app_id, "raw-empty")
        empty.credentials = {}
        omitted = _destination(fake_app.app_id, "raw-omitted")
        db.add_all([explicit, empty, omitted])
        db.flush()
        rows = dict(db.execute(
            select(OutputDestination.id, cast(OutputDestination.credentials, Text))
            .where(OutputDestination.id.in_([explicit.id, empty.id, omitted.id]))
        ).all())
        assert rows[explicit.id] == "null"
        assert rows[empty.id] == "{}"
        assert rows[omitted.id] is None
