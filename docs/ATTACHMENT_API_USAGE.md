# API Attachment Support

The API now supports file attachments in multiple ways:

## 1. JSON Request with Base64 Attachment

Send a JSON request with a base64-encoded file:

```json
{
  "question": "What is this document about?",
  "attachment": "data:application/pdf;base64,JVBERi0xLjQKJcOkw7zDtsO...",
  "attachment_filename": "document.pdf",
  "attachment_mime_type": "application/pdf",
  "search_params": {
    "filter": {
      "source": "documentation"
    }
  }
}
```

## 2. Multipart Form Data

Send a multipart form request with a file upload:

```bash
curl -X POST "http://your-api/api/app/1/call/123" \
  -H "Content-Type: multipart/form-data" \
  -F "question=What is this document about?" \
  -F "file=@document.pdf" \
  -F "search_params={\"filter\":{\"source\":\"documentation\"}}"
```

## 3. File Reference System (Recommended for Chat)

Upload files separately and reference them in chat messages:

### Step 1: Upload a file
```bash
curl -X POST "http://your-api/api/app/1/attach-file/123" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf"
```

Response:
```json
{
  "status": "success",
  "file_reference": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "document.pdf",
  "content_type": "application/pdf",
  "message": "File attached successfully"
}
```

### Step 2: Use file reference in chat
```json
{
  "question": "What is this document about?",
  "file_references": ["550e8400-e29b-41d4-a716-446655440000"]
}
```

### Step 3: List attached files
```bash
curl -X GET "http://your-api/api/app/1/attached-files/123"
```

### Step 4: Remove file when done
```bash
curl -X DELETE "http://your-api/api/app/1/detach-file/123/550e8400-e29b-41d4-a716-446655440000"
```

## File Processing

The API automatically processes different file types:

- **PDF files**: Uses OCR to extract text (if agent has OCR capabilities)
- **Image files**: Converts to base64 for vision models (if agent has vision capabilities)
- **Text files**: Reads and includes content directly
- **Document files**: Basic support (mentions file attachment)

## Supported File Types

- PDF files (.pdf)
- Text files (.txt, .md)
- Image files (.png, .jpg, .jpeg)
- Document files (.doc, .docx)

## Response

The response includes metadata about attachment processing:

```json
{
  "input": "What is this document about?",
  "generated_text": "This document discusses...",
  "control": { ... },
  "metadata": {
    "model_name": "gpt-4",
    "timestamp": "2024-04-04T12:00:00Z",
    "attachments_processed": true,
    "attachment_count": 2
  }
}
```

## File Reference System Benefits

1. **Efficient**: Upload once, use multiple times
2. **Session-based**: Files persist during the chat session
3. **Multiple files**: Reference multiple files in a single message
4. **Cleanup**: Automatic cleanup when session ends or files are removed
5. **Validation**: Files are validated and stored securely

## Security

- Files are saved to temporary locations with secure filenames
- Files are automatically cleaned up after processing
- File type validation prevents malicious uploads
- File size limits can be configured via environment variables
- Session-based file storage with agent isolation

## Environment Variables

Configure file storage paths:

```bash
DOWNLOADS_PATH=data/temp/downloads/
IMAGES_PATH=data/temp/images/
```

## Error Handling

The API provides clear error messages for:
- Invalid file types
- File processing errors
- Missing required fields
- Base64 decoding errors
- Invalid file references
- File not found errors

## Usage Examples

### Chat with multiple files:
```json
{
  "question": "Compare these two documents",
  "file_references": [
    "550e8400-e29b-41d4-a716-446655440000",
    "550e8400-e29b-41d4-a716-446655440001"
  ]
}
```

### Mix base64 and file references:
```json
{
  "question": "Analyze this new document with the previous ones",
  "attachment": "data:application/pdf;base64,JVBERi0xLjQKJcOkw7zDtsO...",
  "attachment_filename": "new_document.pdf",
  "file_references": ["550e8400-e29b-41d4-a716-446655440000"]
}
``` 