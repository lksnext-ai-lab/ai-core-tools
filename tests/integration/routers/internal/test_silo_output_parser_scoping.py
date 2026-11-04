"""Cross-app OutputParser IDOR on silos: attach/read/delete another app's parser."""

import pytest

from models.output_parser import OutputParser
from models.silo import Silo
from services.app_service import AppService
from tests.factories import AppFactory, SiloFactory, configure_factories


@pytest.fixture
def foreign_parser(db):
    configure_factories(db)
    other = AppFactory()
    parser = OutputParser(name="secret", description="d", fields=[{"name": "secret_field", "type": "str"}],
                          app_id=other.app_id)
    db.add(parser)
    db.flush()
    return parser


def test_create_silo_with_foreign_parser_rejected(client, db, fake_app, owner_headers, foreign_parser):
    r = client.post(f"/internal/apps/{fake_app.app_id}/silos",
                    json={"name": "evil", "output_parser_id": foreign_parser.parser_id}, headers=owner_headers)
    assert 400 <= r.status_code < 500, r.text
    assert "secret_field" not in r.text
    assert db.query(Silo).filter_by(app_id=fake_app.app_id, name="evil").count() == 0


def test_update_silo_with_foreign_parser_rejected(client, db, fake_app, owner_headers, foreign_parser):
    configure_factories(db)
    silo = SiloFactory(app=fake_app)
    r = client.put(f"/internal/apps/{fake_app.app_id}/silos/{silo.silo_id}",
                   json={"name": "n", "output_parser_id": foreign_parser.parser_id}, headers=owner_headers)
    assert 400 <= r.status_code < 500, r.text
    db.refresh(silo)
    assert silo.metadata_definition_id is None


def test_detail_hides_foreign_parser_fields(client, db, fake_app, owner_headers, foreign_parser):
    configure_factories(db)
    silo = SiloFactory(app=fake_app)
    silo.metadata_definition_id = foreign_parser.parser_id  # corrupted legacy row
    db.flush()
    r = client.get(f"/internal/apps/{fake_app.app_id}/silos/{silo.silo_id}", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert not r.json().get("metadata_fields")


def test_app_deletion_does_not_delete_foreign_parser(db, fake_app, foreign_parser):
    configure_factories(db)
    silo = SiloFactory(app=fake_app)
    silo.metadata_definition_id = foreign_parser.parser_id  # corrupted legacy row
    db.flush()
    pid = foreign_parser.parser_id
    AppService(db).delete_app(fake_app.app_id)
    db.expire_all()
    assert db.get(OutputParser, pid) is not None
