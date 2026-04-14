# Multimodal Video RAG

> Part of [Mattin AI Documentation](../index.md)

Mattin AI supports **multimodal video analysis** for media ingestion: when enabled, videos are processed both for audio transcription and visual content, producing independent chunks that are embedded separately in the vector store.

This document explains the architecture, configuration, and chunk structure of the multimodal pipeline.

---

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Processing Pipeline](#processing-pipeline)
- [Chunk Structure](#chunk-structure)
- [How Retrieval Works](#how-retrieval-works)
- [Supported Providers](#supported-providers)
- [Frequently Asked Questions](#frequently-asked-questions)

---

## Overview

When a media file (uploaded video or YouTube URL) is added to a repository, Mattin AI processes it through a pipeline that converts it into searchable vector embeddings. The pipeline has two modes depending on repository configuration:

| Mode | Trigger | What is indexed | Chunks per time range | Cost |
|------|---------|----------------|----------------------|------|
| **Basic** | Repository has no Video Analysis Service | Audio transcript only | 1 (audio) | Low — only Whisper API |
| **Multimodal** | Repository has a Video Analysis Service configured | Audio transcript + visual descriptions | Up to 2 (audio + visual) | Higher — Whisper + Gemini |

Multimodal analysis activates **automatically** when the repository has a `Video Analysis Service` configured — no per-upload toggle is needed.

In **multimodal mode**, for each time window (e.g. 0:00–0:30) the system produces **two independent chunks**:

1. **Audio chunk** — contains the transcribed speech for that time range.
2. **Visual chunk** — contains a description of what is shown on screen (slides, code, diagrams, UI, etc.).

Both chunks share the same `start_time` / `end_time` but are embedded independently, allowing the vector search to match based on the most relevant modality.

---

## Prerequisites

To use multimodal video analysis you need:

1. **A Whisper-compatible AI Service** — for audio transcription (e.g., OpenAI with `whisper-1`).
2. **A Google Gemini AI Service with video enabled** — for visual analysis. Only `Google` and `GoogleCloud` providers support video analysis.

> Video analysis is **only available** for Google (Gemini Developer API) and GoogleCloud (Vertex AI) providers. The AI Service must have the `supports_video` flag enabled.

---

## Configuration

### 1. Create a video-capable AI Service

In your App settings, create (or edit) an AI Service:

- **Provider**: `Google` or `GoogleCloud`
- **Model**: A Gemini model with video capabilities (e.g., `gemini-2.0-flash`, `gemini-2.5-pro`)
- **Video Analysis Capable**: Enable the checkbox (only visible for Google providers)

For **Google** (Gemini Developer API):

- **API Key**: Your Gemini API key

For **GoogleCloud** (Vertex AI):

- **API Key**: Service Account JSON
- **Base URL**: GCP Project ID
- **API Version**: GCP region (defaults to `europe-west1`)

### 2. Configure services at the repository level

All AI service configuration is done **once at the repository level**. There is no per-upload service selection — every media file in the repository uses these settings.

In the repository create/edit form:

- **Transcription Service (Whisper)** — Required. All media in this repository will use this service for audio transcription.
- **Video Analysis Service (Gemini)** — Optional. When set, **all media uploaded to this repository** will automatically go through visual analysis. Leave empty for audio-only processing.

> Multimodal mode is repository-wide: if a Video Analysis Service is configured, every uploaded video/audio file will be processed with both Whisper and Gemini.

### 3. Upload media

When uploading a media file (or adding a YouTube URL), the only configurable parameters are:

- **Folder** *(optional)* — Target folder within the repository.
- **Language** *(optional)* — Force transcription language (e.g., `es`, `en`). Leave empty for auto-detection.
- **Chunking parameters** — See table below.

> The upload form shows which services the repository will use (read-only), so you can confirm the configuration before uploading.

### Chunking parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `chunk_min_duration` | 30s | Minimum chunk duration in seconds |
| `chunk_max_duration` | 120s | Maximum chunk duration in seconds |
| `chunk_overlap` | 0s | Overlap between consecutive chunks |

---

## Processing Pipeline

```
Video Input (upload or YouTube URL)
      │
      ├──► Extract audio (pydub/ffmpeg)
      │         │
      │         ▼
      │    Transcribe with Whisper
      │         │
      │         ▼
      │    Create time-based audio chunks
      │         │
      │    ┌────┴──────────────────────────────┐
      │    │ repo has video_ai_service_id?      │
      │    └────┬──────────────────────────────┘
      │         │ no              │ yes
      │         │                 ▼
      │         │          status: analyzing_video
      │         │                 │
      │         │          Send video to Gemini
      │         │          (chunk-aligned prompt)
      │         │                 │
      │         │          Visual descriptions
      │         │          (one per audio chunk)
      │         │                 │
      │         │          split_audio_visual_chunks()
      │         │                 │
      │         │      ┌──────────┴──────────┐
      │         │      ▼                     ▼
      │         │  Audio chunks         Visual chunks
      │         │  chunk_type=          chunk_type=
      │         │  'audio'              'visual'
      │         │      │                     │
      │         │      └──────────┬──────────┘
      │         │                 │
      │         ▼                 ▼
      └────────────► Index all chunks in vector store
```

### Step-by-step

1. **Download** — If the source is a YouTube URL, the video is downloaded with `yt-dlp`. Status: `downloading`.
2. **Extract audio** — The video is converted to normalized audio using `pydub`/`ffmpeg`. Status: `processing`.
3. **Transcribe** — Audio is sent to Whisper for speech-to-text transcription with timestamps. Status: `transcribing`.
4. **Create audio chunks** — Transcript segments are grouped into time-window chunks (30–120s, configurable).
5. **Analyze video** *(if repository has a Video Analysis Service)* — The full video is sent to Gemini with a **chunk-aligned prompt**: the model is asked to describe visual content for the exact time ranges of each audio chunk. Status: `analyzing_video`.
6. **Split into audio + visual chunks** *(multimodal only)* — For each time range, two independent chunks are produced: one with the transcript text, one with the visual description.
7. **Index** — All chunks are embedded and stored in the vector database (PGVector or Qdrant). Status: `indexing` → `ready`.

> **Media status states**: `pending` → `downloading` *(YouTube only)* → `processing` → `transcribing` → `analyzing_video` *(multimodal only)* → `indexing` → `ready` / `error`

### Chunk-aligned prompting

Instead of letting the LLM decide its own time segments, the system sends the exact time ranges of the audio chunks to Gemini and asks it to produce one visual description per range. This ensures audio and visual chunks are perfectly aligned temporally and a direct mapping by index is possible.

---

## Chunk Structure

### Audio chunk (basic and multimodal)

```json
{
  "text": "And here we can see the microservices architecture where the API gateway...",
  "start_time": 30.0,
  "end_time": 60.0,
  "chunk_type": "audio",
  "chunk_index": 1
}
```

### Visual chunk (multimodal only)

```json
{
  "text": "Slide showing a microservices architecture diagram with three connected boxes labeled 'API Gateway', 'Auth Service', and 'User Service'. Code editor visible in bottom half showing a Python FastAPI endpoint definition.",
  "start_time": 30.0,
  "end_time": 60.0,
  "chunk_type": "visual",
  "chunk_index": 2
}
```

### Metadata stored in the vector DB

Both chunk types share the same metadata fields:

| Field | Example | Description |
|-------|---------|-------------|
| `content_type` | `media_chunk` | Always `media_chunk` for media-derived chunks |
| `chunk_type` | `audio` / `visual` | Modality of this chunk |
| `start_time` | `30.0` | Start time in seconds |
| `end_time` | `60.0` | End time in seconds |
| `duration` | `30.0` | Chunk duration in seconds |
| `media_id` | `42` | Source media ID |
| `repository_id` | `7` | Parent repository ID |
| `processing_mode` | `basic` | *(Legacy field — may not reflect actual processing performed; always stored as `basic` regardless. Check `chunk_type` instead.)* |
| `name` | `"tutorial.mp4"` | Media file name |
| `file_type` | `.mp4` | File extension of the source media file |
| `source_type` | `youtube` | `upload` or `youtube` |
| `source_url` | `https://...` | YouTube URL (if applicable) |
| `language` | `en` | Detected language |
| `media_duration` | `620.5` | Total duration of the source video |

---

## How Retrieval Works

Audio and visual chunks are embedded **independently** in the same vector store collection (silo). When an agent performs a RAG query:

1. The vector store performs a standard **similarity search** across all chunks in the collection.
2. If the query is about something **spoken** (e.g., *"what did the presenter say about authentication?"*), audio chunks score higher.
3. If the query is about something **visual** (e.g., *"what diagram was shown?"* or *"what code was on screen?"*), visual chunks score higher.

The agent receives results with all metadata (including `chunk_type`, `start_time`, `end_time`), so it can:

- Identify whether a result comes from audio or visual analysis.
- Correlate chunks from the same time range using `media_id` + `start_time`/`end_time` to build a complete multimodal answer.

> No special search configuration is needed. The standard silo retriever handles both chunk types transparently.

---

## Supported Providers

Video analysis **only supports Google Gemini models**:

| Provider | Auth method | How video is sent | Max file size |
|----------|------------|-------------------|---------------|
| **Google** (Gemini Developer API) | API key | Uploaded to Google Files API, referenced by URI | 2 GB |
| **GoogleCloud** (Vertex AI) | Service Account JSON | Sent inline as base64 in the request | 2 GB |

Both providers use `ChatGoogleGenerativeAI` from `langchain-google-genai` v4.x with the `google-genai` SDK.

- **Google**: uploads the video first via the Files API, then sends only the file URI to the model.
- **GoogleCloud**: reads the video locally, base64-encodes it, and sends it inline with `vertexai=True`.

### Recommended models

| Model | Strengths |
|-------|-----------|
| `gemini-2.0-flash` | Fast, cost-effective, good for most videos |
| `gemini-2.5-flash` | Balance of speed and quality |
| `gemini-2.5-pro` | Higher quality, better for complex visual content |

---

## Frequently Asked Questions

### Does video analysis slow down processing?

Yes. When a repository has a Video Analysis Service configured, the video analysis step adds processing time because the video must be uploaded/sent to Gemini and processed before descriptions are returned. For the `Google` provider there is an additional polling wait while Google's servers process the file. Audio transcription runs first and is unaffected.

### What happens if video analysis fails?

The pipeline is **fault-tolerant**: if video analysis fails (e.g., unsupported format, network error, API error), processing continues with audio-only chunks. A warning is logged but the media is still marked as `ready`.

### Can I use OpenAI or other providers for video analysis?

No. Only `Google` and `GoogleCloud` providers support video analysis. The `supports_video` checkbox is only shown in the UI when one of these providers is selected, and switching to another provider automatically resets the flag.

### How many chunks are created for a 10-minute video?

Depends on chunking configuration. With defaults (30–120s windows):

- **Without a Video Analysis Service**: ~5–20 audio chunks.
- **With a Video Analysis Service configured**: up to ~10–40 chunks (audio + visual for each time range that has visual content).

### Can the agent combine audio and visual chunks from the same time range?

Yes. Both chunk types carry `media_id`, `start_time`, and `end_time` in their metadata. The agent can correlate results from the same time range to build a complete multimodal answer.

### What visual information does Gemini capture?

The prompt focuses on visual content that **would not be captured by audio transcription alone**:

- Text shown on screen (slides, code, terminal output)
- Diagrams, charts, and visual elements
- UI interactions and demonstrations
- Scene transitions and visual context
- People, objects, and visible actions

### How do I know if a retrieved chunk is audio or visual?

Check the `chunk_type` metadata field returned with every search result: `"audio"` or `"visual"`.

---

## See Also

- [RAG & Vector Stores](../ai/rag-vector-stores.md) — Silo system and vector database backends
- [LLM Integration](../ai/llm-integration.md) — Supported providers and AI Service configuration
- [Video-RAG Architectures](../Video-RAG.md) — Comparison of different Video RAG levels
