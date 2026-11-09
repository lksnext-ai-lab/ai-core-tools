"""Contract tests for the inbound provider primitives (definition only)."""

import copy
import pickle
from collections.abc import Mapping
from types import SimpleNamespace

import pytest
from connectors.core.contracts import Direction, InboundProvider, ProviderDescriptor
from connectors.core.inbound import (
    BaseInboundProvider,
    InboundMessage,
    RawInboundRequest,
    VerifiedRequest,
)
from connectors.core.messages import JsonValue

SECRET = "super-secret-value"


def _raw(secret: str = "ok") -> RawInboundRequest:
    return RawInboundRequest(
        method="POST", path="/x", headers={"x-test-secret": secret}, query={}, body=SECRET.encode(),
    )


class _Echo(BaseInboundProvider):
    descriptor = ProviderDescriptor(
        key="echo", name="Echo", directions=frozenset({Direction.INBOUND}), outbound=None,
    )

    def _authenticate(self, raw: RawInboundRequest) -> Mapping[str, JsonValue]:
        if raw.headers.get("x-test-secret") != "ok":
            raise PermissionError("bad secret")
        return {"user": "u1"}

    def _parse_verified(self, verified: VerifiedRequest) -> InboundMessage:
        return InboundMessage(
            provider_key=verified.provider_key, external_conversation_id="c", sender_id="u1",
            text=verified.request.body.decode(), attachments=(), event_id=None,
        )


class _Other(_Echo):
    descriptor = ProviderDescriptor(
        key="other", name="Other", directions=frozenset({Direction.INBOUND}), outbound=None,
    )


def test_direct_construction_rejected() -> None:
    with pytest.raises(TypeError):
        VerifiedRequest(_token=object(), provider_key="echo", request=_raw(), claims={})
    with pytest.raises(TypeError):  # missing token entirely
        VerifiedRequest(provider_key="echo", request=_raw(), claims={})  # type: ignore[call-arg]


def test_subclassing_rejected() -> None:
    with pytest.raises(TypeError):
        type("Sub", (VerifiedRequest,), {})


def test_immutable_and_not_copyable() -> None:
    vr = _Echo().verify(_raw())
    with pytest.raises(AttributeError):
        vr.provider_key = "x"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        vr.extra = 1  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        del vr.claims
    with pytest.raises(TypeError):
        vr.claims["user"] = "evil"  # type: ignore[index]
    with pytest.raises(TypeError):
        copy.copy(vr)
    with pytest.raises(TypeError):
        copy.deepcopy(vr)
    with pytest.raises(TypeError):
        pickle.dumps(vr)


def test_verify_and_parse_roundtrip() -> None:
    p = _Echo()
    vr = p.verify(_raw())
    assert isinstance(vr, VerifiedRequest)
    assert vr.provider_key == "echo"
    assert p.parse(vr).text == SECRET


def test_verify_bad_secret() -> None:
    with pytest.raises(PermissionError):
        _Echo().verify(_raw("nope"))


def test_parse_rejects_non_verified() -> None:
    with pytest.raises(TypeError):
        _Echo().parse(SimpleNamespace(provider_key="echo", request=_raw(), claims={}))  # type: ignore[arg-type]


def test_parse_rejects_other_provider() -> None:
    vr = _Other().verify(_raw())
    with pytest.raises(TypeError):
        _Echo().parse(vr)


def test_runtime_protocol() -> None:
    assert isinstance(_Echo(), InboundProvider)


def test_overriding_verify_or_parse_rejected() -> None:
    with pytest.raises(TypeError):
        class _Bad(_Echo):
            def verify(self, raw: RawInboundRequest) -> VerifiedRequest:  # type: ignore[override]
                raise AssertionError

    with pytest.raises(TypeError):
        class _Bad2(_Echo):
            def parse(self, verified: VerifiedRequest) -> InboundMessage:  # type: ignore[override]
                raise AssertionError


def test_repr_hides_secrets() -> None:
    raw = _raw(secret="ok")
    headers = {"x-test-secret": "ok", "authorization": "Bearer tok123"}
    vr = _Echo().verify(RawInboundRequest("POST", "/x", headers, {"k": "qv"}, b"body-secret"))
    for obj in (raw, vr, vr.request):
        text = repr(obj)
        for leaked in ("tok123", "body-secret", "qv", SECRET, "u1"):
            assert leaked not in text


def test_mixin_override_rejected() -> None:
    class _Mixin:
        def verify(self, raw: RawInboundRequest) -> VerifiedRequest:
            raise AssertionError

    with pytest.raises(TypeError):
        type("_M", (_Mixin, _Echo), {})


def test_reassignment_rejected() -> None:
    with pytest.raises(AttributeError):
        _Echo.verify = lambda self, raw: None  # type: ignore[method-assign,assignment]
    with pytest.raises(AttributeError):
        _Echo().parse = lambda v: None  # type: ignore[method-assign,assignment]


def test_async_authenticate_rejected() -> None:
    with pytest.raises(TypeError):
        class _Async(_Echo):
            async def _authenticate(self, raw: RawInboundRequest) -> Mapping[str, JsonValue]:  # type: ignore[override]
                return {"a": 1}


def _provider_returning(value: object, exc: Exception | None = None) -> BaseInboundProvider:
    class _P(_Echo):
        def _authenticate(self, raw: RawInboundRequest) -> Mapping[str, JsonValue]:
            if exc is not None:
                raise exc
            return value  # type: ignore[return-value]

    return _P()


def test_verify_fails_closed() -> None:
    with pytest.raises(PermissionError) as info:
        _provider_returning({}, ValueError("leaky detail")).verify(_raw())
    assert "leaky" not in str(info.value)
    with pytest.raises(PermissionError):
        _provider_returning({}).verify(_raw())
    with pytest.raises(PermissionError):
        _provider_returning(["x"]).verify(_raw())
    with pytest.raises(PermissionError):
        _provider_returning(None).verify(_raw())


def test_raw_request_snapshot_and_lowercase_headers() -> None:
    headers = {"X-Test-Secret": "ok"}
    query = {"a": "1"}
    vr = _Echo().verify(RawInboundRequest("POST", "/x", headers, query, b""))
    headers["X-Test-Secret"] = "changed"
    query["a"] = "2"
    assert vr.request.headers["x-test-secret"] == "ok"
    assert vr.request.query["a"] == "1"


def test_verify_stamps_descriptor_key() -> None:
    assert _Other().verify(_raw()).provider_key == "other"


def test_incomplete_subclass_cannot_instantiate() -> None:
    class _NoParse(BaseInboundProvider):
        descriptor = _Echo.descriptor

        def _authenticate(self, raw: RawInboundRequest) -> Mapping[str, JsonValue]:
            return {"a": 1}

    with pytest.raises(TypeError):
        _NoParse()  # type: ignore[abstract]


def test_dataclasses_immutable() -> None:
    with pytest.raises(AttributeError):
        _raw().method = "GET"  # type: ignore[misc]
    msg = InboundMessage("echo", None, None, None, (), None)
    with pytest.raises(AttributeError):
        msg.text = "x"  # type: ignore[misc]


def test_deepcopy_container_rejected() -> None:
    with pytest.raises(TypeError):
        copy.deepcopy([_Echo().verify(_raw())])


def test_raw_request_rejects_headers_differing_only_in_case():
    with pytest.raises(ValueError, match="duplicate inbound header"):
        RawInboundRequest(method="POST", path="/", headers={"X-Sig": "good", "x-sig": "evil"}, query={}, body=b"")
