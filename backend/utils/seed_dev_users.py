"""
Development user seeding utility.

Creates users in the database so they can log in while the platform runs in
development authentication mode (``AICT_LOGIN=FAKE``), where any pre-existing
user email is accepted without a password.

The user set is resolved with the following precedence:
    1. ``--users "email:Name,email2:Name2"`` CLI argument
    2. ``AICT_DEV_SEED_USERS`` environment variable (same CSV format)
    3. the built-in ``DEV_USERS`` defaults

Designed to be safe and non-interactive inside containers. Typical usage:

    # Inside a running Docker deployment (no TTY required):
    docker compose exec -T backend python -m utils.seed_dev_users --yes

    # Local interactive run (asks for confirmation):
    python -m utils.seed_dev_users

The script refuses to run unless ``AICT_LOGIN`` is ``FAKE`` or ``LOCAL``, to
avoid creating password-less users in an OIDC deployment. Use ``--force`` to
override that guard deliberately.
"""

import argparse
import os
import sys
from pathlib import Path

# Add backend directory to path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy.orm import Session
from db.database import SessionLocal
from services.user_service import UserService
from utils.logger import get_logger

logger = get_logger(__name__)

# Default dev users to create when no CLI/env list is provided
DEV_USERS = [
    {
        "email": "admin@example.com",
        "name": "Admin User",
        "description": "Admin/test user for development"
    },
    {
        "email": "user1@example.com",
        "name": "Test User 1",
        "description": "Regular test user 1"
    },
    {
        "email": "user2@example.com",
        "name": "Test User 2",
        "description": "Regular test user 2"
    },
    {
        "email": "dev@example.com",
        "name": "Developer",
        "description": "Developer test account"
    },
]

# Env var holding a declarative, comma-separated user list ("email:Name,email2:Name2")
SEED_USERS_ENV = "AICT_DEV_SEED_USERS"

# Auth modes under which seeding password-less dev users is meaningful
_SEEDABLE_MODES = ("FAKE", "LOCAL")


def _parse_users_spec(spec: str) -> list:
    """Parse a ``email:Name,email2:Name2`` string into seed user dicts.

    The name part is optional; when omitted, the local part of the email is
    used as a fallback display name. Blank entries are ignored.

    Args:
        spec: Comma-separated user specification.

    Returns:
        List of user dicts with ``email``, ``name`` and ``description`` keys.
    """
    users = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue

        if ":" in chunk:
            email, name = (part.strip() for part in chunk.split(":", 1))
        else:
            email, name = chunk, ""

        if not email:
            continue
        if not name:
            name = email.split("@", 1)[0]

        users.append({
            "email": email,
            "name": name,
            "description": "Seeded dev user",
        })

    return users


def resolve_users(cli_spec: str = None) -> list:
    """Resolve the user list from CLI arg, env var, or built-in defaults.

    Args:
        cli_spec: Value of the ``--users`` argument, if provided.

    Returns:
        List of user dicts to seed.
    """
    if cli_spec:
        return _parse_users_spec(cli_spec)

    env_spec = os.getenv(SEED_USERS_ENV, "").strip()
    if env_spec:
        return _parse_users_spec(env_spec)

    return DEV_USERS


def current_login_mode() -> str:
    """Return the configured login mode (``AICT_LOGIN``), uppercased."""
    return os.getenv("AICT_LOGIN", "OIDC").strip().upper()


def is_seedable_mode() -> bool:
    """Whether the current login mode allows seeding dev users safely."""
    return current_login_mode() in _SEEDABLE_MODES


def seed_dev_users(db: Session, users_data: list = None):
    """
    Seed development users into the database.

    Idempotent: existing users (matched by email) are left untouched.

    Args:
        db: Database session
        users_data: List of user dicts with email, name, description.
                   If None, uses DEV_USERS default list.

    Returns:
        Dict with ``created``, ``existing`` user lists and ``total`` count.
    """
    if users_data is None:
        users_data = DEV_USERS

    created_users = []
    updated_users = []

    for user_data in users_data:
        email = user_data["email"]
        name = user_data["name"]

        # Check if user already exists
        existing_user = UserService.get_user_by_email(db, email)

        if existing_user:
            logger.info(
                f"User already exists: {email} "
                f"(user_id: {existing_user.user_id})"
            )
            updated_users.append(existing_user)
        else:
            # Create new user
            user, created = UserService.get_or_create_user(
                db=db,
                email=email,
                name=name
            )

            if created:
                logger.info(
                    f"Created dev user: {email} "
                    f"(user_id: {user.user_id}) - {user_data.get('description', '')}"
                )
                created_users.append(user)
            else:
                logger.info(f"User already exists: {email}")
                updated_users.append(user)

    return {
        "created": created_users,
        "existing": updated_users,
        "total": len(created_users) + len(updated_users)
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed_dev_users",
        description="Seed development users for FAKE/LOCAL login mode.",
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
        help="Seed even if AICT_LOGIN is not FAKE/LOCAL. Use with care.",
    )
    parser.add_argument(
        "--users",
        metavar="SPEC",
        default=None,
        help="Comma-separated users to create, e.g. "
             "'admin@acme.com:Admin,dev@acme.com:Dev'. Overrides "
             f"{SEED_USERS_ENV} and the built-in defaults.",
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
        suffix = f" - {description}" if description else ""
        print(f"  - {user['email']:30s} {user['name']}{suffix}")


def main():
    """CLI entry point for user seeding."""
    args = _build_arg_parser().parse_args()

    users = resolve_users(args.users)
    login_mode = current_login_mode()

    print("\n" + "=" * 70)
    print("  Development User Seeding Utility")
    print("=" * 70 + "\n")

    if not users:
        print("No users to seed (empty list resolved). Nothing to do.\n")
        return

    if args.list_only:
        print(f"Login mode: {login_mode}")
        print(f"Resolved users ({len(users)}):\n")
        _print_users(users)
        print()
        return

    # Safety guard: only seed password-less users in dev/local modes.
    if not is_seedable_mode() and not args.force:
        message = (
            f"AICT_LOGIN={login_mode} is not a development mode. "
            "Seeding password-less users is only intended for FAKE/LOCAL. "
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
    print(f"This will create the following users ({len(users)}):\n")
    _print_users(users)
    print("\n" + "-" * 70)

    if not args.yes:
        if input("\nProceed with seeding? (y/N): ").strip().lower() != "y":
            print("\nAborted.\n")
            return

    print("\nSeeding users...\n")

    db = SessionLocal()
    try:
        result = seed_dev_users(db, users)
        db.commit()

        print("\n" + "=" * 70)
        print("  Seeding Complete!")
        print("=" * 70)
        print(f"\n  Created:  {len(result['created'])} new users")
        print(f"  Existing: {len(result['existing'])} users already in database")
        print(f"  Total:    {result['total']} users ready for dev mode\n")

        if result["created"]:
            print("  Newly created users:")
            for user in result["created"]:
                print(f"    - {user.email} (ID: {user.user_id})")

        print("\n  These emails can now log in while AICT_LOGIN=FAKE.\n")

    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding users: {str(e)}", exc_info=True)
        print(f"\nERROR: {str(e)}\n")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
