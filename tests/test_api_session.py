#!/usr/bin/env python3
"""
Test script for the refactored API with proper session management.
This script maintains session state across requests, allowing file references to work properly.
"""

import requests
import json
import os
import base64
from typing import Optional

# Configuration
BASE_URL = "http://localhost:5000"
API_KEY = "buNxeaqkGzZJprMRMbFD6uR04hHy0SyPION5s10vF5z9t2Yx"
APP_ID = 16
AGENT_ID = 32

# Headers for all requests
HEADERS = {
    "X-API-KEY": API_KEY,
    "Content-Type": "application/json"
}

def log_test(test_name: str, success: bool, message: str = ""):
    """Log test results with emoji indicators."""
    status = "✅" if success else "❌"
    print(f"{status} {test_name}: {message}")

def test_with_session():
    """Test the API with proper session management."""
    print("🧪 Testing Refactored API with Session Management")
    print("=" * 50)
    print("This script maintains session state across requests")
    print("")
    
    # Create a session object to maintain cookies across requests
    session = requests.Session()
    session.headers.update(HEADERS)
    
    try:
        # Test 1: Simple chat
        print("1. Testing simple chat...")
        url = f"{BASE_URL}/api/app/{APP_ID}/call/{AGENT_ID}"
        data = {
            "question": "Hello! This is a test message.",
            "search_params": {
                "filter": {
                    "source": "test"
                }
            }
        }
        
        response = session.post(url, json=data)
        if response.status_code == 200:
            result = response.json()
            log_test("Simple Chat", True, f"Response: {result.get('generated_text', '')[:50]}...")
        else:
            log_test("Simple Chat", False, f"HTTP {response.status_code}: {response.text}")
            return False
        
        print()
        
        # Test 2: Chat with base64 attachment
        print("2. Testing chat with base64 attachment...")
        # Create test content and encode it
        test_content = "This is test content for base64 attachment"
        base64_content = base64.b64encode(test_content.encode()).decode()
        
        data = {
            "question": "What is in this attached file?",
            "attachment": f"data:text/plain;base64,{base64_content}",
            "attachment_filename": "test.txt",
            "attachment_mime_type": "text/plain",
            "search_params": None
        }
        
        response = session.post(url, json=data)
        if response.status_code == 200:
            result = response.json()
            log_test("Base64 Attachment", True, f"Response: {result.get('generated_text', '')[:50]}...")
        else:
            log_test("Base64 Attachment", False, f"HTTP {response.status_code}: {response.text}")
            return False
        
        print()
        
        # Test 3: File upload
        print("3. Testing file upload...")
        upload_url = f"{BASE_URL}/api/app/{APP_ID}/attach-file/{AGENT_ID}"
        
        # Create a test file
        test_file_path = "upload_test.txt"
        with open(test_file_path, "w") as f:
            f.write("This is test content for file upload")
        
        with open(test_file_path, "rb") as f:
            files = {"file": f}
            response = session.post(upload_url, files=files)
        
        if response.status_code == 200:
            result = response.json()
            file_reference = result.get("file_reference")
            log_test("File Upload", True, f"File reference: {file_reference}")
        else:
            log_test("File Upload", False, f"HTTP {response.status_code}: {response.text}")
            return False
        
        # Clean up test file
        if os.path.exists(test_file_path):
            os.remove(test_file_path)
        
        print()
        
        # Test 4: List attached files
        print("4. Testing list attached files...")
        list_url = f"{BASE_URL}/api/app/{APP_ID}/attached-files/{AGENT_ID}"
        
        response = session.get(list_url)
        if response.status_code == 200:
            result = response.json()
            files = result.get("files", {})
            if file_reference in files:
                log_test("List Attached Files", True, f"Found {result.get('count', 0)} files")
            else:
                log_test("List Attached Files", False, "Uploaded file not found in list")
                return False
        else:
            log_test("List Attached Files", False, f"HTTP {response.status_code}: {response.text}")
            return False
        
        print()
        
        # Test 5: Use file reference in chat
        print("5. Testing chat with file reference...")
        data = {
            "question": "What is in the uploaded file?",
            "file_references": [file_reference]
        }
        
        response = session.post(url, json=data)
        if response.status_code == 200:
            result = response.json()
            metadata = result.get("metadata", {})
            if metadata.get("attachments_processed"):
                log_test("Chat with File Reference", True, f"Response: {result.get('generated_text', '')[:50]}...")
            else:
                log_test("Chat with File Reference", False, "File reference not processed")
                return False
        else:
            log_test("Chat with File Reference", False, f"HTTP {response.status_code}: {response.text}")
            return False
        
        print()
        
        # Test 6: Remove attached file
        print("6. Testing remove attached file...")
        remove_url = f"{BASE_URL}/api/app/{APP_ID}/detach-file/{AGENT_ID}/{file_reference}"
        
        response = session.delete(remove_url)
        if response.status_code == 200:
            log_test("Remove Attached File", True, "File removed successfully")
        else:
            log_test("Remove Attached File", False, f"HTTP {response.status_code}: {response.text}")
            return False
        
        print()
        
        # Test 7: Verify file is removed
        print("7. Verifying file is removed...")
        response = session.get(list_url)
        if response.status_code == 200:
            result = response.json()
            files = result.get("files", {})
            if file_reference not in files:
                log_test("Verify File Removal", True, "File successfully removed from list")
            else:
                log_test("Verify File Removal", False, "File still appears in list")
                return False
        else:
            log_test("Verify File Removal", False, f"HTTP {response.status_code}: {response.text}")
            return False
        
        print()
        
        # Test 8: Reset conversation
        print("8. Testing reset conversation...")
        reset_url = f"{BASE_URL}/api/app/{APP_ID}/reset/{AGENT_ID}"
        
        response = session.post(reset_url)
        if response.status_code == 200:
            log_test("Reset Conversation", True, "Conversation reset successfully")
        else:
            log_test("Reset Conversation", False, f"HTTP {response.status_code}: {response.text}")
            return False
        
        print()
        
        print("✅ All tests completed successfully!")
        print("Session management is working correctly.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with exception: {str(e)}")
        return False
    finally:
        session.close()

if __name__ == "__main__":
    success = test_with_session()
    exit(0 if success else 1) 