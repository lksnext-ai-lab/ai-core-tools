"""
Development user seeding utility.

This script creates test users in the database for development mode authentication.
Only use in development environments.

Usage:
    python -m utils.seed_dev_users
    
Or via PowerShell (with venv activated):
    .\.venv\Scripts\Activate.ps1; python -m utils.seed_dev_users
"""

import sys
import os
from pathlib import Path

# Add backend directory to path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy.orm import Session
from db.database import SessionLocal
from services.user_service import UserService
from utils.logger import get_logger

logger = get_logger(__name__)

# Default dev users to create
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


def seed_dev_users(db: Session, users_data: list = None):
    """
    Seed development users into the database.
    
    Args:
        db: Database session
        users_data: List of user dicts with email, name, description.
                   If None, uses DEV_USERS default list.
    
    Returns:
        List of created/updated user objects
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
                    f"(user_id: {user.user_id}) - {user_data['description']}"
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


def main():
    """Main function to run seeding."""
    print("\n" + "="*70)
    print("  Development User Seeding Utility")
    print("="*70 + "\n")
    
    # Check environment
    oidc_enabled = os.getenv('OIDC_ENABLED', 'true').lower() == 'true'
    
    if oidc_enabled:
        print("⚠️  WARNING: OIDC authentication is enabled!")
        print("   Set OIDC_ENABLED=false in your .env file")
        print("   to use development authentication.\n")
        response = input("Continue anyway? (y/N): ").strip().lower()
        if response != 'y':
            print("\nAborted.\n")
            return
    
    print("This will create the following test users:\n")
    for user in DEV_USERS:
        print(f"  • {user['email']:25s} - {user['description']}")
    
    print("\n" + "-"*70)
    response = input("\nProceed with seeding? (y/N): ").strip().lower()
    
    if response != 'y':
        print("\nAborted.\n")
        return
    
    print("\nSeeding users...\n")
    
    # Create database session
    db = SessionLocal()
    
    try:
        result = seed_dev_users(db)
        
        print("\n" + "="*70)
        print("  Seeding Complete!")
        print("="*70)
        print(f"\n  Created:  {len(result['created'])} new users")
        print(f"  Existing: {len(result['existing'])} users already in database")
        print(f"  Total:    {result['total']} users ready for dev mode\n")
        
        if result['created']:
            print("  Newly created users:")
            for user in result['created']:
                print(f"    • {user.email} (ID: {user.user_id})")
        
        print("\n  You can now login with any of these emails in dev mode.")
        print("  Set OIDC_ENABLED=false in frontend/.env to use dev login.\n")
        
    except Exception as e:
        logger.error(f"Error seeding users: {str(e)}", exc_info=True)
        print(f"\n❌ Error: {str(e)}\n")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
