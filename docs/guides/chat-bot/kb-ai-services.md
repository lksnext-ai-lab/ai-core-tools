# AI Services

## What is an AI Service?

An **AI Service** is a connection to an LLM (Large Language Model) provider. Agents use AI Services to power their responses. You configure the provider, model, and API key once — then any agent in your App can use it.

## Supported Providers

| Provider | Notes |
|----------|-------|
| **OpenAI** | GPT-4, GPT-4o, GPT-3.5, and other OpenAI models |
| **Anthropic** | Claude models (Claude 3.5, Claude 3, etc.) |
| **Azure OpenAI** | OpenAI models hosted on Azure (requires endpoint + deployment name) |
| **MistralAI** | Mistral models |
| **Google** | Gemini models |
| **Custom** | Any OpenAI-compatible API endpoint (local models, LM Studio, Ollama, etc.) |

## Creating an AI Service

1. Open your App and go to **AI Services**.
2. Click **New AI Service**.
3. Select the provider.
4. Enter the required fields:
   - **Name** — a label for this service (e.g. "GPT-4o Production")
   - **Model** — the model identifier (e.g. `gpt-4o`, `claude-3-5-sonnet-20241022`)
   - **API Key** — your provider's API key
   - For Azure: also the endpoint URL and deployment name
5. Save.

## Using an AI Service

When creating an agent, select the AI Service in the **LLM Service** field. The agent will use that model for all its responses.

## System AI Services

Platform administrators may configure system-level AI Services that are available to all Apps without users needing to provide their own API keys. These appear in the AI Service selector alongside your own services.

## Embedding Services

**Embedding Services** are similar to AI Services but are used for generating vector embeddings for Silos (knowledge bases). They are configured separately under **Embedding Services** in your App. The supported providers are the same as for AI Services.
