"""`services.a2a_server.table_names` is the single source of truth for the
`a2a_*` SDK table names; `sdk_models.py` must re-export the exact same
objects (not merely equal-valued copies), so `alembic/env.py` (which imports
only `table_names`, never `sdk_models`, to avoid an a2a-sdk import at
Alembic-CLI-load time) and everything that imports from `sdk_models` always
agree.
"""

from __future__ import annotations

from services.a2a_server import sdk_models, table_names


def test_sdk_models_reexports_table_names_constants():
    assert sdk_models.TASKS_TABLE == table_names.TASKS_TABLE == "a2a_tasks"
    assert sdk_models.EVENTS_TABLE == table_names.EVENTS_TABLE == "a2a_task_events"
    assert sdk_models.VERSIONS_TABLE == table_names.VERSIONS_TABLE == "a2a_task_versions"

    # Not just equal strings -- the exact same object, proving sdk_models imports
    # (rather than redefines) them.
    assert sdk_models.TASKS_TABLE is table_names.TASKS_TABLE
    assert sdk_models.EVENTS_TABLE is table_names.EVENTS_TABLE
    assert sdk_models.VERSIONS_TABLE is table_names.VERSIONS_TABLE


def test_table_names_module_has_no_a2a_sdk_import():
    """`table_names.py` must stay free of any `a2a`/`a2a.*` import.

    This is what lets `alembic/env.py` read the three constants on every CLI
    invocation without transitively importing a2a-sdk.
    """
    import ast
    import inspect

    source = inspect.getsource(table_names)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("a2a"), (
                    f"table_names.py imports {alias.name!r}; it must stay a2a-sdk-free"
                )
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("a2a"), (
                f"table_names.py imports from {node.module!r}; it must stay a2a-sdk-free"
            )
