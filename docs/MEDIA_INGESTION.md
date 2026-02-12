# Media Management System

## Overview

The media system handles video/audio transcription, chunking, and vector indexing. Files can be uploaded directly or pulled from YouTube, then automatically processed for RAG queries.

## Supported Formats

**Video:** mp4, mov, avi, mkv, webm, flv, wmv, mpeg, mpg  
**Audio:** mp3, wav, m4a, aac, ogg, flac, wma

## API Endpoints

### Upload Media Files
```bash
POST /api/app/{app_id}/repositories/{repository_id}/media
```
**Form data:**
- `files`: One or more media files
- `folder_id`: Target folder (0 or null for root)
- `transcription_service_id`: AI service for transcription
- `forced_language`: Optional (e.g., 'es', 'en', 'fr')
- `chunk_min_duration`: Min chunk seconds (default: 30)
- `chunk_max_duration`: Max chunk seconds (default: 120)
- `chunk_overlap`: Overlap seconds (default: 0, recommended: 5-10)

**Response:**
```json
{
  "message": "Uploaded 2 media file(s)",
  "created_media": [...],
  "failed_files": [...]
}
```

### Add YouTube Video
```bash
POST /api/app/{app_id}/repositories/{repository_id}/media/youtube
```
**Form data:**
- `url`: YouTube URL
- Same chunking/transcription params as upload

Validates URL format and checks for duplicates within repository.

### List Media
```bash
GET /api/app/{app_id}/repositories/{repository_id}/media?folder_id={folder_id}
```
Returns all media in repository, optionally filtered by folder.

### Move Media
```bash
POST /api/app/{app_id}/repositories/{repository_id}/media/{media_id}/move
```
**Form data:**
- `new_folder_id`: Target folder (null for root)

Moves media file, audio file, updates DB, and re-indexes vectors with new metadata.

### Get Media Status
```bash
GET /api/app/{app_id}/repositories/{repository_id}/media/{media_id}
```

### Delete Media
```bash
DELETE /api/app/{app_id}/repositories/{repository_id}/media/{media_id}
```
Removes media from vector DB, deletes files (media + audio), and removes DB record.

## Processing Pipeline

1. **File Upload/Download:** Saved to `{REPO_BASE_FOLDER}/{repository_id}/[folder_path/]{media_id}.ext`
2. **Audio Extraction:** Video converted to `{media_id}_audio.wav`
3. **Transcription:** Uses Whisper (OpenAI API or local model)
4. **Chunking:** Groups segments by time windows with optional overlap
5. **Vector Indexing:** Each chunk indexed with metadata

## Transcription

**Service-based (OpenAI Whisper API):**
```python
TranscriptionService.transcribe_audio(
    audio_path, 
    language='es',  # or None for auto-detect
    db=db,
    ai_service_id=123
)
```

**Output:**
```python
{
    'segments': [{'start': 0.0, 'end': 3.5, 'text': '...'}],
    'language': 'en',
    'duration': 120.5,
    'text': 'Full transcript...'
}
```

## Chunking Strategy

```python
TranscriptionService.create_chunks(
    segments,
    min_window=30,    # Min duration
    max_window=120,   # Max duration
    overlap=5         # Overlap between chunks
)
```

**Logic:**
- Accumulates segments until `max_window` reached
- Splits at natural breaks (sentence endings) if past `min_window`
- Adds `overlap` seconds to next chunk for context continuity

## Vector Storage

Each chunk stored with metadata:
```python
{
    "repository_id": 1,
    "media_id": 123,
    "content_type": "media_chunk",
    "chunk_index": 0,
    "start_time": 0.0,
    "end_time": 30.5,
    "duration": 30.5,
    "name": "Interview.mp4",
    "source_type": "upload|youtube",
    "source_url": "https://...",
    "language": "en",
    "folder_id": 5,
    "folder_path": "interviews/2024",
    "ref": "1/interviews/2024/123.mp4"
}
```

**Indexing:**
```python
SiloService.index_media_chunk(chunk_dict, media, db)
```

**Deletion:**
```python
SiloService.delete_media(media)  # Removes all chunks via media_id filter
```

## Move Operation

When moving media to new folder:
1. Moves `{media_id}.ext` and `{media_id}_audio.wav` to new path
2. Updates `media.file_path` and `media.folder_id` in DB
3. Re-indexes all chunks with updated `folder_id`, `folder_path`, and `ref` metadata

## Background Processing

All transcription/indexing runs async via FastAPI `background_tasks`:
```python
background_tasks.add_task(process_media_task_sync, media.media_id)
```

Media status: `pending` → `processing` → `completed` or `failed`

## Error Handling

Upload endpoint returns partial success:
```python
return (created_media, failed_files)
```

Failed files include filename and error message. Successful media proceed to background processing.