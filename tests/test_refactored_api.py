#!/usr/bin/env python3
"""
Test script for the refactored API functionality.
This script tests all the main endpoints and functionality that was refactored.
"""

import requests
import json
import base64
import os
import time
from pathlib import Path

# Configuration
BASE_URL = "http://localhost:5000"  # Adjust if your server runs on different port
API_KEY = "your-api-key-here"  # Replace with your actual API key
APP_ID = 16  # Replace with your actual app ID
AGENT_ID = 32  # Replace with your actual agent ID

# Headers for API requests
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Test results
test_results = []

def log_test(test_name, success, message=""):
    """Log test results"""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status} {test_name}")
    if message:
        print(f"   {message}")
    test_results.append({"test": test_name, "success": success, "message": message})
    print()

def test_api_imports():
    """Test that all API modules can be imported correctly"""
    try:
        from api.api import api
        from api.chat.service import ChatService
        from api.chat.handlers import ChatRequestHandler
        from api.files.service import FileService
        from api.files.utils import FileUtils
        from api.ocr.service import OCRService
        from tools.agentTools import setup_tracer
        from api.shared.session_utils import SessionUtils
        log_test("API Imports", True, "All modules imported successfully")
        return True
    except Exception as e:
        log_test("API Imports", False, f"Import error: {str(e)}")
        return False

def test_simple_chat():
    """Test basic chat functionality without attachments"""
    try:
        url = f"{BASE_URL}/api/app/{APP_ID}/call/{AGENT_ID}"
        data = {
            "question": "Hello! This is a test message.",
            "search_params": {
                "filter": {
                    "source": "test"
                }
            }
        }
        
        response = requests.post(url, headers=HEADERS, json=data)
        
        if response.status_code == 200:
            result = response.json()
            if "generated_text" in result:
                log_test("Simple Chat", True, f"Response received: {result['generated_text'][:50]}...")
                return True
            else:
                log_test("Simple Chat", False, "No generated_text in response")
                return False
        else:
            log_test("Simple Chat", False, f"HTTP {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        log_test("Simple Chat", False, f"Request error: {str(e)}")
        return False

def test_chat_with_base64_attachment():
    """Test chat with base64 encoded attachment"""
    try:
        # Create a simple text file and encode it
        test_content = "This is a test file content for base64 attachment testing."
        base64_content = base64.b64encode(test_content.encode()).decode()
        
        url = f"{BASE_URL}/api/app/{APP_ID}/call/{AGENT_ID}"
        data = {
            "question": "What is in this attached file?",
            "attachment": f"data:text/plain;base64,{base64_content}",
            "attachment_filename": "test.txt",
            "attachment_mime_type": "text/plain"
        }
        
        response = requests.post(url, headers=HEADERS, json=data)
        
        if response.status_code == 200:
            result = response.json()
            if "generated_text" in result and result.get("metadata", {}).get("attachments_processed"):
                log_test("Chat with Base64 Attachment", True, "Base64 attachment processed successfully")
                return True
            else:
                log_test("Chat with Base64 Attachment", False, "Attachment not processed")
                return False
        else:
            log_test("Chat with Base64 Attachment", False, f"HTTP {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        log_test("Chat with Base64 Attachment", False, f"Request error: {str(e)}")
        return False

def test_file_attachment_workflow():
    """Test the complete file attachment workflow"""
    try:
        # Step 1: Upload a file
        url = f"{BASE_URL}/api/app/{APP_ID}/attach-file/{AGENT_ID}"
        
        # Create a test file
        test_file_path = "test_attachment.txt"
        with open(test_file_path, "w") as f:
            f.write("This is a test file for attachment workflow testing.")
        
        with open(test_file_path, "rb") as f:
            files = {"file": f}
            response = requests.post(url, headers={"Authorization": f"Bearer {API_KEY}"}, files=files)
        
        if response.status_code != 200:
            log_test("File Attachment Workflow", False, f"Upload failed: HTTP {response.status_code}")
            return False
        
        result = response.json()
        file_reference = result.get("file_reference")
        
        if not file_reference:
            log_test("File Attachment Workflow", False, "No file reference returned")
            return False
        
        log_test("File Upload", True, f"File uploaded with reference: {file_reference}")
        
        # Step 2: List attached files
        url = f"{BASE_URL}/api/app/{APP_ID}/attached-files/{AGENT_ID}"
        response = requests.get(url, headers=HEADERS)
        
        if response.status_code == 200:
            result = response.json()
            if file_reference in result.get("files", {}):
                log_test("List Attached Files", True, f"Found {result.get('count', 0)} files")
            else:
                log_test("List Attached Files", False, "Uploaded file not found in list")
                return False
        else:
            log_test("List Attached Files", False, f"HTTP {response.status_code}")
            return False
        
        # Step 3: Use file reference in chat
        url = f"{BASE_URL}/api/app/{APP_ID}/call/{AGENT_ID}"
        data = {
            "question": "What is in the attached file?",
            "file_references": [file_reference]
        }
        
        response = requests.post(url, headers=HEADERS, json=data)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("metadata", {}).get("attachments_processed"):
                log_test("Chat with File Reference", True, "File reference used successfully")
            else:
                log_test("Chat with File Reference", False, "File reference not processed")
                return False
        else:
            log_test("Chat with File Reference", False, f"HTTP {response.status_code}")
            return False
        
        # Step 4: Remove the file
        url = f"{BASE_URL}/api/app/{APP_ID}/detach-file/{AGENT_ID}/{file_reference}"
        response = requests.delete(url, headers=HEADERS)
        
        if response.status_code == 200:
            log_test("Remove Attached File", True, "File removed successfully")
        else:
            log_test("Remove Attached File", False, f"HTTP {response.status_code}")
            return False
        
        # Cleanup
        if os.path.exists(test_file_path):
            os.remove(test_file_path)
        
        log_test("File Attachment Workflow", True, "Complete workflow tested successfully")
        return True
        
    except Exception as e:
        log_test("File Attachment Workflow", False, f"Workflow error: {str(e)}")
        return False

def test_reset_conversation():
    """Test conversation reset functionality"""
    try:
        url = f"{BASE_URL}/api/app/{APP_ID}/reset/{AGENT_ID}"
        response = requests.post(url, headers=HEADERS)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                log_test("Reset Conversation", True, "Conversation reset successfully")
                return True
            else:
                log_test("Reset Conversation", False, "Reset failed")
                return False
        else:
            log_test("Reset Conversation", False, f"HTTP {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        log_test("Reset Conversation", False, f"Request error: {str(e)}")
        return False

def test_multipart_chat():
    """Test multipart form data chat with file upload"""
    try:
        # Create a test file
        test_file_path = "test_multipart.txt"
        with open(test_file_path, "w") as f:
            f.write("This is a test file for multipart form testing.")
        
        url = f"{BASE_URL}/api/app/{APP_ID}/call/{AGENT_ID}"
        
        with open(test_file_path, "rb") as f:
            files = {"file": f}
            data = {
                "question": "What is in this uploaded file?",
                "search_params": json.dumps({"filter": {"source": "multipart_test"}})
            }
            headers = {"Authorization": f"Bearer {API_KEY}"}
            
            response = requests.post(url, headers=headers, data=data, files=files)
        
        # Cleanup
        if os.path.exists(test_file_path):
            os.remove(test_file_path)
        
        if response.status_code == 200:
            result = response.json()
            if "generated_text" in result:
                log_test("Multipart Chat", True, "Multipart form data processed successfully")
                return True
            else:
                log_test("Multipart Chat", False, "No response text generated")
                return False
        else:
            log_test("Multipart Chat", False, f"HTTP {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        log_test("Multipart Chat", False, f"Request error: {str(e)}")
        return False

def run_all_tests():
    """Run all tests and provide summary"""
    print("🧪 Testing Refactored API Functionality")
    print("=" * 50)
    
    # Test imports first
    if not test_api_imports():
        print("❌ Import tests failed. Cannot continue with API tests.")
        return
    
    # Test API functionality
    test_simple_chat()
    test_chat_with_base64_attachment()
    test_file_attachment_workflow()
    test_reset_conversation()
    test_multipart_chat()
    
    # Summary
    print("=" * 50)
    print("📊 Test Summary")
    print("=" * 50)
    
    passed = sum(1 for result in test_results if result["success"])
    total = len(test_results)
    
    print(f"Total tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("\n🎉 All tests passed! The refactored API is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
        
        # Show failed tests
        failed_tests = [result for result in test_results if not result["success"]]
        if failed_tests:
            print("\n❌ Failed tests:")
            for test in failed_tests:
                print(f"   - {test['test']}: {test['message']}")

if __name__ == "__main__":
    run_all_tests() 