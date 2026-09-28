import pytest

from output import teams_workflow as module


def test_webhook_url_requires_https_and_public_host(monkeypatch):
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("20.1.2.3", 443))])
    assert module.validate_webhook_url("https://prod.logic.azure.com/trigger?sig=secret") == "https://prod.logic.azure.com/trigger?sig=secret"

    with pytest.raises(ValueError, match="HTTPS"):
        module.validate_webhook_url("http://prod.logic.azure.com/trigger")

    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("10.0.0.8", 443))])
    with pytest.raises(ValueError, match="private or reserved"):
        module.validate_webhook_url("https://prod.logic.azure.com/trigger")


def test_card_has_result_and_authenticated_file_actions():
    card = module.build_adaptive_card(
        title="Daily report", status="succeeded", scheduled_time="2026-09-28T10:00:00Z",
        result="Report is ready", view_url="https://mattin.test/run/1",
        files=[{"filename": "report.csv", "url": "https://mattin.test/run/1/files/f1"}],
    )
    content = card["attachments"][0]["content"]
    assert card["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert content["actions"][0]["url"] == "https://mattin.test/run/1"
    assert content["actions"][1]["url"] == "https://mattin.test/run/1/files/f1"
    assert any("Report is ready" in block.get("text", "") for block in content["body"])


def test_card_bounds_result_excerpt():
    card = module.build_adaptive_card(
        title="Daily report", status="succeeded", scheduled_time="today",
        result="x" * 10000, view_url="https://mattin.test/run/1", content_mode="excerpt",
    )
    body_text = " ".join(block.get("text", "") for block in card["attachments"][0]["content"]["body"])
    assert len(body_text) < 5200
    assert "View result" in [action["title"] for action in card["attachments"][0]["content"]["actions"]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, expected_kind",
    [(429, "retryable"), (503, "unknown"), (400, "permanent")],
)
async def test_post_card_classifies_http_outcomes(monkeypatch, status, expected_kind):
    monkeypatch.setattr(module, "validate_webhook_url", lambda url: url)

    class FakeResponse:
        status_code = status
        headers = {"Retry-After": "7"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    with pytest.raises(module.DeliveryError) as caught:
        await module.post_card("https://prod.logic.azure.com/trigger", {"type": "message"})
    assert caught.value.kind == expected_kind
    if status == 429:
        assert caught.value.retry_after == 7


@pytest.mark.asyncio
async def test_post_card_accepts_2xx_without_persisting_response_body(monkeypatch):
    monkeypatch.setattr(module, "validate_webhook_url", lambda url: url)

    class FakeResponse:
        status_code = 202
        headers = {}
        text = "sensitive workflow response"

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    assert await module.post_card("https://prod.logic.azure.com/trigger", {"type": "message"}) == {"http_status": 202}


def test_provider_registry_exposes_teams_capabilities():
    from output.registry import get_output_provider, list_output_providers

    provider = get_output_provider("teams_workflow")
    assert provider.descriptor.supports_links is True
    assert provider.descriptor.supports_native_attachments is False
    assert [item.descriptor.key for item in list_output_providers()] == ["teams_workflow"]


def test_run_payload_never_publishes_file_scheme(monkeypatch):
    from types import SimpleNamespace
    from output.service import _run_payload

    monkeypatch.setenv("FRONTEND_URL", "https://mattin.example")
    task = SimpleNamespace(id=4, app_id=3, name="Daily")
    run = SimpleNamespace(
        id=12, scheduled_time=__import__("datetime").datetime(2026, 9, 28), status="succeeded",
        output_text="Open file://f-123 for details", output_files=[{"file_id": "f-123", "filename": "report.csv"}],
    )
    binding = SimpleNamespace(content_mode="result")
    payload = _run_payload(task, run, binding)
    serialized = str(payload)
    assert "file://" not in serialized
    assert "report.csv" in serialized
    assert "https://mattin.example/apps/3/scheduled-tasks/4/runs/12/files/f-123" in serialized
