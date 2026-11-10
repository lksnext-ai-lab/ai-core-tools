"""Import isolation (AC-13): the connector package may only depend on an explicit allowlist of first-party
modules, and every refactored module must import cleanly on its own in a fresh interpreter (no load-time
cycles).

Every check runs in its own clean interpreter, but all interpreters are launched concurrently from the
module-scoped ``results`` fixture, so wall time is roughly the slowest single import.  Tests only read the
stored results.

Hermeticity: ``PYTHONDONTWRITEBYTECODE`` and ``PYTHONHASHSEED`` are pinned, and ``PYTHON_DOTENV_DISABLED=1``
(python-dotenv >= 1.2) stops ``load_dotenv()`` in ``config.py`` & co. from reading ``backend/.env``; the
variables pytest-env injects (SECRET_KEY, ...) are inherited from this process.
"""

from __future__ import annotations

import os
import pkgutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import connectors
import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"

# First-party names that may be loaded as a side effect of importing connectors (besides connectors.*).
_ALLOWED_FIRST_PARTY = ("connectors", "utils", "utils.logger", "utils.ssrf_guard")


def _first_party() -> list[str]:
    names = {p.name for p in _BACKEND.iterdir() if p.is_dir() and any(p.rglob("*.py")) and p.name != "__pycache__"}
    names |= {p.stem for p in _BACKEND.glob("*.py")}
    return sorted(names)


def _connector_modules() -> list[str]:
    return ["connectors", *sorted(m.name for m in pkgutil.walk_packages(connectors.__path__, "connectors."))]


def _output_channel_modules() -> list[str]:
    return sorted(
        "services.output_channels" if p.stem == "__init__" else f"services.output_channels.{p.stem}"
        for p in (_BACKEND / "services" / "output_channels").glob("*.py")
    )


_CONNECTOR_MODULES = _connector_modules()
_CORE_MODULES = [m for m in _CONNECTOR_MODULES if m == "connectors" or m.startswith("connectors.core")]
_CLEAN_IMPORT_MODULES = [
    *_output_channel_modules(), "services.scheduled_task_service", "scheduling.output_delivery",
    "routers.internal.output_providers",
]


def _allowlist_check(modules: list[str], allowed_connector_prefixes: tuple[str, ...]) -> str:
    return (
        "import importlib, sys\n"
        f"for m in {modules!r}:\n    importlib.import_module(m)\n"
        f"fp = set({_first_party()!r})\n"
        f"allowed = {_ALLOWED_FIRST_PARTY!r}\n"
        f"prefixes = {allowed_connector_prefixes!r}\n"
        "bad = sorted(n for n in sys.modules if n.split('.')[0] in fp and n not in allowed\n"
        "             and not any(n == p or n.startswith(p + '.') for p in prefixes))\n"
        "print('UNEXPECTED_FIRST_PARTY=' + ','.join(bad))\n"
        "sys.exit(1 if bad else 0)\n"
    )


_JOBS: dict[str, str] = {
    "all_connectors_allowlist": _allowlist_check(_CONNECTOR_MODULES, ("connectors",)),
    "core_only_allowlist": _allowlist_check(_CORE_MODULES, ("connectors.core",)),
    "core_does_not_load_providers": (
        "import sys\n" + "".join(f"import {m}\n" for m in _CORE_MODULES) +
        "bad = sorted(n for n in sys.modules if n.startswith('connectors.providers') or n == 'connectors.registry')\n"
        "print('LOADED=' + ','.join(bad))\nsys.exit(1 if bad else 0)\n"
    ),
    # Negative controls: the same checks must fail when they should.
    "control_leak_detected": _allowlist_check(["services.output_channels.dto"], ("connectors",)),
    "control_missing_module": "import services.output_channels.this_module_does_not_exist",
    "control_core_loads_messages": "import sys, connectors.core.contracts\nsys.exit(0 if 'connectors.core.messages' in sys.modules else 3)\n",
    **{f"import:{m}": f"import {m}" for m in _CLEAN_IMPORT_MODULES},
}


@pytest.fixture(scope="module")
def results() -> dict[str, subprocess.CompletedProcess[str]]:
    env = {
        **os.environ,
        "PYTHONPATH": str(_BACKEND),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHON_DOTENV_DISABLED": "1",
    }

    def run(code: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", code], cwd=_BACKEND, env=env, capture_output=True, text=True, timeout=180, check=False,
        )

    workers = min(len(_JOBS), os.cpu_count() or 4)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {name: pool.submit(run, code) for name, code in _JOBS.items()}
        return {name: future.result() for name, future in futures.items()}


def _out(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr[-2000:]


def test_connectors_load_only_allowlisted_first_party_modules(results):
    assert results["all_connectors_allowlist"].returncode == 0, _out(results["all_connectors_allowlist"])


def test_core_loads_only_core_and_allowlisted_modules(results):
    assert results["core_only_allowlist"].returncode == 0, _out(results["core_only_allowlist"])


def test_importing_core_does_not_load_providers_or_registry(results):
    assert results["core_does_not_load_providers"].returncode == 0, _out(results["core_does_not_load_providers"])


def test_module_list_is_discovered_not_hard_coded():
    assert {"connectors.registry", "connectors.core.inbound", "connectors.providers.webhook.provider",
            "connectors.providers.teams_workflow.card"} <= set(_CONNECTOR_MODULES)
    assert "services.output_channels.destinations" in _CLEAN_IMPORT_MODULES
    assert len(_CLEAN_IMPORT_MODULES) >= 12


def test_allowlist_check_detects_a_leak(results):
    result = results["control_leak_detected"]
    assert result.returncode == 1
    assert "UNEXPECTED_FIRST_PARTY=" in result.stdout and "services" in result.stdout


def test_clean_import_check_detects_failure(results):
    result = results["control_missing_module"]
    assert result.returncode != 0
    assert "ModuleNotFoundError" in result.stderr


def test_core_check_is_not_vacuous(results):
    assert results["control_core_loads_messages"].returncode == 0, _out(results["control_core_loads_messages"])


@pytest.mark.parametrize("module", _CLEAN_IMPORT_MODULES)
def test_module_imports_alone_in_a_clean_interpreter(results, module):
    result = results[f"import:{module}"]
    assert result.returncode == 0, f"import {module} failed:\n{result.stderr[-2000:]}"


