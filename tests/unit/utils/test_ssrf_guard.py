"""Unit tests for ``utils.ssrf_guard``, the single shared SSRF-defense module.

No *external* network access is used anywhere here. A handful of tests spin up
a real ``http.server`` bound to ``127.0.0.1`` (loopback only, never leaves the
machine) to exercise ``fetch_bytes`` end-to-end, including ``_PinnedBackend``;
everything else mocks DNS resolution and/or the httpcore connection pool.
"""

import asyncio
import http.server
import ipaddress
import socket
import ssl
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock

import httpcore
import pytest

from utils import ssrf_guard


def _addr_info(ip: str):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return [(family, socket.SOCK_STREAM, 6, "", (ip, 0))]


# ---------------------------------------------------------------------------
# is_blocked_ip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "::1",
        "::ffff:127.0.0.1",
        "0.0.0.0",
        "224.0.0.1",
    ],
)
def test_blocked_ips_are_blocked(ip):
    assert ssrf_guard.is_blocked_ip(ip) is True


@pytest.mark.parametrize(
    "ip",
    [
        "64:ff9b::808:808",  # NAT64 well-known prefix (embeds 8.8.8.8)
        "64:ff9b:1::1",  # NAT64 translator-specific prefix
        "2001::1",  # Teredo tunneling
        "fec0::1",  # deprecated IPv6 site-local
        "::0.1.2.3",  # deprecated "IPv4-compatible" IPv6
    ],
)
def test_extra_ipv6_ranges_are_blocked(ip):
    assert ssrf_guard.is_blocked_ip(ip) is True


@pytest.mark.parametrize("ip", ["8.8.8.8", "93.184.216.34", "1.1.1.1", "2606:4700:4700::1111"])
def test_public_ips_are_allowed(ip):
    assert ssrf_guard.is_blocked_ip(ip) is False


def test_unparseable_ip_is_blocked():
    assert ssrf_guard.is_blocked_ip("not-an-ip") is True


# ---------------------------------------------------------------------------
# validate_url
# ---------------------------------------------------------------------------


def test_disallowed_scheme_is_rejected():
    result = ssrf_guard.validate_url("ftp://example.com/file")
    assert result is not None
    assert result.reason == "scheme"
    assert result.message == "Only http/https URLs are allowed"


def test_public_host_is_allowed(monkeypatch):
    monkeypatch.setattr(ssrf_guard, "resolve_host", lambda host: ["93.184.216.34"])
    assert ssrf_guard.validate_url("https://example.com/report.pdf") is None


def test_private_host_is_blocked(monkeypatch):
    monkeypatch.setattr(ssrf_guard, "resolve_host", lambda host: ["10.0.0.5"])
    result = ssrf_guard.validate_url("http://internal.example.com/file")
    assert result is not None
    assert result.reason == "blocked"
    assert "disallowed host" in result.message


def test_unresolvable_host_is_rejected_by_default(monkeypatch):
    def _raise(host):
        raise socket.gaierror("nope")

    monkeypatch.setattr(ssrf_guard, "resolve_host", _raise)
    result = ssrf_guard.validate_url("http://does-not-resolve.invalid/file")
    assert result is not None
    assert result.reason == "unresolvable"


def test_unresolvable_host_allowed_when_requested(monkeypatch):
    def _raise(host):
        raise socket.gaierror("nope")

    monkeypatch.setattr(ssrf_guard, "resolve_host", _raise)
    result = ssrf_guard.validate_url("http://does-not-resolve.invalid/file", allow_unresolvable=True)
    assert result is None


# ---------------------------------------------------------------------------
# endpoint_is_disallowed
# ---------------------------------------------------------------------------


def test_endpoint_is_disallowed_requires_allow_unresolvable_kwarg():
    with pytest.raises(TypeError):
        ssrf_guard.endpoint_is_disallowed("example.com")  # missing required kwarg


def test_endpoint_is_disallowed_for_private_literal():
    assert ssrf_guard.endpoint_is_disallowed("127.0.0.1:8080", allow_unresolvable=True) is True
    assert ssrf_guard.endpoint_is_disallowed("10.0.0.5:5432", allow_unresolvable=True) is True


def test_endpoint_is_disallowed_for_public_host(monkeypatch):
    monkeypatch.setattr(ssrf_guard, "resolve_host", lambda host: ["8.8.8.8"])
    assert ssrf_guard.endpoint_is_disallowed("https://8.8.8.8:8080", allow_unresolvable=True) is False


def test_endpoint_unresolvable_allowed_by_default(monkeypatch):
    def _raise(host):
        raise socket.gaierror("nope")

    monkeypatch.setattr(ssrf_guard, "resolve_host", _raise)
    assert ssrf_guard.endpoint_is_disallowed("this-does-not-resolve.invalid", allow_unresolvable=True) is False


def test_endpoint_unresolvable_rejected_when_disallowed(monkeypatch):
    def _raise(host):
        raise socket.gaierror("nope")

    monkeypatch.setattr(ssrf_guard, "resolve_host", _raise)
    assert ssrf_guard.endpoint_is_disallowed("this-does-not-resolve.invalid", allow_unresolvable=False) is True


def test_endpoint_empty_or_none_is_allowed():
    assert ssrf_guard.endpoint_is_disallowed(None, allow_unresolvable=True) is False
    assert ssrf_guard.endpoint_is_disallowed("", allow_unresolvable=True) is False


# ---------------------------------------------------------------------------
# _PinnedBackend.connect_tcp (mocked resolver and inner backend; no network)
# ---------------------------------------------------------------------------


async def test_pinned_backend_rejects_blocked_resolved_ip(monkeypatch):
    backend = ssrf_guard._PinnedBackend()

    async def _resolve(host):
        return ["10.0.0.5"]

    monkeypatch.setattr(ssrf_guard, "resolve_host_async", _resolve)

    with pytest.raises(ssrf_guard.SsrfBlockedError):
        await backend.connect_tcp("internal.example.com", 443)


async def test_pinned_backend_connects_to_ip_literal_not_hostname(monkeypatch):
    backend = ssrf_guard._PinnedBackend()

    async def _resolve(host):
        return ["93.184.216.34"]

    monkeypatch.setattr(ssrf_guard, "resolve_host_async", _resolve)
    fake_connect = AsyncMock(return_value="fake-stream")
    monkeypatch.setattr(backend._inner, "connect_tcp", fake_connect)

    stream = await backend.connect_tcp("example.com", 443, timeout=5.0)

    assert stream == "fake-stream"
    fake_connect.assert_called_once()
    called_host = fake_connect.call_args.args[0]
    assert called_host == "93.184.216.34"
    assert called_host != "example.com"


async def test_pinned_backend_dials_ipv4_before_ipv6(monkeypatch):
    backend = ssrf_guard._PinnedBackend()

    async def _resolve(host):
        return ["2606:4700:4700::1111", "93.184.216.34"]

    monkeypatch.setattr(ssrf_guard, "resolve_host_async", _resolve)
    fake_connect = AsyncMock(return_value="fake-stream")
    monkeypatch.setattr(backend._inner, "connect_tcp", fake_connect)

    await backend.connect_tcp("example.com", 443)

    called_host = fake_connect.call_args.args[0]
    assert called_host == "93.184.216.34"


async def test_pinned_backend_falls_back_to_next_ip_on_connect_failure(monkeypatch):
    backend = ssrf_guard._PinnedBackend()

    async def _resolve(host):
        return ["93.184.216.34", "1.1.1.1"]

    monkeypatch.setattr(ssrf_guard, "resolve_host_async", _resolve)

    attempted = []

    async def _inner_connect(host, port, timeout=None, local_address=None, socket_options=None):
        attempted.append(host)
        if host == "93.184.216.34":
            raise httpcore.ConnectError("boom")
        return "fake-stream"

    monkeypatch.setattr(backend._inner, "connect_tcp", _inner_connect)

    stream = await backend.connect_tcp("example.com", 443)

    assert attempted == ["93.184.216.34", "1.1.1.1"]
    assert stream == "fake-stream"


async def test_pinned_backend_reraises_last_error_when_all_ips_fail(monkeypatch):
    backend = ssrf_guard._PinnedBackend()

    async def _resolve(host):
        return ["93.184.216.34", "1.1.1.1"]

    monkeypatch.setattr(ssrf_guard, "resolve_host_async", _resolve)

    async def _inner_connect(host, port, timeout=None, local_address=None, socket_options=None):
        raise httpcore.ConnectTimeout(f"timeout for {host}")

    monkeypatch.setattr(backend._inner, "connect_tcp", _inner_connect)

    with pytest.raises(httpcore.ConnectTimeout, match="1.1.1.1"):
        await backend.connect_tcp("example.com", 443)


async def test_pinned_backend_raises_unresolvable_not_generic_blocked(monkeypatch):
    """FetchUnresolvableError (a SsrfBlockedError subclass) is raised for DNS
    failure, distinct from the generic SsrfBlockedError raised for an
    actually-resolved-but-blocked address, so callers can tell them apart."""
    backend = ssrf_guard._PinnedBackend()

    async def _resolve(host):
        raise socket.gaierror("nope")

    monkeypatch.setattr(ssrf_guard, "resolve_host_async", _resolve)

    with pytest.raises(ssrf_guard.FetchUnresolvableError):
        await backend.connect_tcp("does-not-resolve.invalid", 443)
    # It's also a SsrfBlockedError, for callers that only distinguish "blocked".
    with pytest.raises(ssrf_guard.SsrfBlockedError):
        await backend.connect_tcp("does-not-resolve.invalid", 443)


async def test_pinned_backend_bounds_each_connect_attempt(monkeypatch):
    """A blackholed first IP (connect neither refuses nor completes) must not
    by itself consume the whole per-fetch deadline: each attempt gets its own
    bounded timeout, derived from min(_MAX_CONNECT_TIMEOUT_S, timeout_s / 2)."""
    backend = ssrf_guard._PinnedBackend(connect_timeout_s=0.05)

    async def _resolve(host):
        return ["93.184.216.34", "1.1.1.1"]

    monkeypatch.setattr(ssrf_guard, "resolve_host_async", _resolve)

    seen_timeouts = []

    async def _inner_connect(host, port, timeout=None, local_address=None, socket_options=None):
        seen_timeouts.append(timeout)
        if host == "93.184.216.34":
            raise httpcore.ConnectTimeout("blackholed")
        return "fake-stream"

    monkeypatch.setattr(backend._inner, "connect_tcp", _inner_connect)

    stream = await backend.connect_tcp("example.com", 443, timeout=None)

    assert stream == "fake-stream"
    assert seen_timeouts == [0.05, 0.05]


# ---------------------------------------------------------------------------
# fetch_bytes: pure checks that never touch the network
# ---------------------------------------------------------------------------


async def test_fetch_bytes_rejects_disallowed_scheme():
    with pytest.raises(ssrf_guard.SsrfBlockedError):
        await ssrf_guard.fetch_bytes("ftp://example.com/file", max_bytes=1024)


async def test_fetch_bytes_rejects_out_of_range_port():
    with pytest.raises(ssrf_guard.SsrfBlockedError):
        await ssrf_guard.fetch_bytes("http://example.com:99999/x", max_bytes=1024)


async def test_fetch_bytes_rejects_non_ascii_url():
    with pytest.raises(ssrf_guard.FetchError):
        await ssrf_guard.fetch_bytes("http://exämple.com/x", max_bytes=1024)


async def test_fetch_bytes_unresolvable_host_raises_fetch_unresolvable_error(monkeypatch):
    async def _resolve_async(host):
        raise socket.gaierror("nope")

    monkeypatch.setattr(ssrf_guard, "resolve_host_async", _resolve_async)

    with pytest.raises(ssrf_guard.FetchUnresolvableError):
        await ssrf_guard.fetch_bytes("https://does-not-resolve.invalid/file", max_bytes=1024)


async def test_fetch_bytes_dns_rebinding_is_blocked_by_real_pool(monkeypatch):
    """Even if something upstream believed the host resolved publicly, the
    pinned backend resolves again at connect time, asynchronously, and blocks
    if that resolution lands on a private address. Uses the real httpcore
    pool (not a fake one) with only DNS resolution mocked, so no socket is
    ever actually opened to a real remote host."""

    monkeypatch.setattr(ssrf_guard, "resolve_host", lambda host: ["93.184.216.34"])

    async def _resolve_async(host):
        return ["10.0.0.5"]

    monkeypatch.setattr(ssrf_guard, "resolve_host_async", _resolve_async)

    with pytest.raises(ssrf_guard.SsrfBlockedError):
        await ssrf_guard.fetch_bytes("https://rebinding.example.test/file", max_bytes=1024)


# ---------------------------------------------------------------------------
# fetch_bytes: mocked pool (ssl_context plumbing, size cap, timeout wrapping)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status, headers=None, chunks=None):
        self.status = status
        self.headers = headers or []
        self._chunks = chunks or []

    async def aiter_stream(self):
        for chunk in self._chunks:
            yield chunk

    async def aclose(self):
        return None


class _StreamCM:
    """Mimics ``contextlib.asynccontextmanager``-wrapped ``pool.stream(...)``."""

    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc_info):
        await self._response.aclose()
        return False


class _FakePool:
    """Stands in for ``httpcore.AsyncConnectionPool`` in fetch_bytes tests."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.requested_urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def stream(self, method, url, headers=None):
        self.requested_urls.append(url)
        return self._next_stream()

    def _next_stream(self):
        raise NotImplementedError


def _patch_pool(monkeypatch, responses):
    captured = {}

    class _Pool(_FakePool):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            captured.update(kwargs)
            self._responses = list(responses)

        def _next_stream(self):
            return _StreamCM(self._responses.pop(0))

    monkeypatch.setattr(ssrf_guard.httpcore, "AsyncConnectionPool", _Pool)
    return captured


async def test_fetch_bytes_rejects_non_ascii_redirect_location(monkeypatch):
    non_ascii_location = "http://例え.com/evil".encode("utf-8")
    _patch_pool(monkeypatch, [_FakeResponse(302, headers=[(b"location", non_ascii_location)])])
    monkeypatch.setattr(ssrf_guard, "resolve_host", lambda host: ["93.184.216.34"])

    with pytest.raises(ssrf_guard.FetchError):
        await ssrf_guard.fetch_bytes("https://example.com/start", max_bytes=1024)


async def test_fetch_bytes_enforces_size_cap_without_content_length(monkeypatch):
    big_chunk = b"x" * 1024
    _patch_pool(monkeypatch, [_FakeResponse(200, headers=[], chunks=[big_chunk, big_chunk])])
    monkeypatch.setattr(ssrf_guard, "resolve_host", lambda host: ["93.184.216.34"])

    with pytest.raises(ssrf_guard.FetchTooLargeError):
        await ssrf_guard.fetch_bytes("https://example.com/big.bin", max_bytes=1500)


async def test_fetch_bytes_timeout_fires(monkeypatch):
    class _SlowStreamCM:
        async def __aenter__(self):
            await asyncio.sleep(0.2)
            return _FakeResponse(200, headers=[], chunks=[b"ok"])

        async def __aexit__(self, *exc_info):
            return False

    class _SlowPool(_FakePool):
        def _next_stream(self):
            return _SlowStreamCM()

    monkeypatch.setattr(ssrf_guard.httpcore, "AsyncConnectionPool", _SlowPool)
    monkeypatch.setattr(ssrf_guard, "resolve_host", lambda host: ["93.184.216.34"])

    with pytest.raises(ssrf_guard.FetchTimeoutError):
        await ssrf_guard.fetch_bytes("https://example.com/slow", max_bytes=1024, timeout_s=0.01)


async def test_fetch_bytes_success_returns_content_and_metadata_and_verifying_ssl_context(monkeypatch):
    responses = [
        _FakeResponse(
            200,
            headers=[(b"content-type", b"text/plain; charset=utf-8"), (b"content-length", b"5")],
            chunks=[b"hello"],
        ),
    ]
    captured = _patch_pool(monkeypatch, responses)
    monkeypatch.setattr(ssrf_guard, "resolve_host", lambda host: ["93.184.216.34"])

    result = await ssrf_guard.fetch_bytes("https://example.com/report.txt", max_bytes=1024)

    assert result.content == b"hello"
    assert result.media_type == "text/plain"
    assert result.filename == "report.txt"
    assert result.final_url == "https://example.com/report.txt"

    ssl_context = captured["ssl_context"]
    assert ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert ssl_context.check_hostname is True


async def test_fetch_bytes_sends_identity_accept_encoding(monkeypatch):
    captured_headers = {}

    class _Pool(_FakePool):
        def stream(self, method, url, headers=None):
            captured_headers["headers"] = headers
            self.requested_urls.append(url)
            return _StreamCM(_FakeResponse(200, headers=[], chunks=[b"ok"]))

    monkeypatch.setattr(ssrf_guard.httpcore, "AsyncConnectionPool", _Pool)
    monkeypatch.setattr(ssrf_guard, "resolve_host", lambda host: ["93.184.216.34"])

    await ssrf_guard.fetch_bytes("https://example.com/x", max_bytes=1024)

    assert (b"accept-encoding", b"identity") in captured_headers["headers"]


async def test_fetch_bytes_rejects_non_identity_content_encoding(monkeypatch):
    _patch_pool(
        monkeypatch,
        [_FakeResponse(200, headers=[(b"content-encoding", b"gzip")], chunks=[b"\x1f\x8b"])],
    )
    monkeypatch.setattr(ssrf_guard, "resolve_host", lambda host: ["93.184.216.34"])

    with pytest.raises(ssrf_guard.FetchError):
        await ssrf_guard.fetch_bytes("https://example.com/x.gz", max_bytes=1024)


# ---------------------------------------------------------------------------
# fetch_bytes: real local HTTP server over loopback (no external network)
# ---------------------------------------------------------------------------


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002 - matches BaseHTTPRequestHandler's signature
        pass

    def do_GET(self):  # noqa: N802 - matches BaseHTTPRequestHandler's naming convention
        if self.path == "/ok":
            body = b"hello world"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/chunked-big":
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            chunk = b"x" * 4096
            for _ in range(10):
                self.wfile.write(b"%x\r\n" % len(chunk))
                self.wfile.write(chunk + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
        elif self.path == "/content-length-big":
            self.send_response(200)
            self.send_header("Content-Length", str(100 * 1024 * 1024))
            self.end_headers()
            # Deliberately never send the (huge) body; the client must reject
            # based on the header alone, before reading further.
        elif self.path == "/redirect-blocked":
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/evil")
            self.end_headers()
        elif self.path == "/redirect-to-ok":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
        elif self.path == "/redirect-slow-chain":
            time.sleep(0.15)
            self.send_response(302)
            self.send_header("Location", "/redirect-slow-chain-2")
            self.end_headers()
        elif self.path == "/redirect-slow-chain-2":
            time.sleep(0.15)
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
        elif self.path == "/not-found":
            self.send_response(404)
            self.end_headers()
        elif self.path == "/gzip":
            body = b"not-really-gzipped-but-the-header-is-what-matters"
            self.send_response(200)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def local_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def allow_loopback(monkeypatch):
    """Let ``is_blocked_ip`` through for 127.0.0.1/::1 only, for these tests.

    Everything else (including the 169.254.169.254 target used by the
    redirect-to-blocked-host test below) still goes through the real check.
    """
    real_is_blocked_ip = ssrf_guard.is_blocked_ip

    def _patched(ip):
        candidate = ip
        if isinstance(candidate, str):
            try:
                candidate = ipaddress.ip_address(candidate)
            except ValueError:
                return real_is_blocked_ip(ip)
        if candidate.is_loopback:
            return False
        return real_is_blocked_ip(ip)

    monkeypatch.setattr(ssrf_guard, "is_blocked_ip", _patched)


def _url(local_server, path):
    port = local_server.server_address[1]
    return f"http://127.0.0.1:{port}{path}"


async def test_real_server_success(local_server, allow_loopback):
    result = await ssrf_guard.fetch_bytes(_url(local_server, "/ok"), max_bytes=1024)
    assert result.content == b"hello world"
    assert result.media_type == "text/plain"


async def test_real_server_redirect_is_followed(local_server, allow_loopback):
    result = await ssrf_guard.fetch_bytes(_url(local_server, "/redirect-to-ok"), max_bytes=1024)
    assert result.content == b"hello world"


async def test_real_server_chunked_body_over_cap_is_rejected(local_server, allow_loopback):
    with pytest.raises(ssrf_guard.FetchTooLargeError):
        await ssrf_guard.fetch_bytes(_url(local_server, "/chunked-big"), max_bytes=1024)


async def test_real_server_content_length_over_cap_is_rejected(local_server, allow_loopback):
    with pytest.raises(ssrf_guard.FetchTooLargeError):
        await ssrf_guard.fetch_bytes(_url(local_server, "/content-length-big"), max_bytes=1024)


async def test_real_server_redirect_to_blocked_host_is_rejected(local_server, allow_loopback):
    with pytest.raises(ssrf_guard.SsrfBlockedError):
        await ssrf_guard.fetch_bytes(_url(local_server, "/redirect-blocked"), max_bytes=1024)


async def test_real_server_non_2xx_status_is_rejected(local_server, allow_loopback):
    with pytest.raises(ssrf_guard.FetchStatusError):
        await ssrf_guard.fetch_bytes(_url(local_server, "/not-found"), max_bytes=1024)


async def test_real_server_non_identity_content_encoding_is_rejected(local_server, allow_loopback):
    with pytest.raises(ssrf_guard.FetchError):
        await ssrf_guard.fetch_bytes(_url(local_server, "/gzip"), max_bytes=1024)


async def test_real_server_too_many_redirects_is_rejected(local_server, allow_loopback):
    with pytest.raises(ssrf_guard.TooManyRedirectsError):
        await ssrf_guard.fetch_bytes(_url(local_server, "/redirect-slow-chain"), max_bytes=1024, max_redirects=0)


async def test_real_server_deadline_spans_all_hops(local_server, allow_loopback):
    """Two redirect hops each sleep 0.15s (~0.3s total); neither hop alone
    would exceed a 0.2s deadline, but the single overall deadline does."""
    with pytest.raises(ssrf_guard.FetchTimeoutError):
        await ssrf_guard.fetch_bytes(
            _url(local_server, "/redirect-slow-chain"), max_bytes=1024, timeout_s=0.2, max_redirects=3
        )


async def test_real_server_connection_refused_is_fetch_transport_error(allow_loopback):
    # Nothing listens here; a closed loopback port gives us a real connection
    # failure (ECONNREFUSED) without touching any external host.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    # Port is closed again as soon as the socket above is garbage-collected/closed.

    with pytest.raises(ssrf_guard.FetchTransportError):
        await ssrf_guard.fetch_bytes(f"http://127.0.0.1:{closed_port}/ok", max_bytes=1024, timeout_s=5.0)


# ---------------------------------------------------------------------------
# AC-30: utils.ssrf_guard must be the *only* SSRF-defense implementation
# ---------------------------------------------------------------------------


def test_no_duplicated_ssrf_logic_outside_ssrf_guard():
    """Guard against a new hand-rolled ``is_private``/``getaddrinfo`` SSRF
    check creeping back into the codebase outside ``utils.ssrf_guard``.

    ``socket.getaddrinfo`` as a *patch target* (the test-seam comments in
    ``workspaceTools.py`` and ``openai.py``) is allow-listed; those modules no
    longer call it themselves.
    """
    backend_root = Path(__file__).resolve().parents[3] / "backend"
    assert (backend_root / "utils" / "ssrf_guard.py").is_file()

    # openai.py no longer has its own socket.getaddrinfo patch seam (round 2):
    # its SSRF resolution now happens entirely inside fetch_bytes, so only
    # workspaceTools.py still needs a module-level `socket` import for its
    # existing tests to keep patching the real stdlib module.
    allowlisted_getaddrinfo_patch_seams = {
        backend_root / "tools" / "ai" / "workspaceTools.py",
    }

    offenders = []
    for path in backend_root.rglob("*.py"):
        if path == backend_root / "utils" / "ssrf_guard.py":
            continue
        if "/.claude/" in str(path) or "/__pycache__/" in str(path):
            continue
        text = path.read_text(encoding="utf-8")
        if "is_private" in text:
            offenders.append(f"{path}: contains 'is_private'")
        if "getaddrinfo" in text and path not in allowlisted_getaddrinfo_patch_seams:
            offenders.append(f"{path}: contains 'getaddrinfo'")

    assert not offenders, "Found SSRF-relevant logic outside utils.ssrf_guard:\n" + "\n".join(offenders)
