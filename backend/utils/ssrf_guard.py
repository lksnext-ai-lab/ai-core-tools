"""Shared SSRF (server-side request forgery) guard.

This module is the **only** SSRF-defense implementation in the codebase (AC-30).
It was extracted from two previously duplicated copies:
``backend/tools/ai/workspaceTools.py`` (``_is_blocked_ip``, ``_validate_url_host``,
``_CGNAT_NETWORK``) and ``backend/services/sandbox_service_service.py``
(``_is_blocked_ip``, ``_extract_hostname``, ``_endpoint_is_disallowed``). Both call
sites now delegate to the functions below; their external behaviour, including
their differing policies, is unchanged. ``backend/routers/public/v1/openai.py``'s
remote-image fetch also delegates here.

Public API:
- ``is_blocked_ip``: the core IP-range check, including CGNAT (100.64.0.0/10),
  NAT64, Teredo, deprecated site-local and IPv4-compatible IPv6 ranges, and
  IPv4-mapped/6to4/Teredo-embedded IPv6 addresses, which Python's ``ipaddress``
  does not flag on its own.
- ``resolve_host`` / ``resolve_host_async``: DNS resolution via ``socket.getaddrinfo``.
- ``check_scheme_and_host``: cheap, non-resolving scheme/hostname/ASCII/port
  check for a full URL, returning a structured :class:`SsrfResult` (or
  ``None``). Safe to call inline, without a deadline.
- ``validate_url``: ``check_scheme_and_host`` plus a blocking resolved-host
  check for a full URL, returning a structured :class:`SsrfResult` (or
  ``None``).
- ``endpoint_is_disallowed``: bare ``host:port`` validation, as used by the sandbox
  "Test Connection" probe.
- ``fetch_bytes``: an async, size- and time-capped HTTP(S) fetch that pins every
  connection to a validated IP literal (closing the DNS-rebinding TOCTOU window)
  while still using the original hostname for TLS SNI and certificate verification.
  IP resolution and blocking happen entirely inside the network backend, on the
  running event loop and inside the overall deadline — never via a blocking
  ``socket.getaddrinfo`` call on the caller's path.

Error hierarchy: every error ``fetch_bytes`` can raise is a :class:`FetchError`,
so callers that only care about "did the fetch fail" can catch that one base
class. Callers that need to distinguish SSRF blocks (400-ish) from size caps
(413) or anything else should catch the specific subclasses first.
"""

from __future__ import annotations

import asyncio
import dataclasses
import ipaddress
import socket
import ssl
import urllib.parse
from typing import Iterable, Literal

import httpcore

from utils.logger import get_logger

logger = get_logger(__name__)

# RFC 6598 shared/CGNAT address space (100.64.0.0/10) — used by some cloud
# providers' metadata services (e.g. Alibaba Cloud's 100.100.100.200) and by
# carrier-grade NAT. Not covered by ipaddress.is_private/is_reserved in
# Python's stdlib, so it must be checked explicitly.
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")

# IPv6 ranges that can reach, or encode, a non-public destination and are not
# covered by ipaddress.is_private/is_reserved/is_loopback/is_link_local:
#  - 64:ff9b::/96 and 64:ff9b:1::/48: NAT64 well-known / translator-specific
#    prefixes, which embed an IPv4 address that itself needs checking, but the
#    whole prefix is blocked outright since it is never a normal public route;
#  - 2001::/32: Teredo tunneling, whose embedded (obfuscated) client address is
#    also unwrapped below as defense in depth;
#  - fec0::/10: deprecated IPv6 site-local, the IPv6 analogue of RFC 1918;
#  - ::/96: deprecated "IPv4-compatible" IPv6, which embeds an IPv4 address in
#    its low 32 bits (distinct from the ``::ffff:0:0/96`` IPv4-mapped range,
#    which ``ip.ipv4_mapped`` already covers).
_EXTRA_BLOCKED_V6_NETWORKS = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
    ipaddress.ip_network("2001::/32"),
    ipaddress.ip_network("fec0::/10"),
    ipaddress.ip_network("::/96"),
)

_ALLOWED_SCHEMES = ("http", "https")

_DEFAULT_TIMEOUT_S = 15.0
_DEFAULT_MAX_REDIRECTS = 3
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)
_MAX_CONNECT_TIMEOUT_S = 5.0

# Built once at import time and reused across calls: ssl.SSLContext is safe to
# share across concurrent connections (httpx/requests/urllib3 all do this),
# and this avoids repeating the (mildly expensive) default-context setup —
# including loading the system trust store — on every single fetch.
_SSL_CONTEXT = ssl.create_default_context()


class FetchError(Exception):
    """Base class for every error :func:`fetch_bytes` can raise."""


class SsrfBlockedError(FetchError):
    """Raised when a URL or host must not be reached because it targets a blocked address."""


class FetchTooLargeError(FetchError):
    """Raised when a fetched response exceeds the caller's size cap."""


class FetchStatusError(FetchError):
    """Raised when the response status is not 2xx, or a redirect is malformed."""


class TooManyRedirectsError(FetchError):
    """Raised when more than ``max_redirects`` hops occur."""


class FetchTransportError(FetchError):
    """Raised when the underlying TCP/TLS transport fails (connect, read, write, protocol)."""


class FetchTimeoutError(FetchError):
    """Raised when the fetch (including all redirects) exceeds its overall deadline."""


class FetchUnresolvableError(SsrfBlockedError):
    """Raised when a host (the original URL's, or a redirect target's) cannot be resolved at all.

    A subclass of :class:`SsrfBlockedError` rather than a sibling: callers that
    only distinguish "blocked" from "everything else" can keep catching
    :class:`SsrfBlockedError`. Callers that need to tell "DNS failed" apart
    from "resolved to a disallowed address" (to build a different message, as
    ``routers.public.v1.openai`` does) should catch this subclass first.
    """


class FetchInvalidURLError(FetchError):
    """Raised when a URL (or a redirect target) is structurally invalid.

    Covers non-ASCII URLs/redirect targets, out-of-range ports, and anything
    else that would otherwise surface as a raw ``ValueError``/``TypeError``/
    ``httpcore.UnsupportedProtocol`` instead of a :class:`FetchError`.
    """


@dataclasses.dataclass(frozen=True)
class FetchedFile:
    """Result of a guarded fetch."""

    content: bytes
    media_type: str | None
    filename: str | None
    final_url: str


@dataclasses.dataclass(frozen=True)
class SsrfResult:
    """A structured reason a URL must be rejected, returned by :func:`validate_url`."""

    reason: Literal["scheme", "unresolvable", "blocked"]
    message: str


def is_blocked_ip(ip: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if *ip* must not be reached by any SSRF-guarded code path.

    Blocks loopback, link-local, private, reserved, multicast, unspecified,
    CGNAT (100.64.0.0/10), NAT64, Teredo, deprecated IPv6 site-local and
    deprecated IPv4-compatible IPv6 addresses. IPv4-mapped, 6to4 and
    Teredo-embedded IPv6 addresses are unwrapped and the embedded IPv4 address
    is checked as well. An unparseable string is treated as blocked, rather
    than risk a bypass.
    """
    if isinstance(ip, str):
        try:
            ip = ipaddress.ip_address(ip)
        except ValueError:
            return True

    if ip.version == 6:
        for network in _EXTRA_BLOCKED_V6_NETWORKS:
            if ip in network:
                return True

        embedded = ip.ipv4_mapped or ip.sixtofour
        if embedded is None:
            teredo = ip.teredo
            if teredo is not None:
                _server, client = teredo
                embedded = client
        if embedded is not None and is_blocked_ip(embedded):
            return True

    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or (ip.version == 4 and ip in _CGNAT_NETWORK)
    )


def resolve_host(host: str) -> list[str]:
    """Resolve *host* to its IP literals via ``socket.getaddrinfo``.

    Raises:
        socket.gaierror: if the host cannot be resolved.
    """
    addr_infos = socket.getaddrinfo(host, None)
    return [sockaddr[0] for _family, _type, _proto, _canonname, sockaddr in addr_infos]


async def resolve_host_async(host: str) -> list[str]:
    """Async equivalent of :func:`resolve_host`, via the running loop's resolver."""
    loop = asyncio.get_running_loop()
    addr_infos = await loop.getaddrinfo(host, None)
    return [sockaddr[0] for _family, _type, _proto, _canonname, sockaddr in addr_infos]


def check_scheme_and_host(
    url: str,
    allowed_schemes: Iterable[str] = _ALLOWED_SCHEMES,
) -> SsrfResult | None:
    """Cheap, non-resolving check: scheme, hostname, ASCII-ness and port only.

    This never touches the network or a resolver, so it is safe to call
    outside any deadline (see :func:`fetch_bytes`, which only ever resolves
    inside the pinned backend, on the event loop, inside its own timeout).
    Callers validating a URL before fetching it (e.g.
    ``routers.public.v1.openai._validate_image_url``) should use this instead
    of :func:`validate_url` if they don't want (or can't afford) a blocking
    DNS resolution on their own call path.

    Also rejects non-ASCII URLs (e.g. IDN homograph tricks or stray unicode
    smuggled into a redirect ``Location``) and out-of-range ports, which
    would otherwise surface deeper in the stack as a raw exception rather
    than a structured result.
    """
    schemes = tuple(allowed_schemes)
    message = f"Only {'/'.join(schemes)} URLs are allowed"
    if not isinstance(url, str) or not url.isascii():
        return SsrfResult("scheme", "URL must be an ASCII http/https URL")
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return SsrfResult("scheme", message)
    if parsed.scheme not in schemes:
        return SsrfResult("scheme", message)
    if not parsed.hostname:
        return SsrfResult("scheme", message)
    try:
        _ = parsed.port  # Accessing this validates the port range (0-65535).
    except ValueError:
        return SsrfResult("scheme", "URL has an invalid port")
    return None


def validate_url(
    url: str,
    *,
    allowed_schemes: Iterable[str] = _ALLOWED_SCHEMES,
    allow_unresolvable: bool = False,
) -> SsrfResult | None:
    """Validate a candidate URL's scheme and resolved host.

    Args:
        url: The URL to validate before it is fetched.
        allowed_schemes: Schemes that may be used. Defaults to http/https.
        allow_unresolvable: If True, a DNS resolution failure is not an error
            (used by callers where an unresolvable host is not itself an SSRF
            signal, since the real request will fail naturally afterwards).

    Returns:
        A :class:`SsrfResult` if the URL must be rejected, otherwise ``None``.

    Note:
        This performs a blocking DNS resolution (``socket.getaddrinfo``). It is
        meant for callers validating a URL on their own time budget (e.g. a
        synchronous tool), not for use inside an async deadline — ``fetch_bytes``
        resolves asynchronously, inside the pinned backend, instead of calling
        this function per hop.
    """
    scheme_result = check_scheme_and_host(url, allowed_schemes)
    if scheme_result is not None:
        return scheme_result

    parsed = urllib.parse.urlparse(url)
    try:
        resolved_ips = resolve_host(parsed.hostname)
    except socket.gaierror as exc:
        if allow_unresolvable:
            return None
        return SsrfResult("unresolvable", f"Could not resolve host: {exc}")
    if not resolved_ips:
        if allow_unresolvable:
            return None
        return SsrfResult("unresolvable", "Could not resolve host")

    for ip_str in resolved_ips:
        if is_blocked_ip(ip_str):
            return SsrfResult("blocked", f"Refusing to reach disallowed host: {parsed.hostname}")
    return None


def endpoint_is_disallowed(endpoint: str | None, *, allow_unresolvable: bool) -> bool:
    """Return True if *endpoint* (a bare ``host:port`` or full URL) resolves to a blocked address.

    Mirrors the sandbox "Test Connection" policy. ``allow_unresolvable`` is
    keyword-only and has no default here deliberately: callers must state
    their policy explicitly. The sandbox caller passes ``True`` — a DNS
    failure is not itself an SSRF signal there, and the provider call will
    fail naturally afterwards. An endpoint that fails to parse at all (empty,
    or not even a valid ``host:port``/URL shape) fails **open** (returns
    False) regardless of ``allow_unresolvable``, matching the sandbox's
    original behaviour: a malformed string isn't itself an address to block,
    and the downstream provider call will reject it on its own.
    """
    endpoint = (endpoint or "").strip()
    if not endpoint:
        return False

    # urlsplit needs a "//" prefix to parse a bare "host:port" into netloc
    # instead of mistaking "host" for a URL scheme.
    candidate = endpoint if "//" in endpoint else f"//{endpoint}"
    try:
        hostname = urllib.parse.urlsplit(candidate).hostname
    except ValueError:
        return False
    if not hostname:
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        return is_blocked_ip(ip)
    except ValueError:
        pass  # Not a literal IP — resolve it below.

    try:
        resolved_ips = resolve_host(hostname)
    except (socket.gaierror, socket.timeout, UnicodeError):
        logger.debug("ssrf_guard: could not resolve host %r for endpoint check", hostname)
        return not allow_unresolvable

    for ip_str in resolved_ips:
        if is_blocked_ip(ip_str):
            return True
    return False


class _PinnedBackend(httpcore.AsyncNetworkBackend):
    """A network backend that pins every TCP connection to a validated IP literal.

    Composes the public ``httpcore.AnyIOBackend`` rather than subclassing any
    private module, so this class only depends on httpcore's public surface.

    ``connect_tcp`` resolves *host* itself (async, on the running loop — never
    a blocking call), rejects the connection outright if **any** resolved IP is
    blocked, and then dials the validated IPs in order (IPv4 first), falling
    back to the next one on a connect failure. This closes the DNS-rebinding
    TOCTOU window (NFR-5): the IPs that were validated are the IPs that are
    dialed. TLS still uses the original hostname for SNI and certificate
    verification, because httpcore's connection pool calls
    ``start_tls(ssl_context, server_hostname=...)`` with the origin's hostname,
    independently of which backend performed the TCP connect.
    """

    def __init__(self, *, connect_timeout_s: float = _MAX_CONNECT_TIMEOUT_S) -> None:
        self._inner = httpcore.AnyIOBackend()
        # Bounds each individual IP's connect attempt so a single blackholed
        # candidate (one that neither refuses nor completes) can't by itself
        # consume the whole fetch_bytes deadline before the next IP is tried.
        self._connect_timeout_s = connect_timeout_s

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            resolved_ips = await resolve_host_async(host)
        except socket.gaierror as exc:
            raise FetchUnresolvableError(f"Could not resolve host: {host}") from exc
        if not resolved_ips:
            raise FetchUnresolvableError(f"Could not resolve host: {host}")

        for ip_str in resolved_ips:
            if is_blocked_ip(ip_str):
                raise SsrfBlockedError(f"Refusing to connect to disallowed address for host: {host}")

        # De-dup, preserving resolver order, then try IPv4 literals before IPv6.
        unique_ips = list(dict.fromkeys(resolved_ips))
        unique_ips.sort(key=lambda ip_str: ipaddress.ip_address(ip_str).version)

        per_attempt_timeout = self._connect_timeout_s if timeout is None else min(timeout, self._connect_timeout_s)

        last_exc: Exception | None = None
        for ip_str in unique_ips:
            try:
                return await self._inner.connect_tcp(
                    ip_str,
                    port,
                    timeout=per_attempt_timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_exc = exc
                continue
        assert last_exc is not None  # unique_ips is non-empty whenever we reach here
        raise last_exc

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options=None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._inner.connect_unix_socket(path, timeout=timeout, socket_options=socket_options)

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def _content_type_without_params(headers: list[tuple[bytes, bytes]]) -> str | None:
    value = _header_value(headers, b"content-type")
    if value is None:
        return None
    return value.decode("latin-1").split(";", 1)[0].strip() or None


def _filename_from_content_disposition(headers: list[tuple[bytes, bytes]]) -> str | None:
    value = _header_value(headers, b"content-disposition")
    if value is None:
        return None
    disposition = value.decode("latin-1")
    for part in disposition.split(";"):
        part = part.strip()
        if part.lower().startswith("filename="):
            filename = part[len("filename="):].strip().strip('"')
            if filename:
                return filename
    return None


def _header_value(headers: list[tuple[bytes, bytes]], name: bytes) -> bytes | None:
    for header_name, value in headers:
        if header_name.lower() == name:
            return value
    return None


async def _fetch_bytes_inner(url: str, *, max_bytes: int, max_redirects: int, timeout_s: float) -> FetchedFile:
    connect_timeout_s = min(_MAX_CONNECT_TIMEOUT_S, timeout_s / 2)
    backend = _PinnedBackend(connect_timeout_s=connect_timeout_s)
    current_url = url

    async with httpcore.AsyncConnectionPool(network_backend=backend, ssl_context=_SSL_CONTEXT) as pool:
        for _hop in range(max_redirects + 1):
            scheme_result = check_scheme_and_host(current_url)
            if scheme_result is not None:
                raise SsrfBlockedError(scheme_result.message)

            # Ask for an unencoded body: we size-cap on raw bytes as they stream in,
            # and a compressed body would let a small transfer decompress far past
            # the cap downstream.
            async with pool.stream(b"GET", current_url, headers=[(b"accept-encoding", b"identity")]) as response:
                if response.status in _REDIRECT_STATUSES:
                    location = _header_value(response.headers, b"location")
                    if not location:
                        raise FetchStatusError("Redirect response missing Location header")
                    try:
                        location_str = location.decode("ascii")
                    except UnicodeDecodeError as exc:
                        raise FetchInvalidURLError("Redirect Location contains non-ASCII bytes") from exc
                    current_url = urllib.parse.urljoin(current_url, location_str)
                    if not current_url.isascii():
                        raise FetchInvalidURLError("Redirect target is not a valid ASCII URL")
                    continue

                if not 200 <= response.status < 300:
                    raise FetchStatusError(f"Fetch failed with status {response.status}")

                content_encoding = _header_value(response.headers, b"content-encoding")
                if content_encoding is not None and content_encoding.strip().lower() not in (b"", b"identity"):
                    raise FetchError(
                        f"Unsupported Content-Encoding: {content_encoding.decode('latin-1')!r}"
                    )

                content_length = _header_value(response.headers, b"content-length")
                if content_length is not None:
                    try:
                        parsed_length = int(content_length)
                    except ValueError:
                        parsed_length = None  # Malformed header: ignore, the stream cap still applies.
                    if parsed_length is not None and parsed_length >= 0 and parsed_length > max_bytes:
                        raise FetchTooLargeError(f"Response exceeds the maximum allowed size of {max_bytes} bytes")

                buffer = bytearray()
                async for chunk in response.aiter_stream():
                    buffer += chunk
                    if len(buffer) > max_bytes:
                        raise FetchTooLargeError(f"Response exceeds the maximum allowed size of {max_bytes} bytes")

                media_type = _content_type_without_params(response.headers)
                filename = _filename_from_content_disposition(response.headers)
                if not filename:
                    path = urllib.parse.urlparse(current_url).path
                    filename = path.rsplit("/", 1)[-1] or None

                return FetchedFile(
                    content=bytes(buffer),
                    media_type=media_type,
                    filename=filename,
                    final_url=current_url,
                )
        raise TooManyRedirectsError("Too many redirects")


async def fetch_bytes(
    url: str,
    *,
    max_bytes: int,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    max_redirects: int = _DEFAULT_MAX_REDIRECTS,
) -> FetchedFile:
    """Fetch *url*, following redirects manually with SSRF re-validation at each hop.

    Every connection is pinned to a validated IP literal (see ``_PinnedBackend``);
    DNS resolution happens asynchronously inside the backend, never as a
    blocking call on this coroutine's path. TLS verification is always on. The
    response body is capped at *max_bytes* while streaming, and
    ``Content-Length`` is pre-checked when present (a malformed header is
    ignored rather than trusted). The whole fetch, including every redirect
    hop and DNS resolution, is bounded by a single *timeout_s* deadline.

    Every error this function can raise is a :class:`FetchError`:

    Raises:
        SsrfBlockedError: the URL, or a redirect target, targets a blocked
            scheme or a resolved address that must not be reached.
        FetchUnresolvableError: (a subclass of ``SsrfBlockedError``) the host,
            or a redirect target's host, could not be resolved at all.
        FetchInvalidURLError: the URL, or a redirect target, is structurally
            invalid (non-ASCII, an out-of-range port, or an unsupported
            protocol surfaced by the transport).
        FetchTooLargeError: the response exceeds *max_bytes*.
        FetchStatusError: a non-2xx status, or a malformed redirect.
        TooManyRedirectsError: more than *max_redirects* hops occurred.
        FetchTransportError: the TCP/TLS transport failed (connect, read,
            write, or protocol error).
        FetchTimeoutError: the overall deadline was exceeded.
    """
    try:
        async with asyncio.timeout(timeout_s):
            return await _fetch_bytes_inner(url, max_bytes=max_bytes, max_redirects=max_redirects, timeout_s=timeout_s)
    except FetchError:
        # Already one of ours (including SsrfBlockedError/FetchUnresolvableError
        # raised from inside _PinnedBackend.connect_tcp) — propagate as-is.
        raise
    except TimeoutError as exc:
        # asyncio.timeout() raises the stdlib TimeoutError (not FetchError), so
        # it must be caught and wrapped like any other transport failure.
        raise FetchTimeoutError(f"Fetch of {url!r} exceeded {timeout_s}s") from exc
    except ssl.SSLError as exc:
        raise FetchTransportError(f"TLS error: {exc}") from exc
    except (
        httpcore.NetworkError,
        httpcore.TimeoutException,
        httpcore.ProtocolError,
        httpcore.ConnectionNotAvailable,
    ) as exc:
        raise FetchTransportError(str(exc)) from exc
    except httpcore.UnsupportedProtocol as exc:
        raise FetchInvalidURLError(str(exc)) from exc
    except (ValueError, TypeError) as exc:
        # Guards against anything structurally wrong with the URL that slipped
        # past check_scheme_and_host and surfaced as a raw exception deeper in
        # httpcore/urllib — fetch_bytes must only ever raise FetchError.
        raise FetchInvalidURLError(str(exc)) from exc
