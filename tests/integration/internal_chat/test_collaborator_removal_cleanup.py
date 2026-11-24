"""Removing a collaborator (or leaving an App) removes that user's Chat data in THAT App only."""
from unittest.mock import patch

import pytest

from models.app_collaborator import CollaborationRole, CollaborationStatus
from models.conversation import Conversation
from services.conversation_service import ConversationService
from tests.factories import AppCollaboratorFactory, UserFactory, configure_factories
from tests.integration.internal_chat._chat_support import base, fakes, ok_turn, selection, world  # noqa: F401
from tests.integration.routers.internal._eos_helpers import headers_for


def _turn(client, scene, who, app_key, ai_key):
    response = client.post(
        base(scene[app_key]) + "/messages", headers=scene[who],
        data={"message": "hi", "selection": __import__("json").dumps(selection(scene[ai_key]))},
    )
    assert response.status_code == 200, response.text
    return response.json()["conversation_id"]


def _rows(db, *ids):
    db.expire_all()
    return {c for (c,) in db.query(Conversation.conversation_id).filter(Conversation.conversation_id.in_(ids)).all()}


@pytest.mark.parametrize("how", ["removed", "left"])
def test_the_removed_members_chat_data_of_that_app_is_gone_and_nothing_else(client, db, world, fakes, how):
    configure_factories(db)
    from models.app import App

    app, other = db.get(App, world["app_id"]), db.get(App, world["other_app_id"])
    m, n = UserFactory(), UserFactory()
    for user, a in ((m, app), (n, app), (m, other)):
        AppCollaboratorFactory(app=a, user=user, role=CollaborationRole.EDITOR,
                               status=CollaborationStatus.ACCEPTED, invited_by=a.owner_id)
    db.flush()
    db.commit()
    scene = dict(world, m=headers_for(m), n=headers_for(n))
    m_conv = _turn(client, scene, "m", "app_id", "ai_a")
    n_conv = _turn(client, scene, "n", "app_id", "ai_a")
    m_other = _turn(client, scene, "m", "other_app_id", "other_ai")
    assert _rows(db, m_conv, n_conv, m_other) == {m_conv, n_conv, m_other}

    threads = []
    real = ConversationService.delete_thread_histories_in_background
    with patch.object(ConversationService, "delete_thread_histories_in_background",
                      side_effect=lambda t: (threads.extend(t), real(t))[1]):
        if how == "removed":
            response = client.delete(f"/internal/collaboration/{m.user_id}?app_id={world['app_id']}", headers=world["alice"])
        else:
            response = client.post(f"/internal/apps/{world['app_id']}/leave", headers=scene["m"])
    assert response.status_code == 200, response.text
    assert _rows(db, m_conv, n_conv, m_other) == {n_conv, m_other}  # M's data in THIS App only
    assert len(threads) == 1  # M's checkpoint thread of this App was scheduled for deletion, nobody else's


def test_a_cleanup_failure_never_fails_the_removal(client, db, world, fakes):
    configure_factories(db)
    from models.app import App

    app = db.get(App, world["app_id"])
    m = UserFactory()
    AppCollaboratorFactory(app=app, user=m, role=CollaborationRole.EDITOR,
                           status=CollaborationStatus.ACCEPTED, invited_by=app.owner_id)
    db.flush()
    db.commit()
    scene = dict(world, m=headers_for(m))
    conv = _turn(client, scene, "m", "app_id", "ai_a")
    with patch.object(ConversationService, "delete_thread_histories_in_background", side_effect=RuntimeError("boom")):
        response = client.delete(f"/internal/collaboration/{m.user_id}?app_id={world['app_id']}", headers=world["alice"])
    assert response.status_code == 200, response.text
    assert _rows(db, conv) == set()
