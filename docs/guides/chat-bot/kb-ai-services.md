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

## Service End of Service

AI, embedding and sandbox (code interpreter) services can have a planned **end of service**, for example when a provider retires a model.

| Field | Description |
|-------|-------------|
| **End of service** | Optional date. The service is retired from 00:00 UTC of that day |
| **Deprecation notice** | Optional text (max 1000 characters) shown to users, e.g. which service to migrate to |

Who can edit them: app administrators (Administrator and above) for the App's services, platform administrators for system services. Leaving a field empty clears it.

### Status

| Status | Meaning |
|--------|---------|
| **Active** | No end of service, or it is further away than the warning window |
| **Deprecated** | The date is within the warning window (30 days by default, configurable by platform admins; 0 disables this phase) |
| **Retired** | The date has been reached |

The status badge appears in the services lists. Agents, silos, repositories, scheduled tasks and playgrounds that depend on a deprecated or retired service show a warning.

### What happens when a service is retired

- Chat, indexing, transcription and embedding calls that need the service fail with a message naming the service and the deprecation notice. Over the API this is HTTP `409` with `error_code: "SERVICE_RETIRED"`.
- Scheduled task runs fail with that message and are not retried. Background indexing items are marked as failed.
- Retired services no longer appear in selection dropdowns (a deprecated one is labelled), and cannot be newly selected. An existing selection is kept until you change it.
- **Test connection** keeps working. Deleting silos, repositories and apps keeps working too.
- A retired embedding service means its silos must be re-indexed with another embedding service. Until then, searching, indexing and the chunk-neighbour view of those silos are blocked.
- A retired sandbox service (the agent's own, or the App default) does not fail the chat: the agent's code interpreter is disabled for that turn. There is no fallback to another provider.
- Users of a published marketplace agent see the retirement message of the owning App's service.

### Finding and moving what depends on a service

Use **Used by** on a service to list the agents (with the role the service plays), silos, repositories, middlewares and scheduled tasks that use it. For sandbox services it also lists the Apps using it as their default.

For AI services, **Move agents** (Administrator and above) points all agents that use the service as their main LLM at another service in one step. If the number of agents changed since you opened the dialog, nothing is moved and you are asked to review again.

### Copy, export and import

Copying a service does not carry the end-of-service fields. App export/import does for AI and embedding services (see [App Export/Import](../app-export-import.md)).
