#!/usr/bin/env python3
"""
Basic test script for core services (without problematic imports)
"""

import asyncio
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.session_management_service import SessionManagementService
from services.file_management_service import FileManagementService


async def test_session_management():
    """Test session management service"""
    print("🧪 Testing Session Management Service...")
    
    session_service = SessionManagementService()
    
    # Test user context
    user_context = {"user_id": 123, "oauth": True, "app_id": 1}
    
    # Test session creation
    session = await session_service.get_user_session(agent_id=1, user_context=user_context)
    if session:
        print(f"✅ Session created: {session.id}")
    else:
        print("❌ Session creation failed")
        return False
    
    # Test message addition
    await session_service.add_message_to_session(session.id, "Hello", "Hi there!")
    
    # Test conversation history
    history = await session_service.get_conversation_history(agent_id=1, user_context=user_context)
    if len(history) == 1:
        print(f"✅ Message added to history: {history[0]}")
    else:
        print("❌ Message not added to history")
        return False
    
    # Test session reset
    success = await session_service.reset_user_session(agent_id=1, user_context=user_context)
    if success:
        print("✅ Session reset successful")
    else:
        print("❌ Session reset failed")
        return False
    
    print("✅ Session Management Service tests passed!")
    return True


async def test_file_management():
    """Test file management service"""
    print("\n🧪 Testing File Management Service...")
    
    file_service = FileManagementService()
    
    # Test file stats
    stats = file_service.get_file_stats()
    print(f"✅ File stats: {stats}")
    
    # Test session stats
    session_service = SessionManagementService()
    session_stats = session_service.get_session_stats()
    print(f"✅ Session stats: {session_stats}")
    
    print("✅ File Management Service tests passed!")
    return True


async def main():
    """Run all tests"""
    print("🚀 Starting Basic Service Tests...\n")
    
    tests = [
        test_session_management(),
        test_file_management()
    ]
    
    results = await asyncio.gather(*tests, return_exceptions=True)
    
    print("\n📊 Test Results:")
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"❌ Test {i+1} failed with exception: {result}")
        elif result:
            print(f"✅ Test {i+1} passed")
        else:
            print(f"❌ Test {i+1} failed")
    
    success_count = sum(1 for r in results if r and not isinstance(r, Exception))
    total_count = len(results)
    
    print(f"\n🎯 Overall Result: {success_count}/{total_count} tests passed")
    
    if success_count == total_count:
        print("🎉 All tests passed! Core services are working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 