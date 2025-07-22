#!/usr/bin/env python3
"""
Simple Azure OpenAI Connection Test

This script helps you test your Azure OpenAI connection and find available deployments.
"""

import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_azure_connection():
    """Test Azure OpenAI connection and list deployments"""
    
    # Get credentials from environment or use your values
    api_key = os.getenv('AZURE_OPENAI_API_KEY') or "F7C5kZZuTC6CYNdmuK7kymk1BngxlWLe3I9OZymV2arTr8bbgCSAJQQJ99ALAC5RqLJXJ3w3AAAAACOGgbRj"
    endpoint = os.getenv('AZURE_OPENAI_ENDPOINT') or "https://aula-deusto-openai-services.services.ai.azure.com/models"
    api_version = os.getenv('AZURE_OPENAI_API_VERSION') or "2024-05-01-preview"
    
    print("🔧 Testing Azure OpenAI Connection")
    print("=" * 50)
    print(f"Endpoint: {endpoint}")
    print(f"API Version: {api_version}")
    print(f"API Key: {api_key[:10]}..." if api_key else "Not provided")
    print()
    
    # Clean endpoint (remove /models if present)
    base_endpoint = endpoint.replace('/models', '')
    print(f"Cleaned endpoint: {base_endpoint}")
    print()
    
    try:
        headers = {
            'api-key': api_key,
            'Content-Type': 'application/json'
        }
        
        # Test deployments endpoint
        deployments_url = f"{base_endpoint}/openai/deployments?api-version={api_version}"
        print(f"Testing URL: {deployments_url}")
        print()
        
        response = requests.get(deployments_url, headers=headers)
        
        print(f"Response Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print()
        
        if response.status_code == 200:
            deployments = response.json()
            print("✅ Connection successful!")
            print()
            print("Available deployments:")
            print("-" * 30)
            
            if 'data' in deployments and deployments['data']:
                for deployment in deployments['data']:
                    print(f"  Deployment ID: {deployment['id']}")
                    print(f"  Model: {deployment['model']}")
                    print(f"  Status: {deployment.get('status', 'Unknown')}")
                    print(f"  Created: {deployment.get('created_at', 'Unknown')}")
                    print()
            else:
                print("  No deployments found or empty response")
                print(f"  Full response: {deployments}")
        else:
            print("❌ Connection failed!")
            print(f"Error: {response.text}")
            print()
            print("💡 Troubleshooting tips:")
            print("   1. Check if your API key is correct")
            print("   2. Verify the endpoint URL is correct")
            print("   3. Make sure your Azure OpenAI service is active")
            print("   4. Check if you have the necessary permissions")
            
    except Exception as e:
        print(f"❌ Connection test failed: {str(e)}")
        print()
        print("💡 Possible issues:")
        print("   1. Network connectivity problem")
        print("   2. Invalid endpoint URL")
        print("   3. SSL/TLS certificate issues")

if __name__ == "__main__":
    test_azure_connection() 