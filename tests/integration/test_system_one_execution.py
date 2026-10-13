"""AgentExecutionService.execute_agent_system_one against the real test DB (server call mocked)."""
import io
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from services.agent_execution_service import AgentExecutionService
from tests.integration.system_one_helpers import platform_editor  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("platform_editor")]

QUESTIONS = [{"key": "urgent", "type": "noul", "instructions": "Is it urgent?"}]
RAW = {"model": "nimble-latest", "usage": {"input_tokens": 10, "output_tokens": 2},
       "answers": {"urgent": {"type": "noul", "noul": 0.9}}}


@pytest.fixture
def agent(db, fake_app):
    from models.system_one_agent import SystemOneAgent
    from models.system_one_service import SystemOneService

    svc = SystemOneService(name="Nimble", endpoint="http://so.test", description="nimble-latest",
                           app_id=fake_app.app_id, create_date=datetime.now())
    db.add(svc)
    db.flush()
    a = SystemOneAgent(name="Triage", app_id=fake_app.app_id, system_one_service_id=svc.service_id,
                       questions=QUESTIONS, max_state_chars=6000, create_date=datetime.now())
    db.add(a)
    db.flush()
    return a


@pytest.fixture
def server():
    with patch("services.system_one_evaluator.system_one_client.evaluate", AsyncMock(return_value=RAW)) as ev, \
         patch("services.system_one_evaluator.record_agent_execution") as rec:
        yield ev, rec


def upload(name, data: bytes, content_type="text/plain"):
    return UploadFile(file=io.BytesIO(data), filename=name, headers={"content-type": content_type})


async def run(db, agent, text="call me", files=None, app_id=None, ctx=None):
    return await AgentExecutionService().execute_agent_system_one(
        agent.agent_id, text, files, ctx or {"user_id": 1}, db, app_id=app_id)


async def test_evaluates_the_text(db, agent, server):
    result = await run(db, agent, app_id=agent.app_id)
    assert result.answers["urgent"].decision is True
    ev, rec = server
    assert ev.await_args.args[1] == "call me" and rec.call_count == 1


async def test_text_files_are_read_and_added(db, agent, server):
    await run(db, agent, "see file", [upload("notes.txt", b"FILE BODY")])
    state = server[0].await_args.args[1]
    assert "see file" in state and "notes.txt" in state and "FILE BODY" in state


async def test_request_count_goes_up(db, agent, server):
    before = agent.request_count or 0
    await run(db, agent)
    db.refresh(agent)
    assert (agent.request_count or 0) == before + 1


async def test_agent_of_another_app_is_a_404(db, agent, server):
    with pytest.raises(HTTPException) as e:
        await run(db, agent, app_id=agent.app_id + 12345)
    assert e.value.status_code == 404
    server[0].assert_not_awaited()


async def test_unknown_or_other_type_agent_is_a_404(db, fake_agent, server):
    with pytest.raises(HTTPException) as e:
        await AgentExecutionService().execute_agent_system_one(fake_agent.agent_id, "x", None, {}, db)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        await AgentExecutionService().execute_agent_system_one(987654, "x", None, {}, db)
    assert e.value.status_code == 404


@pytest.mark.parametrize("name,ctype", [("photo.png", "image/png"), ("scan.JPG", "image/jpeg"), ("x.webp", "")])
async def test_images_are_rejected_not_ignored(db, agent, server, name, ctype):
    with pytest.raises(HTTPException) as e:
        await run(db, agent, "x", [upload(name, b"\x89PNG", ctype)])
    assert e.value.status_code == 400 and name in e.value.detail and "text only" in e.value.detail
    server[0].assert_not_awaited()


@pytest.fixture
def openai_agent(db, agent):
    agent.system_one_service.extra_config = '{"max_concurrency": 1, "provider": "openai_decisions"}'
    db.flush()
    return agent


async def test_an_openai_service_receives_png_and_jpeg_images_as_data_urls(db, openai_agent, server):
    await run(db, openai_agent, "", [upload("a.png", b"\x89PNG", "image/png"), upload("b.jpg", b"\xff\xd8", "image/jpg")])
    ev, rec = server
    images = ev.await_args.kwargs["images"]
    assert [i.split(";")[0] for i in images] == ["data:image/png", "data:image/jpeg"]
    assert rec.call_args.kwargs["event_overrides"]["had_images"] is True


@pytest.mark.parametrize("name,ctype", [("x.webp", "image/webp"), ("anim.gif", "image/gif")])
async def test_an_openai_service_rejects_other_image_formats(db, openai_agent, server, name, ctype):
    with pytest.raises(HTTPException) as e:
        await run(db, openai_agent, "x", [upload(name, b"data", ctype)])
    assert e.value.status_code == 400 and "PNG and JPEG" in e.value.detail and name in e.value.detail
    server[0].assert_not_awaited()


async def test_unreadable_attachments_are_named_in_a_400_instead_of_being_dropped(db, agent, server):
    with pytest.raises(HTTPException) as e:
        await run(db, agent, "x", [upload("ok.txt", b"fine"), upload("blob.bin", b"\xff\xfe\x00\x01", "application/octet-stream")])
    assert e.value.status_code == 400 and "blob.bin" in e.value.detail and "ok.txt" not in e.value.detail
    server[0].assert_not_awaited()


def _scanned_pdf() -> bytes:
    """A PDF whose page has no text layer (what a scan is): readable, but nothing to extract."""
    from pypdf import PdfWriter
    out = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.write(out)
    return out.getvalue()


async def test_an_attachment_with_no_extractable_text_is_named_even_when_other_text_exists(db, agent, server):
    # Otherwise "see attached" would be evaluated alone and the user would believe the scan had been read.
    with pytest.raises(HTTPException) as e:
        await run(db, agent, "see attached", [upload("scan.pdf", _scanned_pdf(), "application/pdf")])
    assert e.value.status_code == 400 and "scan.pdf" in e.value.detail and "extractable" in e.value.detail.lower()
    server[0].assert_not_awaited()


async def test_a_readable_attachment_next_to_one_without_text_still_names_only_the_empty_one(db, agent, server):
    with pytest.raises(HTTPException) as e:
        await run(db, agent, "x", [upload("ok.txt", b"fine"), upload("scan.pdf", _scanned_pdf(), "application/pdf")])
    assert "scan.pdf" in e.value.detail and "ok.txt" not in e.value.detail


async def test_empty_text_and_no_files_is_a_400(db, agent, server):
    with pytest.raises(HTTPException) as e:
        await run(db, agent, "  ")
    assert e.value.status_code == 400
    server[0].assert_not_awaited()


async def test_the_callers_api_key_never_reaches_the_logs(db, agent, server):
    """The app logger does not propagate to caplog, so the calls to the module logger are inspected directly."""
    ctx = {"user_id": "apikey_abc", "app_id": agent.app_id, "api_key": "SUPER-SECRET-API-KEY-123"}
    with patch("services.agent_execution_service.logger") as log, patch("services.system_one_evaluator.logger") as log2:
        await run(db, agent, "call me", ctx=ctx, app_id=agent.app_id)
    written = [str(c) for mock in (log, log2) for c in mock.mock_calls]
    assert "SUPER-SECRET-API-KEY-123" not in " ".join(written)
