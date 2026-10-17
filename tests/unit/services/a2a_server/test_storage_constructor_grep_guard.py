"""Guard (step_012 fix round, item 11): the pinned SDK's cluster store/stream
constructors must be called in exactly one place.

AD-2's whole design rests on `services/a2a_server/storage.py` being the only
code that builds a `VersionedDatabaseTaskStore`/`DatabaseTaskEventStream` --
every other caller must go through `storage.build_bound_storage`, so every
store/stream in the process is bound to the `a2a_*` registry models. This
test greps the real `backend/` tree (not an import-time check, since the
constructors are perfectly importable from elsewhere -- the point is that
nothing *calls* them) and fails loudly if a second call site appears.
"""

from __future__ import annotations

import re
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[4] / "backend"

_CONSTRUCTOR_CALL_PATTERN = re.compile(r"\b(VersionedDatabaseTaskStore|DatabaseTaskEventStream)\(")

_ALLOWED_FILES = {
    _BACKEND_DIR / "services" / "a2a_server" / "storage.py",
}


def _iter_backend_python_files():
    for path in _BACKEND_DIR.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def test_sdk_store_and_stream_constructors_are_only_called_in_storage_py():
    assert _BACKEND_DIR.is_dir(), f"expected backend/ at {_BACKEND_DIR}"

    offending: list[str] = []
    for path in _iter_backend_python_files():
        if path in _ALLOWED_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _CONSTRUCTOR_CALL_PATTERN.search(line):
                offending.append(f"{path.relative_to(_BACKEND_DIR.parent)}:{lineno}: {line.strip()}")

    assert not offending, (
        "VersionedDatabaseTaskStore/DatabaseTaskEventStream must only be constructed in "
        "services/a2a_server/storage.py (AD-2); found direct construction elsewhere:\n"
        + "\n".join(offending)
    )
