"""AC-15: the httpx URL-redaction filter is installed once and hides webhook credentials."""

import logging
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from connectors.core import http as core_http
from connectors.core.http import install_httpx_redaction
from connectors.providers.webhook import provider as module

SECRET_URL = "https://hooks.example.com/mattin?token=s3cr3t"


def test_install_httpx_redaction_is_idempotent():
    install_httpx_redaction()
    install_httpx_redaction()

    filters = [item for item in logging.getLogger("httpx").filters if isinstance(item, core_http._RedactHttpxRequestUrls)]
    assert len(filters) == 1


@pytest.mark.asyncio
async def test_webhook_send_does_not_log_url_or_token(monkeypatch, caplog):
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202)

    def factory(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(**kwargs)

    monkeypatch.setattr(core_http, "resolve_host", lambda host: ["20.1.2.3"])
    monkeypatch.setattr(httpx, "AsyncClient", factory)

    with caplog.at_level(logging.INFO, logger="httpx"):
        receipt = await module.WebhookProvider().send(
            SECRET_URL, {"event_type": "task.run.succeeded"},
            config={"schema_version": "1", "auth_mode": "none", "receiver_deduplicates": False, "include_attachments": False},
            credentials={}, event_id="evt-1", attempt_number=1, content_type="application/json", body=b"{}",
        )

    assert receipt["http_status"] == 202
    # Positive check: httpx did log the request, so the negative checks below are meaningful.
    assert "HTTP request completed (URL redacted)" in caplog.text
    assert "s3cr3t" not in caplog.text
    assert "hooks.example.com" not in caplog.text


@pytest.mark.parametrize(
    "module_name",
    ["connectors.providers.webhook.provider", "connectors.providers.teams_workflow.provider"],
)
def test_importing_a_provider_alone_installs_the_filter(module_name):
    """The filter must be installed by the import itself, in a clean interpreter."""
    backend_dir = Path(__file__).resolve().parents[3] / "backend"
    code = (
        "import logging, importlib\n"
        f"importlib.import_module({module_name!r})\n"
        "names = [type(f).__name__ for f in logging.getLogger('httpx').filters]\n"
        "assert names.count('_RedactHttpxRequestUrls') == 1, names\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=backend_dir,
        env={**os.environ, "PYTHONPATH": str(backend_dir)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
