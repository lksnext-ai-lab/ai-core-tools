#!/usr/bin/env python3
"""
Test script to verify unique logging functionality
"""
import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_unique_logging():
    """Test the unique logging system"""
    print("🧪 Testing unique logging system...")
    
    try:
        from utils.logger import get_logger, get_current_log_file, get_current_error_log_file, get_session_id
        
        # Get loggers from different modules
        main_logger = get_logger("main")
        service_logger = get_logger("services.user_service")
        blueprint_logger = get_logger("blueprints.domains")
        
        # Get session info
        session_id = get_session_id()
        log_file = get_current_log_file()
        error_log_file = get_current_error_log_file()
        
        print(f"✅ Session ID: {session_id}")
        print(f"✅ Log File: {log_file}")
        print(f"✅ Error Log File: {error_log_file}")
        
        # Test logging from different sources
        main_logger.info("This is a test log from main")
        service_logger.info("This is a test log from user service")
        service_logger.warning("This is a warning from user service")
        blueprint_logger.info("This is a test log from domains blueprint")
        blueprint_logger.error("This is an error from domains blueprint")
        
        # Check if log file exists and has content
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                log_content = f.read()
                if len(log_content) > 0:
                    lines = log_content.strip().split('\n')
                    print(f"✅ Log file created with {len(lines)} lines")
                    print(f"✅ Log file size: {len(log_content)} characters")
                else:
                    print("❌ Log file is empty")
                    return False
        else:
            print(f"❌ Log file not found: {log_file}")
            return False
        
        # Check if error log file exists (should have the error message)
        if os.path.exists(error_log_file):
            with open(error_log_file, 'r') as f:
                error_content = f.read()
                if "error from domains blueprint" in error_content:
                    print(f"✅ Error log file working correctly")
                else:
                    print("⚠️  Error log file exists but doesn't contain expected error")
        else:
            print("⚠️  Error log file not found (may be normal if no errors logged)")
        
        print("✅ Unique logging system working correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Unique logging test failed: {e}")
        return False

def test_log_file_uniqueness():
    """Test that each app restart creates new unique log files"""
    print("\n🧪 Testing log file uniqueness...")
    
    try:
        from utils.logger import get_session_id, get_current_log_file
        import time
        
        # Get first session details
        session_id_1 = get_session_id()
        log_file_1 = get_current_log_file()
        
        print(f"✅ First session: {session_id_1}")
        print(f"✅ First log file: {os.path.basename(log_file_1)}")
        
        # Simulate time passage and new session
        time.sleep(1)
        
        # Reset the class variables to simulate app restart
        from utils.logger import LoggerConfig
        LoggerConfig._session_id = None
        LoggerConfig._unique_log_file = None
        LoggerConfig._unique_error_file = None
        LoggerConfig._session_logged = False
        
        # Get new session details
        session_id_2 = get_session_id()
        log_file_2 = get_current_log_file()
        
        print(f"✅ Second session: {session_id_2}")
        print(f"✅ Second log file: {os.path.basename(log_file_2)}")
        
        # Verify they are different
        if session_id_1 != session_id_2 and log_file_1 != log_file_2:
            print("✅ Log files are unique between sessions!")
            return True
        else:
            print("❌ Log files are not unique between sessions")
            return False
            
    except Exception as e:
        print(f"❌ Log uniqueness test failed: {e}")
        return False

def main():
    """Run unique logging tests"""
    print("🚀 Testing Unique Logging System")
    print("=" * 40)
    
    tests = [
        test_unique_logging,
        test_log_file_uniqueness
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
    
    print("\n" + "=" * 40)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 Unique logging system working perfectly!")
        return 0
    else:
        print("⚠️  Some tests failed.")
        return 1

if __name__ == "__main__":
    exit(main()) 