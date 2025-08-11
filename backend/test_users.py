#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import all models to ensure relationships are resolved
from models.app import App
from models.user import User
from models.app_collaborator import AppCollaborator
from models.mcp_config import MCPConfig
from models.agent import Agent
from models.api_key import APIKey
from models.silo import Silo
from models.domain import Domain
from models.repository import Repository
from models.ai_service import AIService
from models.embedding_service import EmbeddingService
from models.output_parser import OutputParser
from models.subscription import Subscription
from models.api_usage import APIUsage
from models.resource import Resource
from models.url import Url

from db.database import SessionLocal
from services.user_service import UserService

def test_users():
    """Test if users exist and UserService works"""
    session = SessionLocal()
    try:
        # Check total users
        total_users = session.query(User).count()
        print(f"Total users in database: {total_users}")
        
        # List all users
        users = session.query(User).all()
        for user in users:
            print(f"User: {user.user_id} - {user.email} - {user.name} - Created: {user.create_date}")
        
        # Test UserService
        print("\nTesting UserService.get_all_users():")
        try:
            users_list, total = UserService.get_all_users(session, 1, 10)
            print(f"UserService returned {len(users_list)} users, total: {total}")
            for user in users_list:
                print(f"  {user['user_id']} - {user['email']} - {user['name']}")
        except Exception as e:
            print(f"UserService.get_all_users() failed: {e}")
            
    finally:
        session.close()

if __name__ == "__main__":
    test_users() 