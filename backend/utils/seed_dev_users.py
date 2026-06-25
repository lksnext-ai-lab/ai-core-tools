"""Development user seeding utility.

Creates users in the database so they can log in while the platform runs in
LOCAL authentication mode (``AICT_LOGIN=LOCAL``).

In LOCAL mode, users must have a password.  This script can set passwords via
the ``email:Name:password`` CSV format or via the ``AICT_DEV_SEED_PASSWORD``
env var.

CSV formats accepted:
    "email:Name"              — user only (seeded without credentials; admin must issue a set-password link)
    "email:Name:password"     — user + password (LOCAL mode)
    "email::password"         — email + password, name derived from email local-part

The user set is resolved with the following precedence:
    1. ``--users "email:Name[:pw],email2:Name2[:pw]"`` CLI argument
    2. ``AICT_DEV_SEED_USERS`` environment variable (same CSV format)
    3. the built-in ``DEV_USERS`` defaults

Password fallback (LOCAL mode):
    ``AICT_DEV_SEED_PASSWORD`` is applied ONLY to users explicitly provided via
    ``--users`` or ``AICT_DEV_SEED_USERS``.  It is intentionally NOT applied to
    the built-in ``DEV_USERS`` defaults (``admin@example.com`` etc.) — doing so
    would silently give well-known example accounts a shared password from an
    env var, which is a security anti-pattern in production deployments that
    accidentally have the env var set.

    In LOCAL mode, a user without any password source is seeded without
    credentials (created but unable to log in until an admin issues a
    set-password link).

Omniadmin recovery path:
    If the omniadmin account (set via ``AICT_OMNIADMINS``) is accidentally
    locked out or has no credential, run this script in LOCAL mode with an
    explicit password, e.g.::

        AICT_DEV_SEED_USERS="admin@acme.com:Admin:NewPass123!" \\
        python -m utils.seed_dev_users --yes

    Omniadmins are exempt from the exponential lockout in
    ``CredentialService.authenticate`` (they can never be locked out of their
    own instance by brute-force).  If their account is deactivated, use the
    admin panel or the database directly to flip ``is_active=True``.

Safety:
    The script refuses to run unless ``AICT_LOGIN`` is ``LOCAL``,
    to avoid creating users in an OIDC deployment.  Use ``--force`` to
    override that guard deliberately.

Designed to be safe and non-interactive inside containers. Typical usage::

    # Inside a running Docker deployment (no TTY required):
    docker compose exec -T backend python -m utils.seed_dev_users --yes

    # LOCAL mode with explicit passwords:
    docker compose exec -T backend \\
      python -m utils.seed_dev_users --yes \\
      --users "admin@acme.com:Admin:S3cr3tPass!,dev@acme.com:Dev:AnotherPass!"

    # LOCAL mode with a shared fallback password (applied only to --users entries):
    AICT_DEV_SEED_PASSWORD=S3cr3tPass! \\
      python -m utils.seed_dev_users --yes \\
      --users "admin@acme.com:Admin,dev@acme.com:Dev"
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy.orm import Session
from db.database import SessionLocal
from services.user_service import UserService
from utils.logger import get_logger

logger = get_logger(__name__)

DEV_USERS = [
    {
        "email": "admin@example.com",
        "name": "Admin User",
        "description": "Admin/test user for development",
        "password": None,
    },
    {
        "email": "user1@example.com",
        "name": "Test User 1",
        "description": "Regular test user 1",
        "password": None,
    },
    {
        "email": "user2@example.com",
        "name": "Test User 2",
        "description": "Regular test user 2",
        "password": None,
    },
    {
        "email": "dev@example.com",
        "name": "Developer",
        "description": "Developer test account",
        "password": None,
    },
]

SEED_USERS_ENV = "AICT_DEV_SEED_USERS"
SEED_PASSWORD_ENV = "AICT_DEV_SEED_PASSWORD"
_SEEDABLE_MODES = ("LOCAL",)


def _parse_users_spec(spec: str) -> list:
    """Parse comma-separated ``email:Name[:password]`` entries into seed user dicts."""
    users = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue

        parts = chunk.split(":", 2)
        email = parts[0].strip().lower()
        name = parts[1].strip() if len(parts) > 1 else ""
        password: str | None = parts[2].strip() if len(parts) > 2 else None

        if not email:
            continue
        if not name:
            name = email.split("@", 1)[0]

        if password == "":
            password = None

        users.append({
            "email": email,
            "name": name,
            "description": "Seeded dev user",
            "password": password,
        })

    return users


def resolve_users(cli_spec: str = None) -> list:
    """Resolve user list from ``--users`` arg, ``AICT_DEV_SEED_USERS`` env var, or built-in defaults."""
    if cli_spec:
        return _parse_users_spec(cli_spec)

    env_spec = os.getenv(SEED_USERS_ENV, "").strip()
    if env_spec:
        return _parse_users_spec(env_spec)

    return list(DEV_USERS)


def _is_explicit_user_spec(cli_spec: str = None) -> bool:
    """Return True when users came from ``--users`` or ``AICT_DEV_SEED_USERS`` (not built-in defaults).

    Used to gate whether ``AICT_DEV_SEED_PASSWORD`` is applied as a fallback —
    built-in example accounts must not silently receive a shared env-var password.
    """
    if cli_spec:
        return True
    return bool(os.getenv(SEED_USERS_ENV, "").strip())


def current_login_mode() -> str:
    """Return ``AICT_LOGIN`` uppercased."""
    return os.getenv("AICT_LOGIN", "OIDC").strip().upper()


def is_seedable_mode() -> bool:
    """Return True when the current login mode supports dev user seeding."""
    return current_login_mode() in _SEEDABLE_MODES


async def seed_dev_users_async(
    db: Session,
    users_data: list = None,
    apply_password_fallback: bool = False,
) -> dict:
    """Idempotently seed dev users.  In LOCAL mode uses ``CredentialService``
    so ``auth_method='local'`` is set correctly.

    Args:
        apply_password_fallback: When True, ``AICT_DEV_SEED_PASSWORD`` is
            applied to explicit users without a per-user password.  Never set
            for the built-in ``DEV_USERS`` defaults.

    Returns:
        Dict with ``created``, ``existing`` lists, and ``total`` count.
    """
    from services.auth.credential_service import CredentialService, UserAlreadyExistsError
    from services.email import smtp_configured

    if users_data is None:
        users_data = DEV_USERS

    login_mode = current_login_mode()
    fallback_password: str | None = (
        os.getenv(SEED_PASSWORD_ENV, "").strip() or None
    ) if apply_password_fallback else None

    created_users = []
    updated_users = []

    for user_data in users_data:
        email = user_data["email"]
        name = user_data["name"]
        explicit_password: str | None = user_data.get("password")

        effective_password: str | None = explicit_password or (
            fallback_password if login_mode == "LOCAL" else None
        )

        existing_user = UserService.get_user_by_email(db, email)
        if existing_user:
            user = existing_user
            logger.info(
                "User already exists: %s (user_id: %s)",
                email,
                existing_user.user_id,
            )
            # Repair legacy rows with wrong auth_method so they can log in.
            if login_mode == "LOCAL" and effective_password and user.auth_method != "local":
                logger.info(
                    "Normalising auth_method for existing user %s: %s -> local",
                    email,
                    user.auth_method,
                )
                user.auth_method = "local"
                user.email_verified = not smtp_configured()
                db.flush()
            updated_users.append(user)
        elif login_mode == "LOCAL":
            try:
                user = await CredentialService.admin_create_user(db, email=email, name=name)
            except UserAlreadyExistsError:
                # Concurrent creation — fall back to the existing row.
                user = UserService.get_user_by_email(db, email)
                logger.info("User created concurrently: %s (user_id: %s)", email, user.user_id)
                updated_users.append(user)
                if effective_password:
                    try:
                        await CredentialService.admin_set_password(db, user_id=user.user_id, new_password=effective_password)
                        logger.info("Credential set for user: %s (user_id: %s)", email, user.user_id)
                    except Exception as exc:
                        logger.error(
                            "Failed to set credential for user %s: %s",
                            email,
                            exc,
                            exc_info=True,
                        )
                continue
            logger.info(
                "Created dev user: %s (user_id: %s) - %s",
                email,
                user.user_id,
                user_data.get("description", ""),
            )
            created_users.append(user)
        else:
            user, created = UserService.get_or_create_user(db=db, email=email, name=name)
            if created:
                logger.info(
                    "Created dev user: %s (user_id: %s) - %s",
                    email,
                    user.user_id,
                    user_data.get("description", ""),
                )
                created_users.append(user)
            else:
                logger.info("User already exists: %s", email)
                updated_users.append(user)

        if login_mode == "LOCAL" and effective_password:
            try:
                await CredentialService.admin_set_password(db, user_id=user.user_id, new_password=effective_password)
                logger.info("Credential set for user: %s (user_id: %s)", email, user.user_id)
            except Exception as exc:
                logger.error(
                    "Failed to set credential for user %s: %s",
                    email,
                    exc,
                    exc_info=True,
                )
        elif login_mode == "LOCAL" and not effective_password:
            logger.info(
                "User %s seeded without password (no password source in LOCAL mode). "
                "Admin must issue a set-password link before this user can log in.",
                email,
            )

    return {
        "created": created_users,
        "existing": updated_users,
        "total": len(created_users) + len(updated_users),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed_dev_users",
        description="Seed development users for LOCAL login mode.",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Run non-interactively (skip confirmation prompts). Required when "
             "invoked without a TTY, e.g. 'docker compose exec -T'.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Seed even if AICT_LOGIN is not LOCAL. Use with care.",
    )
    parser.add_argument(
        "--users",
        metavar="SPEC",
        default=None,
        help="Comma-separated users to create, e.g. "
             "'admin@acme.com:Admin:Pass123!,dev@acme.com:Dev'. Overrides "
             f"{SEED_USERS_ENV} and the built-in defaults. "
             "In LOCAL mode a third ':password' field is supported.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="Print the resolved user list and exit without writing anything.",
    )
    return parser


def _print_users(users: list) -> None:
    for user in users:
        description = user.get("description", "")
        has_pw = " [+password]" if user.get("password") else ""
        suffix = f" - {description}" if description else ""
        print(f"  - {user['email']:30s} {user['name']}{has_pw}{suffix}")


def main():
    """CLI entry point for user seeding."""
    args = _build_arg_parser().parse_args()

    users = resolve_users(args.users)
    is_explicit = _is_explicit_user_spec(args.users)
    login_mode = current_login_mode()
    fallback_password = os.getenv(SEED_PASSWORD_ENV, "").strip() or None

    print("\n" + "=" * 70)
    print("  Development User Seeding Utility")
    print("=" * 70 + "\n")

    if not users:
        print("No users to seed (empty list resolved). Nothing to do.\n")
        return

    if args.list_only:
        print(f"Login mode: {login_mode}")
        if fallback_password and login_mode == "LOCAL":
            print(f"Fallback password: {SEED_PASSWORD_ENV} is set")
        print(f"Resolved users ({len(users)}):\n")
        _print_users(users)
        print()
        return

    if not is_seedable_mode() and not args.force:
        message = (
            f"AICT_LOGIN={login_mode} is not a development mode. "
            "Seeding dev users is only intended for LOCAL. "
            "Re-run with --force to override."
        )
        if args.yes:
            print(f"ERROR: {message}\n")
            sys.exit(2)
        print(f"WARNING: {message}\n")
        if input("Continue anyway? (y/N): ").strip().lower() != "y":
            print("\nAborted.\n")
            return

    print(f"Login mode: {login_mode}")
    if login_mode == "LOCAL" and fallback_password and is_explicit:
        print(f"Fallback password: {SEED_PASSWORD_ENV} is set (applied to explicitly-provided users without a per-user password)")
    elif login_mode == "LOCAL" and fallback_password and not is_explicit:
        print(f"Note: {SEED_PASSWORD_ENV} is set but will NOT be applied to the built-in default users.")
    print(f"This will create/update the following users ({len(users)}):\n")
    _print_users(users)
    print("\n" + "-" * 70)

    if not args.yes:
        if input("\nProceed with seeding? (y/N): ").strip().lower() != "y":
            print("\nAborted.\n")
            return

    print("\nSeeding users...\n")

    db = SessionLocal()
    try:
        result = asyncio.run(seed_dev_users_async(db, users, apply_password_fallback=is_explicit))
        db.commit()

        print("\n" + "=" * 70)
        print("  Seeding Complete!")
        print("=" * 70)
        print(f"\n  Created:  {len(result['created'])} new users")
        print(f"  Existing: {len(result['existing'])} users already in database")
        print(f"  Total:    {result['total']} users ready for {login_mode} mode\n")

        if result["created"]:
            print("  Newly created users:")
            for user in result["created"]:
                print(f"    - {user.email} (ID: {user.user_id})")

        if login_mode == "LOCAL":
            print(
                "\n  In LOCAL mode, users with no password source will need an "
                "admin to issue a set-password link via the admin panel or:\n"
                "  POST /internal/admin/users/{user_id}/reset-link\n"
            )
        else:
            print("\n  These emails can now log in while AICT_LOGIN=LOCAL.\n")

    except Exception as exc:
        db.rollback()
        logger.error("Error seeding users: %s", exc, exc_info=True)
        print(f"\nERROR: {exc}\n")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
