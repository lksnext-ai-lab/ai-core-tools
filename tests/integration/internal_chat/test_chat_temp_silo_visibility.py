"""The hidden temp silo of a conversation (Chat or playground) is invisible and unreachable by anyone but its turn.

Chat uploads are indexed into ONE temp silo per conversation (a ``Repository`` of type ``playground_media``). It holds
the chunks of a single user's attachments, so no other member, API key or agent form may list, search, read, change,
delete or index into it: every such request answers the same 404 as a missing silo. Only ``PlaygroundMediaService``
(upload, the turn's retriever, cleanup) reaches it.
"""
import re

import pytest
from unittest.mock import patch

from models.agent import Agent
from models.app import App
from models.app_collaborator import CollaborationRole
from models.repository import PLAYGROUND_MEDIA_REPO_TYPE, Repository
from models.silo import Silo
from services.playground_media_service import PlaygroundMediaService
from services.silo_service import SiloService
from tests.factories import AgentFactory, APIKeyFactory, AppCollaboratorFactory, UserFactory, configure_factories
from tests.integration.internal_chat._chat_support import base, selection
from tests.integration.routers.internal._eos_helpers import headers_for


@pytest.fixture
def scene(client, db, world, worker_session_on_test_db):
    """Member ``author`` (EDITOR) uploads to a Chat conversation of the App; the temp silo exists afterwards."""
    configure_factories(db)
    app = db.get(App, world["app_id"])
    app.default_embedding_service_id = world["emb"]
    author = UserFactory()
    from models.app_collaborator import CollaborationStatus

    AppCollaboratorFactory(app=app, user=author, role=CollaborationRole.EDITOR,
                           status=CollaborationStatus.ACCEPTED, invited_by=app.owner_id)
    key = APIKeyFactory(app=app, user=db.get(type(author), world["alice_id"]))
    db.flush()
    scene = dict(world, author=headers_for(author), author_id=author.user_id, api_key={"X-API-KEY": key.key})
    db.commit()
    with patch.object(SiloService, "index_multiple_content", return_value=None):
        created = client.post(base(world["app_id"]) + "/conversations", headers=scene["author"],
                              json={"selection": selection(world["ai_a"])})
        assert created.status_code == 200, created.text
        scene["cid"] = created.json()["conversation_id"]
        uploaded = client.post(
            f"{base(world['app_id'])}/conversations/{scene['cid']}/files", headers=scene["author"],
            files={"file": ("note.txt", b"PRIVATE attachment text of the author", "text/plain")},
        )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["vectorized"] is True
    repo = db.query(Repository).filter(Repository.app_id == world["app_id"],
                                       Repository.type == PLAYGROUND_MEDIA_REPO_TYPE).one()
    scene.update(temp_repo=repo.repository_id, temp_silo=repo.silo_id)
    return scene


@pytest.fixture
def playground_scene(client, db, world):
    """The same, for a playground temp silo (an agent with memory)."""
    configure_factories(db)
    app = db.get(App, world["app_id"])
    agent = AgentFactory(app=app, has_memory=True)
    db.flush()
    repo = PlaygroundMediaService.get_or_create_temp_repository(
        app.app_id, agent.agent_id, "conv_pg_session", db, embedding_service_id=world["emb"]
    )
    scene = dict(world, temp_repo=repo.repository_id, temp_silo=repo.silo_id, agent_id=agent.agent_id,
                 author=world["alice"])
    scene["api_key"] = {"X-API-KEY": APIKeyFactory(app=app, user=db.get(type(app.owner), world["alice_id"])).key}
    db.commit()
    return scene


def _internal_requests(client, scene):
    app, silo, repo = scene["app_id"], scene["temp_silo"], scene["temp_repo"]
    s = f"/internal/apps/{app}/silos/{silo}"
    r = f"/internal/apps/{app}/repositories/{repo}"
    return [
        ("GET", s, {}), ("POST", s + "/search", {"json": {"query": "PRIVATE"}}),
        ("GET", s + "/documents/neighbors", {"params": {"source_type": "media", "source_id": "1"}}),
        ("POST", s + "/documents/count", {"json": {}}),
        ("DELETE", s + "/documents", {"json": {"document_ids": ["x"]}}),
        ("PUT", s, {"json": {"name": "hijacked"}}), ("POST", s + "/export", {}), ("DELETE", s, {}),
        ("GET", r, {}), ("PUT", r, {"json": {"name": "hijacked"}}), ("DELETE", r, {}),
        ("POST", r + "/search", {"json": {"query": "PRIVATE"}}), ("GET", r + "/media", {}),
        ("POST", r + "/export", {}),
    ]


def _public_requests(scene):
    app, silo, repo = scene["app_id"], scene["temp_silo"], scene["temp_repo"]
    s = f"/public/v1/app/{app}/silos/{silo}"
    r = f"/public/v1/app/{app}/repositories/{repo}"
    return [
        ("GET", s, {}), ("PUT", s, {"json": {"name": "hijacked"}}), ("DELETE", s, {}),
        ("POST", s + "/search", {"json": {"query": "PRIVATE"}}), ("GET", s + "/docs", {}),
        ("POST", s + "/docs/index", {"json": {"content": "planted"}}),
        ("POST", s + "/docs/multiple-index", {"json": {"documents": [{"content": "planted"}]}}),
        ("DELETE", s + "/docs/delete", {"json": {"ids": ["x"]}}),
        ("POST", s + "/docs/find", {"json": {"query": "PRIVATE"}}), ("GET", s + "/media", {}),
        ("GET", r, {}), ("DELETE", r, {}), ("GET", r + "/media", {}),
    ]


@pytest.mark.parametrize("kind", ["chat", "playground"])
@pytest.mark.parametrize("caller", ["viewer", "owner"])
def test_internal_requests_on_the_temp_silo_and_repository_answer_404(
    client, db, request, kind, caller
):
    scene = request.getfixturevalue("scene" if kind == "chat" else "playground_scene")
    headers = scene["alice" if caller == "owner" else caller]
    answers = []
    for method, url, kwargs in _internal_requests(client, scene):
        response = client.request(method, url, headers=headers, **kwargs)
        # a viewer is refused earlier (403) by the role of write endpoints; what must never happen is a 2xx / 5xx
        answers.append((method, url, response.status_code))
    bad = [a for a in answers if a[2] not in (403, 404)]
    assert not bad, bad
    if caller == "owner":
        assert all(code == 404 for _, _, code in answers), answers
    from models.silo import Silo

    db.expire_all()
    assert db.get(Silo, scene["temp_silo"]) is not None  # nothing was deleted
    assert db.get(Repository, scene["temp_repo"]).name != "hijacked"


@pytest.mark.parametrize("kind", ["chat", "playground"])
def test_public_requests_with_an_app_api_key_on_the_temp_silo_and_repository_answer_404(client, db, request, kind):
    scene = request.getfixturevalue("scene" if kind == "chat" else "playground_scene")
    answers = [
        (method, url, client.request(method, url, headers=scene["api_key"], **kwargs).status_code)
        for method, url, kwargs in _public_requests(scene)
    ]
    assert [a for a in answers if a[2] != 404] == [], answers


@pytest.mark.parametrize("kind", ["chat", "playground"])
def test_lists_never_contain_the_temp_silo_or_repository(client, db, request, kind):
    scene = request.getfixturevalue("scene" if kind == "chat" else "playground_scene")
    app = scene["app_id"]
    for headers in (scene["viewer"], scene["alice"]):
        silos = client.get(f"/internal/apps/{app}/silos/", headers=headers)
        repos = client.get(f"/internal/apps/{app}/repositories/", headers=headers)
        assert silos.status_code == repos.status_code == 200
        assert scene["temp_silo"] not in [s["silo_id"] for s in silos.json()]
        assert scene["temp_repo"] not in [r["repository_id"] for r in repos.json()]
    pub_silos = client.get(f"/public/v1/app/{app}/silos/", headers=scene["api_key"])
    pub_repos = client.get(f"/public/v1/app/{app}/repositories/", headers=scene["api_key"])
    assert pub_silos.status_code == pub_repos.status_code == 200
    assert scene["temp_silo"] not in [s["silo_id"] for s in pub_silos.json()["silos"]]
    assert scene["temp_repo"] not in [r["repository_id"] for r in pub_repos.json()["repositories"]]


@pytest.mark.parametrize("kind", ["chat", "playground"])
def test_an_agent_cannot_be_pointed_at_the_temp_silo(client, db, request, kind):
    scene = request.getfixturevalue("scene" if kind == "chat" else "playground_scene")
    app = scene["app_id"]
    agent = AgentFactory(app=db.get(App, app))
    db.flush()
    internal = client.post(
        f"/internal/apps/{app}/agents/{agent.agent_id}", headers=scene["alice"],
        json={"name": agent.name, "type": "agent", "description": "d", "system_prompt": "p",
              "service_id": scene["ai_a"], "silo_id": scene["temp_silo"]},
    )
    assert internal.status_code in (400, 404, 422), internal.text
    assert "silo_id" in internal.text
    public = client.put(
        f"/public/v1/app/{app}/agents/{agent.agent_id}", headers=scene["api_key"], json={"silo_id": scene["temp_silo"]},
    )
    assert public.status_code in (400, 404, 422), public.text
    db.expire_all()
    assert db.get(Agent, agent.agent_id).silo_id is None


def test_the_chat_options_never_offer_the_temp_silo(client, scene):
    for who in ("viewer", "alice", "author"):
        options = client.get(base(scene["app_id"]) + "/options", headers=scene[who]).json()
        assert scene["temp_silo"] not in [s["silo_id"] for s in options["silos"]]


def test_the_authors_own_turn_still_resolves_the_temp_silo_and_nobody_elses_does(client, db, scene):
    """The turn's source of truth (``get_temp_silo_ids_for_agent``) is not affected by the visibility rule.

    The real retriever over it is proven end to end (committed data, real embeddings pipeline) by
    ``test_chat_isolation_concurrency.TestAttachmentsAndTempSiloRag``: the retriever builder opens its own session,
    which cannot see this test's transaction.
    """
    from models.conversation import Conversation

    conversation = db.get(Conversation, scene["cid"])
    own = PlaygroundMediaService.get_temp_silo_ids_for_agent(
        scene["app_id"], conversation.agent_id, conversation.session_id, db)
    assert own == [scene["temp_silo"]]
    assert PlaygroundMediaService.get_temp_silo_ids_for_agent(
        scene["app_id"], conversation.agent_id, "conv_other_session", db) == []


def test_a_user_cannot_create_a_repository_with_the_reserved_type(client, scene):
    response = client.post(
        f"/internal/apps/{scene['app_id']}/repositories/", headers=scene["alice"],
        json={"name": "sneaky", "type": PLAYGROUND_MEDIA_REPO_TYPE},
    )
    assert response.status_code == 422, response.text


def test_deleting_a_user_removes_their_chat_conversations_with_storage_and_temp_silo(client, db, scene):
    """``Conversation.user_id`` goes NULL on user deletion: without this the chat, files and temp silo would be orphans."""
    import os

    from models.conversation import Conversation
    from models.internal_chat import ChatConversationState
    from models.silo import Silo
    from services.file_management_service import FileManagementService
    from services.user_service import UserService

    cid, repo_id, silo_id = scene["cid"], scene["temp_repo"], scene["temp_silo"]
    other = client.post(base(scene["app_id"]) + "/conversations", headers=scene["viewer"],
                        json={"selection": selection(scene["ai_a"])}).json()["conversation_id"]
    folder = os.path.join(FileManagementService().tmp_base_folder, "conversations", str(cid))
    assert os.path.isdir(folder)

    UserService.delete_user(db, scene["author_id"], actor_user_id=scene["alice_id"], mode="block")

    db.expire_all()
    assert db.get(Conversation, cid) is None and db.get(ChatConversationState, cid) is None
    assert db.get(Repository, repo_id) is None and db.get(Silo, silo_id) is None
    assert not os.path.isdir(folder)
    assert db.get(Conversation, other) is not None  # another user's chat is untouched


# ------------------------------------------------------------------ metadata parser and name-based lookups (round 3)


def _temp_names(db, scene):
    from models.output_parser import OutputParser
    from models.silo import Silo

    silo = db.get(Silo, scene["temp_silo"])
    repo = db.get(Repository, scene["temp_repo"])
    return silo.name, repo.name, silo.metadata_definition_id, db.get(OutputParser, silo.metadata_definition_id).name


@pytest.mark.parametrize("kind", ["chat", "playground"])
def test_the_temp_metadata_parser_is_hidden_from_lists_details_and_edits(client, db, request, kind):
    scene = request.getfixturevalue("scene" if kind == "chat" else "playground_scene")
    _, repo_name, parser_id, parser_name = _temp_names(db, scene)
    assert repo_name in parser_name  # the leak this test guards: the session id travels in the parser's name
    base_url = f"/internal/apps/{scene['app_id']}/output-parsers"
    for who in ("viewer", "alice"):
        listed = client.get(base_url + "/", headers=scene[who]).json()
        assert parser_id not in [p["parser_id"] for p in listed]
        assert repo_name not in client.get(base_url + "/", headers=scene[who]).text
    assert client.get(f"{base_url}/{parser_id}", headers=scene["viewer"]).status_code == 404
    assert client.get(f"{base_url}/{parser_id}", headers=scene["alice"]).status_code == 404
    assert client.delete(f"{base_url}/{parser_id}", headers=scene["alice"]).status_code == 404
    assert client.post(f"{base_url}/{parser_id}", headers=scene["alice"], json={"name": "x", "fields": []}).status_code in (
        404, 422)
    assert client.post(f"{base_url}/{parser_id}/export", headers=scene["alice"]).status_code == 404
    from models.output_parser import OutputParser

    db.expire_all()
    assert db.get(OutputParser, parser_id).name == parser_name  # untouched


@pytest.mark.parametrize("kind", ["chat", "playground"])
def test_the_agent_form_and_silo_form_pickers_do_not_offer_the_temp_parser(client, db, request, kind):
    scene = request.getfixturevalue("scene" if kind == "chat" else "playground_scene")
    _, _, parser_id, _ = _temp_names(db, scene)
    agent = AgentFactory(app=db.get(App, scene["app_id"]))
    db.flush()
    form = client.get(f"/internal/apps/{scene['app_id']}/agents/{agent.agent_id}", headers=scene["alice"])
    assert form.status_code == 200
    assert str(parser_id) not in [str(p.get("parser_id")) for p in form.json().get("output_parsers", [])]
    silo_form = client.get(f"/internal/apps/{scene['app_id']}/silos/0", headers=scene["alice"])
    assert parser_id not in [p["parser_id"] for p in silo_form.json().get("output_parsers", [])]


@pytest.mark.parametrize("kind", ["chat", "playground"])
def test_an_agent_cannot_be_given_the_temp_parser(client, db, request, kind):
    scene = request.getfixturevalue("scene" if kind == "chat" else "playground_scene")
    _, _, parser_id, _ = _temp_names(db, scene)
    agent = AgentFactory(app=db.get(App, scene["app_id"]))
    db.flush()
    response = client.post(
        f"/internal/apps/{scene['app_id']}/agents/{agent.agent_id}", headers=scene["alice"],
        json={"name": agent.name, "type": "agent", "service_id": scene["ai_a"], "output_parser_id": parser_id},
    )
    assert response.status_code in (400, 404, 422) and "output_parser_id" in response.text


@pytest.mark.parametrize("kind", ["chat", "playground"])
def test_name_based_import_lookups_never_resolve_the_temp_silo(db, request, kind):
    """An ADMINISTRATOR could name another user's temp silo in an import file; every by-name lookup must say "none"."""
    from types import SimpleNamespace

    from services.agent_import_service import AgentImportService
    from services.domain_import_service import DomainImportService
    from services.repository_import_service import RepositoryImportService
    from services.silo_import_service import SiloImportService

    scene = request.getfixturevalue("scene" if kind == "chat" else "playground_scene")
    silo_name, *_ = _temp_names(db, scene)
    app_id = scene["app_id"]
    assert SiloImportService(db).get_by_name_and_app(silo_name, app_id) is None
    assert AgentImportService(db)._check_silo_conflict(silo_name, app_id) is False
    repo_export = SimpleNamespace(repository=SimpleNamespace(silo_name=silo_name), silo=None, metadata=None)
    domain_export = SimpleNamespace(domain=SimpleNamespace(silo_name=silo_name), silo=None, metadata=None)
    for service, export in ((RepositoryImportService(db), repo_export), (DomainImportService(db), domain_export)):
        assert service._resolve_silo(export, app_id, None, None, None, None) is None


# ------------------------------------------------------------------ route enumeration guard


# Routes with a silo / repository id that cannot be called generically (nothing to prove here). Keep each reason.
GUARD_ALLOW_LIST: dict = {}

# Valid bodies for the routes whose body is validated BEFORE the handler checks the silo (422 otherwise).
_FILE = {"files": {"file": ("a.txt", b"x", "text/plain")}}
_FILES = {"files": {"files": ("a.txt", b"x", "text/plain")}}
_FILTER = {"json": {"filter_metadata": {"a": "b"}}}
GUARD_BODIES = {
    ("PUT", "silos/{silo_id}"): {"json": {"name": "x"}},
    ("PUT", "repositories/{repository_id}"): {"json": {"name": "x"}},
    ("PUT", "repositories/{repo_id}"): {"json": {"name": "x"}},
    ("POST", "silos/{silo_id}/search"): {"json": {"query": "q"}},
    ("POST", "repositories/{repository_id}/search"): {"json": {"query": "q"}},
    ("GET", "silos/{silo_id}/documents/neighbors"): {"params": {"source_type": "media", "source_id": "1"}},
    ("DELETE", "silos/{silo_id}/documents"): {"json": {"document_ids": ["x"]}},
    ("POST", "repositories/{repo_id}/docs/find"): {"json": {"query": "q"}},
    ("POST", "repositories/{repo_id}/media"): _FILES,
    ("POST", "repositories/{repo_id}/media/youtube"): {"json": {"url": "https://youtu.be/x"}},
    ("POST", "resources/{repo_id}"): _FILES,
    ("POST", "silos/{silo_id}/docs/index"): {"json": {"content": "x"}},
    ("POST", "silos/{silo_id}/docs/multiple-index"): {"json": {"documents": [{"content": "x"}]}},
    ("DELETE", "silos/{silo_id}/docs/delete"): {"json": {"ids": ["x"]}},
    ("DELETE", "silos/{silo_id}/docs/delete-by-metadata"): _FILTER,
    ("POST", "silos/{silo_id}/docs/count-by-metadata"): _FILTER,
    ("POST", "silos/{silo_id}/docs/metadata-values"): {"json": {"field": "a"}},
    ("POST", "silos/{silo_id}/docs/update-metadata"): {"json": {"filter_metadata": {"a": "b"}, "metadata_updates": {}}},
    ("POST", "silos/{silo_id}/docs/find"): {"json": {"query": "q"}},
    ("POST", "silos/{silo_id}/docs/index-file"): _FILE,
    ("POST", "silos/{silo_id}/media/youtube"): {"json": {"url": "https://youtu.be/x"}},
}


_ID_PARAM = re.compile(r"\{[a-z_]*(silo_id|repository_id|repo_id)\}")
MISSING_ID = 999999999
# Second path parameters that name no database row, so no real child can exist: keep a placeholder (reported).
PLACEHOLDER_PARAMS = {"field": "a"}  # GET silos/{silo_id}/metadata/{field}/values: a metadata field NAME


def _guard_routes(client):
    """(method, path template) of every internal / public route with a silo or repository id, from the OpenAPI docs."""
    found = []
    for doc in ("/openapi-internal.json", "/openapi-public.json"):
        spec = client.get(doc).json()
        for path, operations in spec["paths"].items():
            if not _ID_PARAM.search(path):
                continue
            if "/apps/{app_id}/" not in path and "/app/{app_id}/" not in path:
                continue
            prefix = "/internal" if doc == "/openapi-internal.json" else "/public/v1"
            full = path if path.startswith(prefix) else prefix + path
            found.extend((method.upper(), full) for method in operations if method in ("get", "post", "put", "delete", "patch"))
    return found


def _make_children(db, silo_id: int, repo_id: int, template: str) -> dict:
    """A REAL child of the temp repository / silo for each second path parameter of the route."""
    from models.folder import Folder
    from models.media import Media
    from models.resource import Resource

    children = {}
    if "{resource_id}" in template:
        row = Resource(name="child.txt", type="txt", status="indexed", repository_id=repo_id)
        db.add(row)
        db.flush()
        children["resource_id"] = row.resource_id
    if "{media_id}" in template:
        row = Media(name="child.mp3", source_type="upload", silo_id=silo_id, repository_id=repo_id)
        db.add(row)
        db.flush()
        children["media_id"] = row.media_id
    if "{folder_id}" in template:
        row = Folder(name="child", repository_id=repo_id)
        db.add(row)
        db.flush()
        children["folder_id"] = row.folder_id
    return children


def _guard_call(client, method, template, parent_id, app_id, children, headers, kwargs, mask):
    """Call the route with ``parent_id`` in every silo/repository slot; returns (status, id-masked body)."""
    import re as _re

    def fill(match):
        name = match.group(0)[1:-1]
        if name == "app_id":
            return str(app_id)
        if _ID_PARAM.fullmatch(match.group(0)):
            return str(parent_id)
        if name in children:
            return str(children[name])
        assert name in PLACEHOLDER_PARAMS, f"unknown path parameter {name} in {template}: decide its child"
        return PLACEHOLDER_PARAMS[name]

    url = _re.sub(r"\{[a-z_]+\}", fill, template)
    response = client.request(method, url, headers=headers, **kwargs)
    body = response.text
    for value in mask:
        body = _re.sub(rf"\b{value}\b", "<ID>", body)
    return response.status_code, body


def test_every_route_with_a_silo_or_repository_id_answers_404_for_a_temp_one(client, db, scene):
    """A temp silo/repository is indistinguishable from a missing one on every route (same status AND body).

    Each route is called twice with identical inputs except the silo/repository id (the temp one, then 999999999).
    Second path parameters (resource / media / folder) are REAL children of the temp resource, so the lookup would
    succeed were the visibility rule absent. A route that echoes the id in its body is compared with the id masked.
    """
    routes = _guard_routes(client)
    assert len(routes) > 40, "the enumeration found too few routes: the guard is broken"
    app_id, silo, repo = scene["app_id"], scene["temp_silo"], scene["temp_repo"]
    offenders, unverified = [], []
    # Destructive routes last: were the rule absent, a DELETE that succeeds would make every later route on the same
    # resource answer a (vacuous) 404.
    for method, template in sorted(routes, key=lambda route: route[0] == "DELETE"):
        if (method, template) in GUARD_ALLOW_LIST:
            continue
        internal = template.startswith("/internal/")
        short = re.sub(r"^.*?/(silos|repositories|resources)/", r"\1/", template)
        by_silo = "silo_id}" in template
        temp_id = silo if by_silo else repo
        children = _make_children(db, silo, repo, template)
        db.commit()
        kwargs = GUARD_BODIES.get((method, short), {"json": {}})
        headers = scene["alice"] if internal else scene["api_key"]
        mask = (str(silo), str(repo), str(MISSING_ID))
        missing = _guard_call(client, method, template, MISSING_ID, app_id, children, headers, kwargs, mask)
        temp = _guard_call(client, method, template, temp_id, app_id, children, headers, kwargs, mask)
        if temp[0] == 422 or missing[0] == 422:
            unverified.append((method, template))
        elif temp[0] != 404 or temp != missing:
            offenders.append((method, template, temp, missing))
        try:
            db.expire_all()
            destroyed = db.get(Repository, repo) is None or db.get(Silo, silo) is None
        except Exception:  # a route that crashed mid-flush poisons the shared session: it is already in `offenders`
            db.rollback()
            destroyed = True
        if destroyed:
            offenders.append(("DESTROYED the temp resource", method, template))
            break  # nothing left to probe: the remaining routes would answer a vacuous 404
    assert not offenders, f"routes that do not hide a temp silo/repository: {offenders}"
    assert not unverified, (
        f"routes whose request validation fails before the visibility rule runs; add a valid body to GUARD_BODIES or "
        f"an allow-list entry with a reason: {unverified}"
    )


# ------------------------------------------------------------------ output parsers and ids in request bodies

_PARSER_PARAM = re.compile(r"\{[a-z_]*parser_id\}")


def _temp_parser_id(db, scene):
    from models.silo import Silo as _Silo

    parser_id = db.get(_Silo, scene["temp_silo"]).metadata_definition_id
    assert parser_id is not None, "the temp silo has no metadata parser: the guard would be vacuous"
    return parser_id


def test_every_route_with_a_parser_id_in_the_path_hides_a_temp_silos_parser(client, db, scene):
    """The metadata parser of a temp silo (its name carries the session id) answers like a missing parser."""
    parser = _temp_parser_id(db, scene)
    found = []
    for doc, prefix in (("/openapi-internal.json", "/internal"), ("/openapi-public.json", "/public/v1")):
        for path, operations in client.get(doc).json()["paths"].items():
            if _PARSER_PARAM.search(path) and ("/apps/{app_id}/" in path or "/app/{app_id}/" in path):
                full = path if path.startswith(prefix) else prefix + path
                found.extend((m.upper(), full, prefix) for m in operations if m in ("get", "put", "post", "patch"))
    assert found, "no route with a parser id: the enumeration is broken"
    offenders = []
    for method, template, prefix in found:
        headers = scene["alice"] if prefix == "/internal" else scene["api_key"]

        def call(parser_id):
            url = re.sub(r"\{app_id\}", str(scene["app_id"]), template)
            url = _PARSER_PARAM.sub(str(parser_id), url)
            r = client.request(method, url, headers=headers, json={"name": "x", "output_parser_id": parser_id})
            body = re.sub(rf"\b({parser}|{MISSING_ID})\b", "<ID>", r.text)
            return r.status_code, body

        temp, missing = call(parser), call(MISSING_ID)
        if temp != missing or temp[0] not in (400, 404, 405, 422):  # a rejection, never 200 / 5xx
            offenders.append((method, template, temp, missing))
    assert not offenders, offenders


def test_ids_sent_in_agent_bodies_answer_the_same_for_temp_and_missing(client, db, scene):
    """silo_id / output_parser_id in create / update bodies of the internal and public routers."""
    app_id = scene["app_id"]
    parser = _temp_parser_id(db, scene)
    silo = scene["temp_silo"]
    agent = AgentFactory(app=db.get(App, app_id))
    db.commit()
    cases = [
        ("POST", f"/internal/apps/{app_id}/agents/0", scene["alice"]),
        ("POST", f"/internal/apps/{app_id}/agents/{agent.agent_id}", scene["alice"]),
        ("POST", f"/public/v1/app/{app_id}/agents/", scene["api_key"]),
        ("PUT", f"/public/v1/app/{app_id}/agents/{agent.agent_id}", scene["api_key"]),
    ]
    offenders = []
    for method, url, headers in cases:
        for field, temp_id in (("silo_id", silo), ("output_parser_id", parser)):
            def call(value):
                r = client.request(method, url, headers=headers, json={"name": "probe-agent", field: value})
                return r.status_code, re.sub(rf"\b({temp_id}|{MISSING_ID})\b", "<ID>", r.text)

            temp, missing = call(temp_id), call(MISSING_ID)
            if temp != missing or missing[0] not in (400, 404, 422):  # a rejection, never 200 / 5xx
                offenders.append((method, url, field, temp, missing))
    assert not offenders, offenders
