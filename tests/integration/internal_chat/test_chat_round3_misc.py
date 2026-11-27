"""Round 3: parser lifecycle, session-bound temp creation, orphan sweep, filter-field scoping."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from models.agent import Agent
from models.app import App
from models.conversation import Conversation
from models.output_parser import OutputParser
from models.repository import PLAYGROUND_MEDIA_REPO_TYPE, Repository
from models.silo import Silo
from services.agent_service import AgentService
from services.file_cleanup_worker import sweep_orphan_chat_temp_repositories
from services.playground_media_service import PlaygroundMediaService, TempSessionGone
from tests.factories import AgentFactory
from tests.integration.internal_chat.test_chat_temp_silo_visibility import scene  # noqa: F401  (fixture)


def _session_factory(db):
    return lambda: Session(bind=db.get_bind(), join_transaction_mode="create_savepoint", autoflush=False)


def test_deleting_a_temp_repository_deletes_its_metadata_parser_too(db, scene):  # noqa: F811
    silo = db.get(Silo, scene["temp_silo"])
    parser_id = silo.metadata_definition_id
    assert db.get(OutputParser, parser_id) is not None
    repo = db.get(Repository, scene["temp_repo"])
    PlaygroundMediaService.cleanup(scene["app_id"], *_agent_and_session(db, scene), db)
    db.expire_all()
    assert db.get(Repository, scene["temp_repo"]) is None and db.get(Silo, scene["temp_silo"]) is None
    assert db.get(OutputParser, parser_id) is None, "the parser (it names the session) must not outlive the conversation"
    del repo


def _agent_and_session(db, scene):
    conversation = db.get(Conversation, scene["cid"])
    return conversation.agent_id, conversation.session_id


def test_a_temp_repository_is_not_created_for_a_session_no_conversation_binds(db, scene):  # noqa: F811
    agent_id, _ = _agent_and_session(db, scene)
    with pytest.raises(TempSessionGone):
        PlaygroundMediaService.get_or_create_temp_repository(
            scene["app_id"], agent_id, f"conv_{agent_id}_not-a-live-session", db, embedding_service_id=scene["emb"]
        )
    assert db.query(Repository).filter(Repository.name.like("%not-a-live-session")).count() == 0


def test_the_sweep_removes_only_orphaned_chat_temp_repositories(db, scene):  # noqa: F811
    factory = _session_factory(db)
    repo = db.get(Repository, scene["temp_repo"])
    repo.create_date = datetime.now() - timedelta(hours=2)
    db.flush()
    assert sweep_orphan_chat_temp_repositories(session_factory=factory) == 0  # its conversation is alive
    parser_id = db.get(Silo, scene["temp_silo"]).metadata_definition_id

    db.delete(db.get(Conversation, scene["cid"]))  # the conversation is gone, the repository was left behind
    db.flush()
    repo.create_date = datetime.now()  # inside the grace period: not touched yet
    db.flush()
    assert sweep_orphan_chat_temp_repositories(session_factory=factory) == 0
    repo.create_date = datetime.now() - timedelta(hours=2)
    db.flush()
    assert sweep_orphan_chat_temp_repositories(session_factory=factory) == 1
    db.expire_all()
    assert db.get(Repository, scene["temp_repo"]) is None and db.get(Silo, scene["temp_silo"]) is None
    assert db.get(OutputParser, parser_id) is None


@pytest.mark.parametrize("tz", ["Pacific/Kiritimati", "Pacific/Pago_Pago"])  # UTC+14 and UTC-11
def test_the_sweep_grace_period_uses_the_clock_the_repository_date_is_written_with(db, scene, tz):  # noqa: F811
    import os
    import time

    previous = os.environ.get("TZ")
    os.environ["TZ"] = tz
    time.tzset()
    try:
        factory = _session_factory(db)
        db.delete(db.get(Conversation, scene["cid"]))  # orphaned: only the grace period protects it
        db.flush()
        repo = db.get(Repository, scene["temp_repo"])
        repo.create_date = datetime.now()  # exactly how RepositoryService.create_repository writes it
        db.flush()
        assert sweep_orphan_chat_temp_repositories(session_factory=factory) == 0
        repo.create_date = datetime.now() - timedelta(minutes=30)  # past the 15 minute grace, in local time
        db.flush()
        assert sweep_orphan_chat_temp_repositories(session_factory=factory) == 1
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


def test_the_sweep_leaves_the_temp_repositories_of_normal_agents_alone(db, world):
    from tests.factories import configure_factories

    configure_factories(db)
    agent = AgentFactory(app=db.get(App, world["app_id"]), has_memory=True)
    db.flush()
    repo = PlaygroundMediaService.get_or_create_temp_repository(
        world["app_id"], agent.agent_id, "conv_x_no_conversation", db, embedding_service_id=world["emb"]
    )
    repo.create_date = datetime.now() - timedelta(days=2)
    db.flush()
    assert sweep_orphan_chat_temp_repositories(session_factory=_session_factory(db)) == 0
    assert db.get(Repository, repo.repository_id) is not None


def test_chat_filter_fields_ignore_other_apps_and_the_temp_silo(db, scene, world):  # noqa: F811
    own_agent = AgentFactory(app=db.get(App, scene["app_id"]))
    foreign_agent = AgentFactory(app=db.get(App, world["other_app_id"]))
    own_silo = Silo(name="own-visible", app_id=scene["app_id"], embedding_service_id=scene["emb"])
    db.add(own_silo)
    db.flush()
    own_agent.silo_id = own_silo.silo_id
    foreign_agent.silo_id = world["other_silo"]
    db.flush()

    def declared(self, session, silo_id):
        return [{"name": f"f{silo_id}", "type": "str"}]

    with patch.object(AgentService, "_load_declared_metadata_fields", declared):
        fields = AgentService().get_available_chat_filter_fields(
            db, [own_agent.agent_id, foreign_agent.agent_id], scene["temp_silo"], app_id=scene["app_id"]
        )
        unscoped = AgentService().get_available_chat_filter_fields(
            db, [foreign_agent.agent_id], world["other_silo"]
        )
    assert [f["name"] for f in fields] == [f"f{own_silo.silo_id}"]  # no foreign silo, no temp silo
    assert unscoped  # the scope is what filters (the service default is unchanged for internal callers)
