"""
Regression tests: every ``/internal/apps/{app_id}/repositories/{repository_id}...`` route must
enforce ``repository.app_id == app_id`` and child (resource/media) ``repository_id`` ownership.

Bug (CRITICAL IDOR): only PUT/DELETE of a repository validated app ownership, so a member of
App A (any role) could read/search/download/upload/delete data of App B's repositories by
putting B's ids under A's URL. ``require_min_role`` only proves a role in the URL's app.

Setup: ``fake_user`` is OWNER of ``fake_app`` (App A) only; ``other_app`` (App B) is owned by a
different user with no collaboration for ``fake_user``.
"""

import io
import os

import pytest

from models.folder import Folder
from models.media import Media
from models.repository import Repository
from models.resource import Resource
from routers.internal.folders import folders_router
from routers.internal.repositories import repositories_router
from tests.factories import AppFactory, SiloFactory, configure_factories

NOT_FOUND = {"Repository not found"}


@pytest.fixture
def other_app(db):
    configure_factories(db)
    return AppFactory()


def _repo(db, app, name="repo"):
    silo = SiloFactory(app=app)
    repo = Repository(name=name, app_id=app.app_id, silo_id=silo.silo_id, type="repo", status="active")
    db.add(repo)
    db.flush()
    return repo


@pytest.fixture
def repo_dir(tmp_path, monkeypatch):
    import services.resource_service as resource_service

    monkeypatch.setattr(resource_service, "REPO_BASE_FOLDER", str(tmp_path))
    return tmp_path


def _resource(db, repo, repo_dir, name="doc.txt"):
    res = Resource(name=name, uri=name, type="txt", status="indexed", repository_id=repo.repository_id)
    db.add(res)
    db.flush()
    folder = repo_dir / str(repo.repository_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text("secret")
    return res, path


def _media(db, repo, name="clip"):
    media = Media(
        name=name, silo_id=repo.silo_id, repository_id=repo.repository_id,
        source_type="upload", status="processed", file_path=None,
    )
    db.add(media)
    db.flush()
    return media


@pytest.fixture
def setup(db, fake_app, other_app, owner_headers, repo_dir):
    configure_factories(db)
    repo_a = _repo(db, fake_app, "A")
    repo_a2 = _repo(db, fake_app, "A2")
    repo_b = _repo(db, other_app, "B")
    res_b, path_b = _resource(db, repo_b, repo_dir)
    res_a2, path_a2 = _resource(db, repo_a2, repo_dir, "a2.txt")
    media_b = _media(db, repo_b)
    media_a2 = _media(db, repo_a2)
    folder_a2 = Folder(name="f", repository_id=repo_a2.repository_id)
    db.add(folder_a2)
    db.flush()
    return dict(
        base=f"/internal/apps/{fake_app.app_id}/repositories",
        headers=owner_headers,
        repo_a=repo_a, repo_a2=repo_a2, repo_b=repo_b,
        res_b=res_b, path_b=path_b, res_a2=res_a2, path_a2=path_a2,
        media_b=media_b, media_a2=media_a2, folder_a2=folder_a2,
    )


def _assert_404(response):
    assert response.status_code == 404, response.text


class TestCrossAppRepositoryAccess:
    """App B's repository under App A's URL -> 404 and no side effects."""

    def test_detail(self, client, setup):
        r = client.get(f"{setup['base']}/{setup['repo_b'].repository_id}", headers=setup["headers"])
        _assert_404(r)
        assert r.json()["detail"] == "Repository not found"

    def test_update_and_delete(self, client, setup, db):
        rid = setup["repo_b"].repository_id
        _assert_404(client.put(f"{setup['base']}/{rid}", json={"name": "x"}, headers=setup["headers"]))
        _assert_404(client.delete(f"{setup['base']}/{rid}", headers=setup["headers"]))
        assert db.get(Repository, rid) is not None

    def test_export(self, client, setup):
        r = client.post(f"{setup['base']}/{setup['repo_b'].repository_id}/export", headers=setup["headers"])
        _assert_404(r)

    def test_search(self, client, setup):
        r = client.post(
            f"{setup['base']}/{setup['repo_b'].repository_id}/search",
            json={"query": "secret"}, headers=setup["headers"],
        )
        _assert_404(r)

    def test_upload_resource(self, client, setup, db):
        rid = setup["repo_b"].repository_id
        before = db.query(Resource).filter_by(repository_id=rid).count()
        r = client.post(
            f"{setup['base']}/{rid}/resources",
            files=[("files", ("evil.txt", io.BytesIO(b"x"), "text/plain"))],
            headers=setup["headers"],
        )
        _assert_404(r)
        assert db.query(Resource).filter_by(repository_id=rid).count() == before

    def test_move_delete_download_resource(self, client, setup, db):
        rid, res = setup["repo_b"].repository_id, setup["res_b"].resource_id
        base = f"{setup['base']}/{rid}/resources/{res}"
        _assert_404(client.post(f"{base}/move", headers=setup["headers"]))
        _assert_404(client.delete(base, headers=setup["headers"]))
        _assert_404(client.get(f"{base}/download", headers=setup["headers"]))
        assert db.get(Resource, res) is not None
        assert os.path.exists(setup["path_b"])

    def test_upload_media(self, client, setup, db):
        rid = setup["repo_b"].repository_id
        before = db.query(Media).filter_by(repository_id=rid).count()
        r = client.post(
            f"{setup['base']}/{rid}/media",
            files=[("files", ("a.mp3", io.BytesIO(b"x"), "audio/mpeg"))],
            headers=setup["headers"],
        )
        _assert_404(r)
        yt = client.post(
            f"{setup['base']}/{rid}/media/youtube",
            data={"url": "https://youtu.be/abc"}, headers=setup["headers"],
        )
        _assert_404(yt)
        assert db.query(Media).filter_by(repository_id=rid).count() == before

    def test_list_status_move_delete_media(self, client, setup, db):
        rid, mid = setup["repo_b"].repository_id, setup["media_b"].media_id
        _assert_404(client.get(f"{setup['base']}/{rid}/media", headers=setup["headers"]))
        _assert_404(client.get(f"{setup['base']}/{rid}/media/{mid}", headers=setup["headers"]))
        _assert_404(client.post(f"{setup['base']}/{rid}/media/{mid}/move", headers=setup["headers"]))
        _assert_404(client.delete(f"{setup['base']}/{rid}/media/{mid}", headers=setup["headers"]))
        assert db.get(Media, mid) is not None


class TestChildBelongsToParentSameApp:
    """Resource/media of repository A2 addressed through repository A (same app) -> 404."""

    def test_resource_routes(self, client, setup, db):
        rid, res = setup["repo_a"].repository_id, setup["res_a2"].resource_id
        base = f"{setup['base']}/{rid}/resources/{res}"
        _assert_404(client.get(f"{base}/download", headers=setup["headers"]))
        _assert_404(client.post(f"{base}/move", headers=setup["headers"]))
        _assert_404(client.delete(base, headers=setup["headers"]))
        assert db.get(Resource, res) is not None
        assert os.path.exists(setup["path_a2"])

    def test_media_routes(self, client, setup, db):
        rid, mid = setup["repo_a"].repository_id, setup["media_a2"].media_id
        _assert_404(client.get(f"{setup['base']}/{rid}/media/{mid}", headers=setup["headers"]))
        _assert_404(client.post(f"{setup['base']}/{rid}/media/{mid}/move", headers=setup["headers"]))
        _assert_404(client.delete(f"{setup['base']}/{rid}/media/{mid}", headers=setup["headers"]))
        assert db.get(Media, mid) is not None

    def test_media_upload_into_foreign_folder(self, client, setup, db):
        rid = setup["repo_a"].repository_id
        before = db.query(Media).filter_by(repository_id=rid).count()
        r = client.post(
            f"{setup['base']}/{rid}/media",
            files=[("files", ("a.mp3", io.BytesIO(b"x"), "audio/mpeg"))],
            data={"folder_id": str(setup["folder_a2"].folder_id)},
            headers=setup["headers"],
        )
        _assert_404(r)
        assert db.query(Media).filter_by(repository_id=rid).count() == before

    def test_media_move_to_foreign_folder(self, client, setup, db):
        media = _media(db, setup["repo_a"], "own")
        r = client.post(
            f"{setup['base']}/{setup['repo_a'].repository_id}/media/{media.media_id}/move",
            data={"new_folder_id": str(setup["folder_a2"].folder_id)},
            headers=setup["headers"],
        )
        _assert_404(r)

    def test_own_resource_download_still_works(self, client, setup, db, repo_dir):
        res, _ = _resource(db, setup["repo_a"], repo_dir, "mine.txt")
        r = client.get(
            f"{setup['base']}/{setup['repo_a'].repository_id}/resources/{res.resource_id}/download",
            headers=setup["headers"],
        )
        assert r.status_code == 200
        assert r.content == b"secret"

    def test_own_media_status_still_works(self, client, setup):
        r = client.get(
            f"{setup['base']}/{setup['repo_a2'].repository_id}/media/{setup['media_a2'].media_id}",
            headers=setup["headers"],
        )
        assert r.status_code == 200

    def test_new_repository_form_still_works(self, client, setup):
        r = client.get(f"{setup['base']}/0", headers=setup["headers"])
        assert r.status_code == 200


class TestFolderRoutesCrossApp:
    """Folders of App B's repository under App A's URL -> 404 and no side effects."""

    def test_tree_detail_delete(self, client, setup, db):
        rid = setup["repo_b"].repository_id
        folder = Folder(name="bf", repository_id=rid)
        db.add(folder)
        db.flush()
        base = f"{setup['base']}/{rid}/folders"
        h = setup["headers"]
        _assert_404(client.get(f"{base}/tree", headers=h))
        _assert_404(client.get(f"{base}/", headers=h))
        _assert_404(client.get(f"{base}/{folder.folder_id}", headers=h))
        _assert_404(client.post(f"{base}/", json={"name": "x"}, headers=h))
        _assert_404(client.put(f"{base}/{folder.folder_id}", json={"name": "x"}, headers=h))
        _assert_404(client.post(f"{base}/{folder.folder_id}/move", json={"new_parent_folder_id": None}, headers=h))
        _assert_404(client.delete(f"{base}/{folder.folder_id}", headers=h))
        db.expire_all()
        assert db.get(Folder, folder.folder_id).name == "bf"
        assert db.query(Folder).filter_by(repository_id=rid).count() == 1


class TestRoleCheckedBeforeScoping:
    def test_non_member_gets_same_status_for_existing_and_missing_repository(self, client, db, setup, other_app):
        from tests.factories import UserFactory
        from utils.local_auth_tokens import mint_access_token

        stranger = UserFactory()
        db.flush()
        token, _ = mint_access_token(stranger.user_id, stranger.email, stranger.name)
        h = {"Authorization": f"Bearer {token}"}
        base = setup["base"]
        existing = client.get(f"{base}/{setup['repo_a'].repository_id}", headers=h)
        missing = client.get(f"{base}/99999999", headers=h)
        folders_existing = client.get(f"{base}/{setup['repo_a'].repository_id}/folders/tree", headers=h)
        folders_missing = client.get(f"{base}/99999999/folders/tree", headers=h)
        assert existing.status_code == missing.status_code == 403
        assert folders_existing.status_code == folders_missing.status_code == 403


class TestNewRepositoryZeroOnlyForDetail:
    def test_zero_is_404_for_mutating_routes(self, client, setup):
        base, h = setup["base"], setup["headers"]
        _assert_404(client.delete(f"{base}/0", headers=h))
        _assert_404(client.put(f"{base}/0", json={"name": "x"}, headers=h))


def test_every_repository_id_route_has_the_app_scope_dependency():
    """Guard against forgetting the dependency on a new /{repository_id}... route."""
    from routers.controls.repository_scope import require_repository_in_app, require_repository_in_app_or_new

    allowed = {require_repository_in_app, require_repository_in_app_or_new}
    checked = 0
    for router in (repositories_router, folders_router):
        for route in router.routes:
            if router is repositories_router and "{repository_id}" not in route.path:
                continue
            checked += 1
            calls = {d.call for d in route.dependant.dependencies}
            assert calls & allowed, f"{route.methods} {route.path} lacks app scoping"
    assert checked >= 22
