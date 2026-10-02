# Agent middlewares — behaviour and testing

Middlewares are app-scoped, reusable [LangChain agent middlewares](https://docs.langchain.com/oss/python/langchain/middleware)
that an agent runs around every model and tool call. They are created under
**App → Middlewares** and attached from the agent's **Advanced** tab.

## Types

| Type (`middleware_type`) | LangChain implementation | Config (validated server-side) |
|---|---|---|
| `guardrails` | `GuardrailsMiddleware` (`backend/tools/middleware/guardrails.py`): appends a policy to the system prompt of each call via `wrap_model_call` + `request.override(system_message=...)`. Never writes to the conversation state. Prompt-based, best effort. | `input.{block_malicious_prompts,block_jailbreak}`, `output.{prevent_pii_leakage,block_toxic_biased,enforce_business_facts}`, `custom_prompt` (≤ 4000 chars) |
| `pii` | One built-in `PIIMiddleware` per selected type, plus the optional `LLMPIIMiddleware` (`backend/tools/middleware/llm_pii.py`) for entities without a fixed pattern | `pii_types` ⊆ `email, credit_card, ip, mac_address, url`; `strategy` = `redact`/`mask`/`hash`/`block`; `apply_to_input/output/tool_results`; `llm_detector.{enabled, ai_service, extra_entities}` |
| `human_in_the_loop` | `HumanInTheLoopMiddleware` | `interrupt_on: {tool_name: {allowed_decisions: [approve, edit, reject]}}`, `description_prefix` |
| `model_call_limit` | `ModelCallLimitMiddleware(run_limit=max_calls)` | `max_calls` 1–10000 |
| `tool_call_limit` | `ToolCallLimitMiddleware(run_limit=max_calls)` | `max_calls` 1–10000 |
| `summarization` | `SummarizationMiddleware` (replaces the memory-based one) | `summarization_model` (`agent_llm` or `ai_service:<id>` of the same app), `trigger_tokens`, `keep_messages`, `trim_tokens` |

The chain is built in `backend/tools/middleware/factory.py`. Summarization always runs first; the
rest follow the agent's order (`agent_middlewares.order`).

## Rules

- **One middleware per type per agent.** LangChain rejects duplicate middleware instances, so the
  API returns `400` and the UI disables a second middleware of the same type.
- **Human approval requires conversation memory** (the checkpointer is what pauses and resumes the
  run). Selecting it in the UI turns memory on; the API returns `400` otherwise.
- **Tenant isolation:** middlewares, and the AI services a config references, must belong to the
  same app (`404`/`400`/`422` otherwise).
- **Stored configs are re-validated** when the chain is built: an invalid row is skipped with a
  warning instead of breaking the chat.
- **PII output redaction and streaming:** with `apply_to_output`, tokens are not streamed; the
  redacted answer arrives in the `done` event. `strategy="block"` ends the turn with
  "The message was blocked because it contains personal data (…)" (SSE `error` / HTTP 422).

## Human-in-the-loop flow

1. `POST /internal/apps/{app}/agents/{agent}/chat/stream` emits a `hitl_interrupt` event
   (`{action_requests, review_configs}`, LangChain's format) and `done` with `hitl_paused: true`.
2. The playground shows the approval card. Arguments are editable only if `edit` is allowed.
3. `POST …/chat/resume` (form fields `conversation_id`, `decisions` = JSON list, one per action, in
   order) streams the rest of the turn. Decisions are validated against the pending approval
   before `Command(resume=…)`, so an invalid decision returns an error and the approval can be
   answered again.
4. `GET /internal/conversations/{id}/history` returns `pending_approval` so the card is restored
   after a reload.
5. Channels that cannot collect a decision fail clearly: public API / MCP / scheduled tasks and the
   non-streaming chat return `409`; the marketplace chat streams an `error` event.

## Manual test checklist

Use an app with an AI service, an agent marked **is tool** (e.g. "Docs Search") and a main agent
using it, with memory on.

1. **Guardrails** — attach it, ask something that makes the agent call the tool. Expect a normal
   answer; with an Anthropic model too. The conversation history must not show policy text.
2. **PII** — `email`, `redact`, all "apply to" on. Send "my email is jane@example.com": the LLM
   receives `[REDACTED_EMAIL]`, the answer appears at once (no token streaming) and the backend
   log contains no message text. With `block`, the chat shows the blocked message.
3. **Human approval** — tool `Docs_Search` (the name the UI shows), decisions approve + reject.
   Ask for the tool: the card appears, arguments read-only. Reload, reopen the conversation: the
   card is back. Approve → final answer; repeat and Reject → the agent explains it did not run it.
   Call the same agent through the public API: `409`.
4. **Limits** — model call limit 1 on an agent that needs a tool: the run stops after one call.
5. **Ordering / duplicates** — select two guardrails: the second is disabled. Reorder with the
   arrows, save, reopen: order kept.
6. **Deletion** — delete a middleware in use (agents lose it), an agent with middlewares, and the app.

## Automated tests

| Area | Tests |
|---|---|
| Guardrails (system prompt only, tool-call message order, no state writes) | `tests/unit/tools/test_guardrails_middleware.py` |
| LLM PII detector | `tests/unit/tools/test_llm_pii_middleware.py` |
| Chain building from DB rows (order, invalid config skipped, one per type) | `tests/integration/tools/test_agent_middleware_chain_integration.py` |
| CRUD, config validation, tenant isolation, agent selection rules, cascades | `tests/integration/routers/internal/test_middlewares.py` |
| HITL decision validation, pending approval, 409 for non-interactive runs | `tests/unit/services/test_hitl_service.py` |
| Streaming pause / resume | `tests/unit/services/test_agent_streaming_service.py` |
