# RAG & Vector Stores

> Part of [Mattin AI Documentation](../README.md)

## Overview

Mattin AI provides a comprehensive **Retrieval-Augmented Generation (RAG)** system that enables agents to access external knowledge by retrieving relevant documents from vector databases. The system is built around the **Silo** concept — a vector store that holds embeddings of documents for semantic search.

**Key features**:
- **Multi-backend support**: PGVector (PostgreSQL extension) or Qdrant (standalone vector DB)
- **Document ingestion**: Upload files or scrape websites
- **Semantic search**: Find relevant documents based on meaning, not keywords
- **Embedding models**: OpenAI, HuggingFace, Ollama
- **Factory pattern**: Unified interface for all vector store backends

## Silo System

A **Silo** is a named vector store within an app. Each silo:
- Has a unique name and description
- Uses a specific vector database backend (PGVector or Qdrant)
- Uses a specific embedding service for generating vectors
- Can be associated with multiple repositories (file collections)

### Silo Model

```python
class Silo(Base):
    __tablename__ = 'Silo'
    
    silo_id = Column(Integer, primary_key=True)
    app_id = Column(Integer, ForeignKey('App.app_id'))
    name = Column(String(255))
    description = Column(Text)
    vector_db_type = Column(String(45))  # 'PGVECTOR' or 'QDRANT'
    embedding_service_id = Column(Integer, ForeignKey('EmbeddingService.service_id'))
    retrieval_count = Column(Integer, default=5)  # Number of docs to retrieve
    create_date = Column(DateTime, default=datetime.now)
```

### Collection Naming

Each silo maps to a collection in the vector database:

```python
collection_name = f"silo_{silo.silo_id}"
```

This naming convention ensures:
- **Namespace isolation**: Each silo has its own collection
- **Multi-tenancy**: Apps' silos don't interfere with each other
- **Simple lookups**: Easy to find a silo's vectors

### Per-Silo Configuration

Each silo has its own:
- **Embedding service**: Different silos can use different embedding models
- **Retrieval count**: How many documents to return in searches
- **Vector DB backend**: One app can have PGVector silos and Qdrant silos simultaneously

**Example**: 
- Silo A: OpenAI embeddings, PGVector, retrieves 5 docs
- Silo B: HuggingFace embeddings, Qdrant, retrieves 10 docs

### Creating a Silo

Via Internal API:

```bash
POST /internal/silos
Content-Type: application/json

{
  "name": "Knowledge Base",
  "description": "Company documentation and policies",
  "vector_db_type": "PGVECTOR",
  "embedding_service_id": 1,
  "retrieval_count": 5
}
```

## Vector Database Backends

### Factory Pattern

The `vector_store_factory.py` module provides a **unified interface** for all vector store backends:

```python
from tools.vector_store_factory import get_vector_store

store = get_vector_store(silo)
# Returns PGVectorStore or QdrantStore based on silo.vector_db_type
```

**Interface methods** (common to all backends):
- `index_documents(collection_name, documents, embedding_service)`: Add documents to vector store
- `similarity_search(collection_name, query, k, embedding_service)`: Search for similar documents
- `get_retriever(collection_name, k, embedding_service)`: Get LangChain retriever
- `delete_collection(collection_name)`: Delete all vectors in a collection

This abstraction allows **switching backends without changing agent code**.

### PGVector

**Default backend** — PostgreSQL with pgvector extension.

**Advantages**:
- Single database for both structured and vector data
- No additional infrastructure required
- Native PostgreSQL performance and reliability
- ACID transactions for vector operations

**Setup**:

1. **Install pgvector extension**:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

2. **LangChain creates tables automatically**:
- `langchain_pg_collection`: Collection metadata
- `langchain_pg_embedding`: Vector storage

3. **Configure in Silo**:
```python
vector_db_type = "PGVECTOR"
```

**Implementation**: `backend/tools/vector_stores/pgvector_store.py`

**Under the hood**:
- Uses `langchain_postgres.vectorstores.PGVector`
- Supports HNSW and IVFFlat indexes for fast approximate nearest neighbor search
- Vector similarity operators: `<->` (L2), `<#>` (cosine), `<=>` (inner product)

**Example query**:
```sql
SELECT * FROM langchain_pg_embedding
WHERE collection_id = (SELECT uuid FROM langchain_pg_collection WHERE name = 'silo_1')
ORDER BY embedding <-> '[0.1, 0.2, ...]'  -- L2 distance to query vector
LIMIT 5;
```

### Qdrant

**Dedicated vector database** optimized for high-performance similarity search.

**Advantages**:
- Specialized for vector operations (faster for large-scale use cases)
- Advanced filtering and hybrid search
- gRPC support for low-latency operations
- Horizontal scalability

**Setup**:

1. **Run Qdrant server** via Docker Compose:
```bash
docker-compose -f docker-compose-qdrant.yaml up -d
```

`docker-compose-qdrant.yaml`:
```yaml
version: '3.8'
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"  # REST API
      - "6334:6334"  # gRPC
    volumes:
      - qdrant_data:/qdrant/storage
volumes:
  qdrant_data:
```

2. **Configure environment variable**:
```bash
QDRANT_URL=http://localhost:6333
```

3. **Configure in Silo**:
```python
vector_db_type = "QDRANT"
```

**Implementation**: `backend/tools/vector_stores/qdrant_store.py`

**Under the hood**:
- Uses `langchain_qdrant.QdrantVectorStore`
- Requires `qdrant-client` package
- Collections stored in Qdrant, not PostgreSQL

**Connection**:
```python
from qdrant_client import QdrantClient

client = QdrantClient(
    url="http://localhost:6333",  # or Qdrant Cloud URL
    api_key="your-api-key",        # Optional, for Qdrant Cloud
    prefer_grpc=True               # Use gRPC for lower latency
)
```

### Planned Backends

Future backends under consideration:

| Backend | Status | Use Case |
|---------|--------|----------|
| **Pinecone** | Planned | Cloud-native, serverless vector DB |
| **Weaviate** | Planned | GraphQL API, hybrid search |
| **Chroma** | Planned | Lightweight, embeddable vector DB |

Adding a new backend requires:
1. Implement `VectorStoreInterface` in `backend/tools/vector_stores/`
2. Add to `get_vector_store()` factory function
3. Add enum value to `VectorDBType`

## Document Ingestion

### Repository System

A **Repository** is a collection of files within a silo. It represents a logical grouping of documents (e.g., "HR Policies", "Technical Docs").

```python
class Repository(Base):
    __tablename__ = 'Repository'
    
    repository_id = Column(Integer, primary_key=True)
    app_id = Column(Integer, ForeignKey('App.app_id'))
    silo_id = Column(Integer, ForeignKey('Silo.silo_id'))
    name = Column(String(255))
    description = Column(Text)
    status = Column(String(45))  # 'active', 'processing', 'error'
```

### File Processing

1. **Upload file** to repository via `/internal/repositories/{repo_id}/files`
2. **Extract text** from file:
   - **PDF**: `extract_text_from_pdf()` or OCR if no text layer
   - **DOCX**: Text extraction via `python-docx`
   - **TXT**: Direct read
   - **Images**: OCR via vision models
3. **Chunk text** into smaller segments (e.g., 500-character chunks with 50-character overlap)
4. **Generate embeddings** using the silo's embedding service
5. **Store vectors** in the silo's vector database (collection = `silo_{silo_id}`)
6. **Update status** to `processed`

**Chunking strategy**:
```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    separators=["\n\n", "\n", ". ", " ", ""]
)
chunks = splitter.split_text(extracted_text)
```

### Embedding Generation

Embeddings are generated using the silo's configured `EmbeddingService`:

```python
from tools.embeddingTools import get_embeddings_model

embeddings = get_embeddings_model(silo.embedding_service)
vectors = embeddings.embed_documents(chunks)
```

Supported embedding providers:
- **OpenAI**: `text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`
- **HuggingFace**: `sentence-transformers/*` (e.g., `all-MiniLM-L6-v2`)
- **Ollama**: Local models (e.g., `nomic-embed-text`)

## Retrieval

### Unified Retriever Interface

All vector stores provide a **LangChain retriever** for agent integration:

```python
from tools.vector_store_factory import get_vector_store_retriever

retriever = get_vector_store_retriever(silo, k=5)
docs = retriever.get_relevant_documents("How do I reset my password?")
# Returns top 5 most relevant document chunks
```

### Search Types

The silo search engine supports three search strategies, selectable via the `search_type` parameter:

| `search_type` | Description | Extra params |
|---|---|---|
| `similarity` | Standard cosine-similarity ranking (default) | — |
| `similarity_score_threshold` | Returns only results at or above a relevance score | `score_threshold` (0.0–1.0) |
| `mmr` | Maximal Marginal Relevance — balances relevance and diversity to avoid near-duplicate chunks | `fetch_k`, `lambda_mult` |

### Search Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | — | Free-text search query |
| `limit` / `k` | `int` | `DEFAULT_SEARCH_LIMIT` (100) | Max results returned; capped at `MAX_SEARCH_LIMIT` (200) |
| `search_type` | `str` | `"similarity"` | One of `similarity`, `similarity_score_threshold`, `mmr` |
| `score_threshold` | `float` | `None` | Minimum score (0–1). Only used with `similarity_score_threshold`. |
| `fetch_k` | `int` | `None` | Candidate pool for MMR (must be ≥ `k`). Only used with `mmr`. |
| `lambda_mult` | `float` | `0.5` | MMR diversity factor (0=max diversity, 1=max relevance). Only used with `mmr`. |
| `filter_metadata` | `dict` | `None` | MongoDB-style metadata filter (e.g. `{"source_type": {"$eq": "pdf"}}`) |
| `min_content_length` | `int` | `None` | Exclude chunks shorter than N characters |
| `max_content_length` | `int` | `None` | Exclude chunks longer than N characters |

**Server-side validation** rejects:
- `score_threshold` when `search_type != "similarity_score_threshold"` → `400`
- `fetch_k` or `lambda_mult` when `search_type != "mmr"` → `400`
- `min_content_length > max_content_length` → `400`

### Similarity Search

When an agent needs context, it performs a **similarity search** against the silo:

1. **Generate query embedding** from user's message
2. **Find top-k most similar vectors** in the silo (default: 100)
3. **Return corresponding document chunks**
4. **Pass to LLM** as context

**Example — standard similarity**:
```python
store = PGVectorStore(db)
docs = store.search_similar_documents(
    collection_name="silo_1",
    query="password reset procedure",
    embedding_service=silo.embedding_service,
    k=5,
    search_type="similarity",
)
```

**Example — score-threshold search**:
```python
docs = store.search_similar_documents(
    collection_name="silo_1",
    query="password reset procedure",
    embedding_service=silo.embedding_service,
    k=10,
    search_type="similarity_score_threshold",
    score_threshold=0.75,
)
```

**Example — MMR (diverse results)**:
```python
docs = store.search_similar_documents(
    collection_name="silo_1",
    query="password reset procedure",
    embedding_service=silo.embedding_service,
    k=5,
    search_type="mmr",
    fetch_k=20,
    lambda_mult=0.6,
)
```

### Retriever Integration with Agent Execution

Agents use silos for RAG via the `silo_id` foreign key:

```python
class Agent(Base):
    silo_id = Column(Integer, ForeignKey('Silo.silo_id'))
    silo = relationship('Silo')
```

**Agent execution flow with RAG**:

1. **User sends message** to agent
2. **Agent checks for silo** association
3. **If silo exists**, perform similarity search to retrieve context
4. **Augment prompt** with retrieved documents
5. **Send to LLM** with full context

**In code** (`agentTools.py`):
```python
if agent.silo_id:
    retriever = get_vector_store_retriever(agent.silo, k=agent.silo.retrieval_count)
    # Add retriever as a tool to the agent
    tools.append(create_retriever_tool(retriever, name="knowledge_base"))
```

The LLM can then invoke the `knowledge_base` tool to retrieve relevant context on demand.

**Important**: `SiloService.get_silo_retriever` passes `search_type` as a top-level argument to LangChain's `as_retriever()`, not inside `search_kwargs`. This ensures MMR and threshold modes work correctly for production agents (a latent bug where `search_type` was silently ignored has been fixed).

## Silo Playground

The **Silo Playground** (`/apps/:appId/silos/:siloId/playground`) is the primary surface for inspecting and tuning vector-store contents. It is backed by the `POST /internal/apps/{appId}/silos/{siloId}/search` endpoint and exposes all retriever parameters described above.

### Key Features

| Feature | Description |
|---|---|
| **Search controls** | Top-K slider, search type selector, score threshold, MMR controls (fetch_k, lambda_mult); all persisted per silo in `localStorage` |
| **Result inspection** | Score bar, source attribution badge, expand/collapse, copy chunk text/JSON, metadata tree view, neighboring chunks, empty-state coaching |
| **Faceted filters** | Autocomplete-driven filter builder for each silo metadata field, operator picker (`$eq`, `$in`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$exists`), live JSON preview, saved filters |
| **Content-length filter** | Min/max character length range to exclude too-short or too-long chunks |
| **Curator tools** | Multi-select bulk delete, delete-by-filter with dry-run count + silo-name confirmation guard, per-result reindex action |
| **API snippets** | Live cURL/Python/JS/TS code snippets mirroring the current playground request (paste-ready with API key) |
| **Observability** | Per-search latency badge (`X-Server-Time-Ms` header), query history (last 20 per silo), A/B compare mode with shared-chunk highlighting |
| **Test against agent** | Shortcut to open the agent playground with the current query pre-filled |

### Source Attribution

The playground detects the chunk origin from its metadata:

| Source type | Detection | Neighboring chunks |
|---|---|---|
| **Media** | `media_id` present + `content_type == "media_chunk"` | Ordered by `chunk_index` |
| **Repository** | `resource_id` present | Ordered by `page` (fallback to `chunk_index`) |
| **URL / Generic** | Fallback | Not supported |

### Neighboring Chunks

The **"Show neighboring chunks"** action calls `GET /internal/apps/{appId}/silos/{siloId}/documents/neighbors?source_type=media&source_id=42` and returns all chunks from the same source document in reading order — useful for reconstructing context around a matched chunk.

## Performance Considerations

| Aspect | PGVector | Qdrant |
|--------|----------|--------|
| **Setup complexity** | Low (single DB) | Medium (separate service) |
| **Query latency** | Good (10-50ms) | Excellent (<10ms) |
| **Scalability** | Limited by PostgreSQL | Horizontal scaling |
| **Maintenance** | PostgreSQL maintenance | Separate Qdrant maintenance |
| **Cost** | Included with DB | Additional service cost |

**Recommendations**:
- **PGVector**: Small to medium deployments (<1M vectors), single-server setups
- **Qdrant**: Large deployments (>1M vectors), high-throughput use cases

## Best Practices

1. **Chunk size**: Use 500-1000 character chunks with 10-20% overlap
2. **Embedding dimensions**: Higher dimensions (1536) for better accuracy, lower (384) for speed
3. **Retrieval count**: Start with 5, adjust based on context window and accuracy needs
4. **Metadata**: Add rich metadata to documents for better filtering
5. **Index optimization**: Use HNSW indexes for PGVector, configure Qdrant for performance
6. **Monitoring**: Track retrieval latency and relevance scores

## See Also

- [LLM Integration](llm-integration.md) — Embedding services
- [Agent System](agent-system.md) — How agents use RAG
- [Database Schema](../architecture/database.md) — Silo, Repository, Domain models
- [File Processing](../reference/file-processing.md) — Document ingestion
