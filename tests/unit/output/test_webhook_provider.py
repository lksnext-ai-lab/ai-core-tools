"""Generic signed webhook provider: validation, signing, streaming and outcome classification."""

import base64
import hashlib
import hmac

import httpx
import pytest

from output import teams_workflow
from output import webhook as module
from output.teams_workflow import DeliveryError

from .factories import HMAC_SECRET, WEBHOOK_URL


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(teams_workflow, "resolve_host", lambda host: ["20.1.2.3"])


class TestValidateWebhookUrl:
    def test_accepts_public_https_url(self):
        assert module.validate_webhook_url(f"  {WEBHOOK_URL}  ") == WEBHOOK_URL

    @pytest.mark.parametrize("url, message", [
        ("http://hooks.example.com/x", "HTTPS URL"),
        ("https://user:pass@hooks.example.com/x", "HTTPS URL"),
        ("https://hooks.example.com/x#fragment", "HTTPS URL"),
        ("https://hooks.example.com:8443/x", "port 443"),
    ])
    def test_rejects_unsafe_urls(self, url, message):
        with pytest.raises(ValueError, match=message):
            module.validate_webhook_url(url)

    @pytest.mark.parametrize("resolved, message", [
        (["127.0.0.1"], "private or reserved"),
        (["20.1.2.3", "169.254.169.254"], "private or reserved"),
        ([], "could not be resolved"),
    ])
    def test_rejects_non_public_targets(self, monkeypatch, resolved, message):
        monkeypatch.setattr(teams_workflow, "resolve_host", lambda host: resolved)
        with pytest.raises(ValueError, match=message):
            module.validate_webhook_url(WEBHOOK_URL)

    def test_rejects_unresolvable_hosts(self, monkeypatch):
        def fail(host):
            raise OSError("nxdomain")

        monkeypatch.setattr(teams_workflow, "resolve_host", fail)
        with pytest.raises(ValueError, match="could not be resolved"):
            module.validate_webhook_url(WEBHOOK_URL)


class TestValidateWebhookConfig:
    def test_defaults_to_hmac_and_normalises_flags(self):
        assert module.validate_webhook_config(None, {"signing_secret": HMAC_SECRET}) == {
            "schema_version": "1", "auth_mode": "hmac_sha256",
            "receiver_deduplicates": False, "include_attachments": False,
        }

    def test_accepts_bearer_and_none_modes(self):
        assert module.validate_webhook_config({"auth_mode": "bearer"}, {"bearer_token": "abc.DEF-123"})["auth_mode"] == "bearer"
        assert module.validate_webhook_config({"auth_mode": "none", "include_attachments": True}, None)["include_attachments"] is True

    @pytest.mark.parametrize("config, credentials, message", [
        ({"surprise": 1}, {}, "unsupported fields"),
        ({"schema_version": "2"}, {}, "schema version"),
        ({"auth_mode": "basic"}, {}, "authentication mode"),
        ({"auth_mode": "none", "receiver_deduplicates": "yes"}, {}, "true or false"),
        ({}, {"signing_secret": "not base64!"}, "base64"),
        ({}, {"signing_secret": base64.b64encode(b"short").decode()}, "32 random bytes"),
        ({}, {"signing_secret": HMAC_SECRET, "extra": "x"}, "32 random bytes"),
        ({"auth_mode": "bearer"}, {"bearer_token": ""}, "printable ASCII"),
        ({"auth_mode": "bearer"}, {"bearer_token": "has space"}, "printable ASCII"),
        ({"auth_mode": "bearer"}, {"bearer_token": "t", "other": "x"}, "only a bearer token"),
        ({"auth_mode": "none"}, {"bearer_token": "t"}, "does not accept credentials"),
    ])
    def test_rejects_invalid_settings(self, config, credentials, message):
        with pytest.raises(ValueError, match=message):
            module.validate_webhook_config(config, credentials)


def test_signature_covers_metadata_and_body_from_memory_or_file(tmp_path):
    key = b"k" * 32
    expected = hmac.new(key, b"evt.123.application/json.{}", hashlib.sha256).hexdigest()
    path = tmp_path / "body"
    path.write_bytes(b"{}")
    assert module._signature(key, "evt", "123", "application/json", b"{}", None) == expected
    assert module._signature(key, "evt", "123", "application/json", None, str(path)) == expected


@pytest.mark.asyncio
async def test_file_stream_yields_whole_file_in_chunks(tmp_path):
    path = tmp_path / "body"
    path.write_bytes(b"x" * (64 * 1024 + 10))
    chunks = [chunk async for chunk in module._file_stream(str(path))]
    assert [len(chunk) for chunk in chunks] == [64 * 1024, 10]


class FakeHttp:
    """Stands in for ``httpx.AsyncClient`` and records the streamed request."""

    def __init__(self, status=202, headers=None, error=None):
        self.status, self.headers, self.error = status, headers or {}, error
        self.request = None

    def __call__(self, **kwargs):
        self.client_kwargs = kwargs
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, *, headers, content):
        self.request = {"method": method, "url": url, "headers": headers, "content": content}
        return self

    @property
    def status_code(self):
        return self.status


def _send(**overrides):
    options = {
        "config": {"auth_mode": "hmac_sha256"}, "credentials": {"signing_secret": HMAC_SECRET},
        "event_id": "evt-1", "attempt_number": 2, "content_type": "application/json", "body": b"{}",
    }
    options.update(overrides)
    return module.WebhookProvider().send(WEBHOOK_URL, {"event_type": "task.run.succeeded"}, **options)


class TestSend:
    @pytest.fixture
    def http(self, monkeypatch):
        fake = FakeHttp()
        monkeypatch.setattr(module.httpx, "AsyncClient", fake)
        return fake

    @pytest.mark.asyncio
    async def test_signed_json_request(self, http):
        assert await _send() == {"http_status": 202, "event_id": "evt-1"}
        headers = http.request["headers"]
        expected = module._signature(base64.b64decode(HMAC_SECRET), "evt-1", headers["X-Mattin-Timestamp"],
                                     "application/json", b"{}", None)
        assert headers["X-Mattin-Signature"] == f"v1={expected}"
        assert headers["X-Mattin-Attempt"] == "2" and headers["Idempotency-Key"] == "evt-1"
        assert headers["Content-Length"] == "2" and http.request["content"] == b"{}"
        assert http.client_kwargs["follow_redirects"] is False and http.client_kwargs["trust_env"] is False

    @pytest.mark.asyncio
    async def test_bearer_request_streams_spooled_body(self, http, tmp_path):
        path = tmp_path / "body.multipart"
        path.write_bytes(b"multipart")
        await _send(config={"auth_mode": "bearer"}, credentials={"bearer_token": "tok"},
                    content_type="multipart/form-data; boundary=b", body=None, body_path=str(path))
        headers = http.request["headers"]
        assert headers["Authorization"] == "Bearer tok" and "X-Mattin-Signature" not in headers
        assert headers["Content-Length"] == "9"
        assert http.client_kwargs["timeout"].read == 120.0
        assert b"".join([chunk async for chunk in http.request["content"]]) == b"multipart"

    @pytest.mark.asyncio
    async def test_unauthenticated_request(self, http):
        await _send(config={"auth_mode": "none"}, credentials={})
        assert "Authorization" not in http.request["headers"] and "X-Mattin-Signature" not in http.request["headers"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("overrides, message", [
        ({"config": {"auth_mode": "basic"}}, "authentication mode"),
        ({"body": None}, "body is missing"),
    ])
    async def test_invalid_requests_fail_permanently(self, http, overrides, message):
        with pytest.raises(DeliveryError, match=message) as caught:
            await _send(**overrides)
        assert caught.value.kind == "permanent" and http.request is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status, deduplicates, kind", [
        (429, False, "retryable"),
        (503, False, "unknown"),
        (503, True, "retryable"),
        (408, False, "unknown"),
        (400, False, "permanent"),
    ])
    async def test_http_errors_are_classified(self, monkeypatch, status, deduplicates, kind):
        monkeypatch.setattr(module.httpx, "AsyncClient", FakeHttp(status=status, headers={"Retry-After": "9"}))
        with pytest.raises(DeliveryError) as caught:
            await _send(config={"auth_mode": "none", "receiver_deduplicates": deduplicates}, credentials={})
        assert (caught.value.kind, caught.value.http_status) == (kind, status)
        if status == 429:
            assert caught.value.retry_after == 9

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error, deduplicates, kind", [
        (httpx.ConnectTimeout("t"), False, "retryable"),
        (httpx.ConnectError("c"), False, "retryable"),
        (httpx.ReadTimeout("r"), False, "unknown"),
        (httpx.ReadTimeout("r"), True, "retryable"),
        (httpx.RemoteProtocolError("p"), False, "unknown"),
        (httpx.RemoteProtocolError("p"), True, "retryable"),
    ])
    async def test_transport_errors_are_classified(self, monkeypatch, error, deduplicates, kind):
        fake = FakeHttp()

        def fail(*args, **kwargs):
            raise error

        fake.stream = fail
        monkeypatch.setattr(module.httpx, "AsyncClient", fake)
        with pytest.raises(DeliveryError) as caught:
            await _send(config={"auth_mode": "none", "receiver_deduplicates": deduplicates}, credentials={})
        assert caught.value.kind == kind


def test_provider_validates_destination_and_secret():
    provider = module.WebhookProvider()
    assert provider.validate_secret(WEBHOOK_URL) == WEBHOOK_URL
    url, config = provider.validate_destination(WEBHOOK_URL, {"auth_mode": "none"}, None)
    assert url == WEBHOOK_URL and config["auth_mode"] == "none"
    assert provider.descriptor.supports_binary_attachments is True
