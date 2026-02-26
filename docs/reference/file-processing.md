# File Processing

> Part of [Mattin AI Documentation](../README.md)

## Overview

Mattin AI supports processing various file types for agent consumption. Files are uploaded, processed (text extraction, OCR, transcription), and made available to agents during conversations.

**Supported file types**:
- **PDF**: Text extraction or OCR for image-based PDFs
- **Images** (PNG, JPEG): OCR via vision models
- **Audio** (MP3, WAV, M4A, WebM): Transcription via Whisper
- **Text** (TXT, MD, JSON, CSV): Direct read
- **Office** (DOCX): Text extraction (limited support)

## PDF Processing

### PDFTools Module

Located in `backend/tools/PDFTools.py`, provides utilities for PDF handling.

### extract_text_from_pdf

Extract text from PDF files with selectable text layers.

```python
from tools.PDFTools import extract_text_from_pdf

text = extract_text_from_pdf("/path/to/document.pdf")
# Returns: str - Extracted text
```

**Implementation**:
- Uses `pypdf` (formerly PyPDF2)
- Extracts text from all pages
- Concatenates page content
- Fast for text-based PDFs

### check_pdf_has_text

Check if PDF contains extractable text (vs. scanned/image-only PDF).

```python
from tools.PDFTools import check_pdf_has_text

has_text = check_pdf_has_text("/path/to/document.pdf", min_text_length=50)
# Returns: bool
```

### convert_pdf_to_images

Convert PDF pages to images for OCR processing.

```python
from tools.PDFTools import convert_pdf_to_images

image_paths = convert_pdf_to_images(
    pdf_path="/path/to/document.pdf",
    output_folder="/tmp/pdf_images"
)
# Returns: List[str] - Paths to generated images
```

**Implementation**:
- Uses `pdf2image` (requires poppler)
- Converts each page to JPEG image
- DPI: 200 (balance quality/performance)

## OCR

### ocrAgentTools Module

Located in `backend/tools/ocrAgentTools.py`, provides OCR functionality via vision models.

### extract_text_from_image

Extract text from image using vision-capable LLM.

```python
from tools.ocrAgentTools import extract_text_from_image

text = extract_text_from_image(
    base64_image=base64_str,
    vision_system_prompt="Extract all text from this document",
    vision_model=vision_llm,
    document_title="Invoice #12345"
)
# Returns: str - Extracted text (JSON format)
```

**Supported vision models**:
- OpenAI: `gpt-4-vision-preview`, `gpt-4-turbo`
- Anthropic: Claude 3 Opus, Sonnet
- MistralAI: `pixtral-12b-2409`
- Ollama: `llava`, `bakllava`

### OCR Endpoints

**Internal API**:
```http
POST /internal/ocr/extract
Content-Type: multipart/form-data

file=@image.jpg
```

**Public API**:
```http
POST /public/v1/ocr/extract?app_id=1
X-API-Key: mattin_...
Content-Type: multipart/form-data

file=@receipt.jpg
```

## Transcription

### transcriptionTools Module

Located in `backend/tools/transcriptionTools.py`, provides audio transcription via OpenAI Whisper.

### transcribe_with_openai_whisper

Transcribe audio file to text using Whisper API.

```python
from tools.transcriptionTools import transcribe_with_openai_whisper

result = transcribe_with_openai_whisper(
    audio_path="/path/to/audio.mp3",
    api_key="sk-...",
    language="en"  # Optional: auto-detect if None
)
```

**Returns**: Dictionary with:
```python
{
    'text': "Full transcription...",
    'language': "english",
    'duration': 120.5,  # seconds
    'segments': [
        {'start': 0.0, 'end': 5.2, 'text': "Hello..."},
        # ... more segments
    ]
}
```

**Supported formats**: MP3, MP4, MPEG, MPGA, M4A, WAV, WebM

**Additional tools**:
- **yt-dlp**: Download audio from YouTube/web videos
- **pydub**: Audio format conversion and manipulation

## Media Processing

### MediaService

Background processing for media files (audio, video).

**Features**:
- Async processing via background tasks
- Progress tracking
- Error handling and retry logic

**Use cases**:
- Transcribe long audio files
- Extract audio from video
- Process batch media uploads

## Web Scraping

### scrapTools Module

Located in `backend/tools/scrapTools.py`, extracts content from URLs.

```python
from tools.scrapTools import scrape_url

content = scrape_url("https://example.com/article")
# Returns: str - Extracted text content
```

**Features**:
- HTML parsing
- Clean text extraction (removes scripts, styles)
- Timeout handling
- Error handling for failed requests

**Use case**: Agents can scrape web pages for real-time information.

## File Management

### FileManagementService

Located in `backend/services/file_management_service.py`, manages file lifecycle.

**Key methods**:

```python
class FileManagementService:
    def upload_file(file: UploadFile, app_id: int, conversation_id: Optional[int]) -> FileReference
    def get_file_reference(file_id: str) -> FileReference
    def delete_file(file_id: str) -> None
    def list_files(conversation_id: int) -> List[FileReference]
```

**FileReference model**:
```python
@dataclass
class FileReference:
    file_id: str
    filename: str
    file_path: str
    mime_type: str
    file_size: int
    conversation_id: Optional[int]
    uploaded_at: datetime
```

### Upload Endpoint

**Internal API**:
```http
POST /internal/agents/{agent_id}/upload
Content-Type: multipart/form-data

file=@document.pdf
conversation_id=42
```

**Public API**:
```http
POST /public/v1/files/{agent_id}/attach-file?app_id=1
X-API-Key: mattin_...
Content-Type: multipart/form-data

file=@document.pdf
```

### Storage

Files stored at: `REPO_BASE_FOLDER/files/{conversation_id}/{file_id}`

**Configuration**:
```bash
REPO_BASE_FOLDER=./data/repositories
TMP_BASE_FOLDER=./data/tmp
```

### File Size Limits

Set per-app via `App.max_file_size_mb`:

```python
class App(Base):
    max_file_size_mb = Column(Integer, default=10)  # 10 MB default
```

**Enforcement**:
```python
from routers.controls.file_size_limit import enforce_file_size_limit

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    _=Depends(enforce_file_size_limit)
):
    ...
```

## File Processing Workflow

### Agent Execution with Files

```
User uploads file → FileManagementService stores file
    ↓
FileReference created with metadata
    ↓
Agent execution starts
    ↓
For each file:
    1. Determine file type (MIME type)
    2. Extract content:
       - PDF: extract_text_from_pdf or OCR
       - Image: OCR via vision model
       - Audio: transcribe_with_openai_whisper
       - Text: direct read
    3. Append to context
    ↓
Augment prompt with file content
    ↓
Execute agent with enriched context
```

### PDF Processing Decision Tree

```
PDF File → check_pdf_has_text()
    ↓
Has text? ─yes─→ extract_text_from_pdf() → Done
    ↓ no
convert_pdf_to_images()
    ↓
For each image:
    OCR via vision model
    ↓
Aggregate texts → Done
```

## Performance Considerations

| Operation | Time (avg) | Cost | Notes |
|-----------|------------|------|-------|
| **PDF text extraction** | <1s | Free | Fast for text-based PDFs |
| **PDF to images** | 2-5s | Free | Depends on page count |
| **OCR (per image)** | 2-10s | ~$0.001 | Vision model API call |
| **Whisper transcription** | 1-3s/min | $0.006/min | OpenAI API |

**Optimization tips**:
- Process files in background (async)
- Cache extracted content
- Use cheaper vision models for simple OCR
- Batch process multiple files

## See Also

- [Agent System](../ai/agent-system.md) — File attachment processing in agent execution
- [Backend Architecture](../architecture/backend.md) — File management service
- [Environment Variables](environment-variables.md) — IMAGES_PATH, API keys
