import httpx
import openai
import pytest

from utils.provider_errors import ProviderErrorKind, classify_provider_error

LABEL = "Embedding service 'small'"


def _openai_error(cls, status: int, message: str):
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    response = httpx.Response(status, request=request)
    return cls(message, response=response, body=None)


def test_revoked_openai_key_is_auth_and_does_not_echo_the_key():
    exc = _openai_error(openai.AuthenticationError, 401, "Incorrect API key provided: sk-proj-***LRsA")
    error = classify_provider_error(exc, LABEL)
    assert error.kind is ProviderErrorKind.AUTH
    assert error.concerns_service
    assert LABEL in error.message
    assert "LRsA" not in error.message


@pytest.mark.parametrize("status, kind", [
    (403, ProviderErrorKind.AUTH),
    (429, ProviderErrorKind.RATE_LIMIT),
    (503, ProviderErrorKind.UNAVAILABLE),
])
def test_http_status_from_httpx_response(status, kind):
    request = httpx.Request("POST", "https://api.mistral.ai/v1/embeddings")
    exc = httpx.HTTPStatusError("boom", request=request, response=httpx.Response(status, request=request))
    assert classify_provider_error(exc, LABEL).kind is kind


def test_status_found_through_wrapping_exceptions():
    inner = _openai_error(openai.RateLimitError, 429, "quota")
    try:
        try:
            raise inner
        except Exception as e:
            raise RuntimeError("embedding batch failed") from e
    except RuntimeError as outer:
        error = classify_provider_error(outer, LABEL)
    assert error.kind is ProviderErrorKind.RATE_LIMIT
    assert error.concerns_service


def test_google_style_integer_code():
    class PermissionDenied(Exception):
        code = 403
    assert classify_provider_error(PermissionDenied("denied"), LABEL).kind is ProviderErrorKind.AUTH


def test_bedrock_error_codes():
    class ClientError(Exception):
        def __init__(self, code):
            super().__init__(code)
            self.response = {"Error": {"Code": code}}
    assert classify_provider_error(ClientError("UnrecognizedClientException"), LABEL).kind is ProviderErrorKind.AUTH
    assert classify_provider_error(ClientError("ThrottlingException"), LABEL).kind is ProviderErrorKind.RATE_LIMIT


def test_unavailable_does_not_concern_the_service_configuration():
    request = httpx.Request("POST", "https://x")
    exc = httpx.HTTPStatusError("x", request=request, response=httpx.Response(502, request=request))
    assert not classify_provider_error(exc, LABEL).concerns_service


def test_other_errors_name_the_step_not_the_service():
    error = classify_provider_error(ValueError("connection to vector store lost"), LABEL, step="Indexing")
    assert error.kind is ProviderErrorKind.OTHER
    assert not error.concerns_service
    assert error.message.startswith("Indexing failed (ValueError)")
    assert LABEL not in error.message


@pytest.mark.parametrize("text", [
    "(psycopg2.OperationalError) connection to server at \"db.internal\" (10.0.0.5), port 5432 failed [SQL: INSERT ...]",
    "404 Client Error for url: https://hf.example/models/x?token=SECRET-TOKEN",
])
def test_exception_text_never_reaches_the_message(text):
    error = classify_provider_error(RuntimeError(text), LABEL, step="Indexing")
    for leaked in ("SECRET", "[SQL", "db.internal", "10.0.0.5", "https://"):
        assert leaked not in error.message


def test_gemini_invalid_key_400_is_auth():
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/x:embedContent")
    exc = httpx.HTTPStatusError(
        "400 API key not valid. Please pass a valid API key. [reason: API_KEY_INVALID]",
        request=request, response=httpx.Response(400, request=request),
    )
    assert classify_provider_error(exc, LABEL).kind is ProviderErrorKind.AUTH


def test_plain_400_is_not_auth():
    request = httpx.Request("POST", "https://x")
    exc = httpx.HTTPStatusError("400 input too long", request=request, response=httpx.Response(400, request=request))
    assert classify_provider_error(exc, LABEL).kind is ProviderErrorKind.OTHER


def test_vector_store_http_errors_are_not_provider_errors():
    QdrantError = type("UnexpectedResponse", (Exception,), {"__module__": "qdrant_client.http.exceptions", "status_code": 401})
    assert classify_provider_error(QdrantError("unauthorized"), LABEL).kind is ProviderErrorKind.OTHER

