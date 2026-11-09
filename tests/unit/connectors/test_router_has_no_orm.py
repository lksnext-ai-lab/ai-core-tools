"""AC-8: the output providers router only does HTTP; all data access lives in services/repositories."""

import ast
from pathlib import Path

ROUTER = Path(__file__).resolve().parents[3] / "backend" / "routers" / "internal" / "output_providers.py"
ORM_CALLS = {"query", "select", "execute", "scalars"}


def _is_models(module: str) -> bool:
    return module == "models" or module.startswith("models.")


def _is_sqlalchemy(module: str) -> bool:
    return module == "sqlalchemy" or module.startswith("sqlalchemy.")


def _violations(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_sqlalchemy(alias.name) or _is_models(alias.name) or alias.name.startswith("repositories"):
                    found.append(f"{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "sqlalchemy.orm":
                found += [f"{node.lineno}: from sqlalchemy.orm import {a.name}" for a in node.names if a.name != "Session"]
            elif _is_sqlalchemy(module) or _is_models(module) or module == "repositories" or module.startswith("repositories."):
                found.append(f"{node.lineno}: from {module} import ...")
            elif module == "db.database":
                found += [f"{node.lineno}: from db.database import {a.name}" for a in node.names if a.name != "get_db"]
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr in ORM_CALLS:
                    found.append(f"{node.lineno}: .{func.attr}(")
                elif isinstance(func.value, ast.Name) and func.value.id == "db":
                    found.append(f"{node.lineno}: db.{func.attr}(")
            elif isinstance(func, ast.Name) and func.id == "select":
                found.append(f"{node.lineno}: select(")
    return found


def test_router_has_no_orm_access():
    assert _violations(ROUTER.read_text(encoding="utf-8")) == []


def test_detector_flags_orm_access():
    assert _violations("from sqlalchemy.orm import Session\nfrom db.database import get_db\n") == []
    cases = {
        "from sqlalchemy import select": 1,
        "import sqlalchemy.orm": 1,
        "from sqlalchemy.orm import joinedload": 1,
        "from models.x import Y": 1,
        "from models import Y": 1,
        "import models.x": 1,
        "from repositories.x import Y": 1,
        "from repositories import x": 1,
        "import repositories.x": 1,
        "from db.database import SessionLocal": 1,
        "db.query(Y)": 1,
        "select(Y)": 1,
        "session.execute(q)": 1,
        "result.scalars()": 1,
        "db.commit()": 1,
        "db.rollback()": 1,
        "db.add(x)": 1,
    }
    for source, expected in cases.items():
        assert len(_violations(source + "\n")) == expected, source
    # A module merely starting with "models" is not the models package.
    assert _violations("from modelsx import Y\n") == []
