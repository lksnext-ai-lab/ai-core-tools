"""AC-11: a new provider built only on ``connectors.core`` is picked up and passes the whole suite."""

import ast
import pathlib

import connectors
import pytest
from connectors import registry
from connectors.core.contracts import Direction

from . import dummy_provider
from .checks import DIRECTION_CHECKS, check_unconfigured_secret_fails_closed, run_check
from .dummy_provider import DummyEchoProvider
from .env import make_env

CASES = [(d, check) for d, checks in DIRECTION_CHECKS.items() for check in checks]


def test_dummy_is_not_registered_globally():
    assert "dummy_echo" not in registry.registered_keys()


def test_dummy_appears_in_both_directions_through_provider_registry(monkeypatch):
    dummy = DummyEchoProvider()
    make_env(monkeypatch, dummy)
    assert dummy in registry.list_output_providers()
    assert dummy in registry.list_providers(Direction.INBOUND)
    assert registry.get_output_provider("dummy_echo") is dummy
    assert "dummy_echo" in registry.registered_keys()
    assert {"teams_workflow", "webhook"} <= registry.registered_keys()  # shipped providers stay registered


def test_dummy_imports_only_core_and_the_ssrf_guard():
    tree = ast.parse(pathlib.Path(dummy_provider.__file__).read_text())
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and not node.level}
    imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    backend = pathlib.Path(connectors.__file__).resolve().parents[1]
    first_party = {p.stem for p in backend.iterdir() if (p.is_dir() and not p.name.startswith(("_", "."))) or p.suffix == ".py"}
    ours = {name for name in imported if name.split(".")[0] in first_party}
    assert ours
    assert {name for name in ours if not name.startswith("connectors.core")} == {"utils.ssrf_guard"}


@pytest.mark.asyncio
@pytest.mark.parametrize(("direction", "check"), CASES, ids=lambda v: v.__name__ if callable(v) else v.value)
async def test_dummy_conformance(direction, check, monkeypatch):
    dummy = DummyEchoProvider()
    assert direction in dummy.descriptor.directions
    await run_check(check, dummy, make_env(monkeypatch, dummy))


def test_dummy_inbound_round_trip():
    from connectors.core.inbound import RawInboundRequest

    dummy = DummyEchoProvider()
    raw = RawInboundRequest(
        method="POST", path="/x", headers={"x-echo-token": DummyEchoProvider.TEST_INBOUND_TOKEN, "x-echo-sender": "u1"},
        query={}, body=b"hello",
    )
    message = dummy.parse(dummy.verify(raw))
    assert (message.provider_key, message.sender_id, message.text) == ("dummy_echo", "u1", "hello")


def test_dummy_with_empty_secret_fails_closed():
    check_unconfigured_secret_fails_closed(DummyEchoProvider(""))
