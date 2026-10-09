# Agent middlewares — behaviour and testing

Middlewares are app-scoped, reusable [LangChain agent middlewares](https://docs.langchain.com/oss/python/langchain/middleware)
that an agent runs around every model and tool call. They are created under
**App → Middlewares** and attached from the agent's **Advanced** tab.

## Types

| Type (`middleware_type`) | LangChain implementation | Config (validated server-side) |
|---|---|---|
| `guardrails` | `GuardrailsMiddleware` (`backend/tools/middleware/guardrails.py`): appends a policy to the system prompt of each call via `wrap_model_call` + `request.override(system_message=...)`. Never writes to the conversation state. Prompt-based, best effort. | `input.{block_malicious_prompts,block_jailbreak}`, `output.{prevent_pii_leakage,block_toxic_biased,enforce_business_facts}`, `custom_prompt` (≤ 4000 chars) |
| `pii` | One built-in `PIIMiddleware` per selected type, plus the optional `LLMPIIMiddleware` (`backend/tools/middleware/llm_pii.py`) for entities without a fixed pattern | `pii_types` ⊆ `email, credit_card, ip, mac_address, url`; `strategy` = `redact`/`mask`/`hash`/`block`; `apply_to_input/output/tool_results`; `llm_detector.{enabled, ai_service, extra_entities}` |
| `human_in_the_loop` | `HumanInTheLoopMiddleware` | `interrupt_on: {tool_name: {allowed_decisions: [approve, edit, reject]}}`, `description_prefix`, `approval_timeout_seconds` (60 – `HITL_MAX_APPROVAL_TTL_SECONDS`, default 3600) |
| `model_call_limit` | `ModelCallLimitMiddleware(run_limit=max_calls)` | `max_calls` 1–10000 |
| `tool_call_limit` | `ToolCallLimitMiddleware(run_limit=max_calls)` | `max_calls` 1–10000 |
| `summarization` | `SummarizationMiddleware` (replaces the default one of agents with memory) | `summarization_model` (`agent_llm` or `ai_service:<id>` of the same app), `trigger_tokens` (empty = 85% of the model window, max 150k; 32k without a model profile), `keep_messages` (default 20), `trim_tokens` (empty = no limit) |

The chain is built in `backend/tools/middleware/factory.py`. Summarization always runs first; the
rest follow the agent's order (`agent_middlewares.order`).

## Rules

- **One middleware per type per agent.** LangChain rejects duplicate middleware instances, so the
  API returns `400` and the UI disables a second middleware of the same type.
- **Human approval requires conversation memory** (the checkpointer is what pauses and resumes the
  run). Selecting it in the UI turns memory on; the API returns `400` otherwise, also when memory is
  turned off on an agent that already has it.
- **Agents used as tools run their own middlewares** (guardrails, PII, limits, summarization). They
  cannot pause for a person, so the tools their approval rules gate are not given to them.
- **Approval rules follow renamed tool agents:** renaming an agent rewrites the rules that name it
  (`Old_Name` → `New_Name`) and cancels the pending approvals of the agents using those rules.
- **AI services in use cannot be deleted:** deleting one that a summarization or PII middleware
  references returns `409` naming the middlewares (otherwise they would silently fall back to the
  agent's model).
- **Tenant isolation:** middlewares, and the AI services a config references, must belong to the
  same app (`404`/`400`/`422` otherwise).
- **Stored configs are re-validated** when the chain is built: an invalid row is skipped with a
  warning instead of breaking the chat.
- **Deletion:** deleting a middleware detaches it from its agents; deleting an agent removes its
  associations, conversations (with their checkpoints, media, sandboxes and files) and approvals but
  keeps the middlewares; deleting an app removes everything, middlewares before AI services.
- **Export/import:** a middleware can be exported and imported on its own (Middlewares page), and
  travels with agent and full-app exports. The AI service it references travels by name; if the target
  app has none with that name the import keeps the agent's model and reports a warning. Agent imports
  reuse an identical existing middleware, otherwise import a renamed copy.
- **PII output redaction and streaming:** with `apply_to_output`, tokens are not streamed; the
  redacted answer arrives in the `done` event. `strategy="block"` ends the turn with
  "The message was blocked because it contains personal data (…)" (SSE `error` / HTTP 422).

## Human-in-the-loop flow

Every pause is recorded in `hitl_approval` (owner, actions, status, `expires_at`); the LangGraph
checkpointer keeps the paused graph. See [Human approval in the public API](../guides/human-approval.md)
for the integrator view.

1. The run pauses → an approval is opened with one action per gated tool call (`action_id` = the
   tool call id). Interactive channels (playground, marketplace, public API) get it back:
   SSE `hitl_interrupt` (`{approval_id, status, expires_at, actions}`) + `done{status: "requires_approval"}`,
   or `status: "requires_approval"` + `pending_approval` from `/call`.
2. Only the requester can answer: the same user (`/internal/approvals/{id}/decisions/stream`,
   `/internal/approvals/{id}/cancel`) or the same API key (`/public/v1/app/{app}/approvals/{id}/decisions[/stream]`).
   Anyone else gets `404`.
3. Decisions are addressed by `action_id`, one per action, validated (allowed type, edited args size
   and `args_schema`) and then claimed with a compare-and-set: a second answer gets
   `409 approval_already_decided`, a late one `409 approval_expired`, and a pause the graph no longer
   has `409 approval_stale`.
4. A new message on a conversation that is waiting gets `409 approval_pending` (it would discard the pause).
5. Unanswered approvals expire: they are **rejected**, never approved. A background sweep (every
   `HITL_EXPIRY_SWEEP_SECONDS`, default 60, under a PostgreSQL advisory lock) resumes them with
   reject decisions, so the conversation gets the agent's final answer and accepts messages again. A
   message sent after the deadline resolves it first.
6. Channels that cannot ask a person (MCP, scheduled tasks, OpenAI-compatible API, platform chatbot,
   non-streaming internal chat) reject the pause on the spot and return
   `409 approval_not_supported_in_channel` (scheduled runs record it as their output). The
   conversation is never left paused.
7. Changing an agent's approval rules (editing/detaching/deleting its human-approval middleware)
   cancels its pending approvals: a resume re-runs the middleware with the current rules, so an
   answer given under the old rules could be ignored.
8. Agent streams send `: ping` every 15 s and every turn is bounded by `AICT_AGENT_RUN_TIMEOUT_SECONDS`
   (default 600): a hung model or tool ends with an `error{code: "run_timeout"}` event.

## Manual test checklist

Use an app with an AI service, an agent marked **is tool** (e.g. "Docs Search") and a main agent
using it, with memory on.

1. **Guardrails** — attach it, ask something that makes the agent call the tool. Expect a normal
   answer; with an Anthropic model too. The conversation history must not show policy text.
2. **PII** — `email`, `redact`, all "apply to" on. Send "my email is jane@example.com": the LLM
   receives `[REDACTED_EMAIL]`, the answer appears at once (no token streaming) and the backend
   log contains no message text. With `block`, the chat shows the blocked message.
3. **Human approval** — tool `Docs_Search` (the name the UI shows), decisions approve + reject,
   time to answer 2 minutes.
   - Ask for the tool: the card appears with a countdown, arguments read-only, the composer is
     locked and the tool panel shows *awaiting approval*. Reload: the card is back.
   - Approve → *running* → final answer. Reject → *rejected*, the agent says it did not run it.
     **Cancel request** → *cancelled*, same answer.
   - Allow `edit`, change the arguments → *edited*, the tool runs with your arguments.
   - Let it expire: the card shows *Expired*, and within about a minute the agent's answer appears
     and the composer unlocks.
   - Public API: `/call` returns `requires_approval`; answer it with
     `POST /public/v1/app/{app}/approvals/{id}/decisions`; a second answer gets `409`; another API key gets `404`.
4. **Limits** — model call limit 1 on an agent that needs a tool: the run stops after one call.
5. **Ordering / duplicates** — select two guardrails: the second is disabled. Reorder with the
   arrows, save, reopen: order kept.
6. **Deletion** — delete a middleware in use (agents lose it), an agent with middlewares and
   conversations, and the app (no agent is left behind). Deleting an AI service a PII detector uses
   returns `409`.
7. **Tool agents** — give an agent used as a tool a guardrail: its answers follow it. Rename it: the
   approval rule of the calling agent follows the new name.
8. **Export/import** — export a PII middleware with an LLM detector and import it into another app,
   with and without an AI service of the same name (the second shows a warning).

## Automated tests

| Area | Tests |
|---|---|
| Guardrails (system prompt only, tool-call message order, no state writes) | `tests/unit/tools/test_guardrails_middleware.py` |
| LLM PII detector | `tests/unit/tools/test_llm_pii_middleware.py` |
| Chain building from DB rows (order, invalid config skipped, one per type) | `tests/integration/tools/test_agent_middleware_chain_integration.py` |
| CRUD, config validation, tenant isolation, agent selection rules, cascades | `tests/integration/routers/internal/test_middlewares.py` |
| Agent/app deletion, AI service in use, tool-agent rename, export/import | `tests/integration/routers/internal/test_middleware_relations.py` |
| Summarization defaults, chain of agents used as tools | `tests/unit/tools/test_middleware_factory.py` |
| Approval ownership, action ids, decision validation, expiry status | `tests/unit/services/test_hitl_approval_service.py` |
| Claim compare-and-set, one pending approval per conversation, cascade | `tests/integration/repositories/test_hitl_approval_repository.py` |
| Streaming pause / resume / stale / non-interactive channel / busy conversation | `tests/unit/services/test_agent_streaming_service.py` |
| Heartbeat, run timeout, cancellation of agent streams | `tests/unit/tools/test_stream_guard.py` |
| Tool events for rejected / edited calls | `tests/unit/tools/test_streaming_utils.py` |
