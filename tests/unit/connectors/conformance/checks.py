"""Provider-neutral conformance checks: ``check_*(provider, env)`` raise ``AssertionError`` on violation.

Outbound checks apply to anything implementing ``OutboundProvider``; inbound checks to ``InboundProvider``.
``DIRECTION_CHECKS`` maps each direction to the checks every provider declaring it must pass.
"""

import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import httpx
from connectors.core.contracts import (
    Direction,
    InboundProvider,
    OutboundProvider,
    ProviderDescriptor,
    UpdatePolicy,
)
from connectors.core.errors import DeliveryError, ProviderNotFoundError
from connectors.core.inbound import (
    BaseInboundProvider,
    InboundMessage,
    RawInboundRequest,
    VerifiedRequest,
)
from connectors.core.messages import (
    DestinationExample,
    DestinationView,
    JsonValue,
    OutboundRequest,
)
from connectors.core.settings import DestinationSettingsBase

from .env import ConformanceEnv

PUBLIC_IPS = ("20.1.2.3",)
BLOCKED_ADDRESSES = (
    "10.0.0.1", "127.0.0.1", "169.254.169.254", "100.64.0.1", "0.0.0.0", "::1", "fd00::1", "fe80::1",
    "::ffff:127.0.0.1",
)
EVIL_URL = "https://evil.example.net/steal"


# ---------------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------------
def _expect_raises(exc_type: type[BaseException], call: Callable[[], Any], what: str) -> BaseException:
    """Return the raised exception; fail (AssertionError) when nothing or something else is raised."""
    try:
        call()
    except exc_type as exc:
        return exc
    except Exception as exc:
        raise AssertionError(f"{what}: expected {exc_type.__name__}, got {type(exc).__name__}") from exc
    raise AssertionError(f"{what}: expected {exc_type.__name__}, nothing was raised")


async def _expect_delivery_error(call: Callable[[], Awaitable[Any]], what: str) -> DeliveryError:
    try:
        await call()
    except DeliveryError as exc:
        return exc
    except Exception as exc:
        raise AssertionError(f"{what}: expected DeliveryError, got {type(exc).__name__}") from exc
    raise AssertionError(f"{what}: expected DeliveryError, send succeeded")


def _secrets_of(example: DestinationExample) -> list[str]:
    """Every fragment of the destination that must never surface: URL, path, query, query values, userinfo, credentials."""
    split = urlsplit(example.url)
    secrets = [example.url, *example.credentials.values()]
    if split.path not in ("", "/"):
        secrets.append(split.path)
    if split.query:
        secrets.append(split.query)
        secrets.extend(value for _, value in parse_qsl(split.query) if len(value) >= 4)
    if split.username:
        secrets.append(split.username)
    if split.password:
        secrets.append(split.password)
    return secrets


def _assert_no_secret(text: str, example: DestinationExample, where: str) -> None:
    for secret in _secrets_of(example):
        assert secret not in text, f"{where} leaks a secret value"


def make_request(
    example: DestinationExample, *, public_config: Mapping[str, JsonValue] | None = None, url: str | None = None,
) -> OutboundRequest:
    return OutboundRequest(
        url=url or example.url,
        payload={"event_id": "evt-conformance", "event_type": "destination.test"},
        public_config=example.public_config if public_config is None else public_config,
        credentials=example.credentials,
        event_id="evt-conformance", attempt_number=1, content_type="application/json", body=b"{}", body_path=None,
    )


def make_view(
    provider: OutboundProvider, example: DestinationExample, public_config: Mapping[str, JsonValue] | None = None,
) -> DestinationView:
    return DestinationView(
        app_id=1, name="n", provider_key=provider.descriptor.key, content_mode="result",
        public_config=example.public_config if public_config is None else public_config,
    )


def _variant(url: str, **parts: str) -> str:
    return urlunsplit(urlsplit(url)._replace(**parts))


def _same_url(seen: httpx.URL, url: str) -> bool:
    return seen.copy_with(fragment=None) == httpx.URL(url).copy_with(fragment=None)


# ---------------------------------------------------------------------------------------------------
# outbound checks
# ---------------------------------------------------------------------------------------------------
def _is_covariant(got: object, want: object) -> bool:
    """A narrower concrete return class is allowed (TypedDicts and generics only match by equality)."""
    try:
        return inspect.isclass(got) and inspect.isclass(want) and issubclass(got, want)
    except TypeError:
        return False


def check_protocol_and_signatures(provider: OutboundProvider, env: ConformanceEnv) -> None:
    assert isinstance(provider, OutboundProvider), "provider does not satisfy OutboundProvider"
    members = [n for n in vars(OutboundProvider) if not n.startswith("_") and callable(getattr(OutboundProvider, n))]
    assert "send" in members and "validate_destination" in members, "Protocol introspection found no methods"
    for name in members:
        try:
            expected = inspect.signature(getattr(OutboundProvider, name), eval_str=True)
            actual = inspect.signature(getattr(provider, name), eval_str=True)
        except NameError as exc:
            raise AssertionError(f"{name}: annotations cannot be resolved ({exc}); import every annotated name") from exc
        expected_params = list(expected.parameters.values())[1:]  # drop ``self``
        actual_params = list(actual.parameters.values())
        assert [(p.name, p.kind, p.default is p.empty) for p in actual_params] == [
            (p.name, p.kind, p.default is p.empty) for p in expected_params
        ], f"{name}: parameters differ from the Protocol"
        assert [p.annotation for p in actual_params] == [p.annotation for p in expected_params], (
            f"{name}: parameter types differ from the Protocol"
        )
        got, want = actual.return_annotation, expected.return_annotation
        assert got == want or _is_covariant(got, want), f"{name}: return type differs"
    assert inspect.iscoroutinefunction(provider.send), "send must be async"


def check_descriptor(provider: OutboundProvider, env: ConformanceEnv) -> None:
    descriptor = provider.descriptor
    assert descriptor.key and descriptor.name, "descriptor key/name missing"
    assert descriptor.directions, "directions is empty"
    assert Direction.OUTBOUND in descriptor.directions, "OUTBOUND missing from directions"
    assert descriptor.outbound is not None, "outbound capabilities missing"
    assert isinstance(descriptor.outbound.update_policy, UpdatePolicy), "update_policy is not an UpdatePolicy"
    assert descriptor.content_modes, "content_modes is empty"
    assert descriptor.key in env.registered_keys, "descriptor.key is not a registered key"


def check_unique_registration(provider: OutboundProvider, env: ConformanceEnv) -> None:
    key = provider.descriptor.key
    try:
        stored = env.registry.get_outbound(key)
    except ProviderNotFoundError as exc:
        raise AssertionError(f"provider '{key}' is not registered") from exc
    assert stored is provider, "registry returns a different instance for this key"
    assert stored.descriptor.key == key, "stored descriptor key differs from the registration key"
    same_key = [p for p in env.registry.list_outbound() if p.descriptor.key == key]
    assert len(same_key) == 1, "provider key is not unique in the registry"


def check_settings_roundtrip_and_strictness(provider: OutboundProvider, env: ConformanceEnv) -> None:
    example = provider.example_destination()
    settings = provider.parse_settings(example.public_config, example.credentials)
    assert isinstance(settings, DestinationSettingsBase)
    assert settings.public_config_json() == example.public_config, "public_config_json differs from the example"
    assert settings.credentials_json() == example.credentials, "credentials_json differs from the example"
    again = provider.parse_settings(settings.public_config_json(), settings.credentials_json())
    assert again == settings, "settings do not round-trip"
    marker = "unexpected-secret-marker"
    error = _expect_raises(
        ValueError, lambda: provider.parse_settings({**example.public_config, "unexpected_key": marker}, example.credentials),
        "extra public_config key",
    )
    assert marker not in str(error), "public_config error echoes the rejected value"
    error = _expect_raises(
        ValueError, lambda: provider.parse_settings(example.public_config, {**example.credentials, "unexpected_key": marker}),
        "extra credentials key",
    )
    _assert_no_secret(str(error), example, "credentials error")
    assert marker not in str(error), "credentials error echoes the rejected value"


def check_update_policy_invariants(provider: OutboundProvider, env: ConformanceEnv) -> None:
    capabilities = provider.descriptor.outbound
    assert capabilities is not None
    example = provider.example_destination()
    if capabilities.update_policy is not UpdatePolicy.ROTATE_URL_ONLY:
        return
    # ROTATE_URL_ONLY providers take no settings: URL rotation is validated with (None, None).
    assert example.public_config == {} and example.credentials == {}, "ROTATE_URL_ONLY provider has settings"
    for empty in ({}, None):
        settings = provider.parse_settings(empty, empty)
        assert settings.public_config_json() == {} and settings.credentials_json() == {}
    _expect_raises(ValueError, lambda: provider.parse_settings({"any_key": "x"}, {}), "ROTATE_URL_ONLY public_config key")
    _expect_raises(ValueError, lambda: provider.parse_settings({}, {"any_key": "x"}), "ROTATE_URL_ONLY credentials key")
    env.resolve_to(PUBLIC_IPS)
    validated = provider.validate_destination(example.url, None, None)
    assert validated.public_config == {} and validated.credentials == {}


def check_destination_validation(provider: OutboundProvider, env: ConformanceEnv) -> None:
    capabilities = provider.descriptor.outbound
    assert capabilities is not None
    example = provider.example_destination()
    split = urlsplit(example.url)
    host = split.hostname or ""

    def validate(url: str) -> object:
        return provider.validate_destination(url, example.public_config, example.credentials)

    env.resolve_to(PUBLIC_IPS)
    validated = validate(example.url)
    assert validated.url == example.url, "valid example URL was altered"  # type: ignore[attr-defined]
    structural = {
        "http scheme": _variant(example.url, scheme="http"),
        "ftp scheme": _variant(example.url, scheme="ftp"),
        "file scheme": _variant(example.url, scheme="file"),
        "user info": _variant(example.url, netloc=f"u:p@{split.netloc}"),
        "username-only user info": _variant(example.url, netloc=f"u@{split.netloc}"),
        "port 8443": _variant(example.url, netloc=f"{host}:8443"),
        "port 80": _variant(example.url, netloc=f"{host}:80"),
    }
    for label, url in structural.items():
        _expect_raises(ValueError, lambda url=url: validate(url), f"validate_destination must reject {label}")  # type: ignore[misc]
    fragment_url = _variant(example.url, fragment="frag")
    if capabilities.url_allows_fragment:
        validate(fragment_url)
    else:
        _expect_raises(ValueError, lambda: validate(fragment_url), "validate_destination must reject URL fragment")
    for address in BLOCKED_ADDRESSES:
        env.resolve_to({host: [address]})
        _expect_raises(ValueError, lambda: validate(example.url), f"validate_destination must reject host resolving to {address}")
    env.resolve_to({host: ["20.1.2.3", "10.0.0.1"]})
    _expect_raises(ValueError, lambda: validate(example.url), "validate_destination must reject mixed public/private DNS answers")
    env.resolve_fails()
    _expect_raises(ValueError, lambda: validate(example.url), "validate_destination must reject unresolvable host")


async def check_send_classification(provider: OutboundProvider, env: ConformanceEnv) -> None:
    capabilities = provider.descriptor.outbound
    assert capabilities is not None
    example = provider.example_destination()
    request = make_request(example)

    def respond(status: int, headers: dict[str, str] | None = None) -> list[httpx.Request]:
        return env.mock_http(lambda r: httpx.Response(status, headers=headers))

    def raising(exc_type: type[httpx.RequestError]) -> Callable[[httpx.Request], httpx.Response]:
        def handler(r: httpx.Request) -> httpx.Response:
            raise exc_type("simulated", request=r)

        return handler

    async def failure(what: str, req: OutboundRequest = request) -> DeliveryError:
        return await _expect_delivery_error(lambda: provider.send(req), what)

    with env.capture_logs() as logs:
        seen = respond(202)
        receipt = await provider.send(request)
        assert receipt["http_status"] == 202, "HTTP 202 must be reported as accepted"
        assert len(seen) == 1 and seen[0].method == "POST" and _same_url(seen[0].url, example.url), (
            "send must POST exactly once to the destination URL"
        )

        respond(400)
        error = await failure("HTTP 400")
        assert (error.kind, error.http_status) == ("permanent", 400), "HTTP 400 must be permanent"
        for text in (str(error), repr(error)):
            _assert_no_secret(text, example, "DeliveryError")

        respond(429, {"Retry-After": "9"})
        error = await failure("HTTP 429")
        assert error.kind == "retryable", "HTTP 429 must be retryable"
        assert error.retry_after == 9.0, "HTTP 429 must carry Retry-After"

        respond(503)
        error = await failure("HTTP 503")
        assert error.kind == "unknown", "5xx without receiver deduplication must be 'unknown'"

        env.mock_http(raising(httpx.ReadTimeout))
        error = await failure("read timeout")
        assert error.kind == "unknown", "read timeout without receiver deduplication must be 'unknown'"

        seen = env.mock_http(
            lambda r: httpx.Response(302, headers={"Location": EVIL_URL}) if r.url.host != "evil.example.net"
            else httpx.Response(200),
        )
        error = await failure("HTTP 302 redirect")
        assert len(seen) == 1, "send must not follow redirects (302 redirect was followed)"
        assert (error.kind, error.http_status) == ("permanent", 302), "HTTP 302 must be permanent"

        if capabilities.receiver_deduplication:
            assert example.deduplicating_public_config is not None, "receiver_deduplication needs a deduplicating example"
            dedup = example.deduplicating_public_config
            assert provider.receiver_deduplicates(dedup) is True, "deduplicating example does not deduplicate"
            dedup_request = make_request(example, public_config=dedup)
            respond(503)
            error = await failure("HTTP 503 (dedup)", dedup_request)
            assert error.kind == "retryable", "5xx with receiver deduplication must be 'retryable'"
            env.mock_http(raising(httpx.ReadTimeout))
            error = await failure("timeout (dedup)", dedup_request)
            assert error.kind == "retryable", "timeout with receiver deduplication must be 'retryable'"
        assert provider.receiver_deduplicates(example.public_config) is False, "plain example must not deduplicate"

        for exc_type in (httpx.ConnectTimeout, httpx.ConnectError):
            env.mock_http(raising(exc_type))
            error = await failure(exc_type.__name__)
            assert error.kind == "retryable", f"{exc_type.__name__} (nothing was sent) must be 'retryable'"
    for line in logs:
        _assert_no_secret(line, example, "log output during send")


def check_secrets_not_in_repr(provider: OutboundProvider, env: ConformanceEnv) -> None:
    example = provider.example_destination()
    env.resolve_to(PUBLIC_IPS)
    settings = provider.parse_settings(example.public_config, example.credentials)
    validated = provider.validate_destination(example.url, example.public_config, example.credentials)
    snapshot = provider.build_snapshot(make_view(provider, example))
    surfaces = {
        "repr(provider)": repr(provider),
        "repr(OutboundRequest)": repr(make_request(example)),
        "repr(settings)": repr(settings),
        "str(settings)": str(settings),
        "repr(ValidatedDestination)": repr(validated),
        "repr(DestinationExample)": repr(example),
        "snapshot": json.dumps(snapshot),
    }
    for where, text in surfaces.items():
        _assert_no_secret(text, example, where)


def check_snapshot(provider: OutboundProvider, env: ConformanceEnv) -> None:
    example = provider.example_destination()
    snapshot = provider.build_snapshot(make_view(provider, example))
    json.dumps(snapshot)  # must be JSON-serializable
    assert snapshot["provider_key"] == provider.descriptor.key, "snapshot provider_key differs from the descriptor"
    assert snapshot["name"] == "n" and snapshot["content_mode"] == "result", "snapshot name/content_mode wrong"
    assert provider.snapshot_public_config(snapshot) == example.public_config, "snapshot_public_config does not round-trip"


def check_snapshot_provider_key_not_overridable(provider: OutboundProvider, env: ConformanceEnv) -> None:
    example = provider.example_destination()
    hostile = {**example.public_config, "provider_key": "hijacked", "name": "hijacked", "content_mode": "hijacked"}
    snapshot = provider.build_snapshot(make_view(provider, example, hostile))
    assert snapshot["provider_key"] == provider.descriptor.key, "public_config overrides snapshot provider_key"
    assert snapshot["name"] == "n" and snapshot["content_mode"] == "result", "public_config overrides snapshot fields"


async def check_send_is_ssrf_guarded(provider: OutboundProvider, env: ConformanceEnv) -> None:
    """AC-17: DNS is re-validated at send time through the pinned transport (genuine httpx client)."""
    example = provider.example_destination()
    host = urlsplit(example.url).hostname
    env.resolve_to(PUBLIC_IPS)  # validation-time DNS is public: only the send-time answer is hostile (rebinding)
    env.real_http()
    with env.capture_logs() as logs:
        for address in ("10.0.0.1", "127.0.0.1", "169.254.169.254"):
            asked = env.async_dns_answers(address)
            error = await _expect_delivery_error(lambda: provider.send(make_request(example)), f"send to {address}")
            assert host in asked, "send did not consult the pinned transport's asynchronous resolver"
            assert error.kind == "permanent", f"send to {address} must be permanent, got {error.kind}"
            _assert_no_secret(str(error), example, "SSRF DeliveryError")
    for line in logs:
        _assert_no_secret(line, example, "log output during send")


OUTBOUND_CHECKS: tuple[Callable[..., Any], ...] = (
    check_protocol_and_signatures,
    check_descriptor,
    check_unique_registration,
    check_settings_roundtrip_and_strictness,
    check_update_policy_invariants,
    check_destination_validation,
    check_send_classification,
    check_secrets_not_in_repr,
    check_snapshot,
    check_snapshot_provider_key_not_overridable,
    check_send_is_ssrf_guarded,
)


# ---------------------------------------------------------------------------------------------------
# inbound checks
# ---------------------------------------------------------------------------------------------------
class _ForeignProvider(BaseInboundProvider):
    """Authenticates anything under another key: mints a genuine ``VerifiedRequest`` of a different provider."""

    descriptor = ProviderDescriptor(
        key="conformance_foreign", name="Foreign", directions=frozenset({Direction.INBOUND}), outbound=None,
    )

    def _authenticate(self, raw: RawInboundRequest) -> Mapping[str, JsonValue]:
        return {"who": "foreign"}

    def _parse_verified(self, verified: VerifiedRequest) -> InboundMessage:
        raise NotImplementedError


def _anonymous() -> RawInboundRequest:
    return RawInboundRequest(method="POST", path="/x", headers={}, query={}, body=b"{}")


def check_inbound_protocol(provider: InboundProvider, env: ConformanceEnv) -> None:
    assert isinstance(provider, InboundProvider), "provider does not satisfy InboundProvider"
    assert isinstance(provider, BaseInboundProvider), "inbound provider must derive from BaseInboundProvider"
    assert Direction.INBOUND in provider.descriptor.directions, "INBOUND missing from directions"
    assert provider.descriptor.key in env.registered_keys, "descriptor.key is not a registered key"


def check_parse_rejects_unverified(provider: InboundProvider, env: ConformanceEnv) -> None:
    for forged in (_anonymous(), {"provider_key": provider.descriptor.key}, None):
        _expect_raises(TypeError, lambda forged=forged: provider.parse(forged), f"parse({type(forged).__name__})")  # type: ignore[arg-type,misc]


def check_parse_rejects_foreign_verified(provider: InboundProvider, env: ConformanceEnv) -> None:
    foreign = _ForeignProvider().verify(_anonymous())
    assert isinstance(foreign, VerifiedRequest)
    _expect_raises(TypeError, lambda: provider.parse(foreign), "parse(VerifiedRequest of another provider)")


def check_verify_fails_closed(provider: InboundProvider, env: ConformanceEnv) -> None:
    _expect_raises(PermissionError, lambda: provider.verify(_anonymous()), "verify(anonymous request)")
    garbage = RawInboundRequest(
        method="POST", path="/x", headers={"authorization": "Bearer wrong", "x-signature": "bad"}, query={"token": "bad"},
        body=b"\xff\xfe",
    )
    _expect_raises(PermissionError, lambda: provider.verify(garbage), "verify(request with wrong credentials)")


def check_unconfigured_secret_fails_closed(unconfigured: InboundProvider) -> None:
    """Factory-level check: a provider built with an EMPTY secret must not let an empty credential through."""
    empty_header = RawInboundRequest(
        method="POST", path="/x", headers={"x-echo-token": ""}, query={}, body=b"{}",
    )
    for raw in (_anonymous(), empty_header):
        _expect_raises(PermissionError, lambda raw=raw: unconfigured.verify(raw), "verify with an unconfigured (empty) secret")


INBOUND_CHECKS: tuple[Callable[..., Any], ...] = (
    check_inbound_protocol,
    check_parse_rejects_unverified,
    check_parse_rejects_foreign_verified,
    check_verify_fails_closed,
)

DIRECTION_CHECKS: dict[Direction, tuple[Callable[..., Any], ...]] = {
    Direction.OUTBOUND: OUTBOUND_CHECKS,
    Direction.INBOUND: INBOUND_CHECKS,
}


async def run_check(check: Callable[..., Any], provider: object, env: ConformanceEnv) -> None:
    result = check(provider, env)
    if inspect.isawaitable(result):
        await result
