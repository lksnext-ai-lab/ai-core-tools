#!/bin/bash

# Test script for the refactored API using curl
# Replace these values with your actual configuration

BASE_URL="http://localhost:5000"
API_KEY="buNxeaqkGzZJprMRMbFD6uR04hHy0SyPION5s10vF5z9t2Yx"
APP_ID=16
AGENT_ID=32
COOKIE_FILE="session_cookies.txt"

echo "🧪 Testing Refactored API with curl"
echo "=================================="
echo "Note: This script uses session cookies to maintain state across requests"
echo "Each request will use the same session, allowing file references to work properly"
echo ""

# Clean up any existing cookie file
rm -f $COOKIE_FILE

# Test 1: Simple chat
echo "1. Testing simple chat..."
curl -X POST "${BASE_URL}/api/app/${APP_ID}/call/${AGENT_ID}" \
  -H "X-API-KEY: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -c $COOKIE_FILE \
  -d '{
    "question": "Hello! This is a test message.",
    "search_params": {
      "filter": {
        "source": "test"
      }
    }
  }' | jq '.'

echo -e "\n"

# Test 2: Chat with base64 attachment
echo "2. Testing chat with base64 attachment..."
# Create a test file and encode it
echo "This is test content for base64 attachment" > test.txt
BASE64_CONTENT=$(base64 -w 0 test.txt)

# Create JSON payload file to avoid escaping issues
cat > payload.json << EOF
{
  "question": "What is in this attached file?",
  "attachment": "data:text/plain;base64,${BASE64_CONTENT}",
  "attachment_filename": "test.txt",
  "attachment_mime_type": "text/plain",
  "search_params": null
}
EOF

curl -X POST "${BASE_URL}/api/app/${APP_ID}/call/${AGENT_ID}" \
  -H "X-API-KEY: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -b $COOKIE_FILE \
  -c $COOKIE_FILE \
  -d @payload.json | jq '.'

rm test.txt payload.json
echo -e "\n"

# Test 3: File upload
echo "3. Testing file upload..."
echo "This is test content for file upload" > upload_test.txt

curl -X POST "${BASE_URL}/api/app/${APP_ID}/attach-file/${AGENT_ID}" \
  -H "X-API-KEY: ${API_KEY}" \
  -b $COOKIE_FILE \
  -c $COOKIE_FILE \
  -F "file=@upload_test.txt" | jq '.'

rm upload_test.txt
echo -e "\n"

# Test 4: List attached files
echo "4. Testing list attached files..."
curl -X GET "${BASE_URL}/api/app/${APP_ID}/attached-files/${AGENT_ID}" \
  -H "X-API-KEY: ${API_KEY}" \
  -b $COOKIE_FILE \
  -c $COOKIE_FILE | jq '.'

echo -e "\n"

# Test 5: Reset conversation
echo "5. Testing reset conversation..."
curl -X POST "${BASE_URL}/api/app/${APP_ID}/reset/${AGENT_ID}" \
  -H "X-API-KEY: ${API_KEY}" \
  -b $COOKIE_FILE \
  -c $COOKIE_FILE | jq '.'

echo -e "\n"

# Clean up cookie file
rm -f $COOKIE_FILE

echo "✅ All curl tests completed!"
echo "Check the responses above for any errors."
echo ""
echo "Note: Test 6 (multipart form data) was removed because it's not compatible"
echo "with the current API structure that requires JSON body validation."
echo "Use the file upload + reference approach (tests 3-4) for file attachments." 