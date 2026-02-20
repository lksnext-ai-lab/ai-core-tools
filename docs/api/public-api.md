# Public API

> Part of [Mattin AI Documentation](../README.md)

## Overview

The **Public API** (`/public/v1/*`) provides **external programmatic access** to Mattin AI features. It enables third-party applications to execute agents, manage resources, and perform operations via HTTP requests.

**Base URL**: `http://localhost:8000/public/v1` (dev) or `https://your-domain.com/public/v1` (production)

**Authentication**: API key in header

**Rate Limiting**: Configurable per API key

**OpenAPI Docs**: `http://localhost:8000/docs/public`

## Authentication

### API Key Header

All Public API requests must include an API key in the `X-API-Key` header:

```http
GET /public/v1/agents
X-API-Key: mattin_...
```

### Key Generation

API keys are generated via the Internal API by app owners:

```http
POST /internal/api_keys?app_id=1
Cookie: session=...

{
  "name": "Production API Key",
  "rate_limit": 100
}

Response:
{
  "key": "mattin_ABC123XYZ...",  // Only shown once!
  "key_id": 5,
  "name": "Production API Key"
}
```

**Important**: Save the API key immediately — it's only displayed once during creation.

### Validation

API keys are validated on each request:

```python
from .auth import get_api_key_auth

@router.get("/")
async def list_agents(
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    # api_key is validated and rate limit checked
    ...
```

**Validation checks**:
1. Key exists in database
2. Key is not revoked (`status = 'active'`)
3. Rate limit not exceeded

## Rate Limiting

### Configuration

Rate limits are set per API key:

```json
{
  "rate_limit": 100  // Requests per minute
}
```

**Default**: 0 (unlimited)

### Headers

Rate limit info included in response headers:

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640000000
```

### Exceeded Response

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json

{
  "detail": "Rate limit exceeded. Try again in 60 seconds."
}
```

## Endpoints

### Agent Execution

**Base**: `/public/v1/agents`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | List agents in app |
| GET | `/{agent_id}` | Get agent details |

**Example: List Agents**

```http
GET /public/v1/agents?app_id=1
X-API-Key: mattin_...

Response:
[
  {
    "agent_id": 10,
    "name": "Customer Support Bot",
    "description": "Answers customer questions",
    "type": "agent"
  }
]
```

### Chat

**Base**: `/public/v1/chat`

The primary endpoint for agent execution.

#### POST /{agent_id}/call

Execute agent chat with message and optional file attachments.

**Request**:

```http
POST /public/v1/chat/10/call?app_id=1
X-API-Key: mattin_...
Content-Type: multipart/form-data

message=How do I reset my password?
files=@screenshot.png
conversation_id=null
search_params={"retrieval_count": 5}
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | Yes | User message |
| `files` | file[] | No | File attachments (images, PDFs, text) |
| `file_references` | JSON | No | Array of existing file IDs to include |
| `search_params` | JSON | No | RAG search parameters |
| `conversation_id` | int | No | Continue existing conversation |

**Response** (Server-Sent Events):

```
data: {"type":"token","content":"To"}
data: {"type":"token","content":" reset"}
data: {"type":"token","content":" your"}
data: {"type":"token","content":" password"}
data: {"type":"token","content":","}
...
data: {"type":"done"}
```

**File handling**:
- New files uploaded with request are automatically persisted
- If `file_references` not provided, ALL attached files included
- If `file_references` provided, only those specific files included

**Supported file types**:
- PDF (.pdf): Text extracted automatically
- Text (.txt, .md, .json, .csv): Content read directly
- Images (.png, .jpg): OCR via vision models
- Audio (.mp3, .wav): Transcription via Whisper

**Memory behavior**:
- **WITH memory**: If no `conversation_id`, new conversation auto-created and ID returned
- **WITHOUT memory**: Each call is independent (no persistence)

**Example with curl**:

```bash
curl -X POST "http://localhost:8000/public/v1/chat/10/call?app_id=1" \
  -H "X-API-Key: mattin_..." \
  -F "message=How do I reset my password?" \
  -F "files=@screenshot.png"
```

**Example response parsing (JavaScript)**:

```javascript
const response = await fetch('/public/v1/chat/10/call?app_id=1', {
  method: 'POST',
  headers: {
    'X-API-Key': 'mattin_...'
  },
  body: formData
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  const text = decoder.decode(value);
  const lines = text.split('\n');
  
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const data = JSON.parse(line.slice(6));
      if (data.type === 'token') {
        console.log(data.content);
      }
    }
  }
}
```

### Files

**Base**: `/public/v1/files`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/{agent_id}/attach-file` | Pre-attach file to agent |

#### POST /{agent_id}/attach-file

Pre-attach a file to an agent for later use in conversations.

**Request**:

```http
POST /public/v1/files/10/attach-file?app_id=1
X-API-Key: mattin_...
Content-Type: multipart/form-data

file=@document.pdf
conversation_id=null
```

**Response**:

```json
{
  "file_id": "abc123",
  "filename": "document.pdf",
  "file_size": 1024000
}
```

Use the returned `file_id` in subsequent `/chat` calls via `file_references` parameter.

### Repositories

**Base**: `/public/v1/repositories`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | List repositories |
| GET | `/{repo_id}/resources` | List files in repository |

**Example: List Repositories**

```http
GET /public/v1/repositories?app_id=1
X-API-Key: mattin_...

Response:
[
  {
    "repository_id": 5,
    "name": "Documentation",
    "silo_id": 2,
    "status": "active"
  }
]
```

### Silos

**Base**: `/public/v1/silos`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | List silos (vector stores) |
| GET | `/{silo_id}` | Get silo details |

### Resources

**Base**: `/public/v1/resources`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/{resource_id}` | Get resource details |
| GET | `/{resource_id}/content` | Download resource file |

**Example: Download File**

```http
GET /public/v1/resources/42/content?app_id=1
X-API-Key: mattin_...

Response: (file content)
Content-Type: application/pdf
Content-Disposition: attachment; filename="document.pdf"
```

### OCR

**Base**: `/public/v1/ocr`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/extract` | Extract text from image |

**Example: OCR Request**

```http
POST /public/v1/ocr/extract?app_id=1
X-API-Key: mattin_...
Content-Type: multipart/form-data

file=@receipt.jpg

Response:
{
  "text": "Receipt\nTotal: $45.99\n..."
}
```

### Authentication Validation

**Base**: `/public/v1/auth`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/validate` | Validate API key |

**Example**:

```http
GET /public/v1/auth/validate?app_id=1
X-API-Key: mattin_...

Response:
{
  "valid": true,
  "app_id": 1,
  "key_id": 5,
  "rate_limit": 100
}
```

## API Examples

### Python Example

```python
import requests

API_KEY = "mattin_..."
BASE_URL = "http://localhost:8000/public/v1"
APP_ID = 1

def chat_with_agent(agent_id, message, files=None):
    """Send a message to an agent and stream the response."""
    url = f"{BASE_URL}/chat/{agent_id}/call"
    headers = {"X-API-Key": API_KEY}
    data = {"message": message}
    files_data = {"files": open(files, "rb")} if files else None
    
    params = {"app_id": APP_ID}
    
    with requests.post(url, headers=headers, data=data, files=files_data, 
                       params=params, stream=True) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith(b'data: '):
                data = json.loads(line[6:])
                if data['type'] == 'token':
                    print(data['content'], end='', flush=True)

# Usage
chat_with_agent(10, "How do I reset my password?")
```

### Node.js Example

```javascript
const fetch = require('node-fetch');
const FormData = require('form-data');
const fs = require('fs');

const API_KEY = 'mattin_...';
const BASE_URL = 'http://localhost:8000/public/v1';
const APP_ID = 1;

async function chatWithAgent(agentId, message, filePath = null) {
  const formData = new FormData();
  formData.append('message', message);
  
  if (filePath) {
    formData.append('files', fs.createReadStream(filePath));
  }
  
  const response = await fetch(
    `${BASE_URL}/chat/${agentId}/call?app_id=${APP_ID}`,
    {
      method: 'POST',
      headers: {
        'X-API-Key': API_KEY,
        ...formData.getHeaders()
      },
      body: formData
    }
  );
  
  const reader = response.body;
  reader.on('data', (chunk) => {
    const lines = chunk.toString().split('\n');
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        if (data.type === 'token') {
          process.stdout.write(data.content);
        }
      }
    }
  });
}

// Usage
chatWithAgent(10, 'How do I reset my password?');
```

### cURL Example

```bash
# Simple chat
curl -X POST "http://localhost:8000/public/v1/chat/10/call?app_id=1" \
  -H "X-API-Key: mattin_..." \
  -F "message=Hello, how can you help me?"

# Chat with file attachment
curl -X POST "http://localhost:8000/public/v1/chat/10/call?app_id=1" \
  -H "X-API-Key: mattin_..." \
  -F "message=Summarize this document" \
  -F "files=@document.pdf"

# Continue conversation
curl -X POST "http://localhost:8000/public/v1/chat/10/call?app_id=1" \
  -H "X-API-Key: mattin_..." \
  -F "message=Can you elaborate?" \
  -F "conversation_id=42"

# List agents
curl -X GET "http://localhost:8000/public/v1/agents?app_id=1" \
  -H "X-API-Key: mattin_..."
```

## Error Responses

**Standard error format**:

```json
{
  "detail": "Error message"
}
```

**HTTP Status Codes**:

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request (validation error) |
| 401 | Unauthorized (invalid API key) |
| 403 | Forbidden (revoked API key) |
| 404 | Not Found |
| 429 | Too Many Requests (rate limit exceeded) |
| 500 | Internal Server Error |

**Example error responses**:

```json
// Invalid API key
{
  "detail": "Invalid API key"
}

// Rate limit exceeded
{
  "detail": "Rate limit exceeded. Try again in 60 seconds."
}

// Agent not found
{
  "detail": "Agent not found"
}
```

## Best Practices

1. **Store API keys securely**: Never commit keys to version control
2. **Use environment variables**: Store keys in `.env` files
3. **Handle rate limits**: Implement exponential backoff on 429 responses
4. **Stream responses**: Use streaming for real-time chat experiences
5. **Validate responses**: Check for errors before processing SSE data
6. **Set timeouts**: Configure appropriate timeouts for long-running agent calls
7. **Log errors**: Track API errors for debugging and monitoring

## Security Considerations

1. **HTTPS in production**: Always use HTTPS for API calls in production
2. **Key rotation**: Rotate API keys periodically
3. **Revoke compromised keys**: Immediately revoke keys if compromised
4. **Rate limiting**: Set appropriate rate limits to prevent abuse
5. **Input validation**: Sanitize user input before sending to agents
6. **File size limits**: Enforce file upload size limits (see app settings)

## See Also

- [Internal API](internal-api.md) — Frontend-backend API
- [Backend Architecture](../architecture/backend.md) — Router implementation
- [Agent System](../ai/agent-system.md) — Agent execution details
- [Authentication Guide](../guides/authentication.md) — API key management
