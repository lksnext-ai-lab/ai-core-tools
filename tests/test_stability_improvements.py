#!/usr/bin/env python3
"""
Simple test script to verify our stability improvements work
"""
import sys
import os
import requests

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_app_running():
    """Test that the Flask app is running and responding"""
    print("🧪 Testing Flask app...")
    
    try:
        response = requests.get('http://localhost:4321/', timeout=5)
        if response.status_code in [200, 302]:
            print("✅ Flask app is running and responding")
            return True
        else:
            print(f"❌ Flask app returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Flask app test failed: {e}")
        return False

def test_service_imports():
    """Test that all our enhanced services can be imported"""
    print("\n🧪 Testing service imports...")
    
    try:
        from services.user_service import UserService
        from services.domain_service import DomainService
        from services.api_key_service import APIKeyService
        from utils.logger import get_logger
        from utils.error_handlers import ValidationError, NotFoundError
        
        # Test basic functionality exists
        assert hasattr(UserService, 'get_user_by_id')
        assert hasattr(UserService, 'get_user_subscription')
        assert hasattr(DomainService, 'get_domain')
        assert hasattr(APIKeyService, 'create_api_key')
        
        print("✅ All enhanced services imported successfully")
        return True
    except Exception as e:
        print(f"❌ Service import test failed: {e}")
        return False

def test_error_handlers():
    """Test that error handlers work"""
    print("\n🧪 Testing error handlers...")
    
    try:
        from utils.error_handlers import ValidationError, NotFoundError, DatabaseError
        from utils.logger import get_logger
        
        # Test logger
        logger = get_logger("test")
        logger.info("Test log message")
        
        # Test exception creation
        ve = ValidationError("Test validation")
        nfe = NotFoundError("Test not found", "test")
        
        assert str(ve) == "Test validation"
        assert nfe.resource == "test"
        
        print("✅ Error handlers working correctly")
        return True
    except Exception as e:
        print(f"❌ Error handlers test failed: {e}")
        return False

def test_method_counts():
    """Test that UserService has expected number of methods"""
    print("\n🧪 Testing UserService method count...")
    
    try:
        from services.user_service import UserService
        
        # Count methods (excluding private and built-in methods)
        methods = [name for name in dir(UserService) 
                  if not name.startswith('_') and callable(getattr(UserService, name))]
        
        expected_methods = [
            'get_all_users', 'get_user_by_id', 'get_user_basic', 'get_user_by_email',
            'create_user', 'update_user', 'delete_user', 
            'search_users', 'get_user_stats',
            'get_or_create_user', 'user_exists', 'get_user_app_count', 'validate_user_data',
            'get_user_subscription', 'get_user_current_plan', 
            'can_user_create_agent', 'can_user_create_domain', 'user_has_feature'
        ]
        
        missing = [method for method in expected_methods if method not in methods]
        
        if missing:
            print(f"❌ Missing methods: {missing}")
            return False
        
        print(f"✅ UserService has all {len(expected_methods)} expected methods")
        return True
    except Exception as e:
        print(f"❌ Method count test failed: {e}")
        return False

def main():
    """Run simple tests"""
    print("🚀 Simple Test: IA-Core-Tools Stability Improvements")
    print("=" * 55)
    
    tests = [
        test_app_running,
        test_service_imports,
        test_error_handlers,
        test_method_counts
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            failed += 1
    
    print("\n" + "=" * 55)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! Stability improvements are working!")
        print("✨ Phase 1 & Phase 2 implementation successful!")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above.")
        return 1

if __name__ == "__main__":
    exit(main()) 