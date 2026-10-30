# System One

> Part of [Mattin AI Documentation](../README.md)

System One is a **decision model**: it reads a text and answers a fixed list of closed questions with probabilities, without generating text. Mattin AI lets you connect a System One server and build **System One agents** that classify, route, judge or decide over a text, from the playground, the public API, or as a **tool** of other agents.

> **Text by default.** Attached documents are converted to text. Images are accepted only when the service's provider supports them (today: OpenAI Decisions); otherwise they are rejected. See [Providers](#providers).

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

Settings → System One Services → **Add System One Service**. It is a three-step wizard, like the AI service one:

1. **Connection**: the server's base URL (prefilled with `https://api.typesafe.ai`; `http://` or `https://`; private addresses are allowed on purpose, since a self-hosted server normally lives on a private network) and an optional Bearer token. The token is stored masked: when editing, leave the masked value to keep it or empty it to remove it. It belongs to the URL it was stored for, so changing the URL clears it and you type it again; *Test connection* never sends the stored token to a different URL. Only administrators can create or test services.
2. **Model**: the wizard asks the server which models it offers (`/v1/models`) and you pick one. There is no default model. If the server cannot be reached or lists none, you can type the identifier by hand.
3. **Test**: a name (suggested from the model), the maximum concurrent requests (in **total**, prefilled with the server's limit) and **Test connection**, which calls `/health`, `/v1/models` and `/v1/limits`, checks that the chosen model is offered, and shows the limits the server reports.

Not every server offers `/health`, `/v1/models` or `/v1/limits` (a hosted API may only have `/v1/systemone`): a missing health endpoint is not a failure, and the *Test* step skips the list. **Only when the server gives no way to list its models** does the test send one real, tiny question (one yes/no, a few tokens) with the chosen model, which proves the URL, the token and the model; the result says so. A server that lists its models is not called. Errors name the culprit: token rejected (401/403), no credit left (402), URL not found (404, some servers carry the model name in the URL), or the server's own message for a rejected question.

### Concurrency

A System One server accepts a limited number of simultaneous requests (Nimble: 4) and answers `529` with a `Retry-After` above it. **The cap of a service is the total for the whole backend, not per process**: every call holds one of `cap` slots while it runs, and the slots are shared by all backend processes (Postgres advisory locks on a dedicated connection, `backend/tools/system_one_limiter.py`). Calls above the cap wait their turn instead of being rejected, for at most 20 seconds: every waiting request keeps a database session, so past that the caller gets `503` ("busy") and can retry, the same answer as the server's own `529`. The evaluation also hands its database connection back to the pool before waiting: otherwise a burst of requests would hold the whole pool (20 + 10 per process) and their own authentication could not get a connection. Nothing but a service id and a slot number is stored in the database: no texts, no results.

The test (steps 2 and 3) reads the server's `max_concurrent_requests` and prefills the cap with it. A cap **above that limit cannot be saved**, because it could never be used.

If the database cannot be reached, the call goes ahead without the global limit (the process-local cap still applies): System One does not depend on it. The client also retries `429`, `502`, `503`, `529` up to three times, honoring `Retry-After`, and a changed value applies to new calls without a restart. A service saved before this behaviour had its cap read as *per process*; it now means the total, which is more conservative.

### Deleting a service

A service can be deleted even if agents use it, like an AI service. The agents are **not** deleted: they keep their questions but cannot run (evaluating them answers `409`, and as a tool they tell the calling LLM that their service is gone) until you choose another service in their settings. The UI warns before deleting and says how many agents are affected.

### End of service

Like AI, embedding and sandbox services, a System One service can have a planned **end of service** date and a deprecation notice (set them in the service wizard). Before the date the service is shown as deprecated and agents using it show a warning; from that date it is **retired**: its agents cannot evaluate (`409 SERVICE_RETIRED`; as a tool they tell the calling LLM why), and it can no longer be chosen for an agent that did not already have it. Test connection, copy and delete keep working. The same rule applies to the agent's summarization LLM: a retired AI service cannot be newly chosen, and an agent that already has one truncates long texts instead of summarizing them (with a warning in the log). Export/import carries the date and notice.

## Defining questions

Every System One agent holds at least one question; the maximum is the one the chosen server reports in `/v1/limits` (the form reads it and checks against it). All of them are answered, in one call, for every text.

The order only decides how the questions are listed (playground, tool description, JSON); each one is answered on its own. Drag a question by its handle to reorder it, or use the arrows next to it.

**Colors in the playground.** Yes is green and No is red. Each option of a choice question has its own color, shown in the editor and chosen automatically from the option's name (the same name always gets the same color); click the swatch to pick another, and *auto* to go back. The levels of a score question run along a green-red gradient, and the setting under the levels says whether the first level is green (ascending) or red (descending); the dot next to each level shows the color it gets. These colors are only for display and are never sent to the server.

**How long a question may be** is not a fixed number: every prompt the server evaluates holds the text **plus one question**, and the agent's *maximum text length* is that per-prompt budget. A question (instructions, options, levels) must leave at least 500 characters of it for the text; the form and the API refuse it otherwise, saying how much it takes.

| Type | You define | You get |
|---|---|---|
| **Yes / No** (`noul`) | Instructions; optionally the meaning of yes and no; a threshold (default 0.5). | `decision` = probability ≥ threshold. |
| **Choice** | Instructions; 2 or more options (name + optional description; the maximum is the server's); optional minimum probability. | `decision` = the option with the most probability, or `null` below the minimum. |
| **Score** | Instructions; 2 or more ordered levels (lowest to highest; the maximum is the server's); optional minimum probability. | `decision` = the **most probable level**, or `null` below the minimum. |

Practical rules:

- **Keys and option names are part of what the model reads.** `is_urgent` helps the model; `q1` does not. Make them descriptive. Keys are lowercase letters, digits and underscores (max 40); option names may contain accents and spaces, and are compared ignoring case.
- **`decision` uses probability, not `confidence`.** `confidence` is one minus the normalized entropy of *all* options. It can be low even when the chosen option is clearly best (a measured example: chosen option at 73% with confidence 0.39). It is returned and stored, but it never decides anything.
- **Score returns the most probable level, not a rounded average.** The server's expected index (`expected_score`) is returned too, but with a bimodal distribution (45% "Calm", 45% "Furious") its rounding would be a level nobody picked.
- **Thresholds depend on the server.** The same passage scored 0.96 on one backend and about 0.90 on another. Set them against the server you actually use.

---

## Long texts

The server measures **8192 tokens per question prompt** (the text plus that one question) and was trained on prompts up to 2048 tokens. Each agent has a **maximum text length** in characters (default 6000, at least 500; there is no upper limit of ours: the server enforces its own budget) and an optional **summarization LLM** (one of the app's own AI services; platform-level ones are not offered, because they would run unmetered):

- text fits → evaluated as is (`state_reduction: "none"`);
- does not fit, summarization LLM set (an AI service of **this app**; platform-wide services are not offered, so a summary is never an unmetered call) → summarized first (`"summarized"`); if the summary fails, is empty or still too long → truncated;
- does not fit, no LLM → truncated at a word boundary (`"truncated"`);
- the server still rejects it as too long → shrunk proportionally and retried once.

The result always says which happened, with the original and evaluated sizes, so a decision is never silently based on part of a document. When the text was summarized or truncated it also carries the text that was actually evaluated (`evaluated_text`); in the playground, click the amber notice to read it. While a long text is being summarized the playground says so (the LLM can take up to a minute).

The summarizing LLM is asked for a summary of **at most** the room available (it usually writes much less) and receives the questions, so it keeps what they need. Asking for a size close to the room was tried: it kept more detail but took about ten times longer. It reads at most the first 120,000 characters. Attachments are read as plain text: an HTML file is evaluated with its markup (tags, CSS, scripts), which uses up the room quickly.

Attachments: text and PDF text are extracted and appended to the text with their file names. A scanned PDF has no text layer (the backend extracts text, it does not do OCR): an attachment with no extractable text is a `400` that names the file, **even when other text was sent**, so that the rest is never evaluated alone while the caller believes the file was read. An empty text with nothing attached is a `400` too. Images and files whose text cannot be read are rejected explicitly (never skipped).

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

System One agents (and their services) are created and edited in the app; the public API only evaluates with them. The generic `PUT /agents/{id}` refuses them.

Errors: `400` nothing to evaluate / image / unreadable attachment, `404` agent not found in the app, `422` the server rejected the request (a generic message: the server's own text is logged for the administrator, not returned; the exception is "text too long"), `502` the server answered with an unexpected response or refused the service's token, `503` server unavailable or overloaded, `504` timeout. A call has one overall deadline of 120 s (waiting for a free slot, every attempt and the pauses between them).

---

## Metrics

The agent's *Metrics* tab shows its executions like any other agent, with these differences:
- **System One tokens** (and per execution) are the prompt tokens reported by the System One server, one call per execution. It is a decision model, not an LLM, so these are not counted as LLM calls.
- **Summarization calls** are the calls to the summarizing LLM, with the input and output tokens it reported (0 when the LLM does not report usage). They are recorded apart from the server's tokens.
- **Latency** is the whole evaluation: summarizing (when it happens, seconds) plus the server call (a fraction of a second).
- *Time to first token* and *Tool calls* are not shown: they do not apply (one response, no tools).
- The answers of every question (decision, probability, ...) are stored per execution.

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
| Client (HTTP, retries, concurrency) | `backend/tools/system_one_client.py`, global slots in `backend/tools/system_one_limiter.py` |
| Decisions | `backend/tools/system_one_decisions.py` |
| Text building / size reduction | `backend/services/system_one_state.py` |
| Evaluation + metrics | `backend/services/system_one_evaluator.py`, `AgentExecutionService.execute_agent_system_one` |
| Tool | `backend/tools/system_one_tool.py` (`IACTSystemOneTool`, routed by `discover_tool`) |
| Question / result schemas | `backend/schemas/system_one_schemas.py` |
| Service CRUD | `backend/routers/internal/system_one_services.py` |
| Evaluate endpoints | `backend/routers/internal/system_one.py`, `backend/routers/public/v1/system_one.py` |

`SystemOneAgent.system_one_service_id` is nullable with `ON DELETE SET NULL`, the same as `Agent.service_id` for AI services: deleting a service leaves its agents in place and inoperative.

---

## Quotas in SaaS mode

System One agents are not counted against the plan's `llm_calls` quota (see [SaaS mode](saas-mode.md#system-one-and-quotas) for why and for how a hosted service would be metered, per input token).

## Providers

A service has a **provider**, chosen in the first step of the wizard (stored in `extra_config.provider`; services created before it are `system_one`). The backend client (`backend/tools/system_one_client.py`) translates each provider's wire format and normalizes the answer to the System One shape, so decisions, metrics and the agents are provider-agnostic.

| Provider | Endpoint | Models | Limits | Images |
|---|---|---|---|---|
| `system_one` (Nimble, Jev, any `/v1/systemone` server) | `POST /v1/systemone` | `/v1/models` | `/v1/limits` | no |
| `openai_decisions` | `POST /v1/decisions` (default URL `https://api.openai.com`, API key required) | fixed: `gpt-6-luna` | not published (set the concurrency by hand) | yes (base64 data URLs) |

With OpenAI Decisions the evaluated text and images are sent to OpenAI. `noul` becomes a `predicate` (its true/false meanings are appended to the instructions), `choice` and `score` map to `choices` / `levels`. A `refusal` answer fails the call. Confidence thresholds tuned on one provider do not transfer to another. Images are sent from the playground and the public API; as a tool of another agent, images of the calling turn are still ignored.

To add a provider: a constant and a request/response translator in the client, an entry in `SYSTEM_ONE_PROVIDERS` (frontend `types/systemOne.ts`), and `IMAGE_PROVIDERS` if it takes images.
