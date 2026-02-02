# API Attachment Support

The API now supports file attachments for both the Internal API (OAuth) and Public API (API Key).

## Public API (API Key Authentication)

The Public API uses the `X-API-KEY` header for authentication.

### Single Request Upload (Recommended for Simple Use Cases)

Send a message with file attachments in a single API call - similar to ChatGPT web interface.

#### Chat with files in one request

```bash
curl -X POST "http://your-api/public/v1/app/{app_id}/chat/{agent_id}/call-with-files" \
  -H "X-API-KEY: your-api-key" \
  -F "message=What is in this document?" \
  -F "files=@document.pdf"
```

#### With multiple files

```bash
curl -X POST "http://your-api/public/v1/app/{app_id}/chat/{agent_id}/call-with-files" \
  -H "X-API-KEY: your-api-key" \
  -F "message=Compare these two documents" \
  -F "files=@report1.pdf" \
  -F "files=@image.png"
```

#### With search parameters

```bash
curl -X POST "http://your-api/public/v1/app/{app_id}/chat/{agent_id}/call-with-files" \
  -H "X-API-KEY: your-api-key" \
  -F "message=Find sales data in this document" \
  -F "files=@financial_report.pdf" \
  -F 'search_params={"filter": {"category": "financial"}, "top_k": 5}'
```

#### Include previously uploaded files automatically

By default, all previously uploaded files are automatically included (same behavior as internal API):

```bash
# First request: upload and ask about a document
curl -X POST "http://your-api/public/v1/app/{app_id}/chat/{agent_id}/call-with-files" \
  -H "X-API-KEY: your-api-key" \
  -F "message=What is this document about?" \
  -F "files=@report.pdf"

# Second request: add another file (previous file is automatically included)
curl -X POST "http://your-api/public/v1/app/{app_id}/chat/{agent_id}/call-with-files" \
  -H "X-API-KEY: your-api-key" \
  -F "message=Compare this new file with the previous one" \
  -F "files=@new_report.pdf"
```

#### Filter to specific files only

Use `file_references` to include only specific previously uploaded files:

```bash
curl -X POST "http://your-api/public/v1/app/{app_id}/chat/{agent_id}/call-with-files" \
  -H "X-API-KEY: your-api-key" \
  -F "message=Analyze only this specific file" \
  -F 'file_references=["550e8400-e29b-41d4-a716-446655440000"]'
```

Response:
```json
{
  "response": "Based on the documents you provided...",
  "conversation_id": "api_123_abc12345",
  "usage": {
    "agent_name": "My Agent",
    "agent_type": "agent",
    "files_processed": 2,
    "has_memory": true
  }
}
```

#### Python Example (Single Request)

```python
import requests

API_URL = "http://your-api/public/v1"
APP_ID = 1
AGENT_ID = 123
API_KEY = "your-api-key"

# Send message with files in one request
with open("document.pdf", "rb") as pdf, open("image.png", "rb") as img:
    response = requests.post(
        f"{API_URL}/app/{APP_ID}/chat/{AGENT_ID}/call-with-files",
        headers={"X-API-KEY": API_KEY},
        data={"message": "Analyze these files"},
        files=[
            ("files", ("document.pdf", pdf, "application/pdf")),
            ("files", ("image.png", img, "image/png"))
        ]
    )
    
print(response.json()["response"])
```

---

### File Reference System (For Multi-turn Conversations)

Upload files separately and reference them in chat messages for efficient multi-turn conversations.

#### Step 1: Attach a file

```bash
curl -X POST "http://your-api/public/v1/app/{app_id}/files/{agent_id}/attach-file" \
  -H "X-API-KEY: your-api-key" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf"
```

Response:
```json
{
  "success": true,
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "document.pdf",
  "file_type": "pdf",
  "message": "File attached successfully"
}
```

#### Step 2: List attached files

```bash
curl -X GET "http://your-api/public/v1/app/{app_id}/files/{agent_id}/attached-files" \
  -H "X-API-KEY: your-api-key"
```

Response:
```json
{
  "files": [
    {
      "file_id": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "document.pdf",
      "file_type": "pdf",
      "uploaded_at": "2024-04-04T12:00:00Z"
    }
  ]
}
```

#### Step 3: Chat with the agent (files automatically included)

```bash
curl -X POST "http://your-api/public/v1/app/{app_id}/chat/{agent_id}/call" \
  -H "X-API-KEY: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is this document about?"
  }'
```

All attached files are automatically included in the chat context. To include only specific files:

```bash
curl -X POST "http://your-api/public/v1/app/{app_id}/chat/{agent_id}/call" \
  -H "X-API-KEY: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is this document about?",
    "file_references": ["550e8400-e29b-41d4-a716-446655440000"]
  }'
```

Response:
```json
{
  "response": "This document discusses...",
  "conversation_id": "api_123_abc12345",
  "usage": {
    "agent_name": "My Agent",
    "agent_type": "agent",
    "files_processed": 1,
    "has_memory": true
  }
}
```

#### Step 4: Detach a file when done

```bash
curl -X DELETE "http://your-api/public/v1/app/{app_id}/files/{agent_id}/detach-file/{file_id}" \
  -H "X-API-KEY: your-api-key"
```

Response:
```json
{
  "success": true,
  "message": "File detached successfully"
}
```

#### Step 5: Reset conversation (clears history and files)

```bash
curl -X POST "http://your-api/public/v1/app/{app_id}/chat/{agent_id}/reset" \
  -H "X-API-KEY: your-api-key"
```

## Internal API (OAuth Authentication)

The Internal API uses OAuth/JWT authentication for the playground interface.

### Endpoints

- **Upload file**: `POST /internal/app/{app_id}/agents/{agent_id}/upload-file`
- **List files**: `GET /internal/app/{app_id}/agents/{agent_id}/files`
- **Remove file**: `DELETE /internal/app/{app_id}/agents/{agent_id}/files/{file_id}`
- **Chat**: `POST /internal/app/{app_id}/agents/{agent_id}/chat`

### Chat with files (multipart form)

```bash
curl -X POST "http://your-api/internal/app/{app_id}/agents/{agent_id}/chat" \
  -H "Authorization: Bearer your-jwt-token" \
  -H "Content-Type: multipart/form-data" \
  -F "message=What is this document about?" \
  -F "files=@document.pdf"
```

## File Processing

The API automatically processes different file types:

- **PDF files**: Extracts text using OCR tools
- **Image files**: Converts to base64 for vision models (if agent has vision capabilities)
- **Text files** (.txt, .md, .json, .csv): Reads and includes content directly
- **Document files** (.doc, .docx): Basic support

## Supported File Types

| Extension | Type | Processing |
|-----------|------|------------|
| .pdf | PDF | Text extraction |
| .txt | Text | Direct read |
| .md | Text | Direct read |
| .json | Text | Direct read |
| .csv | Text | Direct read |
| .png, .jpg, .jpeg, .gif, .bmp | Image | Vision model (if available) |
| .doc, .docx | Document | Basic support |

## File Reference System Benefits

1. **Efficient**: Upload once, use multiple times in conversations
2. **Session-based**: Files persist during the chat session (per API key)
3. **Multiple files**: Attach and reference multiple files
4. **Selective**: Choose specific files to include via `file_references`
5. **Cleanup**: Automatic cleanup when conversation resets
6. **Isolation**: Files are isolated per agent and per user/API key

## Security

- Files are saved to secure temporary locations
- Files are validated and processed securely
- File size limits are enforced (configurable)
- Session-based file storage with agent and user isolation
- API key authentication ensures proper access control
- Files are cleaned up during conversation reset

## Environment Variables

Configure file storage and limits:

```bash
TMP_BASE_FOLDER=data/tmp/
MAX_UPLOAD_SIZE=10485760  # 10MB default
```

## Error Handling

The API provides clear error messages for:
- Invalid file types
- File processing errors
- File not found errors
- Authentication failures
- File size exceeded

## Complete Usage Examples

### Python Example

```python
import requests

API_URL = "http://your-api/public/v1"
APP_ID = 1
AGENT_ID = 123
API_KEY = "your-api-key"

headers = {"X-API-KEY": API_KEY}

# 1. Attach files
with open("document.pdf", "rb") as f:
    response = requests.post(
        f"{API_URL}/app/{APP_ID}/files/{AGENT_ID}/attach-file",
        headers=headers,
        files={"file": f}
    )
    file_id = response.json()["file_id"]
    print(f"Attached file: {file_id}")

# 2. Chat with agent (files automatically included)
response = requests.post(
    f"{API_URL}/app/{APP_ID}/chat/{AGENT_ID}/call",
    headers=headers,
    json={"message": "Summarize the attached document"}
)
print(response.json()["response"])

# 3. Continue conversation
response = requests.post(
    f"{API_URL}/app/{APP_ID}/chat/{AGENT_ID}/call",
    headers=headers,
    json={"message": "What are the key points?"}
)
print(response.json()["response"])

# 4. Reset when done
requests.post(
    f"{API_URL}/app/{APP_ID}/chat/{AGENT_ID}/reset",
    headers=headers
)
```

### Chat with multiple files

```bash
# Attach first file
curl -X POST "http://your-api/public/v1/app/1/files/123/attach-file" \
  -H "X-API-KEY: your-api-key" \
  -F "file=@report1.pdf"

# Attach second file
curl -X POST "http://your-api/public/v1/app/1/files/123/attach-file" \
  -H "X-API-KEY: your-api-key" \
  -F "file=@report2.pdf"

# Chat comparing both documents
curl -X POST "http://your-api/public/v1/app/1/chat/123/call" \
  -H "X-API-KEY: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"message": "Compare these two reports and highlight the differences"}'
```

### Using search_params with files

```bash
curl -X POST "http://your-api/public/v1/app/1/chat/123/call" \
  -H "X-API-KEY: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Find information about sales in the attached documents",
    "search_params": {
      "filter": {"category": "financial"},
      "top_k": 5
    }
  }'
```

## Choosing the Right Method

| Use Case | Recommended Method | Endpoint |
|----------|-------------------|----------|
| Quick one-off questions with files | Single Request | `/call-with-files` |
| ChatGPT-like experience | Single Request | `/call-with-files` |
| Multi-turn conversation with same files | File Reference | `/attach-file` + `/call` |
| Large files used across many messages | File Reference | `/attach-file` + `/call` |
| Mixing new and existing files | Both | `/call-with-files` with `file_references` |

### Method Comparison

| Feature | Single Request (`/call-with-files`) | File Reference (`/attach-file` + `/call`) |
|---------|-------------------------------------|-------------------------------------------|
| API calls needed | 1 | 2+ |
| File persistence | ✅ Files saved for session | ✅ Files saved for session |
| Multiple files | ✅ Supported | ✅ Supported |
| Reuse files across messages | ✅ Automatic (same as internal API) | ✅ Automatic |
| Filter specific files | ✅ Via `file_references` param | ✅ Via `file_references` param |
| Best for | ChatGPT-like UX | Explicit file management |

### Behavior Notes

Both APIs (Public and Internal) now share the same behavior:

1. **New files uploaded with the message** are processed and added to the session
2. **Previously uploaded files** are automatically included in the context
3. **Duplicates are avoided** - if a file was just uploaded, it won't be duplicated from the existing session
4. Use `file_references` parameter to filter and include only specific files

## File Upload Response (Visual Feedback)

When uploading a file, the API returns detailed information for visual feedback:

```json
{
  "success": true,
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "document.pdf",
  "file_type": "pdf",
  "message": "File attached successfully",
  "file_size_bytes": 2621440,
  "file_size_display": "2.50 MB",
  "processing_status": "ready",
  "content_preview": "This document contains the annual report...",
  "has_extractable_content": true,
  "mime_type": "application/pdf"
}
```

### Visual Feedback Fields

| Field | Description |
|-------|-------------|
| `file_size_bytes` | File size in bytes |
| `file_size_display` | Human-readable size (e.g., "2.50 MB") |
| `processing_status` | Status: `ready`, `uploaded`, `processing`, or `error` |
| `content_preview` | First 200 characters of extracted text (if available) |
| `has_extractable_content` | `true` if meaningful text was extracted |
| `mime_type` | MIME type of the file |

### Processing Status Values

| Status | Meaning |
|--------|---------|
| `ready` | File processed successfully, text extracted |
| `uploaded` | File stored but not fully processed (e.g., images without OCR) |
| `processing` | File is being processed |
| `error` | Error during processing |

## Conversation-Specific File Storage

Files can be isolated to specific conversations. When `conversation_id` is provided in the user context, files are stored separately for each conversation:

- **Without conversation_id**: Files are shared across all conversations with the same agent
- **With conversation_id**: Files are isolated to that specific conversation

This allows users to have different file contexts in different conversations with the same agent
