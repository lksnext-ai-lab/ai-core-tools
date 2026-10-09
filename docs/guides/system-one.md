# System One

> Part of [Mattin AI Documentation](../README.md)

System One (Nimble, by Bespoke Labs) is a **decision model**: it reads a text and answers a fixed list of closed questions with probabilities, without generating text. Mattin AI lets you connect a System One server and build **System One agents** that classify, route, judge or decide over a text, from the playground, the public API, or as a **tool** of other agents.

> **Text only.** This version evaluates text. Attached documents are converted to text; images are rejected. See [Future: multimodal](#future-multimodal).

---

## Concepts

| Concept | What it is |
|---|---|
| **System One service** | A per-app connection to a System One server: URL, optional Bearer token, model and a concurrency limit. Managed in **Settings → System One Services** (administrators). |
| **System One agent** | An agent type (like OCR agents) that requires exactly one System One service and a fixed list of questions. Created from **Agents → Create Agent → System One Agent**. |
| **Question** | One thing to decide about the text. Three types: yes/no (`noul`), pick one option (`choice`), rate on an ordered scale (`score`). |

A System One agent has no LLM, memory, prompt, RAG, MCP or skills. Each evaluation is independent: there is no conversation.

---

## Setting up a service

Settings → System One Services → **Add System One Service**.

| Field | Notes |
|---|---|
| Name | Free text. |
| Server URL | `http://` or `https://`, e.g. `http://172.16.59.1:8100`. Private addresses are allowed on purpose: a self-hosted server normally lives on a private network. Only administrators can create or test services. |
| Token | Optional Bearer token, if the server requires one. Stored masked; leave the masked value to keep it, empty it to remove it. |
| Model | `nimble-latest` always uses the newest published model, which can change probabilities. **Test connection** lists the models the server offers so you can pin a specific version. If the test fails the field stays free text and you can still save. |
| Maximum concurrent requests | Per **backend process**. |

**Test connection** calls the server's `/health`, `/v1/models` and `/v1/limits` and shows the limits it reports.

### Concurrency

The server accepts a limited number of simultaneous requests (4 by default) and answers `529` with a `Retry-After` above it. The backend runs several processes (`UVICORN_WORKERS`), each with its own cap, so set the value to **the server limit divided by the number of backend processes** (at least 1). The client also retries `429`, `502`, `503` and `529` up to three times, honoring `Retry-After`.

### Deleting a service

A service cannot be deleted while agents use it: the API answers `409` and names them. Switch those agents to another service, or delete them, first.

---

## Defining questions

Every System One agent holds 1 to 64 questions. All of them are answered, in one call, for every text.

| Type | You define | You get |
|---|---|---|
| **Yes / No** (`noul`) | Instructions; optionally the meaning of yes and no; a threshold (default 0.5). | `decision` = probability ≥ threshold. |
| **Choice** | Instructions; 2 to 26 options (name + optional description); optional minimum probability. | `decision` = the option with the most probability, or `null` below the minimum. |
| **Score** | Instructions; 2 to 26 ordered levels (lowest to highest); optional minimum probability. | `decision` = the **most probable level**, or `null` below the minimum. |

Practical rules:

- **Keys and option names are part of what the model reads.** `is_urgent` helps the model; `q1` does not. Make them descriptive. Keys are lowercase letters, digits and underscores (max 40); option names may contain accents and spaces, and are compared ignoring case.
- **`decision` uses probability, not `confidence`.** `confidence` is one minus the normalized entropy of *all* options. It can be low even when the chosen option is clearly best (a measured example: chosen option at 73% with confidence 0.39). It is returned and stored, but it never decides anything.
- **Score returns the most probable level, not a rounded average.** The server's expected index (`expected_score`) is returned too, but with a bimodal distribution (45% "Calm", 45% "Furious") its rounding would be a level nobody picked.
- **Thresholds depend on the server.** The same passage scored 0.96 on one backend and about 0.90 on another. Set them against the server you actually use.

---

## Long texts

The server measures **8192 tokens per question prompt** (the text plus that one question) and was trained on prompts up to 2048 tokens. Each agent has a **maximum text length** in characters (default 6000, 500 to 20000) and an optional **summarization LLM**:

- text fits → evaluated as is (`state_reduction: "none"`);
- does not fit, summarization LLM set → summarized first (`"summarized"`); if the summary fails, is empty or still too long → truncated;
- does not fit, no LLM → truncated at a word boundary (`"truncated"`);
- the server still rejects it as too long → shrunk proportionally and retried once.

The result always says which happened, with the original and evaluated sizes, so a decision is never silently based on part of a document.

Attachments: text and PDF text are extracted and appended to the text with their file names. A scanned PDF without extractable text, or only empty text, is a `400`. Images and files whose text cannot be read are rejected explicitly (never skipped).

---

## Using a System One agent

### Playground

Open the agent's playground: type or paste a text, optionally attach documents, press **Evaluate**. Each question appears as a card with its decision, probability bars, and confidence, plus a notice when the text was summarized or truncated.

### As a tool of another agent

Mark the agent **Use as a tool** (on by default for new System One agents) and add it to another agent's tools like any tool agent. The calling LLM sees:

- an input `{ "text": "<text to evaluate>" }`;
- a description **generated from the questions** (it changes when you edit them);
- a compact JSON result:

```json
{
  "is_urgent": {"decision": true, "probability": 0.912},
  "area": {"decision": "billing", "probability": 0.731, "probabilities": {"billing": 0.731, "support": 0.269}, "confidence": 0.39},
  "state_reduction": "none"
}
```

The full typed result travels as the tool message artifact. Attachments of the calling turn are added to the text (images there are ignored: they belong to the caller's own context). If System One fails, the calling LLM receives a message instead of an error and the turn continues.

Metrics: each evaluation is an `AGENT_AS_TOOL` event linked to the caller's event (`parent_execution_id`), with one row per question in `agent_system_one_answer` (decision, probability, confidence, probabilities, `state_reduction`).

### Public API

Create an API key in the app settings. The request is `multipart/form-data` with a `text` field and optional `files`:

```bash
curl -X POST "https://your-host/public/v1/app/<app_id>/system-one/<agent_id>/evaluate" \
  -H "X-API-KEY: your-api-key" \
  -F "text=Hi, the router has not worked since yesterday" \
  -F "files=@ticket.pdf"
```

The response is typed (see `/docs/public`): `answers` keyed by question key, each a `noul`, `choice` or `score` answer, plus `state_reduction`, `original_chars`, `state_chars`, `model` and `usage`.

Agents can be created and updated with `POST /public/v1/app/<app_id>/agents/system-one` and `PUT .../agents/system-one/<agent_id>` (a partial update changes only the fields sent). **Services are created in the UI**, like every other service type: the API creates agents that reference an existing one.

Errors: `400` nothing to evaluate / image / unreadable attachment, `404` agent not found in the app, `422` the server rejected the request, `503` server unavailable or overloaded, `504` timeout.

---

## Export and import

An exported agent carries the **names** of its System One service and summarization LLM, never a token. Importing a single agent resolves them by name in the target app: the System One service must already exist there (otherwise the import fails and tells you to create it); a missing summarization LLM falls back to truncation.

A **full-app export** also carries the System One services (URL, model, concurrency; no token). Importing it creates them, then the agents, and warns that the token has to be added if the server requires one.

---

## Permissions

| Action | Minimum role |
|---|---|
| List / view services, list agents, evaluate | Viewer |
| Create / edit / copy / delete / test services | Administrator |
| Create / edit agents | Editor |

Like every other write, evaluating from the playground is a `POST`: users whose **platform** role is `viewer` are read-only everywhere and cannot evaluate from the playground. The public API is unaffected (API key).

---

## Architecture

| Piece | File |
|---|---|
| Models | `backend/models/system_one_service.py`, `system_one_agent.py` (joined-table child of `Agent`, `type='system_one_agent'`), `agent_system_one_answer.py` |
| Client (HTTP, retries, concurrency) | `backend/tools/system_one_client.py` |
| Decisions | `backend/tools/system_one_decisions.py` |
| Text building / size reduction | `backend/services/system_one_state.py` |
| Evaluation + metrics | `backend/services/system_one_evaluator.py`, `AgentExecutionService.execute_agent_system_one` |
| Tool | `backend/tools/system_one_tool.py` (`IACTSystemOneTool`, routed by `discover_tool`) |
| Question / result schemas | `backend/schemas/system_one_schemas.py` |
| Service CRUD | `backend/routers/internal/system_one_services.py` |
| Evaluate endpoints | `backend/routers/internal/system_one.py`, `backend/routers/public/v1/system_one.py` |

`SystemOneAgent.system_one_service_id` is `NOT NULL` with `ON DELETE RESTRICT`, so "an agent needs exactly one System One service" and "a service in use cannot be deleted" are guaranteed by the database. The type of an agent cannot be changed after creation.

---

## Future: multimodal

System One evaluation is text only today. If a future model accepts images, the intended path mirrors `AIService.supports_video`: a capability flag **declared by hand on the System One service** (for example `supports_images`), which, when on, lets the agent send images instead of rejecting them. Nothing for this exists yet, and no column has been reserved.
