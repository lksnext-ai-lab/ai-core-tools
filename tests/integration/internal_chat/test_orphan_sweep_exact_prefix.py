"""The orphan temp-repository sweep compares names EXACTLY (``_`` is a LIKE wildcard): agent 3 must not match agent 37."""
from datetime import datetime, timedelta

from models.repository import PLAYGROUND_MEDIA_REPO_TYPE, Repository
from repositories.internal_chat_repository import InternalChatAgentRepository
from tests.factories import AppFactory, SiloFactory, UserFactory, configure_factories


def _repo(db, app, silo, name):
    repo = Repository(name=name, app_id=app.app_id, silo_id=silo.silo_id, type=PLAYGROUND_MEDIA_REPO_TYPE,
                      create_date=datetime.now() - timedelta(days=3))
    db.add(repo)
    db.flush()
    return repo.repository_id


def test_the_sweep_never_matches_another_agents_temp_repository(db):
    configure_factories(db)
    app = AppFactory(owner=UserFactory())
    silo = SiloFactory(app=app)
    db.flush()
    internal = InternalChatAgentRepository.get_or_create(db, app.app_id, "p")
    own_orphan = _repo(db, app, silo, f"_playground_{internal}_conv_{internal}_gone")  # really an orphan
    # another agent of the same App whose id starts with the internal agent's id (e.g. 3 -> 37): live temp repo
    other = _repo(db, app, silo, f"_playground_{internal}7_session-of-another-agent")
    other2 = _repo(db, app, silo, f"_playground_{internal}12_session-of-another-agent")
    ids = InternalChatAgentRepository.list_orphan_temp_repository_ids(db, datetime.now(), 100)
    assert own_orphan in ids
    assert other not in ids and other2 not in ids
