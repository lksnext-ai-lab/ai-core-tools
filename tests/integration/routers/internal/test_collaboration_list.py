"""Regression test for listing app collaborators."""

from models.app_collaborator import AppCollaborator


class TestListCollaborators:

    def test_list_collaborators_accepts_string_auth_identity_id(
        self, client, fake_app, owner_headers, db
    ):
        # owner_headers creates an OWNER collaboration to satisfy access fixtures.
        # Remove it so this app has no collaborator rows to list.
        db.query(AppCollaborator).filter(
            AppCollaborator.app_id == fake_app.app_id
        ).delete(synchronize_session=False)
        db.flush()

        response = client.get(
            f"/internal/collaboration/?app_id={fake_app.app_id}",
            headers=owner_headers,
        )

        assert response.status_code == 200, response.text
        assert response.json() == []
