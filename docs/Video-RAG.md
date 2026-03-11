# Video RAG Architectures

This document outlines different architectural approaches for implementing Video Retrieval-Augmented Generation (RAG) systems, from simple to advanced.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Comparison](#architecture-comparison)
3. [Level 1: Audio-Only RAG](#level-1-audio-only-rag-current)
4. [Level 2: Audio + OCR](#level-2-audio--ocr)
5. [Level 3: Multimodal RAG](#level-3-multimodal-rag)
6. [Level 4: Hierarchical Video RAG](#level-4-hierarchical-video-rag)
7. [Level 5: Graph-Enhanced Video RAG](#level-5-graph-enhanced-video-rag)
8. [AI Models Reference](#ai-models-reference)
9. [Implementation Recommendations](#implementation-recommendations)

---

## Overview

Video RAG extends traditional text-based RAG by extracting knowledge from video content. The complexity and capabilities scale with the number of modalities processed and the sophistication of the indexing strategy.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        VIDEO RAG SPECTRUM                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Simple ◄──────────────────────────────────────────────► Complex   │
│                                                                     │
│  Audio-Only → +OCR → +Vision LLM → +Hierarchical → +Knowledge Graph│
│                                                                     │
│  Low Cost                                              High Cost    │
│  Fast Processing                                  Slow Processing   │
│  Basic Understanding                          Deep Understanding    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Architecture Comparison

| Architecture | Modalities | Cross-Video | Cost | Complexity | Use Case |
|--------------|------------|-------------|------|------------|----------|
| **Level 1** | Audio | ❌ | $ | Low | Podcasts, interviews |
| **Level 2** | Audio + OCR | ❌ | $ | Low | Tutorials, slides |
| **Level 3** | Audio + Vision | ❌ | $$ | Medium | Demos, visual content |
| **Level 4** | Multimodal + Hierarchical | ❌ | $$$ | Medium | Long-form content |
| **Level 5** | Multimodal + Graph | ✅ | $$$$ | High | Video corpus/library |

---

## Level 1: Audio-Only RAG (Current)

### Description
Extracts and indexes only the audio transcript from videos. Simple and cost-effective but misses all visual information.

### Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                     AUDIO-ONLY PIPELINE                         │
└─────────────────────────────────────────────────────────────────┘

  Video Input
       │
       ▼
  ┌─────────────┐
  │   Extract   │
  │    Audio    │
  │  (pydub)    │
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │   Whisper   │
  │Transcription│
  │  (ASR)      │
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  Time-based │
  │  Chunking   │
  │ (30-120s)   │
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  Embedding  │
  │  + Index    │
  │(Vector DB)  │
  └─────────────┘
```

### Chunk Structure
```json
{
  "text": "transcript content...",
  "start_time": 45.2,
  "end_time": 78.5,
  "chunk_index": 3,
  "media_id": "uuid",
  "repository_id": "uuid"
}
```

### Pros
- Simple implementation
- Low cost (only Whisper API)
- Fast processing
- Works for audio-heavy content

### Cons
- Misses visual information (slides, diagrams, code)
- Cannot answer "what does the screen show?"
- No scene understanding

### Technologies
- **ASR**: Whisper (OpenAI API or local)
- **Chunking**: Time-window based with overlap
- **Embeddings**: text-embedding-ada-002, text-embedding-3-small

---

## Level 2: Audio + OCR

### Description
Adds optical character recognition to capture on-screen text (slides, code, terminal output). Low additional cost with significant improvement for tutorial/educational content.

### Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                     AUDIO + OCR PIPELINE                        │
└─────────────────────────────────────────────────────────────────┘

  Video Input
       │
       ├───────────────────────────┐
       ▼                           ▼
  ┌─────────────┐           ┌─────────────┐
  │   Extract   │           │  Keyframe   │
  │    Audio    │           │ Extraction  │
  └──────┬──────┘           │(PySceneDetect)
         │                  └──────┬──────┘
         ▼                         │
  ┌─────────────┐                  ▼
  │   Whisper   │           ┌─────────────┐
  │Transcription│           │     OCR     │
  └──────┬──────┘           │ (EasyOCR/   │
         │                  │ Tesseract)  │
         │                  └──────┬──────┘
         │                         │
         └────────┬────────────────┘
                  ▼
           ┌─────────────┐
           │   FUSION    │
           │  (by time)  │
           └──────┬──────┘
                  │
                  ▼
           ┌─────────────┐
           │  Chunking   │
           │ (enriched)  │
           └──────┬──────┘
                  │
                  ▼
           ┌─────────────┐
           │  Embedding  │
           │  + Index    │
           └─────────────┘
```

### Chunk Structure
```json
{
  "text": "transcript content...",
  "ocr_text": "def hello_world():\n    print('Hello')",
  "start_time": 45.2,
  "end_time": 78.5,
  "chunk_index": 3,
  "keyframe_count": 2,
  "media_id": "uuid"
}
```

### Fusion Strategy
```
For each chunk (start_time, end_time):
  1. Get transcript segments in time range
  2. Get keyframes in time range
  3. Extract OCR text from keyframes
  4. Combine: "{transcript}\n\n[On-screen text]: {ocr_text}"
```

### Pros
- Captures code, slides, terminal output
- Minimal additional cost (local OCR)
- Searchable visual text
- Good for tutorials, presentations

### Cons
- Doesn't understand visual context
- OCR can be noisy
- Misses diagrams, charts, actions

### Technologies
- **Keyframe Extraction**: PySceneDetect, ffmpeg
- **OCR**: EasyOCR (recommended), Tesseract, PaddleOCR
- **Scene Detection**: PySceneDetect, TransNetV2

---

## Level 3: Multimodal RAG

### Description
Adds Vision LLM analysis to understand visual content beyond text. Can describe diagrams, actions, UI elements, and visual context.

### Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    MULTIMODAL PIPELINE                          │
└─────────────────────────────────────────────────────────────────┘

  Video Input
       │
       ├───────────────────────────┐
       ▼                           ▼
  ┌─────────────┐           ┌─────────────┐
  │   Extract   │           │  Keyframe   │
  │    Audio    │           │ Extraction  │
  └──────┬──────┘           └──────┬──────┘
         │                         │
         ▼                         ├─────────────────┐
  ┌─────────────┐                  ▼                 ▼
  │   Whisper   │           ┌─────────────┐   ┌─────────────┐
  │Transcription│           │     OCR     │   │ Vision LLM  │
  └──────┬──────┘           └──────┬──────┘   │(GPT-4V, etc)│
         │                         │          └──────┬──────┘
         │                         │                 │
         └─────────┬───────────────┴─────────────────┘
                   ▼
            ┌─────────────┐
            │   FUSION    │
            │ (multimodal)│
            └──────┬──────┘
                   │
                   ▼
            ┌─────────────┐
            │  Chunking   │
            │ (enriched)  │
            └──────┬──────┘
                   │
                   ▼
            ┌─────────────┐
            │  Embedding  │
            │  + Index    │
            └─────────────┘
```

### Chunk Structure
```json
{
  "text": "transcript content...",
  "ocr_text": "code on screen...",
  "visual_description": "The presenter shows a diagram illustrating microservices architecture with three connected boxes labeled 'API Gateway', 'Auth Service', and 'User Service'",
  "start_time": 45.2,
  "end_time": 78.5,
  "chunk_index": 3,
  "keyframes": [
    {
      "timestamp": 52.1,
      "description": "Architecture diagram",
      "ocr": "API Gateway"
    }
  ],
  "media_id": "uuid"
}
```

### Vision LLM Prompt Template
```
Analyze this video frame and provide:
1. A brief description of what's shown (1-2 sentences)
2. Any text visible on screen (if not already captured by OCR)
3. Key visual elements relevant for search (diagrams, UI, actions)

Context: This is from a video about {video_title}
Transcript around this moment: "{nearby_transcript}"
```

### Processing Modes
| Mode | OCR | Vision LLM | Use Case |
|------|-----|------------|----------|
| **Basic** | ❌ | ❌ | Audio podcasts |
| **Standard** | ✅ | ❌ | Tutorials with code |
| **Advanced** | ✅ | ✅ | Complex visual content |

### Pros
- Full visual understanding
- Can describe diagrams, workflows, UI
- Answers "what is shown at timestamp X?"
- Better search relevance

### Cons
- Higher cost (Vision LLM API calls)
- Slower processing
- May need rate limiting

### Technologies
- **Vision LLM**: GPT-4o, GPT-4V, Claude 3 Sonnet/Opus, Gemini 1.5 Pro/Flash
- **Local alternatives**: LLaVA, Qwen-VL, CogVLM

---

## Level 4: Hierarchical Video RAG

### Description
Adds hierarchical structure with scene-level and video-level summaries. Enables both broad discovery ("find videos about X") and precise retrieval ("find the exact moment").

### Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                   HIERARCHICAL PIPELINE                         │
└─────────────────────────────────────────────────────────────────┘

  Video Input
       │
       ▼
  ┌─────────────────────────────────────────────────────────────┐
  │              MULTIMODAL EXTRACTION (Level 3)                │
  │         (Audio + OCR + Vision LLM → Enriched Chunks)        │
  └──────────────────────────┬──────────────────────────────────┘
                             │
                             ▼
                    ┌─────────────┐
                    │    Scene    │
                    │  Detection  │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
   ┌───────────┐    ┌───────────┐    ┌───────────┐
   │  Scene 1  │    │  Scene 2  │    │  Scene N  │
   │  Chunks   │    │  Chunks   │    │  Chunks   │
   └─────┬─────┘    └─────┬─────┘    └─────┬─────┘
         │                │                │
         ▼                ▼                ▼
   ┌───────────┐    ┌───────────┐    ┌───────────┐
   │  Scene 1  │    │  Scene 2  │    │  Scene N  │
   │  Summary  │    │  Summary  │    │  Summary  │
   └─────┬─────┘    └─────┬─────┘    └─────┬─────┘
         │                │                │
         └────────────────┼────────────────┘
                          ▼
                   ┌─────────────┐
                   │   Video     │
                   │  Summary    │
                   └──────┬──────┘
                          │
                          ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                    HYBRID INDEX                             │
  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
  │  │   Chunk     │  │   Scene     │  │   Video     │         │
  │  │   Index     │  │   Index     │  │   Index     │         │
  │  │ (precision) │  │  (context)  │  │ (discovery) │         │
  │  └─────────────┘  └─────────────┘  └─────────────┘         │
  └─────────────────────────────────────────────────────────────┘
```

### Index Hierarchy
```
VIDEO LEVEL (1 per video)
├── Summary: "Complete tutorial on building REST APIs with FastAPI..."
├── Topics: ["FastAPI", "Python", "REST API", "Authentication"]
└── Duration: 45:32

SCENE LEVEL (5-15 per video)
├── Scene 1: "Introduction and project setup" (0:00 - 5:30)
├── Scene 2: "Creating the first endpoint" (5:30 - 12:45)
├── Scene 3: "Adding authentication" (12:45 - 25:00)
└── ...

CHUNK LEVEL (many per video)
├── Chunk with transcript + OCR + visual description
└── Precise timestamps for seeking
```

### Retrieval Strategy
```python
def hierarchical_retrieve(query):
    # Stage 1: Find relevant videos
    video_matches = search_video_index(query, top_k=10)
    
    # Stage 2: Find relevant scenes within those videos
    scene_matches = search_scene_index(
        query, 
        filter={"video_id": [v.id for v in video_matches]},
        top_k=20
    )
    
    # Stage 3: Find precise chunks within those scenes
    chunk_matches = search_chunk_index(
        query,
        filter={"scene_id": [s.id for s in scene_matches]},
        top_k=10
    )
    
    return rerank(chunk_matches)
```

### Pros
- Better routing for large video libraries
- Enables "about" queries vs "exact moment" queries
- Provides context around retrieved chunks
- Natural chapter-like navigation

### Cons
- More complex indexing
- Requires scene detection quality
- Multiple LLM calls for summaries

### Technologies
- **Scene Detection**: PySceneDetect, TransNetV2
- **Summarization**: GPT-4o, Claude Sonnet
- **Vector Store**: Requires multiple collections/namespaces

---

## Level 5: Graph-Enhanced Video RAG

### Description
Builds a knowledge graph across all videos, enabling cross-video reasoning and concept-based retrieval. Based on the VideoRAG (HKUDS) approach.

### Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                GRAPH-ENHANCED PIPELINE                          │
└─────────────────────────────────────────────────────────────────┘

  Video Corpus (Multiple Videos)
       │
       ▼
  ┌─────────────────────────────────────────────────────────────┐
  │           MULTIMODAL EXTRACTION (per video)                 │
  │    ┌──────────┐    ┌──────────┐    ┌──────────┐            │
  │    │ Video 1  │    │ Video 2  │    │ Video N  │            │
  │    │ Chunks   │    │ Chunks   │    │ Chunks   │            │
  │    └────┬─────┘    └────┬─────┘    └────┬─────┘            │
  └─────────┼───────────────┼───────────────┼──────────────────┘
            │               │               │
            ▼               ▼               ▼
  ┌─────────────────────────────────────────────────────────────┐
  │              ENTITY-RELATION EXTRACTION                     │
  │                                                             │
  │   "OpenAI released GPT-4" → (OpenAI)-[released]->(GPT-4)   │
  │   "GPT-4 powers ChatGPT" → (GPT-4)-[powers]->(ChatGPT)     │
  │                                                             │
  └──────────────────────────┬──────────────────────────────────┘
                             │
                             ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                 KNOWLEDGE GRAPH (G)                         │
  │                                                             │
  │         ┌─────────┐                                         │
  │         │ OpenAI  │                                         │
  │         └────┬────┘                                         │
  │              │ released                                     │
  │              ▼                                              │
  │         ┌─────────┐    powers    ┌─────────┐               │
  │         │  GPT-4  │─────────────►│ ChatGPT │               │
  │         └────┬────┘              └─────────┘               │
  │              │ competes_with                                │
  │              ▼                                              │
  │         ┌─────────┐                                         │
  │         │ Claude  │                                         │
  │         └─────────┘                                         │
  │                                                             │
  └──────────────────────────┬──────────────────────────────────┘
                             │
                             ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                    HYBRID INDEX                             │
  │                                                             │
  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
  │  │    Text     │  │ Multimodal  │  │    Graph    │         │
  │  │  Embeddings │  │ Embeddings  │  │   Index     │         │
  │  │   (TEnc)    │  │   (MEnc)    │  │   (Neo4j)   │         │
  │  └─────────────┘  └─────────────┘  └─────────────┘         │
  │                                                             │
  └─────────────────────────────────────────────────────────────┘
```

### Retrieval Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                   MULTI-MODAL RETRIEVAL                         │
└─────────────────────────────────────────────────────────────────┘

  Query: "What are OpenAI o1 and o1 pro mode in ChatGPT?"
       │
       ▼
  ┌─────────────┐
  │   Query     │
  │Reformulation│
  └──────┬──────┘
         │
         ├─────────────────┬─────────────────┐
         ▼                 ▼                 ▼
  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
  │ Text-based  │   │Graph-based  │   │ Visual      │
  │  Retrieval  │   │ Retrieval   │   │ Retrieval   │
  │   (TEnc)    │   │(traverse G) │   │  (MEnc)     │
  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
         │                 │                 │
         │    ┌────────────┘                 │
         │    │  Graph expands query:        │
         │    │  OpenAI → GPT-4 → o1 → o1-pro│
         │    │                              │
         └────┼──────────────────────────────┘
              ▼
       ┌─────────────┐
       │  LLM-based  │
       │  Filtering  │
       │ & Reranking │
       └──────┬──────┘
              │
              ▼
       ┌─────────────┐
       │  Retrieved  │
       │   Content   │
       └─────────────┘
```

### Entity Extraction Prompt
```
Extract entities and relationships from this text chunk.

Text: "{chunk_text}"

Return JSON:
{
  "entities": [
    {"name": "GPT-4", "type": "product"},
    {"name": "OpenAI", "type": "organization"}
  ],
  "relationships": [
    {"source": "OpenAI", "relation": "created", "target": "GPT-4"}
  ]
}
```

### Graph Schema
```
NODES:
- Entity(name, type, description)
- VideoChunk(id, text, start_time, end_time, video_id)

EDGES:
- MENTIONS: (VideoChunk)-[MENTIONS]->(Entity)
- RELATION: (Entity)-[relation_type]->(Entity)
- APPEARS_WITH: (Entity)-[APPEARS_WITH]->(Entity) // co-occurrence
```

### Retrieval Strategies

| Strategy | How It Works | Use Case |
|----------|--------------|----------|
| **Direct** | Query → Entity match → Get chunks | Specific entity queries |
| **1-hop** | Query → Entity → Related entities → Chunks | "Tell me about X and related concepts" |
| **Community** | Query → Entity cluster → All cluster chunks | Topic exploration |
| **Hybrid** | Combine vector similarity + graph expansion | General queries |

### Pros
- Cross-video knowledge linking
- Concept-based retrieval (not just keyword matching)
- Discovers related content user didn't explicitly ask for
- Enables knowledge exploration

### Cons
- High complexity
- Requires graph database
- Entity extraction can be noisy
- Expensive (many LLM calls)
- Needs entity resolution (deduplication)

### Technologies
- **Graph Database**: Neo4j, Amazon Neptune, NetworkX (in-memory)
- **Entity Extraction**: GPT-4, spaCy + custom NER, GLiNER
- **Graph Embeddings**: node2vec, GraphSAGE (optional)
- **Multimodal Embeddings**: CLIP, ImageBind

---

## AI Models Reference

### Speech Recognition (ASR)

| Model | Type | Quality | Speed | Cost |
|-------|------|---------|-------|------|
| **Whisper large-v3** | Local/API | Excellent | Slow | Free/$ |
| **Whisper medium** | Local | Good | Medium | Free |
| **Deepgram** | API | Excellent | Fast | $$ |
| **AssemblyAI** | API | Excellent | Fast | $$ |

### OCR

| Model | Type | Languages | Quality |
|-------|------|-----------|---------|
| **EasyOCR** | Local | 80+ | Good |
| **Tesseract** | Local | 100+ | Medium |
| **PaddleOCR** | Local | 80+ | Good |
| **Google Cloud Vision** | API | 100+ | Excellent |

### Vision LLM

| Model | Quality | Speed | Cost | Context |
|-------|---------|-------|------|---------|
| **GPT-4o** | Excellent | Fast | $$ | 128K |
| **GPT-4o-mini** | Good | Fast | $ | 128K |
| **Claude 3.5 Sonnet** | Excellent | Fast | $$ | 200K |
| **Gemini 1.5 Flash** | Good | Very Fast | $ | 1M |
| **Gemini 1.5 Pro** | Excellent | Medium | $$ | 1M |
| **LLaVA** | Medium | Slow | Free | 4K |
| **Qwen-VL** | Good | Medium | Free | 32K |

### Multimodal Embeddings

| Model | Modalities | Use Case |
|-------|------------|----------|
| **CLIP** | Image + Text | Visual similarity search |
| **ImageBind** | Image + Text + Audio + Video | Unified embedding space |
| **Twelve Labs Embed** | Video native | Video-specific search |

### Scene Detection

| Tool | Method | Quality |
|------|--------|---------|
| **PySceneDetect** | Rule-based (content/threshold) | Good |
| **TransNetV2** | ML-based | Excellent |
| **ffmpeg** | Keyframe extraction | Basic |

---

## Implementation Recommendations

### For This Project

Based on the current architecture and use cases:

#### Phase 1: Add OCR (Low effort, high value)
```
Current Pipeline + Keyframe Extraction + EasyOCR
```
- **Effort**: 1-2 days
- **Value**: Searchable slides, code, terminal output
- **Cost impact**: Minimal (local processing)

#### Phase 2: Add Vision LLM (Medium effort)
```
Phase 1 + Optional GPT-4o-mini for complex frames
```
- **Effort**: 2-3 days
- **Value**: Visual understanding, diagram descriptions
- **Cost impact**: ~$0.01-0.05 per video minute

#### Phase 3: Hierarchical Indexing (Medium effort)
```
Phase 2 + Scene detection + Multi-level summaries
```
- **Effort**: 1 week
- **Value**: Better navigation, video-level discovery
- **Cost impact**: Additional LLM calls for summaries

#### Phase 4: Knowledge Graph (High effort)
```
Phase 3 + Entity extraction + Neo4j + Graph retrieval
```
- **Effort**: 2-3 weeks
- **Value**: Cross-video reasoning, concept linking
- **Cost impact**: Graph DB + entity extraction LLM calls

### Processing Mode Selection

Add a `processing_mode` field to Media model:

| Mode | Description | Pipeline |
|------|-------------|----------|
| `basic` | Audio only | Level 1 |
| `standard` | Audio + OCR | Level 2 |
| `advanced` | Audio + OCR + Vision | Level 3 |
| `full` | All features | Level 4-5 |

Allow users to select based on content type and budget.

---

## References

- [NVIDIA Video Search and Summarization Blueprint](https://github.com/NVIDIA-AI-Blueprints/video-search-and-summarization)
- [VideoRAG (HKUDS)](https://github.com/HKUDS/VideoRAG)
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
- [Twelve Labs](https://twelvelabs.io/)
- [LangChain Multi-Modal RAG](https://python.langchain.com/docs/use_cases/question_answering/multi_modal_rag)

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-02-10 | 1.0 | Initial architecture documentation |