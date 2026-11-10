"""Negative controls: every assertion branch of every check must REJECT a deliberately broken provider.

Each control is a DummyEchoProvider variant with exactly one defect, and must fail with that defect's own message
(``match=``), so a check that silently asserts nothing -- or fails for the wrong reason -- is caught here.
"""

import dataclasses
import hmac
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse

import httpx
import pytest
from connectors.core import http as core_http
from connectors.core.contracts import UpdatePolicy
from connectors.core.errors import DeliveryError
from connectors.core.http import parse_retry_after, pinned_client
from connectors.core.inbound import InboundMessage
from connectors.core.messages import (
    DestinationExample,
    DestinationView,
    JsonDict,
    OutboundRequest,
    SendReceipt,
    ValidatedDestination,
)
from connectors.core.settings import DestinationSettingsBase
from utils.ssrf_guard import is_blocked_ip

from . import checks
from .checks import DIRECTION_CHECKS, check_unconfigured_secret_fails_closed, run_check
from .dummy_provider import DummyEchoProvider
from .env import make_env

_BASE = DummyEchoProvider.descriptor
_LOG = logging.getLogger("conformance.control")


def broken(**members: Any) -> DummyEchoProvider:
    """A DummyEchoProvider whose listed members are replaced."""
    return type("Broken", (DummyEchoProvider,), members)()


# ---- reusable defect builders ---------------------------------------------------------------------
def _validate_with(skip: tuple[str, ...] = (), dns: Callable[[list[str]], None] | None = None):
    """``validate_destination`` of the dummy with some rules switched off or a weaker DNS rule."""

    def validate_destination(self, url, public_config, credentials):
        parsed = urlparse(url)
        rules = {
            "scheme": parsed.scheme != "https",
            "userinfo": bool(parsed.username or parsed.password),
            "port": parsed.port not in (None, 443),
            "fragment": bool(parsed.fragment),
        }
        for rule, violated in rules.items():
            if violated and rule not in skip:
                raise ValueError(f"Dummy URL violates {rule}")
        if dns is not None:
            try:
                addresses = core_http.resolve_host(parsed.hostname or "")
            except OSError:
                addresses = None
            if addresses is not None:
                dns(addresses)
            elif "unresolved" not in skip:
                raise ValueError("unresolvable")
        else:
            core_http.ensure_public_host(parsed.hostname or "", "Dummy")
        settings = self.parse_settings(public_config, credentials)
        return ValidatedDestination(url, settings.public_config_json(), settings.credentials_json())

    return validate_destination


def _block_where(predicate: Callable[[str], bool]) -> Callable[[list[str]], None]:
    def rule(addresses: list[str]) -> None:
        if any(predicate(a) for a in addresses):
            raise ValueError("blocked")

    return rule


def _first_only(addresses: list[str]) -> None:
    if is_blocked_ip(addresses[0]):
        raise ValueError("blocked")


def _remap(rewrite: Callable[[DeliveryError], DeliveryError]) -> dict[str, Any]:
    """Replace ``send`` so every ``DeliveryError`` of the healthy dummy is rewritten."""

    async def send(self, request: OutboundRequest) -> SendReceipt:
        try:
            return await DummyEchoProvider.send(self, request)
        except DeliveryError as exc:
            replacement = rewrite(exc)
            raise replacement from exc

    return {"send": send}


def _with(exc: DeliveryError, **changes: Any) -> DeliveryError:
    fields: dict[str, Any] = {"kind": exc.kind, "http_status": exc.http_status, "retry_after": exc.retry_after}
    return DeliveryError(str(exc), **{**fields, **changes})


def _plain_send(*, follow_redirects: bool = False, all_errors_permanent: bool = False) -> dict[str, Any]:
    """A send that does NOT use the pinned transport (and optionally follows redirects)."""

    async def send(self, request: OutboundRequest) -> SendReceipt:
        dedup = request.public_config.get("receiver_deduplicates") is True
        try:
            async with httpx.AsyncClient(follow_redirects=follow_redirects) as client:
                response = await client.post(request.url, content=b"")
        except Exception as exc:
            if all_errors_permanent:
                raise DeliveryError("failed", kind="permanent") from exc
            if isinstance(exc, (httpx.ConnectTimeout, httpx.ConnectError)):
                raise DeliveryError("connect", kind="retryable") from exc
            raise DeliveryError("failed", kind="retryable" if dedup else "unknown") from exc
        status = response.status_code
        if 200 <= status < 300:
            return {"http_status": status}
        if status == 429:
            raise DeliveryError("throttled", kind="retryable", http_status=429, retry_after=parse_retry_after(response.headers.get("Retry-After")))
        if status >= 500:
            raise DeliveryError("server", kind="retryable" if dedup else "unknown", http_status=status)
        raise DeliveryError("rejected", kind="permanent", http_status=status)

    return {"send": send}


def _leaky_send(log: bool = False, in_error: bool = False) -> dict[str, Any]:
    async def send(self, request: OutboundRequest) -> SendReceipt:
        if log:
            _LOG.info("posting to %s", request.url)
        try:
            return await DummyEchoProvider.send(self, request)
        except DeliveryError as exc:
            if in_error:
                raise DeliveryError(f"{exc} at {request.url}", kind=exc.kind, http_status=exc.http_status, retry_after=exc.retry_after) from exc
            raise

    return {"send": send}


class _EmptySettings(DestinationSettingsBase):
    def public_config_json(self) -> JsonDict:
        return {}

    def credentials_json(self) -> dict[str, str]:
        return {}


def _lenient_empty_settings(self, public_config, credentials):
    return _EmptySettings()


def _credentials_leaking_parse(self, public_config, credentials):
    if set(credentials or {}) - {"api_key"}:
        raise ValueError(f"unsupported credentials: {dict(credentials)}")
    return DummyEchoProvider.parse_settings(self, public_config, credentials)


def _drop_unknown(public: bool, creds: bool):
    def parse_settings(self, public_config, credentials):
        keep_public = {k: v for k, v in (public_config or {}).items() if not public or k in {"prefix", "receiver_deduplicates"}}
        keep_creds = {k: v for k, v in (credentials or {}).items() if not creds or k == "api_key"}
        return DummyEchoProvider.parse_settings(self, keep_public, keep_creds)

    return {"parse_settings": parse_settings}


def _loud_validated(self, url, public_config, credentials):
    validated = DummyEchoProvider.validate_destination(self, url, public_config, credentials)

    class Loud(ValidatedDestination):
        def __repr__(self) -> str:
            return f"Loud({self.url}, {self.credentials})"

    return Loud(validated.url, validated.public_config, validated.credentials)


def _snapshot(override: bool = False):
    def build_snapshot(self, destination: DestinationView) -> JsonDict:
        reserved = {"provider_key": destination.provider_key, "name": destination.name, "content_mode": destination.content_mode}
        return {**reserved, **dict(destination.public_config)} if override else reserved

    return {"build_snapshot": build_snapshot}


async def _ssrf_leaks_low_level(self, request: OutboundRequest) -> SendReceipt:
    async with pinned_client(5.0) as client:  # no SsrfBlockedError translation
        response = await client.post(request.url, content=b"")
    return {"http_status": response.status_code}


async def _never_sends(self, request: OutboundRequest) -> SendReceipt:
    return {"http_status": 202}


def _sync_send(self, request: OutboundRequest) -> SendReceipt:
    raise NotImplementedError


def _bad_return(self, current_url: str, new_url: str) -> int:
    return 0


def _wrong_arity(self, current_url: str) -> None:
    return None


def _secret_repr(secret_of: Callable[[DestinationExample], str]):
    def __repr__(self) -> str:
        return f"Broken({secret_of(self.example_destination())})"

    return {"__repr__": __repr__}


def _ssrf_reason(exc: DeliveryError) -> bool:
    return exc.kind == "permanent" and exc.http_status is None


def _without_defence_in_descriptor(**changes: Any) -> dict[str, Any]:
    return {"descriptor": dataclasses.replace(_BASE, **changes)}


_ROTATE = dataclasses.replace(_BASE.outbound, update_policy=UpdatePolicy.ROTATE_URL_ONLY)


# ---- inbound doubles ------------------------------------------------------------------------------
class _NoParse:
    descriptor = DummyEchoProvider.descriptor

    def verify(self, raw):
        raise PermissionError


class _Lax:
    """Satisfies the Protocol but trusts anything: no fail-closed verify, no VerifiedRequest check in parse."""

    descriptor = DummyEchoProvider.descriptor

    def verify(self, raw):
        return raw

    def parse(self, verified):
        return InboundMessage("dummy_echo", None, None, None, (), None)


class _LaxBaseWithoutEmptyGuard(DummyEchoProvider):
    def _authenticate(self, raw):
        if not hmac.compare_digest(raw.headers.get("x-echo-token", "").encode(), self._inbound_token.encode()):
            raise PermissionError("bad token")
        return {"sender": "x"}


# ---- control table --------------------------------------------------------------------------------
@dataclass
class Control:
    check: Callable[..., Any]
    provider: Any
    match: str
    registered: bool = True  # False: leave it out of the registry (descriptor may then be invalid)
    registered_instance: Any = field(default=None)  # registry holds this instance instead of ``provider``

    @property
    def id(self) -> str:
        return self.check.__name__ + "-" + re.sub(r"\W+", "_", self.match)[:40]


def _only_blocks(prefix: str) -> Callable[[list[str]], None]:
    return _block_where(lambda a: a.startswith(prefix))


def _blocks_all_except(prefix: str) -> Callable[[list[str]], None]:
    return _block_where(lambda a: not a.startswith(prefix) and is_blocked_ip(a))


OUTBOUND_CONTROLS = [
    Control(checks.check_protocol_and_signatures, broken(ensure_same_endpoint=_wrong_arity), "ensure_same_endpoint: parameters differ"),
    Control(checks.check_protocol_and_signatures, broken(ensure_same_endpoint=_bad_return), "ensure_same_endpoint: return type differs"),
    Control(checks.check_protocol_and_signatures, broken(send=_sync_send), "send must be async"),
    Control(checks.check_descriptor, broken(**_without_defence_in_descriptor(directions=frozenset())), "directions is empty", registered=False),
    Control(checks.check_descriptor, broken(**_without_defence_in_descriptor(outbound=None)), "outbound capabilities missing", registered=False),
    Control(checks.check_descriptor, broken(**_without_defence_in_descriptor(content_modes=())), "content_modes is empty", registered=False),
    Control(checks.check_descriptor, DummyEchoProvider(), "descriptor.key is not a registered key", registered=False),
    Control(checks.check_unique_registration, DummyEchoProvider(), "is not registered", registered=False),
    Control(checks.check_unique_registration, DummyEchoProvider(), "different instance", registered_instance=DummyEchoProvider()),
    Control(checks.check_settings_roundtrip_and_strictness, broken(**_drop_unknown(public=True, creds=False)), "extra public_config key: expected ValueError"),
    Control(checks.check_settings_roundtrip_and_strictness, broken(**_drop_unknown(public=False, creds=True)), "extra credentials key: expected ValueError"),
    Control(checks.check_settings_roundtrip_and_strictness, broken(parse_settings=_credentials_leaking_parse), "credentials error leaks a secret value"),
    Control(checks.check_update_policy_invariants, broken(descriptor=dataclasses.replace(_BASE, outbound=_ROTATE)), "ROTATE_URL_ONLY provider has settings"),
    Control(
        checks.check_update_policy_invariants,
        broken(
            descriptor=dataclasses.replace(_BASE, outbound=_ROTATE), parse_settings=_lenient_empty_settings,
            example_destination=lambda self: DestinationExample("https://echo.example.com/x", {}, {}, None),
        ),
        "ROTATE_URL_ONLY public_config key: expected ValueError",
    ),
    Control(checks.check_destination_validation, broken(validate_destination=_validate_with(skip=("scheme",))), "reject http scheme"),
    Control(checks.check_destination_validation, broken(validate_destination=_validate_with(skip=("userinfo",))), "reject user info"),
    Control(checks.check_destination_validation, broken(validate_destination=_validate_with(skip=("port",))), "reject port 8443"),
    Control(checks.check_destination_validation, broken(validate_destination=_validate_with(skip=("fragment",))), "reject URL fragment"),
    Control(checks.check_destination_validation, broken(validate_destination=_validate_with(dns=_only_blocks("10."))), "reject host resolving to 127.0.0.1"),
    Control(checks.check_destination_validation, broken(validate_destination=_validate_with(dns=_block_where(lambda a: a == "127.0.0.1"))), "reject host resolving to 10.0.0.1"),
    Control(checks.check_destination_validation, broken(validate_destination=_validate_with(dns=_blocks_all_except("169.254."))), "reject host resolving to 169.254.169.254"),
    Control(checks.check_destination_validation, broken(validate_destination=_validate_with(dns=_blocks_all_except("100.64."))), "reject host resolving to 100.64.0.1"),
    Control(checks.check_destination_validation, broken(validate_destination=_validate_with(dns=_block_where(lambda a: ip_address(a).version == 4 and is_blocked_ip(a)))), "reject host resolving to ::1"),
    Control(checks.check_destination_validation, broken(validate_destination=_validate_with(dns=_first_only)), "reject mixed public/private DNS answers"),
    Control(checks.check_destination_validation, broken(validate_destination=_validate_with(dns=_block_where(is_blocked_ip), skip=("unresolved",))), "reject unresolvable host"),
    Control(checks.check_send_classification, broken(send=_never_sends), "send must POST exactly once"),
    Control(checks.check_send_classification, broken(**_remap(lambda e: _with(e, kind="retryable") if e.http_status == 400 else e)), "HTTP 400 must be permanent"),
    Control(checks.check_send_classification, broken(**_remap(lambda e: _with(e, retry_after=None) if e.http_status == 429 else e)), "HTTP 429 must carry Retry-After"),
    Control(checks.check_send_classification, broken(**_remap(lambda e: _with(e, kind="permanent") if e.http_status == 429 else e)), "HTTP 429 must be retryable"),
    Control(checks.check_send_classification, broken(**_remap(lambda e: _with(e, kind="retryable") if e.http_status == 503 else e)), "5xx without receiver deduplication"),
    Control(checks.check_send_classification, broken(**_remap(lambda e: _with(e, kind="permanent") if isinstance(e.__cause__, httpx.ReadTimeout) else e)), "read timeout without receiver deduplication"),
    Control(checks.check_send_classification, broken(**_remap(lambda e: _with(e, kind="unknown") if e.http_status == 503 and e.kind == "retryable" else e)), "5xx with receiver deduplication"),
    Control(checks.check_send_classification, broken(**_remap(lambda e: _with(e, kind="unknown") if isinstance(e.__cause__, httpx.ReadTimeout) and e.kind == "retryable" else e)), "timeout with receiver deduplication"),
    Control(checks.check_send_classification, broken(**_remap(lambda e: _with(e, kind="permanent") if isinstance(e.__cause__, httpx.ConnectTimeout) else e)), "ConnectTimeout (nothing was sent)"),
    Control(checks.check_send_classification, broken(**_remap(lambda e: _with(e, kind="unknown") if isinstance(e.__cause__, httpx.ConnectError) else e)), "ConnectError (nothing was sent)"),
    Control(checks.check_send_classification, broken(**_plain_send(follow_redirects=True)), "HTTP 302 redirect: expected DeliveryError"),
    Control(checks.check_send_classification, broken(**_remap(lambda e: _with(e, http_status=None) if e.http_status == 302 else e)), "HTTP 302 must be permanent"),
    Control(checks.check_send_classification, broken(**_leaky_send(in_error=True)), "DeliveryError leaks a secret value"),
    Control(checks.check_send_classification, broken(**_leaky_send(log=True)), "log output during send leaks a secret value"),
    Control(checks.check_secrets_not_in_repr, broken(**_secret_repr(lambda e: e.url)), "repr(provider) leaks"),
    Control(checks.check_secrets_not_in_repr, broken(**_secret_repr(lambda e: urlparse(e.url).path)), "repr(provider) leaks"),
    Control(checks.check_secrets_not_in_repr, broken(**_secret_repr(lambda e: urlparse(e.url).query)), "repr(provider) leaks"),
    Control(checks.check_secrets_not_in_repr, broken(**_secret_repr(lambda e: next(iter(e.credentials.values())))), "repr(provider) leaks"),
    Control(checks.check_secrets_not_in_repr, broken(validate_destination=_loud_validated), "repr(ValidatedDestination) leaks"),
    Control(checks.check_snapshot, broken(snapshot_public_config=lambda self, snapshot: {}), "snapshot_public_config does not round-trip"),
    Control(checks.check_snapshot, broken(build_snapshot=lambda self, d: {"provider_key": "other", "name": d.name, "content_mode": d.content_mode}), "snapshot provider_key differs"),
    Control(checks.check_snapshot_provider_key_not_overridable, broken(**_snapshot(override=True)), "public_config overrides snapshot provider_key"),
    Control(checks.check_send_is_ssrf_guarded, broken(send=_ssrf_leaks_low_level), "got SsrfBlockedError"),
    Control(checks.check_send_is_ssrf_guarded, broken(**_remap(lambda e: _with(e, kind="retryable") if _ssrf_reason(e) else e)), "must be permanent"),
    Control(checks.check_send_is_ssrf_guarded, broken(**_leaky_send(in_error=True)), "SSRF DeliveryError leaks a secret value"),
    Control(checks.check_send_is_ssrf_guarded, broken(**_leaky_send(log=True)), "log output during send leaks a secret value"),
    Control(checks.check_send_is_ssrf_guarded, broken(**_plain_send(all_errors_permanent=True)), "did not consult the pinned transport"),
]
INBOUND_CONTROLS = [
    Control(checks.check_inbound_protocol, _NoParse(), "does not satisfy InboundProvider", registered=False),
    Control(checks.check_inbound_protocol, _Lax(), "must derive from BaseInboundProvider", registered=False),
    Control(checks.check_parse_rejects_unverified, _Lax(), "parse(RawInboundRequest): expected TypeError", registered=False),
    Control(checks.check_parse_rejects_foreign_verified, _Lax(), "another provider", registered=False),
    Control(checks.check_verify_fails_closed, _Lax(), "verify(anonymous request): expected PermissionError", registered=False),
]


def _env(monkeypatch: pytest.MonkeyPatch, control: Control):
    if not control.registered:
        return make_env(monkeypatch)
    return make_env(monkeypatch, control.registered_instance or control.provider)


def test_every_check_has_a_negative_control():
    covered = {c.check.__name__ for c in OUTBOUND_CONTROLS + INBOUND_CONTROLS}
    assert covered == {check.__name__ for group in DIRECTION_CHECKS.values() for check in group}


@pytest.mark.asyncio
@pytest.mark.parametrize("control", OUTBOUND_CONTROLS + INBOUND_CONTROLS, ids=lambda c: c.id)
async def test_check_rejects_broken_provider(control: Control, monkeypatch):
    with pytest.raises(AssertionError, match=re.escape(control.match)):
        await run_check(control.check, control.provider, _env(monkeypatch, control))


def test_unconfigured_secret_check_rejects_provider_that_accepts_empty_credentials():
    with pytest.raises(AssertionError, match="unconfigured"):
        check_unconfigured_secret_fails_closed(_LaxBaseWithoutEmptyGuard(""))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "check", [c for group in DIRECTION_CHECKS.values() for c in group], ids=lambda c: c.__name__,
)
async def test_healthy_twin_passes(check, monkeypatch):
    """Guards the controls themselves: the unbroken base class passes every check."""
    healthy = DummyEchoProvider()
    await run_check(check, healthy, make_env(monkeypatch, healthy))
