"""Router-level integration test: an administrator-role collaborator (not the
app owner) must be able to invite new collaborators to that app.

Regression: the invite endpoint's require_min_role("administrator") dependency
already accepted administrator-role collaborators, but a redundant manual
permission check inside the handler re-restricted to owner-only, so
administrators got a confusing 403 despite passing the route's own gate.

Run (Linux/CI only, needs the real test DB):
    pytest tests/integration/test_collaboration_administrator_invite.py -v
"""

import sys
import pytest
from models.app_collaborator import CollaborationRole, CollaborationStatus
from tests.factories import (
    UserFactory,
    AppFactory,
    AppCollaboratorFactory,
    configure_factories,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "Router tests require the `client` fixture which triggers a FastAPI lifespan "
        "that imports `fcntl` (Linux-only via file_cleanup_worker.py). Run in CI/Linux."
    ),
)


class TestAdministratorCollaboratorCanInvite:

    def test_administrator_collaborator_can_invite_new_user(self, client, fake_user, auth_headers, db):
        """fake_user is an accepted ADMINISTRATOR collaborator (not owner) on an
        app owned by someone else; they must still be able to invite a third user."""
        configure_factories(db)
        # fake_user's platform_role defaults to 'viewer' (column default), which
        # a separate, unrelated global gate (require_editor_for_writes) blocks
        # from ANY write regardless of app-level role. Bump it so this test
        # isolates the app-level administrator-permission fix being verified.
        fake_user.platform_role = 'editor'
        other_owner = UserFactory()
        app = AppFactory(owner=other_owner)
        AppCollaboratorFactory(
            app=app,
            user=fake_user,
            role=CollaborationRole.ADMINISTRATOR,
            status=CollaborationStatus.ACCEPTED,
        )
        invitee = UserFactory()
        invitee.platform_role = 'editor'  # avoid the unrelated viewer-platform-role invite restriction
        db.flush()

        response = client.post(
            f"/internal/collaboration/invite?app_id={app.app_id}",
            headers=auth_headers,
            json={"email": invitee.email, "role": "editor"},
        )
        assert response.status_code == 200, response.text

    def test_editor_collaborator_still_gets_403(self, client, fake_user, auth_headers, db):
        """Sanity check: only owner/administrator can invite — a plain editor collaborator cannot."""
        configure_factories(db)
        fake_user.platform_role = 'editor'
        other_owner = UserFactory()
        app = AppFactory(owner=other_owner)
        AppCollaboratorFactory(
            app=app,
            user=fake_user,
            role=CollaborationRole.EDITOR,
            status=CollaborationStatus.ACCEPTED,
        )
        invitee = UserFactory()
        db.flush()

        response = client.post(
            f"/internal/collaboration/invite?app_id={app.app_id}",
            headers=auth_headers,
            json={"email": invitee.email, "role": "editor"},
        )
        # Rejected by the require_min_role("administrator") route dependency itself
        # (a plain editor collaborator doesn't meet the minimum role).
        assert response.status_code == 403
