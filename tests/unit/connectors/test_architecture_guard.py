"""Architecture guard for the connectors refactor (AD-11, FR-5/FR-6, AC-1/AC-3/AC-16).

AST based (not text grep), so prose such as "Webhook attachment limit ..." never
triggers a rule.  Violations are reported as ``<path>:<line>: <RULE> ...``.

R1  a ``str`` constant exactly equal to a registered provider key.  Skipped for
    ``connectors/registry.py`` and ``connectors/providers/<key>/**`` (a provider declares its own key).
R2  (files OUTSIDE ``connectors/``) an import (or dynamic-import string) of ``connectors.providers``.
R3  (``connectors/core/**``) allowlist: first-party imports only ``connectors.core.*``, ``utils.logger``,
    ``utils.ssrf_guard``.  String literals naming a forbidden module (``import_module("services.x")``) too.
R7  (``connectors/**`` except ``connectors/registry.py``) allowlist: first-party imports only
    ``connectors.core.*``, the file's own provider package ``connectors.providers.<own>.*`` (relative or
    absolute), ``utils.logger`` and ``utils.ssrf_guard``.  Sibling providers and every other first-party
    package are violations.  "First-party" = top-level dirs/modules present in ``backend/``.
R4  (files outside ``connectors/``) a read of ``<expr>.credentials`` that is not an argument of
    ``read_credentials(...)`` (positional or keyword).  ``credentials`` is also a field of request / patch /
    validated-settings objects, so a small PER-FILE exemption table (``_RECEIVER_EXEMPTIONS``) names the only
    receivers allowed to be read raw; any other receiver is assumed to be the ``OutputDestination`` ORM row,
    whose JSON column must not be read raw (CB-2: no ``{}``/``None`` distinction).  Also flagged:
    ``getattr/hasattr(x, "credentials")``, ``x.__dict__["credentials"]``, ``del x.credentials`` (as a delete),
    and writes (``x.credentials = ...``, ``setattr(x, "credentials", ...)``) outside
    ``services/output_channels/destinations.py``.
R5  (same scope) SQL predicates on the column: class-level ``OutputDestination.credentials``,
    ``<x>.credentials.is_/isnot/in_/...(...)`` and ``<x>.credentials ==/!=/is None`` (column is ``sa.JSON``).
R6  (``backend/`` and ``tests/``, except ``connectors/core/inbound.py``) forging a ``VerifiedRequest``: any
    use of ``_VERIFY_TOKEN`` (name, attribute, import or string constant), ``VerifiedRequest.__new__``,
    ``X.__new__(VerifiedRequest)`` and ``object.__new__/__setattr__`` whose first argument is not ``self``/``cls``.
    Limits: purely static; it cannot see reflection through computed names, ``copy``/``pickle`` round-trips or
    ``__class__`` games.  The runtime defence (a private sentinel checked in ``__post_init__``) is covered by
    ``test_inbound_contract.py``.
R8  (all ``backend/**``) importing ``connectors``/``connectors.*`` is allowed only from ``backend/connectors/**``
    and ``backend/services/*_channels/**``.

Watched set = fixed floor (must exist) + globs + every backend file outside ``connectors/`` that imports
``connectors.*``, ``services.*_channels*`` or ``models.output_delivery`` (derived, so new consumers are
watched automatically).
"""

from __future__ import annotations

import ast
import functools
import re
import textwrap
from collections.abc import Iterable
from pathlib import Path

import pytest
from connectors.registry import registered_keys

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_TESTS = _REPO / "tests"
_SELF = Path(__file__).resolve()

_FIXED_WATCHED = (
    "services/scheduled_task_identity.py",
    "services/scheduled_task_service.py",
    "services/file_cleanup_worker.py",
    "scheduling/output_delivery.py",
    "scheduling/periodic_agent_task.py",
    "routers/internal/output_providers.py",
    "repositories/scheduled_task_output_binding_repository.py",
)
_GLOB_WATCHED = (
    "connectors/**/*.py",
    "services/*_channels/**/*.py",  # glob: modules added later (input_channels too) are watched automatically
    "repositories/output_*_repository.py",
)
_DERIVED_IMPORT_RE = re.compile(r"^(connectors(\.|$)|services\.[a-z_]+_channels(\.|$)|models\.output_delivery$)")

_REGISTRY_TAIL = ("connectors", "registry.py")
_CREDENTIALS_WRITE_TAIL = ("output_channels", "destinations.py")
# Receivers whose ``.credentials`` is a request/patch/validated object, not the ORM row -- per file.
_RECEIVER_EXEMPTIONS: dict[tuple[str, ...], frozenset[str]] = {
    ("routers", "internal", "output_providers.py"): frozenset({"payload"}),
    ("output_channels", "destinations.py"): frozenset({"validated", "patch"}),
}
_SQL_METHODS = frozenset({"is_", "isnot", "is_not", "in_", "not_in", "notin_", "like", "ilike", "contains", "op"})
_CONTAINERS = frozenset({"connectors", "connectors.providers", "utils"})
_UTILS_ALLOWED = ("utils.logger", "utils.ssrf_guard")
_KNOWN_ROOTS = ("connectors", "services", "scheduling", "routers", "repositories")
_MODULE_STRING_RE = re.compile(r"^[A-Za-z_]\w*(\.\w+)*$")
_STRING_LAYER_ONLY = frozenset({"services", "routers", "scheduling", "repositories", "models", "db", "schemas", "tools"})


# ---------------------------------------------------------------- helpers
@functools.cache
def _first_party_cached(backend: Path) -> frozenset[str]:
    names = {p.name for p in backend.iterdir() if p.is_dir() and any(p.rglob("*.py")) and p.name != "__pycache__"}
    names |= {p.stem for p in backend.glob("*.py")}
    return frozenset(names)


def first_party_packages(backend: Path = _BACKEND) -> frozenset[str]:
    return _first_party_cached(backend)


@functools.lru_cache(maxsize=4096)
def _parse_cached(path: str, mtime_ns: int) -> ast.Module:
    del mtime_ns  # part of the cache key only
    return ast.parse(Path(path).read_text(encoding="utf-8-sig"), filename=path)


def _parse(path: Path) -> ast.Module:
    return _parse_cached(str(path), path.stat().st_mtime_ns)


def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(_REPO).as_posix()
    except ValueError:
        return path.as_posix()


def _has_tail(path: Path, tail: tuple[str, ...]) -> bool:
    return path.parts[-len(tail):] == tail


def _in_connectors(path: Path) -> bool:
    return "connectors" in path.parent.parts


def _is_core(path: Path) -> bool:
    parts = path.parts
    return any(parts[i:i + 2] == ("connectors", "core") for i in range(len(parts) - 1))


def _own_provider(path: Path) -> str | None:
    parts = path.parent.parts
    for i in range(len(parts) - 1):
        if parts[i:i + 2] == ("connectors", "providers") and i + 2 < len(parts):
            return parts[i + 2]
    return None


def _in_channel_layer(path: Path) -> bool:
    parts = path.parent.parts
    return any(p == "services" and i + 1 < len(parts) and parts[i + 1].endswith("_channels")
               for i, p in enumerate(parts))


def _package_of(path: Path) -> list[str]:
    parts = list(path.parent.parts)
    if "backend" in parts:
        return parts[len(parts) - parts[::-1].index("backend"):]
    for i, part in enumerate(parts):
        if part in _KNOWN_ROOTS:
            return parts[i:]
    return []


def _import_targets(node: ast.AST, path: Path) -> list[str]:
    """Absolute dotted names (``backend.`` prefix stripped) that an import statement pulls in."""
    names: list[str] = []
    if isinstance(node, ast.Import):
        names = [a.name for a in node.names]
    elif isinstance(node, ast.ImportFrom):
        base = node.module or ""
        if node.level:
            pkg = _package_of(path)
            pkg = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
            base = ".".join([*pkg, base] if base else pkg)
        names = [base] + [f"{base}.{a.name}" if base else a.name for a in node.names]
    return [n.removeprefix("backend.") for n in names if n]


def _under(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def _connector_import_problem(target: str, own: str | None, first_party: frozenset[str]) -> str | None:
    """None when ``target`` is allowed inside ``connectors/``; otherwise a short reason."""
    if target.split(".")[0] not in first_party or target in _CONTAINERS:
        return None
    if _under(target, "connectors.core") or any(_under(target, a) for a in _UTILS_ALLOWED):
        return None
    if _under(target, "connectors.providers"):
        child = target.split(".")[2]
        if own is not None and child == own:
            return None
        return f"sibling provider {target}" if own is not None else f"{target}"
    return target


def _root_name(expr: ast.AST) -> str | None:
    while isinstance(expr, (ast.Attribute, ast.Subscript)):
        expr = expr.value
    return expr.id if isinstance(expr, ast.Name) else None


def _is_read_credentials_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == "read_credentials") or (
        isinstance(func, ast.Attribute) and func.attr == "read_credentials"
    )


def _wrapped_in_read_credentials(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    parent = parents.get(node)
    if isinstance(parent, ast.keyword):
        return _is_read_credentials_call(parents.get(parent))
    return _is_read_credentials_call(parent) and node in parent.args  # type: ignore[union-attr]


def _exempt_receivers(path: Path) -> frozenset[str]:
    for tail, names in _RECEIVER_EXEMPTIONS.items():
        if _has_tail(path, tail):
            return names
    return frozenset()


def _is_none(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _credentials_violations(tree: ast.AST, path: Path) -> list[tuple[int, str]]:
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    found: list[tuple[int, str]] = []
    may_write = _has_tail(path, _CREDENTIALS_WRITE_TAIL)
    exempt = _exempt_receivers(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {
            "getattr", "hasattr", "setattr",
        }:
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and node.args[1].value == "credentials":
                if node.func.id == "setattr":
                    if not may_write:
                        found.append((node.lineno, "R4 setattr(..., 'credentials') outside destinations.py"))
                else:
                    found.append((node.lineno, f"R4 {node.func.id}(..., 'credentials'); use read_credentials()"))
            continue
        if isinstance(node, ast.Subscript):
            if (isinstance(node.value, ast.Attribute) and node.value.attr == "__dict__"
                    and isinstance(node.slice, ast.Constant) and node.slice.value == "credentials"):
                found.append((node.lineno, "R4 raw __dict__['credentials'] access"))
            continue
        if not (isinstance(node, ast.Attribute) and node.attr == "credentials"):
            continue
        receiver, parent = node.value, parents.get(node)
        if isinstance(receiver, ast.Name) and receiver.id == "OutputDestination":
            found.append((node.lineno, "R5 SQL/class-level use of OutputDestination.credentials"))
        elif isinstance(node.ctx, ast.Del):
            found.append((node.lineno, "R4 delete of .credentials"))
        elif isinstance(node.ctx, ast.Store):
            if not may_write:
                found.append((node.lineno, "R4 write to .credentials outside services/output_channels/destinations.py"))
        elif _root_name(receiver) in exempt:
            continue
        elif isinstance(parent, ast.Attribute) and parent.attr in _SQL_METHODS and isinstance(
            parents.get(parent), ast.Call,
        ):
            found.append((node.lineno, f"R5 SQL predicate .credentials.{parent.attr}(...) on the JSON column"))
        elif isinstance(parent, ast.Compare) and any(_is_none(c) for c in [parent.left, *parent.comparators]):
            found.append((node.lineno, "R5 comparison of .credentials with None (use read_credentials)"))
        elif not _wrapped_in_read_credentials(node, parents):
            found.append((node.lineno, "R4 raw .credentials read; wrap it in read_credentials(...)"))
    return found


def _connectors_hits(tree: ast.AST, path: Path, first_party: frozenset[str]) -> list[tuple[int, str]]:
    rule = "R3" if _is_core(path) else "R7"
    own = _own_provider(path)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for target in _import_targets(node, path):
                problem = _connector_import_problem(target, own, first_party)
                if problem:
                    hits.append((node.lineno, f"{rule} connectors code must not import {problem}"))
                    break
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and _MODULE_STRING_RE.match(node.value):
            top = node.value.split(".")[0]
            if top in first_party and top in _STRING_LAYER_ONLY | {"connectors", "utils"} and (
                "." in node.value or top in _STRING_LAYER_ONLY
            ):
                problem = _connector_import_problem(node.value, own, first_party)
                if problem:
                    hits.append((node.lineno, f"{rule} string literal names forbidden module {problem}"))
    return hits


def find_violations(
    paths: Iterable[Path], provider_keys: frozenset[str], *, first_party: frozenset[str] | None = None,
) -> list[str]:
    first_party = first_party if first_party is not None else first_party_packages()
    out: list[str] = []
    for path in map(Path, paths):
        tree = _parse(path)
        in_connectors = _in_connectors(path)
        registry_file = _has_tail(path, _REGISTRY_TAIL)
        hits: list[tuple[int, str]] = []
        if not (registry_file or _own_provider(path)):
            hits += [
                (n.lineno, f"R1 hard-coded provider key {n.value!r}")
                for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in provider_keys
            ]
        if not in_connectors:
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and _under(
                    node.value, "connectors.providers",
                ):
                    hits.append((node.lineno, "R2 dynamic import string of connectors.providers"))
                elif isinstance(node, (ast.Import, ast.ImportFrom)) and any(
                    _under(t, "connectors.providers") for t in _import_targets(node, path)
                ):
                    hits.append((node.lineno, "R2 import of connectors.providers"))
            hits += _credentials_violations(tree, path)
        elif not registry_file:
            hits += _connectors_hits(tree, path, first_party)
        out.extend(f"{_display(path)}:{line}: {rule}" for line, rule in sorted(set(hits)))
    return out


def find_import_boundary_violations(paths: Iterable[Path]) -> list[str]:
    """R8: only ``connectors/**`` and ``services/*_channels/**`` may import ``connectors``."""
    out: list[str] = []
    for path in map(Path, paths):
        if _in_connectors(path) or _in_channel_layer(path):
            continue
        for node in ast.walk(_parse(path)):
            if isinstance(node, (ast.Import, ast.ImportFrom)) and any(
                t.split(".")[0] == "connectors" for t in _import_targets(node, path)
            ):
                out.append(f"{_display(path)}:{node.lineno}: R8 imports connectors outside connectors/ and services/*_channels/")
    return sorted(set(out), key=_line_key)


def find_verified_request_forgeries(paths: Iterable[Path]) -> list[str]:
    out: list[str] = []
    for path in map(Path, paths):
        shown = _display(path)
        for node in ast.walk(_parse(path)):
            line = getattr(node, "lineno", 0)
            if (isinstance(node, ast.Name) and node.id == "_VERIFY_TOKEN") or (
                isinstance(node, ast.Attribute) and node.attr == "_VERIFY_TOKEN"
            ):
                out.append(f"{shown}:{line}: R6 uses _VERIFY_TOKEN")
            elif isinstance(node, ast.Constant) and node.value == "_VERIFY_TOKEN":
                out.append(f"{shown}:{line}: R6 names _VERIFY_TOKEN as a string")
            elif isinstance(node, ast.alias) and node.name == "_VERIFY_TOKEN":
                out.append(f"{shown}:{node.lineno}: R6 imports _VERIFY_TOKEN")
            elif isinstance(node, ast.Attribute) and node.attr == "__new__" and (
                isinstance(node.value, ast.Name) and node.value.id == "VerifiedRequest"
            ):
                out.append(f"{shown}:{line}: R6 VerifiedRequest.__new__")
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and node.func.attr in {"__new__", "__setattr__"} and node.args):
                first = node.args[0]
                is_object = isinstance(node.func.value, ast.Name) and node.func.value.id == "object"
                if isinstance(first, ast.Name) and first.id == "VerifiedRequest":
                    out.append(f"{shown}:{line}: R6 X.__new__(VerifiedRequest)")
                elif is_object and not (isinstance(first, ast.Name) and first.id in {"self", "cls"}):
                    out.append(f"{shown}:{line}: R6 object.{node.func.attr}(<not self/cls>, ...)")
    return sorted(set(out), key=_line_key)


def _line_key(violation: str) -> tuple[str, int]:
    location = violation.split(": ", 1)[0]
    path, _, line = location.rpartition(":")
    return path, int(line)


def watched_files(
    backend: Path = _BACKEND, fixed: tuple[str, ...] = _FIXED_WATCHED, globs: tuple[str, ...] = _GLOB_WATCHED,
) -> list[Path]:
    files: set[Path] = set()
    for rel in fixed:
        path = backend / rel
        assert path.is_file(), f"watched file missing: {path}"
        files.add(path)
    for pattern in globs:
        matched = [p for p in backend.glob(pattern) if "__pycache__" not in p.parts]
        assert matched, f"watched glob matched nothing: {pattern}"
        files.update(matched)
    for path in _py_files(backend):
        if path in files or _in_connectors(path):
            continue
        if any(_DERIVED_IMPORT_RE.match(t) for n in ast.walk(_parse(path))
               if isinstance(n, (ast.Import, ast.ImportFrom)) for t in _import_targets(n, path)):
            files.add(path)
    return sorted(files)


def _py_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _write(tmp_path: Path, rel: str, source: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


_SAMPLE_KEYS = frozenset({"webhook", "teams_workflow"})
_FP = frozenset({"connectors", "services", "routers", "scheduling", "models", "db", "repositories", "schemas",
                 "tools", "utils", "config"})


def _check(path: Path, keys: frozenset[str] = _SAMPLE_KEYS) -> list[str]:
    return find_violations([path], keys, first_party=_FP)


# ---------------------------------------------------------------- real tree
class TestRealTree:
    def test_watched_set_covers_expected_modules(self):
        names = {_display(p) for p in watched_files()}
        for expected in (
            "backend/services/output_channels/destinations.py",
            "backend/services/output_channels/delivery_processor.py",
            "backend/repositories/output_destination_repository.py",
            "backend/repositories/output_delivery_repository.py",
            "backend/repositories/output_artifact_repository.py",
            "backend/repositories/scheduled_task_output_binding_repository.py",
            "backend/connectors/core/inbound.py",
            "backend/connectors/providers/webhook/provider.py",
            "backend/connectors/providers/teams_workflow/card.py",
            "backend/connectors/registry.py",
            "backend/scheduling/output_delivery.py",
            "backend/routers/internal/output_providers.py",
        ):
            assert expected in names
        for path in (_BACKEND / "services" / "output_channels").glob("*.py"):
            assert _display(path) in names

    def test_real_files_have_no_violations(self):
        assert find_violations(watched_files(), registered_keys()) == []

    def test_import_boundary_holds_across_all_of_backend(self):
        assert find_import_boundary_violations(_py_files(_BACKEND)) == []

    def test_first_party_set_is_derived_from_backend(self):
        fp = first_party_packages()
        assert {"connectors", "services", "routers", "models", "db", "utils", "scheduling"} <= fp

    def test_get_webhook_provider_is_gone(self):
        needle = "get_webhook_" + "provider"
        offenders = [
            _display(p) for p in [*_py_files(_BACKEND), *_py_files(_TESTS)]
            if p.resolve() != _SELF and needle in p.read_text(encoding="utf-8-sig")
        ]
        assert offenders == []

    def test_old_output_package_is_gone(self):
        assert not (_BACKEND / "output").exists()
        import_re = re.compile(r"^\s*(from|import)\s+output(\.|\s|$)", re.MULTILINE)
        string_re = re.compile(r"""["']output\.(service|registry|teams_workflow|webhook|contracts)""")
        offenders = []
        for p in [*_py_files(_BACKEND), *_py_files(_TESTS)]:
            if p.resolve() == _SELF:
                continue
            text = p.read_text(encoding="utf-8-sig")
            if import_re.search(text) or string_re.search(text):
                offenders.append(_display(p))
        assert offenders == []

    def test_verified_request_cannot_be_forged_anywhere(self):
        inbound = (_BACKEND / "connectors" / "core" / "inbound.py").resolve()
        # No allowlist beyond the defining module: test_inbound_contract only passes `_token=object()`.
        files = [p for p in [*_py_files(_BACKEND), *_py_files(_TESTS)] if p.resolve() not in (inbound, _SELF)]
        assert find_verified_request_forgeries(files) == []
        assert "_VERIFY_TOKEN" in inbound.read_text(encoding="utf-8")

    def test_output_channel_and_connector_modules_stay_under_400_lines(self):
        files = [*(_BACKEND / "services" / "output_channels").rglob("*.py"), *(_BACKEND / "connectors").rglob("*.py")]
        assert len(files) > 20
        sizes = {_display(p): len(p.read_text(encoding="utf-8").splitlines()) for p in files}
        assert {k: v for k, v in sizes.items() if v > 400} == {}


# ---------------------------------------------------------------- negative controls
class TestWatchedSetControls:
    def test_missing_fixed_watched_file_fails(self, tmp_path):
        with pytest.raises(AssertionError, match="watched file missing"):
            watched_files(tmp_path, ("services/does_not_exist.py",), ())

    def test_empty_glob_fails(self, tmp_path):
        with pytest.raises(AssertionError, match="matched nothing"):
            watched_files(tmp_path, (), ("services/no_such_dir/**/*.py",))

    def test_new_modules_and_consumers_are_watched_automatically(self, tmp_path):
        _write(tmp_path, "connectors/core/a.py", "")
        _write(tmp_path, "connectors/providers/new_one/p.py", "")
        _write(tmp_path, "repositories/output_new_repository.py", "")
        _write(tmp_path, "services/output_channels/brand_new_module.py", "")
        _write(tmp_path, "services/input_channels/future.py", "")
        _write(tmp_path, "services/new_consumer.py", "from services.output_channels.dto import x\n")
        _write(tmp_path, "services/uses_connectors.py", "import connectors.registry\n")
        _write(tmp_path, "services/uses_model.py", "from models.output_delivery import OutputDelivery\n")
        _write(tmp_path, "services/unrelated.py", "import json\nfrom models.agent import Agent\n")
        names = {p.relative_to(tmp_path).as_posix() for p in watched_files(tmp_path, (), _GLOB_WATCHED)}
        assert names == {
            "connectors/core/a.py", "connectors/providers/new_one/p.py", "repositories/output_new_repository.py",
            "services/output_channels/brand_new_module.py", "services/input_channels/future.py",
            "services/new_consumer.py", "services/uses_connectors.py", "services/uses_model.py",
        }


class TestKeyAndProviderImportRules:
    def test_r1_and_r2(self, tmp_path):
        path = _write(tmp_path, "services/x.py", '''\
            KEY = "webhook"
            from connectors.providers.webhook import provider
            MSG = "Webhook attachment limit exceeded"
        ''')
        p = path.as_posix()
        assert _check(path) == [f"{p}:1: R1 hard-coded provider key 'webhook'", f"{p}:2: R2 import of connectors.providers"]

    def test_r1_skipped_in_registry_and_provider_packages_but_not_core(self, tmp_path):
        assert _check(_write(tmp_path, "connectors/registry.py", 'K = "webhook"\n')) == []
        assert _check(_write(tmp_path, "connectors/providers/webhook/p.py", 'K = "webhook"\n')) == []
        core = _write(tmp_path, "connectors/core/c.py", 'K = "webhook"\n')
        assert _check(core) == [f"{core.as_posix()}:1: R1 hard-coded provider key 'webhook'"]

    @pytest.mark.parametrize(("source", "line"), [
        ("import connectors.providers.webhook\n", 1),
        ("from connectors import providers\n", 1),
        ("from backend.connectors.providers import webhook\n", 1),
        ("def f():\n    from connectors.providers.teams_workflow import X\n", 2),
        ("import importlib\nimportlib.import_module('connectors.providers.webhook')\n", 2),
    ])
    def test_r2_import_forms(self, tmp_path, source, line):
        path = _write(tmp_path, "services/x.py", source)
        assert _check(path)[0].startswith(f"{path.as_posix()}:{line}: R2")
        assert len(_check(path)) == 1

    def test_r2_allowlist_is_only_connectors_registry(self, tmp_path):
        allowed = _write(tmp_path, "connectors/registry.py", "from connectors.providers.webhook import W\n")
        other = _write(tmp_path, "other/registry.py", "from connectors.providers.webhook import W\n")
        assert _check(allowed) == []
        assert _check(other) == [f"{other.as_posix()}:1: R2 import of connectors.providers"]


class TestCoreAllowlist:
    @pytest.mark.parametrize(("source", "line", "target"), [
        ("import services.x\n", 1, "services.x"),
        ("from services.x import y\n", 1, "services.x"),
        ("from routers.internal import z\n", 1, "routers.internal"),
        ("import scheduling\n", 1, "scheduling"),
        ("from models.output_delivery import M\n", 1, "models.output_delivery"),
        ("from db.database import Base\n", 1, "db.database"),
        ("from repositories.x_repository import R\n", 1, "repositories.x_repository"),
        ("from schemas.x import S\n", 1, "schemas.x"),
        ("from connectors.registry import find_output_provider\n", 1, "connectors.registry"),
        ("from connectors import registry\n", 1, "connectors.registry"),
        ("from backend.services.x import y\n", 1, "services.x"),
        ("from utils.other import o\n", 1, "utils.other"),
        ("def f():\n    import services.lazy\n", 2, "services.lazy"),
        ("from ..providers import webhook\n", 1, "connectors.providers.webhook"),
    ])
    def test_forbidden_imports(self, tmp_path, source, line, target):
        path = _write(tmp_path, "connectors/core/mod.py", source)
        assert _check(path) == [f"{path.as_posix()}:{line}: R3 connectors code must not import {target}"]

    def test_string_literal_module_names(self, tmp_path):
        path = _write(tmp_path, "connectors/core/mod.py", 'import importlib\nm = importlib.import_module("services.x")\n')
        assert _check(path) == [f"{path.as_posix()}:2: R3 string literal names forbidden module services.x"]

    def test_allowed_imports_and_innocent_strings(self, tmp_path):
        path = _write(tmp_path, "connectors/core/mod.py", """\
            from connectors.core import registry
            from connectors.core.messages import X
            from utils.logger import get_logger
            from utils.ssrf_guard import check
            from . import messages
            import json
            A = "config.json"
            B = "data"
            C = "utils.ssrf_guard"
        """)
        assert _check(path) == []

    def test_not_applied_outside_connectors(self, tmp_path):
        path = _write(tmp_path, "services/mod.py", "import services.x\nfrom connectors.registry import y\n")
        assert _check(path) == []


class TestProviderAllowlist:
    def test_lazy_services_import_in_provider_function(self, tmp_path):
        path = _write(tmp_path, "connectors/providers/webhook/p.py", "def f():\n    from services.output_channels import dto\n")
        assert _check(path) == [f"{path.as_posix()}:2: R7 connectors code must not import services.output_channels"]

    def test_models_and_other_utils(self, tmp_path):
        path = _write(tmp_path, "connectors/providers/webhook/p.py", """\
            from models.output_delivery import OutputDelivery
            from utils.other import o
            import db.database
        """)
        p = path.as_posix()
        assert _check(path) == [
            f"{p}:1: R7 connectors code must not import models.output_delivery",
            f"{p}:2: R7 connectors code must not import utils.other",
            f"{p}:3: R7 connectors code must not import db.database",
        ]

    def test_sibling_provider_absolute_and_relative(self, tmp_path):
        path = _write(tmp_path, "connectors/providers/webhook/p.py", """\
            from connectors.providers.teams_workflow.card import build
            from ..teams_workflow import card
            from connectors.providers import teams_workflow
        """)
        p = path.as_posix()
        assert _check(path) == [
            f"{p}:1: R7 connectors code must not import sibling provider connectors.providers.teams_workflow.card",
            f"{p}:2: R7 connectors code must not import sibling provider connectors.providers.teams_workflow",
            f"{p}:3: R7 connectors code must not import sibling provider connectors.providers.teams_workflow",
        ]

    def test_string_literal_and_registry_import(self, tmp_path):
        path = _write(tmp_path, "connectors/providers/webhook/p.py", 'X = "models.agent"\nimport connectors.registry\n')
        p = path.as_posix()
        assert _check(path) == [
            f"{p}:1: R7 string literal names forbidden module models.agent",
            f"{p}:2: R7 connectors code must not import connectors.registry",
        ]

    def test_allowed_provider_imports(self, tmp_path):
        path = _write(tmp_path, "connectors/providers/webhook/p.py", """\
            import httpx
            from connectors.core.messages import X
            from connectors.providers.webhook.config import C
            from connectors.providers.webhook import events
            from .config import C2
            from . import events as e2
            from utils.ssrf_guard import g
            from utils.logger import get_logger
        """)
        assert _check(path) == []

    def test_registry_is_exempt_from_r7(self, tmp_path):
        path = _write(tmp_path, "connectors/registry.py", "from services.x import y\nfrom connectors.providers.webhook import W\n")
        assert _check(path) == []

    def test_credentials_rules_not_applied_inside_connectors(self, tmp_path):
        path = _write(tmp_path, "connectors/providers/webhook/p.py", "def f(m):\n    return m.credentials\n")
        assert _check(path) == []


class TestImportBoundaryR8:
    def test_forbidden_and_allowed_locations(self, tmp_path):
        bad = _write(tmp_path, "routers/x.py", "from connectors.core.http import y\n")
        bad2 = _write(tmp_path, "services/agent_service.py", "def f():\n    import connectors.registry\n")
        ok = [
            _write(tmp_path, "services/output_channels/a.py", "from connectors.registry import r\n"),
            _write(tmp_path, "services/input_channels/b.py", "from connectors.core import http\n"),
            _write(tmp_path, "connectors/providers/webhook/c.py", "from connectors.core import http\n"),
        ]
        assert find_import_boundary_violations([bad, bad2, *ok]) == [
            f"{bad.as_posix()}:1: R8 imports connectors outside connectors/ and services/*_channels/",
            f"{bad2.as_posix()}:2: R8 imports connectors outside connectors/ and services/*_channels/",
        ]


class TestCredentialsRules:
    def _run(self, tmp_path, rel, source):
        path = _write(tmp_path, rel, source)
        return path, _check(path)

    def test_r4_raw_reads_and_reflection(self, tmp_path):
        path, found = self._run(tmp_path, "services/output_channels/m.py", """\
            def f(destination):
                ok = read_credentials(destination.credentials)
                bad = destination.credentials
                also = bool(destination.credentials)
                nested = read_credentials(dict(destination.credentials))
                via = getattr(destination, "credentials")
                has = hasattr(destination, "credentials")
                raw = destination.__dict__["credentials"]
        """)
        p = path.as_posix()
        assert found == [
            f"{p}:3: R4 raw .credentials read; wrap it in read_credentials(...)",
            f"{p}:4: R4 raw .credentials read; wrap it in read_credentials(...)",
            f"{p}:5: R4 raw .credentials read; wrap it in read_credentials(...)",
            f"{p}:6: R4 getattr(..., 'credentials'); use read_credentials()",
            f"{p}:7: R4 hasattr(..., 'credentials'); use read_credentials()",
            f"{p}:8: R4 raw __dict__['credentials'] access",
        ]

    def test_keyword_form_of_read_credentials_is_accepted(self, tmp_path):
        _, found = self._run(tmp_path, "services/output_channels/m.py", "def f(d):\n    return read_credentials(value=d.credentials)\n")
        assert found == []
        _, found = self._run(tmp_path, "services/output_channels/n.py", "def f(d):\n    return other(value=d.credentials)\n")
        assert len(found) == 1 and ":2: R4" in found[0]

    def test_exemptions_are_scoped_per_file(self, tmp_path):
        source = "def f(payload, patch, validated):\n    a = payload.credentials\n    b = patch.credentials\n    c = validated.credentials\n"
        _, in_router = self._run(tmp_path, "routers/internal/output_providers.py", source)
        _, in_destinations = self._run(tmp_path, "services/output_channels/destinations.py", source)
        _, elsewhere = self._run(tmp_path, "services/output_channels/other.py", source)
        assert [v.split(": ")[1] for v in in_router] == ["R4 raw .credentials read; wrap it in read_credentials(...)"] * 2
        assert [v.split(": ")[1] for v in in_destinations] == ["R4 raw .credentials read; wrap it in read_credentials(...)"]
        assert len(elsewhere) == 3
        _, dropped = self._run(tmp_path, "services/output_channels/destinations.py", "def f(settings, body, changes):\n    return settings.credentials\n")
        assert len(dropped) == 1

    def test_writes_deletes_and_setattr(self, tmp_path):
        source = """\
            def f(d):
                d.credentials = None
                setattr(d, "credentials", {})
                del d.credentials
        """
        allowed, found_allowed = self._run(tmp_path, "services/output_channels/destinations.py", source)
        denied, found_denied = self._run(tmp_path, "services/output_channels/other.py", source)
        assert found_allowed == [f"{allowed.as_posix()}:4: R4 delete of .credentials"]
        d = denied.as_posix()
        assert found_denied == [
            f"{d}:2: R4 write to .credentials outside services/output_channels/destinations.py",
            f"{d}:3: R4 setattr(..., 'credentials') outside destinations.py",
            f"{d}:4: R4 delete of .credentials",
        ]

    @pytest.mark.parametrize("expr", [
        "OutputDestination.credentials.is_(None)",
        "OutputDestination.credentials == None",
        "select(OutputDestination).where(OutputDestination.credentials.isnot(None))",
        "row.credentials.is_(None)",
        "row.credentials is None",
        "row.credentials != None",
        "read_credentials(OutputDestination.credentials)",
    ])
    def test_r5_sql_predicates(self, tmp_path, expr):
        path, found = self._run(tmp_path, "repositories/output_x_repository.py", f"def f(row):\n    return {expr}\n")
        assert len(found) == 1 and found[0].startswith(f"{path.as_posix()}:2: R5")

    def test_exemption_applies_before_r5_but_class_level_does_not(self, tmp_path):
        _, found = self._run(tmp_path, "routers/internal/output_providers.py", """\
            def f(payload):
                a = payload.credentials is None
                b = OutputDestination.credentials.is_(None)
        """)
        assert [v.split(": ")[0].rsplit(":", 1)[1] for v in found] == ["3"]
        assert "R5" in found[0]


class TestVerifiedRequestRule:
    def test_sentinel_new_and_setattr(self, tmp_path):
        path = _write(tmp_path, "t.py", """\
            from connectors.core.inbound import _VERIFY_TOKEN
            import connectors.core.inbound as inb
            a = inb._VERIFY_TOKEN
            b = object.__new__(VerifiedRequest)
            c = VerifiedRequest.__new__
            d = VerifiedRequest(_token=object())
            e = _VERIFY_TOKEN_MAX_AGE_SECONDS
            f = getattr(inb, "_VERIFY_TOKEN")
            g = object.__setattr__(other, "x", 1)
            h = object.__new__(SomethingElse)
            class K:
                def m(self):
                    object.__setattr__(self, "x", 1)
                def __new__(cls):
                    return object.__new__(cls)
        """)
        p = path.as_posix()
        assert find_verified_request_forgeries([path]) == [
            f"{p}:1: R6 imports _VERIFY_TOKEN",
            f"{p}:3: R6 uses _VERIFY_TOKEN",
            f"{p}:4: R6 X.__new__(VerifiedRequest)",
            f"{p}:5: R6 VerifiedRequest.__new__",
            f"{p}:8: R6 names _VERIFY_TOKEN as a string",
            f"{p}:9: R6 object.__setattr__(<not self/cls>, ...)",
            f"{p}:10: R6 object.__new__(<not self/cls>, ...)",
        ]
