# OpenRouter Integration Design

> **Status**: Design document — not yet implemented.
> **Date**: 2026-06-02

## 1. Overview

[OpenRouter](https://openrouter.ai) is a unified API gateway that provides access to 300+ LLMs from dozens of providers through a single OpenAI-compatible endpoint. This document designs the full integration of OpenRouter as a first-class provider in MattinAI.

### Value Proposition

A single OpenRouter API key unlocks every major model family — OpenAI, Anthropic, Google, Meta, DeepSeek, Mistral, and many more. Users no longer need to create separate `AIService` records for each provider. One `AIService` with provider `OpenRouter` and the model identifier stored in `description` (e.g. `openai/gpt-4o`, `anthropic/claude-sonnet-4-20250514`) is sufficient to access any model OpenRouter supports.

### Key Design Principle

OpenRouter is treated as its **own provider** (`ProviderEnum.OpenRouter`), not piggybacked on the existing `Custom` or `OpenAI` providers. This gives it dedicated UI treatment, proper model listing, and the ability to set the required `HTTP-Referer` / `X-Title` attribution headers that the `Custom`/Ollama path doesn't support.

---

## 2. Architecture: How It Fits

```
┌──────────────────────────────────────────────────────────────────┐
│                        MattinAI Backend                           │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              tools/aiServiceTools.py                        │ │
│  │  create_llm_from_service(ai_service, ...)                   │ │
│  │    ┌──────────────────────────────────────────────────┐    │ │
│  │    │ ProviderEnum.OpenRouter                           │    │ │
│  │    │   → _build_openrouter_llm(ai_service, temp)       │    │ │
│  │    │     → ChatOpenAI(                                 │    │ │
│  │    │          model="openai/gpt-4o",                   │    │ │
│  │    │          base_url="https://openrouter.ai/api/v1", │    │ │
│  │    │          api_key="sk-or-v1-...",                  │    │ │
│  │    │          default_headers={                         │    │ │
│  │    │            "HTTP-Referer": "<site_url>",           │    │ │
│  │    │            "X-Title": "<site_name>"               │    │ │
│  │    │          }                                         │    │ │
│  │    │        )                                           │    │ │
│  │    └──────────────────────────────────────────────────┘    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │           tools/ai/provider_model_clients.py                │ │
│  │  list_openrouter_models(req) → List[ProviderModelInfo]      │ │
│  │    → httpx GET https://openrouter.ai/api/v1/models          │ │
│  │    → Parse response, extract: id, name, context_length,     │ │
│  │      architecture, pricing, supported_parameters            │ │
│  │    → Map to ProviderModelInfo + enrich via model_catalog    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │           tools/ai/model_catalog.py                         │ │
│  │  PROVIDER_OPENROUTER = "OpenRouter"                         │ │
│  │  heuristic_capabilities_from_id("OpenRouter",               │ │
│  │      "openai/gpt-4o") → chat=True, vision=True, ...         │ │
│  │  Handles "provider/model" format by stripping prefix        │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### Runtime Flow

```
User sends a chat message
  → AgentExecutionService.execute_agent_chat()
    → get_llm(agent)
      → create_llm_from_service(ai_service, ...)
        → ProviderEnum.OpenRouter.value
          → _build_openrouter_llm(ai_service, temperature)
            → ChatOpenAI(
                model="openai/gpt-4o",            # from ai_service.description
                temperature=0.7,
                api_key="sk-or-v1-...",            # from ai_service.api_key
                base_url="https://openrouter.ai/api/v1",
                default_headers={                   # attribution headers
                  "HTTP-Referer": site_url,
                  "X-Title": site_name
                }
              )
            → LangChain agent chain uses this LLM for all invocations
```

Key insight: because OpenRouter speaks the **OpenAI Chat Completions protocol**, we reuse `langchain_openai.ChatOpenAI` — the same class used for OpenAI and Custom providers. The only differences are the `base_url` and the `default_headers`.

---

## 3. Detailed Changes

### 3.1 Backend — Model Layer

#### `backend/models/ai_service.py`

Add `OpenRouter` to `ProviderEnum`:

```python
class ProviderEnum(enum.Enum):
    OpenAI = "OpenAI"
    Anthropic = "Anthropic"
    MistralAI = "MistralAI"
    Azure = "Azure"
    Custom = "Custom"
    Google = "Google"
    GoogleCloud = "GoogleCloud"
    OpenRouter = "OpenRouter"       # ← NEW
```

No schema changes to `AIService` are needed. Existing fields map naturally:

| AIService field | OpenRouter usage |
|---|---|
| `provider` | `"OpenRouter"` |
| `description` | Full model ID, e.g. `"openai/gpt-4o"`, `"anthropic/claude-sonnet-4-20250514"` |
| `api_key` | OpenRouter API key (`sk-or-v1-...`) |
| `endpoint` | **Optional** self-hosted OpenRouter-compatible proxy URL. Defaults to `https://openrouter.ai/api/v1`. |
| `supports_video` | Existing boolean, unchanged |

---

### 3.2 Backend — LLM Builder

#### `backend/tools/aiServiceTools.py`

New builder function and dispatch entry:

```python
# At module level — configurable site attribution
_OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def _build_openrouter_llm(ai_service, temperature):
    """Build a ChatOpenAI instance pointed at OpenRouter's API.

    OpenRouter speaks the OpenAI chat completions protocol, so we reuse
    ChatOpenAI with a different base_url. The description field stores
    the full model identifier (e.g. 'openai/gpt-4o').

    Attribution headers (HTTP-Referer, X-Title) identify MattinAI on
    the OpenRouter platform. They are sent on every request.
    """
    base_url = ai_service.endpoint or _OPENROUTER_DEFAULT_BASE_URL
    # Ensure base_url doesn't double-suffix /chat/completions
    base_url = base_url.rstrip("/")

    default_headers = {
        "HTTP-Referer": "https://github.com/lksnext-ai-lab/ai-core-tools",
        "X-Title": "MattinAI",
    }

    return ChatOpenAI(
        model=ai_service.description,
        temperature=temperature,
        api_key=ai_service.api_key,
        base_url=base_url,
        default_headers=default_headers,
    )
```

Add to the dispatch dict in `create_llm_from_service`:

```python
provider_builders = {
    # ... existing entries ...
    ProviderEnum.OpenRouter.value: lambda: _build_openrouter_llm(ai_service, temperature),
}
```

**Design note on `HTTP-Referer` and `X-Title`**: These are optional but recommended by OpenRouter for app discovery. We hardcode a default but could later make them configurable via environment variables (`OPENROUTER_SITE_URL`, `OPENROUTER_SITE_NAME`) or per-app settings. For the initial implementation, hardcoded defaults are sufficient.

---

### 3.3 Backend — Model Listing Adapter

#### `backend/tools/ai/provider_model_clients.py`

OpenRouter exposes `GET https://openrouter.ai/api/v1/models` which returns:

```json
{
  "data": [
    {
      "id": "openai/gpt-4o",
      "name": "OpenAI: GPT-4o",
      "created": 1715367049,
      "description": "GPT-4o is a multimodal model...",
      "context_length": 128000,
      "architecture": {
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "tokenizer": "openai",
        "instruct_type": null
      },
      "pricing": {
        "prompt": "0.0000025",
        "completion": "0.000010",
        ...
      },
      "top_provider": {
        "context_length": 128000,
        "max_completion_tokens": 16000,
        "is_moderated": true
      },
      "supported_parameters": ["tools", "max_tokens", "temperature", ...],
      "default_parameters": null,
      "expiration_date": null
    }
  ]
}
```

The adapter function:

```python
import httpx
from schemas.provider_models_schemas import (
    ListProviderModelsRequest,
    ProviderCapabilities,
    ProviderModelInfo,
)
from tools.ai.model_catalog import PROVIDER_OPENROUTER, enrich

_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_OPENROUTER_DEFAULT_TIMEOUT = 15.0


def list_openrouter_models(
    req: ListProviderModelsRequest,
) -> List[ProviderModelInfo]:
    """List models available through OpenRouter.

    Uses the public /api/v1/models endpoint. The API key is optional for
    listing — the models endpoint is public. When provided, it increases
    rate limits.
    """
    headers: dict[str, str] = {}
    if req.api_key:
        headers["Authorization"] = f"Bearer {req.api_key}"

    try:
        response = httpx.get(
            _OPENROUTER_MODELS_URL,
            headers=headers,
            timeout=_OPENROUTER_DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException:
        raise ProviderListingError(
            "timeout", "OpenRouter models listing timed out."
        )
    except httpx.HTTPStatusError as exc:
        code = _classify_by_status(exc.response.status_code)
        raise ProviderListingError(
            code, f"OpenRouter listing failed: {exc.response.status_code}"
        )
    except httpx.RequestError as exc:
        raise ProviderListingError("network", str(exc))

    models: List[ProviderModelInfo] = []
    for raw in payload.get("data", []) or []:
        model_id = raw.get("id")
        if not model_id:
            continue

        name = raw.get("name") or model_id
        created = raw.get("created")
        context_window = raw.get("context_length")
        description = raw.get("description")

        # Build capabilities from architecture + supported_parameters
        arch = raw.get("architecture") or {}
        input_modalities = arch.get("input_modalities", [])
        supported_params = set(raw.get("supported_parameters", []) or [])

        caps = ProviderCapabilities(
            chat=("text" in arch.get("output_modalities", ["text"])),
            vision=("image" in input_modalities),
            function_calling=("tools" in supported_params),
            tool_use=("tools" in supported_params),
            reasoning=("reasoning" in supported_params),
            json_mode=("structured_outputs" in supported_params
                       or "response_format" in supported_params),
        )

        base = ProviderModelInfo(
            id=model_id,
            display_name=name,
            context_window=context_window,
            capabilities=caps,
            created_at=created,
            source="api",
        )
        # The heuristic enriches what the API didn't determine
        models.append(enrich(PROVIDER_OPENROUTER, model_id, base=base))

    return models
```

**Design decision**: Use `httpx` directly instead of `openai.OpenAI` for model listing because OpenRouter's `/api/v1/models` response schema differs from OpenAI's (extra fields like `pricing`, `architecture`, `supported_parameters`). The `httpx` approach gives us full control over parsing.

**Authentication for listing**: The models endpoint is public (no API key required), but passing a key increases rate limits. The adapter sends the key as a Bearer token if provided — same pattern as all other providers.

---

### 3.4 Backend — Model Catalog (Heuristic Patterns)

#### `backend/tools/ai/model_catalog.py`

OpenRouter model IDs are in `provider/model` format (e.g. `openai/gpt-4o`, `anthropic/claude-sonnet-4-20250514`, `google/gemini-2.5-pro`). The heuristic must:

1. **Strip the provider prefix** before matching existing patterns, so `openai/gpt-4o` matches the `^gpt-4o` vision pattern.
2. **Handle OpenRouter-specific IDs** that don't match existing patterns (Meta's Llama, DeepSeek, Qwen, etc.).

```python
PROVIDER_OPENROUTER = "OpenRouter"

# Patterns for models that don't have a dedicated provider in MattinAI
# but are available through OpenRouter.
_OPENROUTER_EXTRA_VISION = (
    re.compile(r"^meta-llama/llama-4"),
    re.compile(r"^meta-llama/llama-3\.2.*vision"),
    re.compile(r"^deepseek/deepseek-vl"),
    re.compile(r"^qwen/qwen.*vl"),
    re.compile(r"^qwen/qvq"),
    re.compile(r"^mistralai/pixtral"),
)

_OPENROUTER_EXTRA_REASONING = (
    re.compile(r"^deepseek/deepseek-r"),
    re.compile(r"^qwen/qwq"),
    re.compile(r"^qwen/qwen.*thinking"),
)


def heuristic_capabilities_from_id(
    provider: str, model_id: str
) -> ProviderCapabilities:
    """Best-effort capability inference from the model id alone.

    For OpenRouter, the id includes a provider prefix. We strip it
    before matching patterns for OpenRouter-hosted models that map to
    a known provider (openai/gpt-4o → gpt-4o). Additional patterns
    cover OpenRouter-exclusive models.
    """
    lid = (model_id or "").lower()

    # Strip OpenRouter provider prefix for pattern matching
    if provider == PROVIDER_OPENROUTER and "/" in lid:
        _, unprefixed = lid.split("/", 1)
        # Try matching unprefixed first (covers openai/gpt-4o → ^gpt-4o)
        caps = _match_heuristic(unprefixed)
        # If the unprefixed match found nothing, try the full id
        if not any(getattr(caps, f) for f in ProviderCapabilities.model_fields):
            caps = _match_heuristic(lid)
            # Fall back to OpenRouter-specific patterns
            if not any(getattr(caps, f)
                       for f in ProviderCapabilities.model_fields):
                caps = _match_openrouter_extras(lid)
        return caps

    # Non-OpenRouter providers use existing logic
    return _match_heuristic(lid)
```

Refactor: extract the existing pattern matching into a private `_match_heuristic(lid)` function so it can be called with both prefixed and unprefixed IDs.

**Capability inference coverage**:

| OpenRouter model ID | unprefixed | vision | reasoning | tool_use | source |
|---|---|---|---|---|---|
| `openai/gpt-4o` | `gpt-4o` | ✅ `^gpt-4o` | — | ✅ (default) | existing pattern |
| `anthropic/claude-sonnet-4-20250514` | `claude-sonnet-4-20250514` | ✅ `^claude-sonnet-[3-9]` | — | ✅ (default) | existing pattern |
| `google/gemini-2.5-pro` | `gemini-2.5-pro` | ✅ `^gemini-[2-9]` | — | ✅ (default) | existing pattern |
| `meta-llama/llama-4-maverick` | `llama-4-maverick` | ✅ extra pattern | — | ✅ (default) | new pattern |
| `deepseek/deepseek-r1` | `deepseek-r1` | — | ✅ extra pattern | ✅ (default) | new pattern |
| `qwen/qwq-32b` | `qwq-32b` | — | ✅ extra pattern | ✅ (default) | new pattern |

---

### 3.5 Backend — Provider Models Service

#### `backend/services/provider_models_service.py`

Add OpenRouter to the dispatch table:

```python
_DISPATCH: Dict[str, str] = {
    # ... existing entries ...
    PROVIDER_OPENROUTER: "list_openrouter_models",
}
```

No other changes needed — `ProviderModelsService.list_models` already handles validation, junk filtering, purpose filtering, and sorting generically.

**Important**: OpenRouter supports chat models only — no embeddings. The `_apply_purpose_filter` will correctly return an empty list for `purpose="embedding"`. We should also add OpenRouter to `MANUAL_INPUT_PROVIDERS` only for the embedding case, or handle it in `_DISPATCH`. Since the dispatch function will return models and they'll all get filtered out by `is_embedding_model`, the result is an empty list — which is correct behavior.

---

### 3.6 Frontend — Provider UI Descriptor

#### `frontend/src/components/services/wizard/providers.ts`

Add to `ALL_PROVIDERS`:

```typescript
{
  value: 'OpenRouter',
  label: 'OpenRouter',
  description: '300+ models from OpenAI, Anthropic, Google, Meta, DeepSeek & more — one API.',
  Icon: Globe,  // lucide-react Globe icon
  apiKey: 'required',
  needsBaseUrl: false,
  supportsModelListing: true,
  apiKeyPlaceholder: 'sk-or-v1-...',
  apiKeyHelp: 'Create a key at openrouter.ai/keys',
  apiKeyDocUrl: 'https://openrouter.ai/keys',
  supportedFor: ['ai'],  // OpenRouter is chat-only, no embeddings
},
```

`supportedFor: ['ai']` — OpenRouter does not offer embedding models through its unified API. Embedding services should use native providers (OpenAI, MistralAI, etc.).

#### `frontend/src/components/ui/providerBadges.ts`

Add badge color:

```typescript
'openrouter': 'bg-indigo-100 text-indigo-800',
```

---

### 3.7 Frontend — Type Definitions

#### `frontend/src/types/services.ts`

Add `'OpenRouter'` to the provider type union used in `ServiceFormData` and related types. This is likely a `string` type already, but verify that the wizard's provider selection step shows the new option correctly.

---

### 3.8 Backend — OpenAI-Compatible Public API

#### `backend/routers/public/v1/openai.py`

**No changes needed.** The public `/v1/{app_id}/chat/completions` endpoint already delegates to `AgentExecutionService`, which goes through `get_llm(agent)` → `create_llm_from_service(ai_service)`. If the agent's AI service is configured with `provider="OpenRouter"`, the new builder function handles it transparently.

---

### 3.9 Testing

#### Unit tests for the listing adapter

`tests/unit/services/test_provider_models_service.py` — add test cases:

```python
class TestListOpenRouterModels:
    def test_empty_api_key(self): ...
    def test_returns_models_with_correct_shape(self): ...
    def test_maps_capabilities_from_architecture(self): ...
    def test_handles_timeout(self): ...
    def test_handles_http_error(self): ...
```

#### Unit tests for heuristics

`tests/unit/services/test_model_catalog.py` — add test cases:

```python
class TestOpenRouterHeuristics:
    def test_openai_gpt4o_is_vision(self): ...
    def test_anthropic_claude_sonnet4_is_vision(self): ...
    def test_deepseek_r1_is_reasoning(self): ...
    def test_meta_llama4_is_vision(self): ...
    def test_qwen_qwq_is_reasoning(self): ...
    def test_unknown_model_defaults_to_chat(self): ...
```

#### Unit tests for the LLM builder

`tests/unit/tools/test_ai_service_tools.py` — add:

```python
class TestBuildOpenRouterLLM:
    def test_uses_default_base_url_when_no_endpoint(self): ...
    def test_uses_custom_endpoint_when_present(self): ...
    def test_includes_attribution_headers(self): ...
    def test_model_name_from_description(self): ...
```

---

## 4. What We DON'T Need to Change

These components work without modification:

| Component | Reason |
|---|---|
| `backend/models/ai_service.py` (AIService table) | `description` → model ID, `api_key` → API key, `endpoint` → optional custom URL |
| `backend/routers/internal/ai_services.py` | Generic provider-agnostic CRUD |
| `backend/services/ai_service_service.py` | Reads `ProviderEnum` dynamically |
| `backend/services/agent_execution_service.py` | Goes through `get_llm()` which delegates to `create_llm_from_service` |
| `backend/tools/agentTools.py` | Uses `get_llm()` |
| `backend/routers/public/v1/openai.py` | Delegates to `AgentExecutionService` |
| `backend/tools/embeddingTools.py` | OpenRouter is chat-only, no embedding support needed |
| `backend/models/embedding_service.py` | No `EmbeddingProvider` entry needed |
| `frontend/src/components/services/wizard/ServiceWizard.tsx` | Generic, uses `getProviderDescriptor` |
| `frontend/src/components/services/wizard/steps/CredentialsStep.tsx` | Handles API key / base URL generically |
| `frontend/src/components/services/wizard/steps/ModelSelectionStep.tsx` | Uses `useProviderModels` hook generically |

---

## 5. Open Questions & Future Considerations

### 5.1 Per-App Attribution Headers

Currently `HTTP-Referer` and `X-Title` are hardcoded. In the future, we could allow per-app customization via `App` model fields or environment variables. This would let white-label deployments set their own attribution.

### 5.2 Pricing Display

OpenRouter returns `pricing` in the models response. We could store per-model pricing in the model catalog and display it in the model selection wizard. This is a nice-to-have for the initial release.

### 5.3 Provider Preferences / Routing

OpenRouter supports `provider` preferences (e.g., prefer Azure over OpenAI for a given model). We could expose this as an advanced agent setting. Out of scope for v1.

### 5.4 Streaming

OpenRouter supports SSE streaming identically to OpenAI. Since we use `ChatOpenAI` under the hood, streaming should work automatically. Needs explicit testing.

### 5.5 Tool Calling

OpenRouter passes `tools` and `tool_choice` through to the underlying provider. Models that support tool calling are tagged with `"tools"` in `supported_parameters`. The LangChain agent tool-calling flow should work transparently.

---

## 6. Implementation Sequence

| Step | File(s) | Effort | Dependencies |
|---|---|---|---|
| 1. Add `ProviderEnum.OpenRouter` | `backend/models/ai_service.py` | Trivial | None |
| 2. Add `PROVIDER_OPENROUTER` + heuristic patterns | `backend/tools/ai/model_catalog.py` | Medium | Step 1 |
| 3. Add `_build_openrouter_llm` | `backend/tools/aiServiceTools.py` | Small | Step 1 |
| 4. Add `list_openrouter_models` | `backend/tools/ai/provider_model_clients.py` | Medium | Steps 1, 2 |
| 5. Register in dispatch table | `backend/services/provider_models_service.py` | Trivial | Step 4 |
| 6. Add UI descriptor | `frontend/src/components/services/wizard/providers.ts` | Small | Step 1 |
| 7. Add badge color | `frontend/src/components/ui/providerBadges.ts` | Trivial | None |
| 8. Write tests | `tests/unit/` | Medium | Steps 2-5 |
| 9. Manual integration testing | — | Small | All |

**Total estimated effort**: ~1 day for a single developer familiar with the codebase.

---

## 7. Migration & Compatibility

- **Existing services are unaffected** — new `ProviderEnum` entry is purely additive.
- **No database migration needed** — `provider` is a free-text `Column(String(45))` that stores the enum value. Existing data is unchanged.
- **Frontend is backward compatible** — new provider card simply appears in the wizard alongside existing ones.
- **Alembic**: No migration required.