# LLM Integration

> Part of [Mattin AI Documentation](../README.md)

## Overview

Mattin AI provides **multi-provider LLM support** via **LangChain**, enabling seamless integration with various language model providers. Each app can configure multiple AI services with different LLM providers and models, allowing agents to use the most appropriate model for their task.

## Supported Providers

| Provider | Models | Use Cases |
|----------|--------|-----------|
| **OpenAI** | GPT-4, GPT-4 Turbo, GPT-3.5 Turbo | General-purpose chat, code generation, structured output |
| **Anthropic** | Claude 3 Opus, Sonnet, Haiku, Claude 2 | Long-context reasoning, safety-focused tasks |
| **MistralAI** | Mistral Large, Medium, Small, Pixtral (vision) | European data sovereignty, multilingual support |
| **Azure OpenAI** | GPT-4, GPT-3.5 (Azure-hosted) | Enterprise deployments, compliance requirements |
| **Google** | Gemini Pro, Gemini Flash | Multimodal tasks, Google ecosystem integration |
| **Ollama** | Llama 3, Mistral, Phi, custom models | Local/on-premise deployment, privacy-sensitive use cases |

### Provider Enum

```python
class ProviderEnum(str, Enum):
    OpenAI = "openai"
    Anthropic = "anthropic"
    MistralAI = "mistralai"
    Azure = "azure"
    Google = "google"
    Custom = "custom"  # Ollama or custom OpenAI-compatible endpoints
```

## Configuration

LLM configurations are stored in the **AIService** model (see [Database Schema](../architecture/database.md#aiservice)).

### Creating an AI Service

Via Internal API:

```bash
POST /internal/ai_services
Content-Type: application/json

{
  "name": "GPT-4 Service",
  "provider": "openai",
  "model": "gpt-4-turbo",
  "api_key": "sk-...",
  "temperature": 0.7,
  "max_tokens": 4096,
  "base_url": null
}
```

### Configuration Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | String | Service display name |
| `provider` | Enum | Provider type (openai, anthropic, mistralai, azure, google, custom) |
| `model` | String | Model identifier (e.g., `gpt-4-turbo`, `claude-3-opus-20240229`) |
| `api_key` | String | Encrypted API key (required for cloud providers) |
| `base_url` | String | Custom API endpoint (optional, for Ollama or custom deployments) |
| `temperature` | Float | Sampling temperature (0.0 - 1.0) |
| `max_tokens` | Integer | Maximum output tokens |

### Per-Agent Configuration

Agents reference an AI service via the `service_id` foreign key:

```python
class Agent(Base):
    service_id = Column(Integer, ForeignKey('AIService.service_id'))
    ai_service = relationship('AIService')
```

This allows different agents in the same app to use different models (e.g., one agent uses GPT-4, another uses Claude).

## LLM Instantiation

The `aiServiceTools.py` module provides utilities to instantiate LLM clients from AI service configurations.

### get_llm Function

```python
from tools.aiServiceTools import get_llm

llm = get_llm(agent, is_vision=False)
# Returns a LangChain ChatModel instance (ChatOpenAI, ChatAnthropic, etc.)
```

### create_llm_from_service Function

```python
from tools.aiServiceTools import create_llm_from_service

llm = create_llm_from_service(ai_service, temperature=0.7, is_vision=False)
```

### Provider-Specific Builders

Each provider has a dedicated builder function:

| Provider | Builder Function | LangChain Class |
|----------|------------------|-----------------|
| OpenAI | `_build_openai_llm()` | `ChatOpenAI` |
| Anthropic | `_build_anthropic_llm()` | `ChatAnthropic` |
| MistralAI | `_build_mistral_llm()` | `ChatMistralAI` |
| Azure OpenAI | `_build_azure_llm()` | `AzureAIChatCompletionsModel` |
| Google | `_build_google_llm()` | `ChatGoogleGenerativeAI` |
| Custom (Ollama) | `_build_custom_llm()` | `ChatOllama` or `ChatOpenAI` |

**Example OpenAI instantiation**:

```python
def _build_openai_llm(ai_service, temperature):
    return ChatOpenAI(
        model=ai_service.model,
        api_key=ai_service.api_key,
        temperature=temperature,
        max_tokens=ai_service.max_tokens,
        base_url=ai_service.base_url  # Optional custom endpoint
    )
```

## Structured Output

Mattin AI supports **structured LLM output** via Pydantic models and JSON schemas.

### Output Parsers

Agents can specify an **OutputParser** to enforce structured responses:

```python
class Agent(Base):
    output_parser_id = Column(Integer, ForeignKey('OutputParser.parser_id'))
    output_parser = relationship('OutputParser')
```

### Parser Types

| Parser | Use Case |
|--------|----------|
| **StrOutputParser** | Plain text output (default) |
| **JsonOutputParser** | JSON output with Pydantic validation |

**Example JSON parser**:

```python
from langchain_core.output_parsers import JsonOutputParser

pydantic_model = get_parser_model_by_id(agent.output_parser_id)
parser = JsonOutputParser(pydantic_object=pydantic_model)
```

### Defining Output Schemas

Output parsers are stored in the **OutputParser** model:

```json
{
  "name": "Product Info",
  "schema": {
    "type": "object",
    "properties": {
      "name": {"type": "string"},
      "price": {"type": "number"},
      "category": {"type": "string"}
    },
    "required": ["name", "price"]
  }
}
```

This schema is converted to a Pydantic model at runtime for validation.

## Vision Models

Some providers support **multimodal (vision) models** that can process images:

- **OpenAI**: `gpt-4-vision-preview`, `gpt-4-turbo` (vision-enabled)
- **MistralAI**: `pixtral-12b-2409` (vision model)
- **Google**: Gemini models (vision-enabled)

### Vision Service Configuration

Agents can have a separate vision service:

```python
class Agent(Base):
    vision_service_id = Column(Integer, ForeignKey('AIService.service_id'))
    vision_service_rel = relationship('AIService', foreign_keys=[vision_service_id])
```

**Usage**:

```python
llm = get_llm(agent, is_vision=True)
# Returns vision-capable LLM
```

Vision models are used for OCR, image analysis, and multimodal conversations.

## LangSmith Tracing

**LangSmith** provides observability for LLM calls, useful for debugging and monitoring.

### Enabling LangSmith

Set the LangSmith API key in the **App** model:

```python
class App(Base):
    langsmith_api_key = Column(String(255))
```

When set, all agent executions in that app will be traced in LangSmith.

### Environment Variables

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<your-langsmith-api-key>
```

### What Gets Traced

- **LLM calls**: Prompts, responses, token counts, latency
- **Tool invocations**: Tool names, inputs, outputs
- **Agent steps**: Full agent reasoning trace
- **Vector store retrievals**: Retrieved documents and scores

### Viewing Traces

Access LangSmith dashboard: https://smith.langchain.com/

Filter traces by app, agent, or time range.

## Embeddings

Embeddings are handled separately via the **EmbeddingService** model (see [RAG & Vector Stores](rag-vector-stores.md)).

Supported embedding providers:
- **OpenAI**: `text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`
- **HuggingFace**: Custom embedding models via `sentence-transformers`
- **Ollama**: Local embedding models

## Temperature and Sampling

**Temperature** controls randomness in LLM output:

- **0.0**: Deterministic (always picks the most likely token)
- **0.3-0.5**: Focused and consistent
- **0.7**: Balanced (default for most agents)
- **1.0+**: Creative and diverse

Temperature can be set:
1. **Per AI Service** (default for all agents using that service)
2. **Per Agent** (overrides service default)

```python
DEFAULT_AGENT_TEMPERATURE = 0.7
```

## Rate Limiting

LLM usage can be rate-limited at the **App** level:

```python
class App(Base):
    agent_rate_limit = Column(Integer, default=0)  # Requests per minute (0 = unlimited)
```

Rate limits are enforced by the `rate_limit` control (see [Backend Architecture](../architecture/backend.md#controls)).

## Error Handling

Common LLM errors and handling:

| Error | Cause | Solution |
|-------|-------|----------|
| **401 Unauthorized** | Invalid API key | Verify API key in AIService config |
| **429 Too Many Requests** | Rate limit exceeded | Implement backoff, upgrade plan |
| **400 Bad Request** | Invalid parameters (e.g., token limit) | Adjust max_tokens or model |
| **500 Internal Server Error** | Provider outage | Retry with exponential backoff |

## Provider-Specific Notes

### OpenAI

- **API Key Format**: `sk-...`
- **Base URL**: `https://api.openai.com/v1` (default)
- **Token Limits**: GPT-4 Turbo (128K), GPT-3.5 Turbo (16K)

### Anthropic

- **API Key Format**: `sk-ant-...`
- **Context Window**: Claude 3 Opus (200K tokens)
- **Best for**: Long documents, safety-critical tasks

### MistralAI

- **API Key Format**: Starts with `...`
- **Base URL**: `https://api.mistral.ai`
- **Vision Model**: `pixtral-12b-2409` supports image input

### Azure OpenAI

- **Requires**: Azure OpenAI resource, deployment name
- **Base URL**: `https://<resource-name>.openai.azure.com/`
- **API Key**: Azure API key (not OpenAI key)

### Google (Gemini)

- **API Key Format**: Google Cloud API key
- **Base URL**: `https://generativelanguage.googleapis.com`
- **Multimodal**: Gemini models natively support images

### Ollama (Local Models)

- **Base URL**: `http://localhost:11434` (default)
- **No API Key Required**: For local models
- **Models**: Download via `ollama pull llama3`

## Best Practices

1. **Use appropriate models for tasks**: GPT-4 for complex reasoning, GPT-3.5 for simple chat, Claude for long context
2. **Set temperature correctly**: Low (0-0.3) for factual tasks, medium (0.7) for balanced, high (1.0+) for creative tasks
3. **Limit max_tokens**: Prevent runaway costs by setting reasonable token limits
4. **Enable LangSmith**: For production deployments, enable tracing to debug issues
5. **Rotate API keys**: Periodically rotate API keys for security
6. **Use vision models only when needed**: Vision models are more expensive than text-only models

## See Also

- [Agent System](agent-system.md) — How agents use LLMs
- [RAG & Vector Stores](rag-vector-stores.md) — Embedding models for RAG
- [Backend Architecture](../architecture/backend.md) — AI service configuration endpoints
- [Database Schema](../architecture/database.md#aiservice) — AIService model details
