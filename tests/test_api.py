#!/usr/bin/env python3
"""
Simple test script for the refactored API functionality.
"""

import requests
import json
import base64
import os

# Configuration
BASE_URL = "http://localhost:5000"
API_KEY = "buNxeaqkGzZJprMRMbFD6uR04hHy0SyPION5s10vF5z9t2Yx"
APP_ID = 16
AGENT_ID = 32

HEADERS = {
    "X-API-KEY": API_KEY,
    "Content-Type": "application/json"
}

def test_imports():
    """Test that all API modules can be imported"""
    try:
        from api.api import api
        from api.chat.service import ChatService
        from api.files.service import FileService
        print("✅ API imports work")
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_simple_chat():
    """Test basic chat functionality"""
    try:
        url = f"{BASE_URL}/api/app/{APP_ID}/call/{AGENT_ID}"
        data = {"question": "Hello! This is a test."}
        
        response = requests.post(url, headers=HEADERS, json=data)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Simple chat works")
            return True
        else:
            print(f"❌ Chat failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Chat error: {e}")
        return False

def test_file_upload():
    """Test file upload functionality"""
    try:
        url = f"{BASE_URL}/api/app/{APP_ID}/attach-file/{AGENT_ID}"
        
        # Create test file
        with open("test.txt", "w") as f:
            f.write("Test content")
        
        with open("test.txt", "rb") as f:
            files = {"file": f}
            headers = {"X-API-KEY": API_KEY}
            response = requests.post(url, headers=headers, files=files)
        
        os.remove("test.txt")
        
        if response.status_code == 200:
            print("✅ File upload works")
            return True
        else:
            print(f"❌ File upload failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ File upload error: {e}")
        return False

def main():
    print("🧪 Testing Refactored API")
    print("=" * 30)
    
    tests = [
        test_imports,
        test_simple_chat,
        test_file_upload
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n📊 Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed")

if __name__ == "__main__":
    main() 