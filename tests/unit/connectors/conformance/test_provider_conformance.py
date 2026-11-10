"""Every registered provider must pass every conformance check of each direction it declares (FR-10, FR-11)."""

import pytest
from connectors import registry as connectors_registry
from connectors.core.contracts import Direction

from .checks import DIRECTION_CHECKS, run_check
from .env import make_env

# (provider key, check name) -> reason. Strict xfail: delete the entry once the gap is fixed.
KNOWN_GAPS: dict[tuple[str, str], str] = {}


def _cases():
    for direction, checks in DIRECTION_CHECKS.items():
        for provider in connectors_registry.list_providers(direction):
            key = provider.descriptor.key  # type: ignore[attr-defined]
            for check in checks:
                gap = KNOWN_GAPS.get((key, check.__name__))
                marks = [pytest.mark.xfail(strict=True, reason=gap, raises=AssertionError)] if gap else []
                yield pytest.param(provider, check, id=f"{direction.value}-{key}-{check.__name__}", marks=marks)


CASES = list(_cases())


def test_every_direction_has_checks():
    assert set(DIRECTION_CHECKS) == set(Direction)


def test_every_declared_direction_runs_every_check():
    ran = {}
    for case in CASES:
        direction = case.id.split("-")[0]
        ran.setdefault((case.values[0].descriptor.key, direction), set()).add(case.values[1].__name__)
    declared = [
        (p.descriptor.key, d) for p in connectors_registry.list_providers() for d in p.descriptor.directions  # type: ignore[attr-defined]
    ]
    assert {"teams_workflow", "webhook"} <= {key for key, _ in declared}
    for key, direction in declared:
        assert ran[(key, direction.value)] == {c.__name__ for c in DIRECTION_CHECKS[direction]}, (key, direction)
    assert set(ran) == {(key, d.value) for key, d in declared}


def test_known_gaps_reference_real_checks():
    names = {check.__name__ for checks in DIRECTION_CHECKS.values() for check in checks}
    assert all(name in names for _, name in KNOWN_GAPS)


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider", "check"), CASES)
async def test_provider_conformance(provider, check, monkeypatch):
    await run_check(check, provider, make_env(monkeypatch))
