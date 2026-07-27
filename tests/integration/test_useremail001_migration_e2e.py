"""End-to-end test of the real ``useremail001`` Alembic migration.

Unlike ``test_localauth001_migration.py`` / ``test_migration_domain_crawling.py`` /
``test_migration_user_deletion.py`` (which only assert schema *state* on the shared,
session-scoped ``test_engine`` fixture -- a schema built via ``Base.metadata.create_all()``,
never through Alembic itself), and unlike ``test_oidc_duplicate_user_race.py`` (which
tests the *application-level* race fix in ``UserService.get_or_create_user``), this test
exercises the actual ``useremail001`` migration's ``upgrade()`` function by:

  1. Creating a brand-new, uniquely-named ephemeral Postgres database on the ``db_test``
     container (port 5433).
  2. Running the real ``alembic upgrade`` CLI as a subprocess against it, stopping one
     revision short of the fix (``20260717_conversation_starters`` -- ``useremail001``'s
     ``down_revision``), reproducing the pre-fix schema (no ``uq_user_email`` constraint).
  3. Inserting two duplicate ``User`` rows sharing an email, each owning 2 ``App`` rows
     with 1 ``Agent`` each (4 Apps + 4 Agents total) -- the literal "duplicate users each
     owning 2 apps with an agent" scenario.
  4. Running the real ``alembic upgrade head`` subprocess, applying ``useremail001``'s
     data merge + ``uq_user_email`` unique constraint.
  5. Asserting, via raw SQL against the ephemeral DB (not the ORM, to stay decoupled from
     any session/identity-map state), that the merge produced exactly the expected result.

Runtime: this test is slower than a typical integration test (~10-20s) -- it creates a
real database and shells out to the real ``alembic`` CLI twice. That tradeoff is
intentional: it is the only way to prove the actual migration script (not a reimplementation
of its SQL) behaves correctly end-to-end.

Requires: the ``db_test`` docker-compose service on port 5433, started via
``docker compose -f docker/docker-compose.yaml --profile test up -d db_test``. Its
``POSTGRES_USER`` (``test_user``) is a Postgres superuser for that container, so it can
freely ``CREATE DATABASE`` / ``DROP DATABASE`` on the shared cluster.
"""

import os
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

DB_HOST = "localhost"
DB_PORT = "5433"
# The db_test container's POSTGRES_USER is a cluster superuser (standard Postgres image
# behavior), so it can CREATE DATABASE / DROP DATABASE freely -- confirmed in the task brief.
DB_SUPERUSER = "test_user"
DB_SUPERUSER_PASSWORD = "test_pass"  # pragma: allowlist secret
MAINTENANCE_DB = "test_db"  # always-present DB used only to issue CREATE/DROP DATABASE
EPHEMERAL_DB_NAME = "mattin_test_useremail001_e2e"

# useremail001's down_revision -- the pre-fix schema (duplicates possible, no unique constraint).
PRE_FIX_REVISION = "20260717_conversation_starters"
POST_FIX_REVISION = "useremail001"

DUPLICATE_EMAIL = "dup-e2e@mattin-test.com"


# ---------------------------------------------------------------------------
# Ephemeral database helpers
# ---------------------------------------------------------------------------


def _admin_connection() -> psycopg2.extensions.connection:
    """Autocommit psycopg2 connection to the always-present maintenance DB.

    CREATE DATABASE / DROP DATABASE cannot run inside a transaction block, so this
    connection must be in autocommit mode and must NOT target the ephemeral DB itself.
    """
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_SUPERUSER,
        password=DB_SUPERUSER_PASSWORD,
        dbname=MAINTENANCE_DB,
    )
    conn.autocommit = True
    return conn


def _drop_ephemeral_db() -> None:
    conn = _admin_connection()
    try:
        with conn.cursor() as cur:
            # WITH (FORCE) (pg13+, we're on pg17) terminates any lingering connections
            # first -- Postgres refuses a plain DROP DATABASE while sessions are attached.
            cur.execute(f'DROP DATABASE IF EXISTS "{EPHEMERAL_DB_NAME}" WITH (FORCE)')
    finally:
        conn.close()


def _create_ephemeral_db() -> None:
    _drop_ephemeral_db()  # guard: a prior crashed run may have left it behind
    conn = _admin_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{EPHEMERAL_DB_NAME}"')
    finally:
        conn.close()


def _run_alembic(revision: str) -> subprocess.CompletedProcess:
    """Invoke the real ``alembic`` CLI as a subprocess against the ephemeral DB.

    alembic/env.py builds its target URL from DATABASE_USER / DATABASE_PASSWORD /
    DATABASE_HOST / DATABASE_PORT / DATABASE_NAME (NOT SQLALCHEMY_DATABASE_URI and NOT
    TEST_DATABASE_URL) -- see alembic/env.py lines 53-55. We invoke via
    ``sys.executable -m alembic`` (rather than relying on an ``alembic`` binary being on
    PATH) so it always runs with the same interpreter/venv as pytest itself, from the
    repo root so alembic.ini / alembic/ resolve normally.
    """
    env = dict(os.environ)
    env.update(
        DATABASE_USER=DB_SUPERUSER,
        DATABASE_PASSWORD=DB_SUPERUSER_PASSWORD,
        DATABASE_HOST=DB_HOST,
        DATABASE_PORT=DB_PORT,
        DATABASE_NAME=EPHEMERAL_DB_NAME,
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture
def ephemeral_pre_fix_db():
    """
    Creates a brand-new ephemeral Postgres database, runs the real ``alembic upgrade``
    to the revision immediately BEFORE ``useremail001`` (pre-fix schema: duplicate emails
    possible, no ``uq_user_email`` constraint), and yields a SQLAlchemy engine bound to
    it. Always drops the database afterward, disposing the engine first so no lingering
    connections block the DROP DATABASE.
    """
    _create_ephemeral_db()
    engine = None
    try:
        result = _run_alembic(PRE_FIX_REVISION)
        assert result.returncode == 0, (
            f"alembic upgrade {PRE_FIX_REVISION} failed (rc={result.returncode}).\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )

        url = (
            f"postgresql://{DB_SUPERUSER}:{DB_SUPERUSER_PASSWORD}"
            f"@{DB_HOST}:{DB_PORT}/{EPHEMERAL_DB_NAME}"
        )
        engine = create_engine(url, pool_pre_ping=True)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()  # release all pooled connections before DROP DATABASE
        _drop_ephemeral_db()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class TestUseremail001MigrationEndToEnd:
    """Genuine end-to-end coverage of the ``useremail001`` migration against a real,
    Alembic-built database (not the ORM-metadata-built shared ``test_engine``)."""

    def test_dedupes_users_reassigns_apps_and_adds_unique_constraint(
        self, ephemeral_pre_fix_db
    ):
        engine = ephemeral_pre_fix_db

        # Import ORM classes lazily (after backend/ is on sys.path via tests/conftest.py)
        # and bind them to a fresh Session against the *ephemeral* engine -- these are the
        # same declarative classes used app-wide, just pointed at a different database.
        from models.user import User
        from models.app import App
        from models.agent import Agent

        Session = sessionmaker(bind=engine)
        setup_session = Session()
        try:
            # --- Seed the pre-fix duplicate-user scenario -----------------------------
            user1 = User(email=DUPLICATE_EMAIL, name="Dup User One", is_active=True)
            user2 = User(email=DUPLICATE_EMAIL, name="Dup User Two", is_active=True)
            setup_session.add_all([user1, user2])
            setup_session.flush()  # assign user_id (serial PK) without committing yet

            # user1 is inserted first, so (barring sequence weirdness) user1.user_id <
            # user2.user_id. Both users end up with an identical activity score (2 owned
            # apps each, 0 API keys / collaborators / usage / marketplace-usage rows), so
            # the migration's tie-break rule -- lowest user_id wins -- must pick user1 as
            # canonical. We assert this explicitly below so the test is deterministic
            # rather than accidentally passing due to insertion order.
            assert user1.user_id < user2.user_id, (
                "sanity: user1 must have the lower user_id for the canonical-tiebreak "
                "assertion below to be meaningful"
            )

            apps_by_user = {}
            agents_by_app = {}
            for owner in (user1, user2):
                owned_apps = []
                for i in range(2):
                    app_obj = App(
                        name=f"E2E App {owner.user_id}-{i}",
                        slug=f"e2e-useremail001-{owner.user_id}-{i}",
                        owner_id=owner.user_id,
                        agent_rate_limit=0,
                        max_file_size_mb=10,
                    )
                    setup_session.add(app_obj)
                    setup_session.flush()
                    owned_apps.append(app_obj)

                    agent_obj = Agent(
                        name=f"E2E Agent {owner.user_id}-{i}",
                        app_id=app_obj.app_id,
                        type="agent",
                    )
                    setup_session.add(agent_obj)
                    setup_session.flush()
                    agents_by_app[app_obj.app_id] = agent_obj.agent_id

                apps_by_user[owner.user_id] = [a.app_id for a in owned_apps]

            setup_session.commit()

            canonical_user_id = user1.user_id
            loser_user_id = user2.user_id
            all_app_ids = set(apps_by_user[canonical_user_id]) | set(apps_by_user[loser_user_id])
            assert len(all_app_ids) == 4

            # --- Reproduce-first checkpoint: confirm the pre-fix DB genuinely has 2 --
            # duplicate rows (proves the setup above actually reproduces the bug state,
            # and that nothing already enforces uniqueness at this revision) before we
            # apply the fix and check it goes away.
            dup_count_before = (
                setup_session.query(User).filter(User.email == DUPLICATE_EMAIL).count()
            )
            assert dup_count_before == 2, (
                "sanity: expected 2 duplicate User rows before useremail001 runs -- "
                "if this fails, the test setup isn't reproducing the bug state"
            )
        finally:
            setup_session.close()

        # setup_session is closed and its transaction committed/finished, so no
        # connections from our own engine hold locks on "User" going into the migration.
        # Dispose the whole pool defensively before shelling out to alembic.
        engine.dispose()

        # --- Apply the real fix -------------------------------------------------------
        result = _run_alembic(POST_FIX_REVISION)
        assert result.returncode == 0, (
            f"alembic upgrade {POST_FIX_REVISION} failed (rc={result.returncode}).\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )

        # --- Assertions: raw SQL only, decoupled from any ORM session state ----------
        with engine.connect() as conn:
            user_rows = conn.execute(
                text('SELECT user_id, email FROM "User" WHERE email = :email'),
                {"email": DUPLICATE_EMAIL},
            ).fetchall()
            assert len(user_rows) == 1, (
                f"Expected exactly 1 User row for {DUPLICATE_EMAIL} after useremail001, "
                f"found {len(user_rows)}: {user_rows}"
            )
            assert user_rows[0].user_id == canonical_user_id, (
                "The surviving User row must be the tie-break winner (lowest user_id, "
                f"{canonical_user_id}), got {user_rows[0].user_id}"
            )

            app_rows = conn.execute(
                text('SELECT app_id, owner_id FROM "App" WHERE app_id = ANY(:ids)'),
                {"ids": list(all_app_ids)},
            ).fetchall()
            assert len(app_rows) == 4, (
                f"Expected all 4 App rows to survive untouched, found {len(app_rows)}"
            )
            assert all(row.owner_id == canonical_user_id for row in app_rows), (
                "All 4 Apps (including the loser's 2) must now be owned by the "
                f"canonical user_id {canonical_user_id}: {app_rows}"
            )

            agent_rows = conn.execute(
                text('SELECT agent_id, app_id FROM "Agent" WHERE app_id = ANY(:ids)'),
                {"ids": list(all_app_ids)},
            ).fetchall()
            assert len(agent_rows) == 4, (
                f"Expected all 4 Agent rows to survive untouched, found {len(agent_rows)}"
            )
            actual_agent_to_app = {row.agent_id: row.app_id for row in agent_rows}
            assert actual_agent_to_app == {
                agent_id: app_id for app_id, agent_id in agents_by_app.items()
            }, "Each Agent's app_id must be unchanged -- agents are only indirectly " \
               "affected via their parent App's ownership."

            # --- Schema assertion: uq_user_email constraint exists -----------------
            constraint_row = conn.execute(
                text(
                    "SELECT constraint_name FROM information_schema.table_constraints "
                    "WHERE table_name = 'User' AND constraint_type = 'UNIQUE' "
                    "AND constraint_name = 'uq_user_email'"
                )
            ).fetchone()
            assert constraint_row is not None, (
                "uq_user_email UNIQUE constraint missing after useremail001 upgrade"
            )

        # --- Schema assertion: the constraint actually rejects a duplicate insert ----
        # Run in its own connection/transaction so a rolled-back failure here doesn't
        # taint the `with engine.connect()` block above.
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                with pytest.raises(IntegrityError):
                    conn.execute(
                        text(
                            'INSERT INTO "User" (email, name, is_active) '
                            "VALUES (:email, :name, true)"
                        ),
                        {"email": DUPLICATE_EMAIL, "name": "Should Be Rejected"},
                    )
            finally:
                trans.rollback()
