"""
Shared fixtures for sandbox integration tests (Phase 3).

Provides mock Skill / SkillFile objects so tests needing ensure_skill
can run without a real filesystem or SDK connection.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def mock_skill_file_text():
    """A SkillFile-like object with text content."""
    sf = SimpleNamespace(
        path="helpers.py",
        content_text="def hello():\n    return 'hi'\n",
        content_bytes=None,
    )
    return sf


@pytest.fixture()
def mock_skill_file_bootstrap():
    """A SkillFile-like object representing a bootstrap script."""
    sf = SimpleNamespace(
        path="bootstrap.py",
        content_text="import helpers; print(helpers.hello())\n",
        content_bytes=None,
    )
    return sf


@pytest.fixture()
def mock_skill_with_files(mock_skill_file_text):
    """A Skill-like object with one text file and no bootstrap script."""
    skill = SimpleNamespace(
        skill_id=101,
        name="test_skill_files",
        bootstrap_script_path=None,
        files=[mock_skill_file_text],
        runtime_options={"runtime": "python-sandbox"},
    )
    return skill


@pytest.fixture()
def mock_skill_with_bootstrap(mock_skill_file_text, mock_skill_file_bootstrap):
    """A Skill-like object with one file and a bootstrap script."""
    skill = SimpleNamespace(
        skill_id=102,
        name="test_skill_bootstrap",
        bootstrap_script_path="bootstrap.py",
        files=[mock_skill_file_text, mock_skill_file_bootstrap],
        runtime_options={"runtime": "python-sandbox"},
    )
    return skill
