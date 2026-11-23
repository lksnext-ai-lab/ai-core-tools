"""App.chat_code_interpreter_enabled: the Chat code-interpreter opt-in, through the App settings API."""
from models.app_collaborator import CollaborationRole
from tests.integration.routers.internal._eos_helpers import member_headers


def put(client, app, headers, **fields):
    return client.put(f"/internal/apps/{app.app_id}", json={"name": app.name, **fields}, headers=headers)


def get(client, app, headers):
    return client.get(f"/internal/apps/{app.app_id}", headers=headers).json()


def test_default_is_false_set_read_and_omitted_keeps(client, fake_app, owner_headers):
    assert get(client, fake_app, owner_headers)["chat_code_interpreter_enabled"] is False
    resp = put(client, fake_app, owner_headers, chat_code_interpreter_enabled=True)
    assert resp.status_code == 200, resp.text
    assert resp.json()["chat_code_interpreter_enabled"] is True
    assert get(client, fake_app, owner_headers)["chat_code_interpreter_enabled"] is True
    # omitted on a later update keeps it
    resp = put(client, fake_app, owner_headers, enable_openai_api=True)
    assert resp.status_code == 200 and resp.json()["chat_code_interpreter_enabled"] is True
    assert put(client, fake_app, owner_headers, chat_code_interpreter_enabled=False).json()[
        "chat_code_interpreter_enabled"] is False


def test_explicit_null_is_a_422_and_changes_nothing(client, fake_app, owner_headers, db):
    put(client, fake_app, owner_headers, chat_code_interpreter_enabled=True)
    resp = put(client, fake_app, owner_headers, chat_code_interpreter_enabled=None)
    assert resp.status_code == 422, resp.text
    db.refresh(fake_app)
    assert fake_app.chat_code_interpreter_enabled is True


def test_viewer_and_editor_cannot_change_it_but_administrator_can(client, fake_app, owner_headers, db):
    for role in (CollaborationRole.VIEWER, CollaborationRole.EDITOR):
        headers = member_headers(db, fake_app, role)
        assert put(client, fake_app, headers, chat_code_interpreter_enabled=True).status_code == 403
    db.refresh(fake_app)
    assert fake_app.chat_code_interpreter_enabled is False
    headers = member_headers(db, fake_app, CollaborationRole.ADMINISTRATOR)
    resp = put(client, fake_app, headers, chat_code_interpreter_enabled=True)
    assert resp.status_code == 200 and resp.json()["chat_code_interpreter_enabled"] is True


# ---- lifecycle warning of the App default sandbox service (only while something uses it)

def _warnings(client, app, headers):
    return [(w["kind"], w["role"], w["lifecycle_status"]) for w in get(client, app, headers)["lifecycle_warnings"]]


def test_a_retiring_default_sandbox_warns_only_while_the_chat_switch_is_on(client, fake_app, owner_headers, db):
    from tests.integration.routers.internal._eos_helpers import future, sandbox_service

    service = sandbox_service(db, fake_app, "sbx-default", eos=future(3))
    fake_app.default_sandbox_service_id = service.service_id
    db.flush()
    assert _warnings(client, fake_app, owner_headers) == []  # nothing uses it
    assert put(client, fake_app, owner_headers, chat_code_interpreter_enabled=True,
               default_sandbox_service_id=service.service_id).status_code == 200
    assert _warnings(client, fake_app, owner_headers) == [("sandbox", "sandbox", "deprecated")]


def test_an_agent_inheriting_the_default_sandbox_also_counts(client, fake_app, owner_headers, db):
    from tests.integration.routers.internal._eos_helpers import future, make_agent, sandbox_service

    service = sandbox_service(db, fake_app, "sbx-default2", eos=future(3))
    fake_app.default_sandbox_service_id = service.service_id
    make_agent(db, fake_app, None, enable_code_interpreter=True)
    db.flush()
    assert _warnings(client, fake_app, owner_headers) == [("sandbox", "sandbox", "deprecated")]
