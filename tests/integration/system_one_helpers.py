"""Fixtures shared by the System One integration tests.

``tests/conftest.py``'s ``fake_user`` is created with the default PLATFORM role (viewer), which blocks every
write at the auth layer regardless of the app role. These fixtures promote it locally instead of editing the
shared conftest. Import them in a test module and add ``pytestmark = pytest.mark.usefixtures("platform_editor")``.
"""
from datetime import datetime

import pytest


@pytest.fixture
def platform_editor(fake_user, db):
    """fake_user may write (platform role editor); app-level permissions still apply on top."""
    fake_user.platform_role = "editor"
    db.flush()
    return fake_user


@pytest.fixture
def viewer_headers(db, fake_app):
    """Bearer headers of a second user who is only a VIEWER collaborator of fake_app."""
    from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
    from models.user import User
    from utils.local_auth_tokens import mint_access_token

    user = User(email="so-viewer@test.com", name="Viewer", is_active=True, platform_role="viewer")
    db.add(user)
    db.flush()
    db.add(AppCollaborator(app_id=fake_app.app_id, user_id=user.user_id, role=CollaborationRole.VIEWER,
                           invited_by=user.user_id, status=CollaborationStatus.ACCEPTED, accepted_at=datetime.now()))
    db.flush()
    token, _ = mint_access_token(user.user_id, user.email, user.name)
    return {"Authorization": f"Bearer {token}"}
