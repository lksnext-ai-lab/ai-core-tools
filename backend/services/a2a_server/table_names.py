"""The `a2a_*` SDK table names, with zero dependency on `a2a-sdk` itself.

Deliberately separate from `sdk_models.py` (which imports `a2a.server.models`
to build the actual model classes): `alembic/env.py` needs these three names
at module import time, for every `alembic` invocation, purely to populate
`include_name()`'s `ignored_tables` list. Importing `sdk_models.py` there
would transitively import the a2a-sdk package on every Alembic CLI call
(upgrade, downgrade, revision --autogenerate, history, ...) just to read
three string constants -- and if that import ever broke (e.g. a dependency
resolution issue in a fresh environment), it would block **all** migrations,
not just a2a-related ones. This module has no such risk: it is pure Python
constants, nothing else.

`sdk_models.py` re-exports these same constants (imported from here, not
redefined) so there is exactly one source of truth for the three names.
"""

from __future__ import annotations

TASKS_TABLE = "a2a_tasks"
EVENTS_TABLE = "a2a_task_events"
VERSIONS_TABLE = "a2a_task_versions"

__all__ = ["TASKS_TABLE", "EVENTS_TABLE", "VERSIONS_TABLE"]
