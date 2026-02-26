# Agent System

> Part of [Mattin AI Documentation](../README.md)

## Overview

The **Agent System** is the core execution engine of Mattin AI, powered by **LangGraph** — a framework for building stateful, multi-turn conversational agents with tool support. Agents are LLM-powered assistants that can:

- Execute multi-turn conversations with memory
- Use tools (functions) to perform actions
- Retrieve context from vector stores (RAG)
- Integrate with MCP servers for extended capabilities
- Stream responses via Server-Sent Events (SSE)

**Key features**:
- **Unified execution interface**: Both internal and public APIs use the same agent execution service
- **Tool support**: Built-in tools (date/time, file access, scraping, PDF, transcription) + custom tools
- **Memory management**: Conversation history persisted via checkpointer with configurable limits
- **File attachments**: Process uploaded files during agent execution
- **Skills system**: Reusable skills (legacy, being phased out)
- **MCP integration**: Connect to Model Context Protocol servers

## Agent Configuration

### Agent Model

```python
class Agent(Base):
    __tablename__ = 'Agent'
    
    agent_id = Column(Integer, primary_key=True)
    app_id = Column(Integer, ForeignKey('App.app_id'))
    name = Column(String(255))
    description = Column(String(1000))
    system_prompt = Column(Text)                   # Agent instructions
    prompt_template = Column(Text)                 # User message template
    type = Column(String(45), default='agent')     # 'agent' or 'tool'
    is_tool = Column(Boolean, default=False)       # Can this agent be used as a tool?
    service_id = Column(Integer, ForeignKey('AIService.service_id'))
    silo_id = Column(Integer, ForeignKey('Silo.silo_id'))  # Linked vector store
    output_parser_id = Column(Integer, ForeignKey('OutputParser.parser_id'))
    temperature = Column(Float, default=0.7)
    request_count = Column(Integer, default=0)
```

**Key configuration fields**:

| Field | Purpose |
|-------|---------|
| `system_prompt` | Instructions and personality for the agent |
| `service_id` | LLM to use (OpenAI, Anthropic, etc.) |
| `silo_id` | Vector store for RAG (optional) |
| `output_parser_id` | Structured output schema (optional) |
| `temperature` | LLM sampling temperature (0.0-1.0) |

**Linked resources**:
- `ai_service`: LLM configuration (OpenAI, Anthropic, etc.)
- `silo`: Default vector store for RAG
- `output_parser`: Structured output schema
- `skill_associations`: AgentSkill (many-to-many, legacy)
- `mcp_associations`: AgentMCP (many-to-many)
- `tool_associations`: AgentTool (self-referential, agents as tools)

### Creating an Agent

Via Internal API:

```bash
POST /internal/agents
Content-Type: application/json

{
  "name": "Customer Support Bot",
  "description": "Answers customer questions about products",
  "system_prompt": "You are a helpful customer support agent. Be polite and concise.",
  "service_id": 1,
  "silo_id": 2,
  "temperature": 0.7
}
```

## Execution Engine

### AgentExecutionService

The `AgentExecutionService` is the unified service for agent execution, used by both internal and public APIs.

**Key methods**:

```python
class AgentExecutionService:
    async def execute_agent_chat_with_file_refs(
        agent_id: int,
        message: str,
        file_references: List = None,
        search_params: Dict = None,
        user_context: Dict = None,
        conversation_id: int = None,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Execute agent chat with persistent file references.
        
        Args:
            agent_id: ID of the agent to execute
            message: User message
            file_references: List of FileReference objects from FileManagementService
            search_params: Optional search parameters for silo-based agents
            user_context: User context (api_key, user_id, etc.)
            conversation_id: Optional conversation ID to continue existing conversation
            
        Returns:
            Dict containing agent response and metadata
        """
```

**What it does**:
1. **Load agent** from database
2. **Validate access** (user has permission to use this agent)
3. **Process file attachments** (extract content from uploaded files)
4. **Perform RAG retrieval** (if agent has a silo and search_params provided)
5. **Augment prompt** with file content and RAG context
6. **Create LangGraph agent** via `create_agent()`
7. **Execute agent** and stream response
8. **Persist conversation** history

### Message Processing

**Message flow**:

```
User Message + File Attachments
    ↓
Extract file content (PDF, images, etc.)
    ↓
Perform RAG search (if silo linked)
    ↓
Construct augmented prompt:
  - System prompt
  - File content
  - RAG context
  - User message
    ↓
Send to LangGraph agent
    ↓
Stream response via SSE
```

### RAG Context

If agent has a linked silo, RAG context is automatically retrieved:

```python
if agent.silo_id and search_params:
    retriever = get_vector_store_retriever(agent.silo)
    docs = retriever.get_relevant_documents(message)
    # Add docs to context
```

## Memory Management

### MemoryManagementService

Manages conversation memory with configurable limits:

```python
class MemoryManagementService:
    # Default limits
    MAX_MESSAGES = 50
    MAX_TOKENS = 16000
    SUMMARIZATION_THRESHOLD = 40
```

**Methods**:

| Method | Purpose |
|--------|---------|
| `trim_conversation(conversation_id, max_tokens, db)` | Trim to fit context window |
| `summarize_conversation(agent_id, conversation_id, db)` | Summarize old messages |
| `get_conversation_token_count(conversation_id, db)` | Count tokens in conversation |

**Memory strategies**:

1. **Sliding window**: Keep only recent N messages
   ```python
   messages = messages[-MemoryManagementService.MAX_MESSAGES:]
   ```

2. **Token-based trimming**: Trim to fit max tokens
   ```python
   trimmed = await MemoryManagementService.trim_conversation(
       conversation_id, 
       max_tokens=4000, 
       db
   )
   ```

3. **Summarization**: Use LLM to summarize old messages when threshold reached
   ```python
   if len(messages) > MemoryManagementService.SUMMARIZATION_THRESHOLD:
       summarized = await MemoryManagementService.summarize_conversation(
           agent_id, conversation_id, db
       )
   ```

## Conversation Persistence

### ConversationService

Manages conversation history storage and retrieval:

```python
class ConversationService:
    def create_conversation(agent_id: int, user_id: int, title: str, db: Session):
        """Create a new conversation session"""
        
    def get_conversation(conversation_id: int, db: Session):
        """Retrieve conversation by ID"""
        
    def get_user_conversations(user_id: int, db: Session):
        """Get all conversations for a user"""
        
    def add_message(conversation_id: int, role: str, content: str, db: Session):
        """Add a message to conversation history"""
```

**Conversation model**:

```python
class Conversation(Base):
    __tablename__ = 'Conversation'
    
    conversation_id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('Agent.agent_id'))
    user_id = Column(Integer, ForeignKey('User.user_id'))
    title = Column(String(255))
    messages = Column(JSON)  # Message history (serialized)
    create_date = Column(DateTime)
    last_message_date = Column(DateTime)
```

**Session-based conversations**: Each conversation has a unique ID (session ID) that maps to a LangGraph checkpointer thread ID.

## Skills

**Note**: The skills system is legacy and being phased out in favor of MCP tools.

Skills are reusable code modules that agents can load and execute:

```python
class Skill(Base):
    __tablename__ = 'Skill'
    skill_id = Column(Integer, primary_key=True)
    app_id = Column(Integer, ForeignKey('App.app_id'))
    name = Column(String(255))
    description = Column(Text)
    code = Column(Text)  # Python code
```

**Skill loader tool**:

```python
from tools.skill_tools import create_skill_loader_tool

skill_loader = create_skill_loader_tool(agent, db)
tools.append(skill_loader)
```

The agent can dynamically load and execute skills at runtime.

**Skills system prompt section**:

```python
from tools.skill_tools import generate_skills_system_prompt_section

skills_section = generate_skills_system_prompt_section(agent)
system_prompt += "\n\n" + skills_section
```

## File Attachments

### File Upload

Files can be uploaded via:

1. **Internal API**: `/internal/repositories/{repo_id}/files`
2. **Public API**: `/public/v1/files`

**Supported file types**:
- **PDF**: Text extraction or OCR
- **Images** (PNG, JPEG): OCR via vision models
- **Audio** (MP3, WAV): Transcription via Whisper
- **Text** (TXT, MD): Direct read

### Content Extraction

File content is extracted during agent execution:

```python
# Extract text from PDF
text = extract_text_from_pdf(file_path)

# OCR from image
text = extract_text_from_image(image_path, vision_llm)

# Transcribe audio
text = transcribe_audio(audio_path)
```

### Attachment Processing During Execution

**Flow**:

1. **User uploads file** → File stored and FileReference created
2. **User sends message** with file_references
3. **AgentExecutionService** extracts content from files
4. **Augment prompt** with file content:
   ```
   System: You are a helpful assistant.
   
   Attached Files:
   - document.pdf: [extracted text]
   - image.png: [OCR text]
   
   User: Summarize the document
   ```
5. **Agent processes** with full context

## Agent Tools

Built-in tools automatically added to all agents:

### dateTimeTools

```python
from tools.ai.dateTimeTools import get_current_date

@tool
def get_current_date() -> str:
    """Get the current date and time in ISO 8601 format."""
    return datetime.now().isoformat()
```

### fileTools

```python
from tools.ai.fileTools import fetch_file_in_base64

@tool
def fetch_file_in_base64(url: str) -> str:
    """Download a file from URL and return as base64-encoded string."""
    response = requests.get(url)
    return base64.b64encode(response.content).decode()
```

### scrapTools

Web scraping utilities:

```python
from tools.scrapTools import scrape_url

@tool
def scrape_url(url: str) -> str:
    """Scrape text content from a URL."""
    # Implementation
    return extracted_text
```

### PDFTools

PDF processing utilities:

```python
from tools.PDFTools import (
    extract_text_from_pdf,
    convert_pdf_to_images,
    check_pdf_has_text
)
```

### transcriptionTools

Audio transcription via OpenAI Whisper:

```python
from tools.transcriptionTools import transcribe_audio

@tool
def transcribe_audio(audio_path: str) -> str:
    """Transcribe audio file to text using Whisper."""
    # Implementation
    return transcription
```

### ocrAgentTools

OCR utilities for vision models:

```python
from tools.ocrAgentTools import (
    extract_text_from_image,
    format_data_with_text_llm,
    format_data_from_vision,
    get_data_from_extracted_text
)
```

## Execution Flow

### Internal API Execution

```
POST /internal/agents/{agent_id}/chat
    ↓
AgentExecutionService.execute_agent_chat_with_file_refs()
    ↓
Process file attachments
    ↓
Perform RAG retrieval (if silo linked)
    ↓
create_agent(agent, session_id, user_context)
    ↓
executor.astream_events({"messages": [...]})
    ↓
Stream SSE events to client
    ↓
Persist conversation history
```

### Public API Execution

```
POST /public/v1/chat
    ↓
API Key Authentication
    ↓
AgentExecutionService.execute_agent_chat_with_file_refs()
    ↓
[Same as internal API]
```

### Streaming Response

Responses are streamed via **Server-Sent Events (SSE)**:

```
data: {"type": "token", "content": "Hello"}
data: {"type": "token", "content": " "}
data: {"type": "token", "content": "there"}
data: {"type": "tool_call", "tool": "knowledge_base", "args": {...}}
data: {"type": "tool_result", "result": "..."}
data: {"type": "done"}
```

**Frontend consumption**:

```javascript
const eventSource = new EventSource('/internal/agents/1/chat');
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'token') {
    appendToChat(data.content);
  }
};
```

## Best Practices

1. **System prompts**: Be specific about agent role, behavior, and constraints
2. **Tool selection**: Add only relevant tools (too many tools confuse the agent)
3. **RAG retrieval**: Use RAG for factual knowledge, not for real-time data
4. **Temperature**: Lower (0-0.3) for factual tasks, higher (0.7-1.0) for creative tasks
5. **Memory management**: Configure limits based on LLM context window
6. **File size limits**: Set reasonable limits for file uploads (see [File Processing](../reference/file-processing.md))
7. **Error messages**: Return clear error messages from tools for agent recovery
8. **LangSmith tracing**: Enable for debugging agent behavior and tool usage

## See Also

- [LLM Integration](llm-integration.md) — AI service configuration
- [RAG & Vector Stores](rag-vector-stores.md) — Silo and retrieval
- [MCP Integration](mcp-integration.md) — MCP servers and tools
- [Backend Architecture](../architecture/backend.md) — Agent execution service
- [Database Schema](../architecture/database.md) — Agent model
- [File Processing](../reference/file-processing.md) — File handling details
