"""Integration tests for the apikeyhash001 data migration (MD5 -> SHA-256).

The migration's upgrade/downgrade functions are run through an Alembic
Operations context bound to the test session's connection, so the round trip is
exercised against real PostgreSQL and rolled back afterwards.
"""

import hashlib
import importlib.util
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from models.conversation import Conversation
from utils.security import hash_api_key

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic" / "versions" / "apikeyhash001_sha256_conversation_api_key_hash.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("apikeyhash001", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, fn):
    db.flush()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        fn()
    db.expire_all()


def _md5(key):
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()


@pytest.fixture
def legacy_conversations(db, fake_agent, fake_api_key):
    known = Conversation(agent_id=fake_agent.agent_id, session_id="apikeyhash001-known",
                         api_key_hash=_md5(fake_api_key.key))
    orphan = Conversation(agent_id=fake_agent.agent_id, session_id="apikeyhash001-orphan",
                          api_key_hash=_md5("key-that-was-deleted"))
    db.add_all([known, orphan])
    db.flush()
    return known, orphan


def test_upgrade_rewrites_md5_hashes_to_sha256(db, fake_api_key, legacy_conversations):
    known, orphan = legacy_conversations

    _run(db, _load_migration().upgrade)

    assert known.api_key_hash == hash_api_key(fake_api_key.key)
    # No key can reach a conversation whose key was deleted, so it is left untouched.
    assert orphan.api_key_hash == _md5("key-that-was-deleted")


def test_downgrade_restores_md5_hashes(db, fake_api_key, legacy_conversations):
    known, _ = legacy_conversations
    migration = _load_migration()

    _run(db, migration.upgrade)
    _run(db, migration.downgrade)

    assert known.api_key_hash == _md5(fake_api_key.key)
