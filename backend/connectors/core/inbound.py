"""Inbound contract: raw requests, proof-of-verification wrapper and the provider base class.

A ``VerifiedRequest`` can only be minted by ``BaseInboundProvider.verify`` (module-private token), so
``parse`` can trust that the signature/authentication check actually ran.
"""

import inspect
from abc import ABCMeta, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, NoReturn, final

from connectors.core.messages import JsonValue

if TYPE_CHECKING:
    from connectors.core.contracts import ProviderDescriptor

_VERIFY_TOKEN = object()  # private sentinel: only verify() in this module passes it


@dataclass(frozen=True)
class RawInboundRequest:
    method: str
    path: str = field(repr=False)  # secrets may live in the path
    headers: Mapping[str, str] = field(repr=False)  # may carry signatures / bearer tokens
    query: Mapping[str, str] = field(repr=False)  # may carry tokens
    body: bytes = field(repr=False)

    def __post_init__(self) -> None:
        # Snapshot so later mutation of the caller's dicts cannot change what was verified.
        headers = {k.lower(): v for k, v in self.headers.items()}
        if len(headers) != len(self.headers):
            # Ambiguous: a proxy/router might read a different copy than the one verified.
            raise ValueError("duplicate inbound header names differing only in case")
        object.__setattr__(self, "headers", MappingProxyType(headers))
        object.__setattr__(self, "query", MappingProxyType(dict(self.query)))


@dataclass(frozen=True)
class InboundMessage:
    provider_key: str
    external_conversation_id: str | None
    sender_id: str | None = field(repr=False)
    text: str | None = field(repr=False)
    attachments: tuple[Mapping[str, JsonValue], ...] = field(repr=False)
    event_id: str | None


@final
class VerifiedRequest:
    """Proof that a ``RawInboundRequest`` passed ``InboundProvider.verify``. Immutable, not copyable/picklable.

    The private token guards against accidental construction, not deliberate in-process forgery.
    ``claims`` is frozen only at the top level (nested values stay mutable).
    """

    __slots__ = ("claims", "provider_key", "request")

    provider_key: str
    request: RawInboundRequest
    claims: Mapping[str, JsonValue]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("VerifiedRequest cannot be subclassed")

    def __init__(
        self, *, _token: object, provider_key: str, request: RawInboundRequest, claims: Mapping[str, JsonValue],
    ) -> None:
        if _token is not _VERIFY_TOKEN:
            raise TypeError("VerifiedRequest can only be created by InboundProvider.verify")
        object.__setattr__(self, "provider_key", provider_key)
        object.__setattr__(self, "request", request)
        object.__setattr__(self, "claims", MappingProxyType(dict(claims)))

    def __setattr__(self, name: str, value: object) -> NoReturn:
        raise AttributeError("VerifiedRequest is immutable")

    def __delattr__(self, name: str) -> NoReturn:
        raise AttributeError("VerifiedRequest is immutable")

    # Both pickle hooks and both copy hooks are blocked: each protocol consults a different one.
    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedRequest cannot be pickled")

    def __reduce_ex__(self, protocol: object) -> NoReturn:
        raise TypeError("VerifiedRequest cannot be pickled")

    def __copy__(self) -> NoReturn:
        raise TypeError("VerifiedRequest cannot be copied")

    def __deepcopy__(self, memo: object) -> NoReturn:
        raise TypeError("VerifiedRequest cannot be copied")

    def __repr__(self) -> str:
        return f"VerifiedRequest(provider_key={self.provider_key!r}, claims=<{len(self.claims)} claims>)"


_GUARDED = ("verify", "parse")


class _InboundMeta(ABCMeta):
    def __setattr__(cls, name: str, value: object) -> None:
        if name in _GUARDED:
            raise AttributeError(f"{name} cannot be reassigned")
        super().__setattr__(name, value)


class BaseInboundProvider(metaclass=_InboundMeta):
    """Base class: ``verify`` and ``parse`` are final; providers implement ``_authenticate``/``_parse_verified``.

    ``_authenticate`` must be synchronous, compare secrets in constant time (``hmac.compare_digest``), return at
    least one identifying claim and raise ``PermissionError`` on failure.
    """

    descriptor: "ProviderDescriptor"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for name in _GUARDED:
            if getattr(cls, name) is not getattr(BaseInboundProvider, name):
                raise TypeError(f"{cls.__name__} must not override {name}")
        if inspect.iscoroutinefunction(cls._authenticate):
            raise TypeError(f"{cls.__name__}._authenticate must be synchronous")

    def __setattr__(self, name: str, value: object) -> None:
        if name in _GUARDED:
            raise AttributeError(f"{name} cannot be reassigned")
        super().__setattr__(name, value)

    @abstractmethod
    def _authenticate(self, raw: RawInboundRequest) -> Mapping[str, JsonValue]:
        """Authenticate ``raw`` synchronously and return identifying claims; raise ``PermissionError`` on failure."""

    @abstractmethod
    def _parse_verified(self, verified: VerifiedRequest) -> InboundMessage:
        """Turn an already verified request into a neutral message."""

    @final
    def verify(self, raw: RawInboundRequest) -> VerifiedRequest:
        try:
            claims = self._authenticate(raw)
        except PermissionError:
            raise
        except Exception:  # noqa: BLE001 - fail closed, never leak provider error details
            raise PermissionError("inbound authentication failed") from None
        if not isinstance(claims, Mapping) or not claims:
            raise PermissionError("inbound authentication produced no claims")
        return VerifiedRequest(
            _token=_VERIFY_TOKEN, provider_key=self.descriptor.key, request=raw, claims=claims,
        )

    @final
    def parse(self, verified: VerifiedRequest) -> InboundMessage:
        if not isinstance(verified, VerifiedRequest):
            raise TypeError("parse requires a VerifiedRequest issued by verify")
        if verified.provider_key != self.descriptor.key:
            raise TypeError("VerifiedRequest was issued by a different provider")
        return self._parse_verified(verified)


__all__ = ["BaseInboundProvider", "InboundMessage", "RawInboundRequest", "VerifiedRequest"]
