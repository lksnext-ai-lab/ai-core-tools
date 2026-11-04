"""
Regression tests for Fix B: the internal OCR endpoint never declared ``app_id`` or a
role dependency, so it had NO authorization at all beyond "is logged in" — any
authenticated user could run OCR through any OCR agent in the system (including
another tenant's agent and its vision/text AI service credentials), by only guessing
an ``agent_id``.

Endpoint under test:
  - POST /internal/apps/{app_id}/ocr/{agent_id}/process
"""

import io
from unittest.mock import AsyncMock

import pytest

from tests.factories import AppFactory, AIServiceFactory, UserFactory, configure_factories


def _editor_headers(fake_user, owner_headers):
    fake_user.platform_role = "editor"
    return owner_headers


@pytest.fixture
def fake_ocr_agent(db, fake_app, fake_ai_service):
    """An OCRAgent (type='ocr_agent') belonging to fake_app."""
    from models.ocr_agent import OCRAgent

    agent = OCRAgent(
        name="Test OCR Agent",
        description="",
        app_id=fake_app.app_id,
        service_id=fake_ai_service.service_id,
        vision_service_id=fake_ai_service.service_id,
        system_prompt="",
        has_memory=False,
        temperature=0.7,
    )
    db.add(agent)
    db.flush()
    return agent


@pytest.fixture
def other_app(db, fake_user):
    configure_factories(db)
    return AppFactory(owner_id=fake_user.user_id)


@pytest.fixture
def other_ocr_agent(db, other_app):
    from models.ocr_agent import OCRAgent

    configure_factories(db)
    ai_service = AIServiceFactory(app=other_app)
    agent = OCRAgent(
        name="Other App's OCR Agent",
        description="",
        app_id=other_app.app_id,
        service_id=ai_service.service_id,
        system_prompt="",
        has_memory=False,
        temperature=0.7,
    )
    db.add(agent)
    db.flush()
    return agent


@pytest.fixture
def unrelated_user_headers(db):
    """Auth headers for a user who has NO role on fake_app at all."""
    from utils.local_auth_tokens import mint_access_token

    configure_factories(db)
    other_user = UserFactory(email="ocr-outsider@mattin-test.com", name="OCR Outsider")
    db.flush()
    token, _ = mint_access_token(other_user.user_id, other_user.email, other_user.name)
    return {"Authorization": f"Bearer {token}"}


def _ocr_url(app_id: int, agent_id: int) -> str:
    return f"/internal/apps/{app_id}/ocr/{agent_id}/process"


def _pdf_file():
    return {"pdf_file": ("test.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}


class TestOcrRouterRequiresRole:
    def test_non_member_user_gets_403(
        self, client, fake_app, fake_ocr_agent, unrelated_user_headers, db
    ):
        """A user with no role on the app cannot invoke its OCR agent."""
        db.flush()
        response = client.post(
            _ocr_url(fake_app.app_id, fake_ocr_agent.agent_id),
            headers=unrelated_user_headers,
            files=_pdf_file(),
        )
        assert response.status_code == 403

    def test_requires_authentication(self, client, fake_app, fake_ocr_agent, db):
        db.flush()
        response = client.post(
            _ocr_url(fake_app.app_id, fake_ocr_agent.agent_id),
            files=_pdf_file(),
        )
        assert response.status_code in (401, 403)


class TestOcrRouterCrossAppScoping:
    def test_member_of_app_a_cannot_run_app_bs_ocr_agent(
        self, client, fake_app, other_ocr_agent, fake_user, owner_headers, db
    ):
        """OWNER of App A requesting App B's OCR agent via App A's path gets 404."""
        headers = _editor_headers(fake_user, owner_headers)
        db.flush()
        response = client.post(
            _ocr_url(fake_app.app_id, other_ocr_agent.agent_id),
            headers=headers,
            files=_pdf_file(),
        )
        assert response.status_code == 404

    def test_unknown_agent_id_returns_404(self, client, fake_app, fake_user, owner_headers, db):
        headers = _editor_headers(fake_user, owner_headers)
        db.flush()
        response = client.post(
            _ocr_url(fake_app.app_id, 9999999),
            headers=headers,
            files=_pdf_file(),
        )
        assert response.status_code == 404


class TestOcrRouterValidCall:
    def test_valid_call_reaches_execution(
        self, client, fake_app, fake_ocr_agent, fake_user, owner_headers, db, mocker
    ):
        """A same-app, authorized call passes the ownership check and reaches the
        execution service (mocked here — OCR processing itself is out of scope)."""
        headers = _editor_headers(fake_user, owner_headers)
        db.flush()
        mock_execute = mocker.patch(
            "services.agent_execution_service.AgentExecutionService.execute_agent_ocr",
            new=AsyncMock(
                return_value={
                    "result": {"content": "extracted"},
                    "agent_id": fake_ocr_agent.agent_id,
                    "extracted_text": "extracted",
                    "metadata": {"agent_name": fake_ocr_agent.name},
                }
            ),
        )

        response = client.post(
            _ocr_url(fake_app.app_id, fake_ocr_agent.agent_id),
            headers=headers,
            files=_pdf_file(),
        )

        assert response.status_code == 200
        assert response.json()["agent_id"] == fake_ocr_agent.agent_id
        mock_execute.assert_awaited_once()
