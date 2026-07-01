"""Integration regression tests for LOCAL-auth admin-provisioning increment.

Requires the test PostgreSQL DB on port 5433 (managed by conftest.py).
Each test runs in a rolled-back transaction — no data persists between tests.

Covers:
1. seed_dev_users_async in LOCAL mode creates a user with auth_method='local'
   and a credential row, and CredentialService.authenticate accepts the password.
2. seed_dev_users_async normalises an existing user whose auth_method is 'oidc'
   to 'local' when re-seeded with a password.
3. bootstrap_omniadmins (first run) creates a user + outstanding reset_token.
4. bootstrap_omniadmins (second run with already-verified user) is a no-op
   (idempotency: no second user created, no new token issued).
"""

import os
import pytest

# ---------------------------------------------------------------------------
# Module-level env setup
#
# pytest.ini is the active config file; the pytest-env entries live in
# pyproject.toml [tool.pytest.ini_options] which is NOT read when pytest.ini
# is present.  We therefore set the minimum required env vars explicitly here
# so that every test in this module sees them regardless of how pytest is
# invoked.  We use os.environ directly (not monkeypatch) because we need the
# values set before the conftest.py session-scoped test_engine fixture imports
# backend modules — module-scoped fixtures run before function-scoped ones.
# ---------------------------------------------------------------------------

os.environ.setdefault("AICT_LOGIN", "LOCAL")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-minimum-ok")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "postgresql://test_user:test_pass@localhost:5433/test_db")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_oidc_user(db, email: str, name: str = "Legacy User"):
    """Create a user with auth_method='oidc' to simulate a pre-LOCAL-mode row."""
    from models.user import User

    user = User(
        email=email,
        name=name,
        is_active=True,
        auth_method="oidc",
        email_verified=True,
    )
    db.add(user)
    db.flush()
    return user


# ---------------------------------------------------------------------------
# Bug 1 — seed creates LOCAL users with auth_method='local' and loginable cred
# ---------------------------------------------------------------------------


class TestSeedCreatesLocalUser:
    @pytest.mark.asyncio
    async def test_new_user_gets_local_auth_method(self, db):
        """seed_dev_users_async must create a user with auth_method='local' in LOCAL mode.

        Regression: previously the seed path called UserService.get_or_create_user
        which defaulted to auth_method='oidc', making the user un-loginable via
        CredentialService.authenticate.
        """
        from utils.seed_dev_users import seed_dev_users_async

        users_data = [
            {
                "email": "seedtest_new@mattin-test.com",
                "name": "Seed Test",
                "description": "Test user",
                "password": "S33dP@ssw0rd!",
            }
        ]

        result = await seed_dev_users_async(db, users_data=users_data)
        assert len(result["created"]) == 1

        user = result["created"][0]
        db.refresh(user)
        assert user.auth_method == "local", (
            "Regression: seed in LOCAL mode must set auth_method='local', "
            f"got {user.auth_method!r}"
        )

    @pytest.mark.asyncio
    async def test_new_user_has_credential_row(self, db):
        """A credential row must be created for the seeded user."""
        from models.user_credential import UserCredential
        from utils.seed_dev_users import seed_dev_users_async

        users_data = [
            {
                "email": "seedtest_cred@mattin-test.com",
                "name": "Seed Cred",
                "description": "",
                "password": "S33dP@ssw0rd!",
            }
        ]

        result = await seed_dev_users_async(db, users_data=users_data)
        user = result["created"][0]

        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        assert cred is not None, "seed_dev_users_async must create a UserCredential row"
        assert cred.hashed_password is not None

    @pytest.mark.asyncio
    async def test_seeded_user_is_loginable(self, db):
        """CredentialService.authenticate must accept the seeded password.

        Regression: previously authenticate rejected the user because
        auth_method was 'oidc' (required 'local').
        """
        from services.auth.credential_service import CredentialService
        from utils.seed_dev_users import seed_dev_users_async

        email = "seedtest_login@mattin-test.com"
        password = "L0g1nP@ssw0rd!"
        users_data = [
            {
                "email": email,
                "name": "Loginable Seed",
                "description": "",
                "password": password,
            }
        ]

        await seed_dev_users_async(db, users_data=users_data)

        authenticated_user = await CredentialService.authenticate(db, email, password)
        assert authenticated_user is not None
        assert authenticated_user.email == email

    @pytest.mark.asyncio
    async def test_seeded_user_without_password_has_local_auth_method(self, db):
        """A user seeded without a password still gets auth_method='local'."""
        from models.user_credential import UserCredential
        from utils.seed_dev_users import seed_dev_users_async

        users_data = [
            {
                "email": "seedtest_nopw@mattin-test.com",
                "name": "No Password",
                "description": "",
                "password": None,
            }
        ]

        result = await seed_dev_users_async(db, users_data=users_data)
        user = result["created"][0]
        db.refresh(user)

        # auth_method must still be 'local' even without a password.
        assert user.auth_method == "local"


# ---------------------------------------------------------------------------
# Bug 1b — seed normalises existing 'oidc' users to 'local' when re-seeded
# ---------------------------------------------------------------------------


class TestSeedNormalisesExistingOidcUser:
    @pytest.mark.asyncio
    async def test_existing_oidc_user_gets_auth_method_set_to_local(self, db):
        """Regression: re-seeding an existing user with auth_method='oidc' and a
        password must normalise auth_method to 'local' so they can log in.

        This handles the case where a deployment migrated from OIDC to LOCAL and
        existing rows still carry auth_method='oidc'.
        """
        email = "oidc_to_local@mattin-test.com"
        existing = _make_oidc_user(db, email)
        assert existing.auth_method == "oidc"

        from utils.seed_dev_users import seed_dev_users_async

        users_data = [
            {
                "email": email,
                "name": existing.name,
                "description": "",
                "password": "N3wL0c4lP@ss!",
            }
        ]

        await seed_dev_users_async(db, users_data=users_data)

        db.refresh(existing)
        assert existing.auth_method == "local", (
            "Regression: re-seeding an 'oidc' user with a password must normalise "
            f"auth_method to 'local', got {existing.auth_method!r}"
        )

    @pytest.mark.asyncio
    async def test_existing_oidc_user_with_credential_is_loginable_after_reseed(self, db):
        """An existing OIDC user that already has a credential row can have their
        password updated via re-seeding and will then be loginable.

        Note: if the OIDC user has NO credential row (no prior LOCAL usage),
        admin_set_password will fail (it updates, not creates). The test below
        uses a user who has a placeholder credential row, mirroring what
        admin_create_user would have created.
        """
        import asyncio
        email = "oidc_relogin@mattin-test.com"
        existing = _make_oidc_user(db, email)

        # Give the OIDC user a placeholder credential row so admin_set_password can update it.
        from models.user_credential import UserCredential
        from services.auth.credential_service import _sync_hash

        placeholder_hash = _sync_hash("__placeholder__")
        cred = UserCredential(
            user_id=existing.user_id,
            hashed_password=placeholder_hash,
            is_verified=True,
        )
        db.add(cred)
        db.flush()

        from services.auth.credential_service import CredentialService
        from utils.seed_dev_users import seed_dev_users_async

        password = "R3s33dP@ss!"
        users_data = [
            {"email": email, "name": "Re-seeded", "description": "", "password": password}
        ]
        await seed_dev_users_async(db, users_data=users_data)

        # auth_method must now be 'local'.
        db.refresh(existing)
        assert existing.auth_method == "local"

        # Must be loginable with the new password.
        authenticated = await CredentialService.authenticate(db, email, password)
        assert authenticated.email == email

    @pytest.mark.asyncio
    async def test_existing_oidc_user_without_password_not_normalised(self, db):
        """Re-seeding without a password source leaves auth_method unchanged.

        Without a password there is nothing to repair: we cannot make the user
        loginable without a credential, so we do not touch auth_method.
        """
        email = "oidc_nopw@mattin-test.com"
        existing = _make_oidc_user(db, email)

        from utils.seed_dev_users import seed_dev_users_async

        # Re-seed with no password — normalisation should NOT apply.
        users_data = [
            {"email": email, "name": existing.name, "description": "", "password": None}
        ]
        await seed_dev_users_async(db, users_data=users_data)

        db.refresh(existing)
        # auth_method must remain 'oidc' — we cannot repair without a password.
        assert existing.auth_method == "oidc"


# ---------------------------------------------------------------------------
# Bug 4 — bootstrap_omniadmins idempotency (new user path + already-verified path)
# ---------------------------------------------------------------------------


class TestBootstrapOmniadminsIdempotency:
    """Exercises bootstrap_omniadmins against the test DB.

    The advisory-lock path requires PostgreSQL; SQLite does not support
    pg_try_advisory_lock.  The test DB is on port 5433, which supports it.

    Note: the conftest db fixture uses a rolled-back outer transaction so
    advisory-lock calls (which are session-scoped in PG) may behave differently
    than in production — but the core idempotency logic (create-once,
    skip-if-verified) is exercised fully.
    """

    @pytest.mark.asyncio
    async def test_first_run_creates_user_with_local_auth_method(self, db, monkeypatch):
        """bootstrap_omniadmins must create a LOCAL user for a new omniadmin email."""
        email = "bootstrap_new@mattin-test.com"
        monkeypatch.setenv("AICT_OMNIADMINS", email)
        monkeypatch.setenv("AUTH_BOOTSTRAP_OMNIADMINS", "true")

        from services.auth.omniadmin_bootstrap import _provision_single_omniadmin
        from repositories.user_repository import UserRepository

        # Ensure no user exists yet.
        user_repo = UserRepository(db)
        assert user_repo.get_by_email(email) is None

        await _provision_single_omniadmin(db, email)

        created = user_repo.get_by_email(email)
        assert created is not None, "bootstrap must create a user row"
        assert created.auth_method == "local"

    @pytest.mark.asyncio
    async def test_first_run_issues_reset_token(self, db, monkeypatch):
        """A new omniadmin account must have an outstanding reset_token after bootstrap."""
        email = "bootstrap_token@mattin-test.com"
        monkeypatch.setenv("AICT_OMNIADMINS", email)

        from models.user_credential import UserCredential
        from repositories.user_repository import UserRepository
        from services.auth.omniadmin_bootstrap import _provision_single_omniadmin

        await _provision_single_omniadmin(db, email)

        user_repo = UserRepository(db)
        user = user_repo.get_by_email(email)
        assert user is not None

        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        assert cred is not None, "bootstrap must create a credential row"
        assert cred.reset_token is not None, (
            "bootstrap must issue a reset_token so the operator can set a password"
        )

    @pytest.mark.asyncio
    async def test_second_run_on_verified_user_is_noop(self, db, monkeypatch):
        """Regression: a second bootstrap run must not re-provision an already-verified user.

        Calling _provision_single_omniadmin twice — first run creates the user
        and issues a token; we then mark the user as verified (simulating the
        operator completing the set-password flow) and run a second time.  The
        second run must leave the credential row completely unchanged.
        """
        email = "bootstrap_idempotent@mattin-test.com"
        monkeypatch.setenv("AICT_OMNIADMINS", email)

        from models.user_credential import UserCredential
        from repositories.user_repository import UserRepository
        from services.auth.omniadmin_bootstrap import _provision_single_omniadmin

        # --- First run: creates user + token ---
        await _provision_single_omniadmin(db, email)

        user_repo = UserRepository(db)
        user = user_repo.get_by_email(email)
        assert user is not None

        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        assert cred is not None

        # Simulate operator completing the set-password flow: mark verified and
        # clear the token (as consume_set_password_token would do).
        cred.is_verified = True
        cred.reset_token = None
        cred.reset_token_expiry = None
        db.flush()

        token_after_first = cred.reset_token  # None after verification

        # --- Second run: must be a no-op ---
        await _provision_single_omniadmin(db, email)

        db.refresh(cred)
        assert cred.is_verified is True
        # reset_token must still be None — no new token issued for verified user.
        assert cred.reset_token is None, (
            "Regression: bootstrap must not re-issue a token for an already-verified omniadmin"
        )

    @pytest.mark.asyncio
    async def test_second_run_with_valid_outstanding_link_is_noop(self, db, monkeypatch):
        """If a valid (unexpired) link already exists, the second run skips token re-issuance."""
        email = "bootstrap_existing_link@mattin-test.com"
        monkeypatch.setenv("AICT_OMNIADMINS", email)

        from models.user_credential import UserCredential
        from repositories.user_repository import UserRepository
        from services.auth.omniadmin_bootstrap import _provision_single_omniadmin

        # First run — creates user + token.
        await _provision_single_omniadmin(db, email)

        user_repo = UserRepository(db)
        user = user_repo.get_by_email(email)
        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()

        # Capture the original token (user is NOT verified, link is outstanding).
        original_token = cred.reset_token
        assert original_token is not None

        # Second run — should detect the valid outstanding link and skip.
        await _provision_single_omniadmin(db, email)

        db.refresh(cred)
        # Token must be unchanged — no new token was issued.
        assert cred.reset_token == original_token, (
            "Regression: bootstrap must not replace a still-valid outstanding link"
        )

    @pytest.mark.asyncio
    async def test_exactly_one_user_created_after_two_runs(self, db, monkeypatch):
        """Idempotency: two calls to _provision_single_omniadmin create exactly one user."""
        email = "bootstrap_once@mattin-test.com"
        monkeypatch.setenv("AICT_OMNIADMINS", email)

        from models.user import User
        from services.auth.omniadmin_bootstrap import _provision_single_omniadmin

        await _provision_single_omniadmin(db, email)
        await _provision_single_omniadmin(db, email)

        count = db.query(User).filter(User.email == email).count()
        assert count == 1, (
            f"Idempotency violated: expected exactly 1 user, found {count}"
        )
