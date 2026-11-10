"""Hermetic environment for the provider conformance checks (no real DNS, no network)."""

import asyncio
import logging
import socket
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager

import httpx
import pytest
from connectors import registry as connectors_registry
from connectors.core import http as core_http
from connectors.core.registry import ProviderRegistry
from utils import ssrf_guard

_REAL_ASYNC_CLIENT = httpx.AsyncClient  # captured at import, before any patching

Handler = Callable[[httpx.Request], httpx.Response]
Answers = Sequence[str] | Mapping[str, Sequence[str]]


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.rendered: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        # format() includes exc_text / traceback, which is where leaked URLs usually hide.
        self.rendered.append(logging.Formatter().format(record))


class ConformanceEnv:
    """What a check may touch: the provider registry plus fake DNS / HTTP / log capture."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, registry: ProviderRegistry) -> None:
        self.monkeypatch = monkeypatch
        self.registry = registry
        self._block_real_dns()

    # ---- registry -------------------------------------------------------------------------------
    @property
    def registered_keys(self) -> frozenset[str]:
        return self.registry.keys()

    # ---- DNS ------------------------------------------------------------------------------------
    def _block_real_dns(self) -> None:
        def sync_lookup(*args: object, **kwargs: object) -> list[object]:
            raise AssertionError("real DNS lookup attempted (socket.getaddrinfo)")

        async def loop_lookup(self: object, *args: object, **kwargs: object) -> list[object]:
            raise AssertionError("real DNS lookup attempted (loop.getaddrinfo)")

        self.monkeypatch.setattr(socket, "getaddrinfo", sync_lookup)
        self.monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", loop_lookup)
        self.monkeypatch.setattr(core_http, "resolve_host", lambda host: sync_lookup())

    def resolve_to(self, answers: Answers) -> None:
        """Synchronous DNS (``ensure_public_host``): the same answers for every host, or a host -> answers map."""

        def lookup(host: str) -> list[str]:
            if isinstance(answers, Mapping):
                if host not in answers:
                    raise socket.gaierror("nxdomain")
                return list(answers[host])
            return list(answers)

        self.monkeypatch.setattr(core_http, "resolve_host", lookup)

    def resolve_fails(self) -> None:
        self.resolve_to({})

    def async_dns_answers(self, *addresses: str) -> list[str]:
        """What the pinned transport's asynchronous resolver returns at send time; returns the hosts asked."""
        asked: list[str] = []

        async def resolve(host: str) -> list[str]:
            asked.append(host)
            return list(addresses)

        self.monkeypatch.setattr(ssrf_guard, "resolve_host_async", resolve)
        return asked

    # ---- HTTP -----------------------------------------------------------------------------------
    def mock_http(self, handler: Handler) -> list[httpx.Request]:
        """Route every ``httpx.AsyncClient`` through ``MockTransport``; returns the list of seen requests."""
        seen: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
            options = {k: v for k, v in kwargs.items() if k != "transport"}
            return _REAL_ASYNC_CLIENT(*args, transport=httpx.MockTransport(respond), **options)  # type: ignore[arg-type]

        self.monkeypatch.setattr(httpx, "AsyncClient", factory)
        return seen

    def real_http(self) -> None:
        """Undo ``mock_http``: the provider builds its genuine client (pinned SSRF transport)."""
        self.monkeypatch.setattr(httpx, "AsyncClient", _REAL_ASYNC_CLIENT)

    # ---- logs -----------------------------------------------------------------------------------
    @contextmanager
    def capture_logs(self) -> Iterator[list[str]]:
        """Collect every log record (any logger, DEBUG and up) as rendered text, including tracebacks."""
        handler = _Capture()
        root = logging.getLogger()
        previous = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            yield handler.rendered
        finally:
            root.removeHandler(handler)
            root.setLevel(previous)


def make_env(
    monkeypatch: pytest.MonkeyPatch, provider: object | None = None, *, register: bool = True,
) -> ConformanceEnv:
    """Environment over the shipped registry; with ``provider`` and ``register`` it is added through ``ProviderRegistry``
    (so descriptor/protocol validation applies) and ``connectors.registry`` is pointed at the new registry."""
    providers = {p.descriptor.key: p for p in connectors_registry.list_providers()}  # type: ignore[attr-defined]
    if provider is not None and register:
        providers[provider.descriptor.key] = provider  # type: ignore[attr-defined]
    registry = ProviderRegistry(providers)  # type: ignore[arg-type]
    monkeypatch.setattr(connectors_registry, "_REGISTRY", registry)
    return ConformanceEnv(monkeypatch, registry)
