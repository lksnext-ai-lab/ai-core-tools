# Middleware Testing - Mattin AI Agent Orchestrator

## Objective

This document shows how different middlewares were tested in the **Mattin AI** agent orchestrator:

1. **Monitoring Middleware**
2. **Human-in-the-Loop Middleware**
3. **PII Detection / Redaction Middleware**
4. **Model Call Limit Middleware**
5. **Tool Call Limit Middleware** _(placeholder — pending manual run)_
6. **Summarization Middleware**

The test uses an agent configured to force specific behaviours and verify whether the middlewares correctly intercept tool calls, execution logs, and sensitive information.

---

## 1. Test Agent

### Configured system prompt

```text
You are a test assistant. Respond directly to the user WITHOUT calling tools unless explicitly asked.

STRICT RULES:
- Use the "Greeting Agent" tool when you are going to send a greeting.
- Only use "anonymize_text" if the user explicitly asks to anonymize text.
- For any other question, respond directly without using tools.
```

### Test intention

The prompt forces three behaviours:

| Case | Expected behaviour |
|---|---|
| User greeting | The agent must call `Greeting Agent` |
| Explicit anonymization request | The agent must call `anonymize_text` |
| Any other question | The agent must respond directly, without tools |

---

## 2. Monitoring Middleware

### Tested case

The agent is triggered and the middleware is expected to log execution metrics.

### Generated log

```text
mattin-backend  | 2026-05-19 12:20:41,996 - services.agent_streaming_service - INFO - [Monitoring] agent_id=3 | models=['gpt-5.2-2025-12-11'] | input_tokens=3309 | output_tokens=818 | total_tokens=4127 | llm_calls=1
```

### Expected result

The middleware correctly captures:

| Metric | Value |
|---|---:|
| `agent_id` | `3` |
| Model used | `gpt-5.2-2025-12-11` |
| Input tokens | `3309` |
| Output tokens | `818` |
| Total tokens | `4127` |
| LLM calls | `1` |

### Validation

The **Monitoring Middleware** works correctly because it logs the model, token consumption, and number of LLM calls during the agent execution.

---

## 3. Human-in-the-Loop Middleware - Greeting Agent

### Tested case

The user sends a greeting:

```text
Good morning!
```

According to the system prompt, the agent must use the `Greeting Agent` tool.

Since the HITL middleware is active, execution is paused before running the tool and human approval is requested.

### Recreated conversation

```text
User
14:31
Good morning!
```

```text
⏸️ Execution paused - waiting for human approval.
14:31

Greeting Agent
```

### Approval required

```text
⚠️ Approval required

🔧 Greeting_Agent

{
  "query": "Good morning!",
  "args": null,
  "kwargs": null
}

✓ Approve
✗ Reject
```

### Expected result

The user must be able to:

| Action | Result |
|---|---|
| Approve | `Greeting_Agent` is executed |
| Reject | The tool execution is blocked |

### Validation

The **Human-in-the-Loop Middleware** works correctly because it intercepts the call to `Greeting_Agent` before execution and requires explicit user approval.

### Additional case: Edit before approval (Greeting Agent)

> _Placeholder — run this against a live agent and replace the `_TODO_`
> markers with the actual conversation/log output before treating this case
> as verified._

Unlike the approve/reject cases above, this exercises the HITL middleware's
**edit** path: the tester changes the tool's arguments in the approval
textarea before approving, and the tool must run with the edited arguments
instead of the ones the model originally proposed.

#### Edit scenario

The user sends a greeting, triggering the same `Greeting_Agent` call as above. Before approving, the tester edits the `query` argument in the approval textarea from the original greeting to:

```text
Say hello in 5 different languages
```

#### Recreated conversation (edited)

```text
_TODO: paste the recreated conversation, same style as the sections above_
```

#### Approval required (edited)

```text
⚠️ Approval required

🔧 Greeting_Agent

{
  "query": "Say hello in 5 different languages",
  "args": null,
  "kwargs": null
}

✓ Approve
✗ Reject
```

#### Response after approval (edited)

```text
_TODO: paste the actual agent response — expected shape similar to a
greeting rendered in 5 distinct languages_
```

#### Expected result (edited case)

| Action | Result |
|---|---|
| Edit `query` then Approve | `Greeting_Agent` runs with the edited query, not the model's original one; the frontend detects the textarea diff and sends `type: 'edit'` with `edited_action` instead of `type: 'approve'` |

#### Validation

_TODO: fill in once run — confirm (1) the frontend detects the textarea edit
and sends an `edit` decision rather than `approve`, (2) `Greeting_Agent`
receives the edited `query` (the 5-language request), not the model's
original greeting, and (3) the response actually contains a greeting in 5
distinct languages._

---

## 4. Human-in-the-Loop Middleware - anonymize_text

### Tested case

The user explicitly asks to anonymize text containing sensitive information:

```text
Anonymize this: usuario@mattin.de, password 1234_mattin
```

According to the system prompt, the agent may use `anonymize_text` because the user explicitly requested anonymization.

### Recreated conversation

```text
User
14:36
Anonymize this: usuario@mattin.de, password 1234_mattin
```

```text
⏸️ Execution paused - waiting for human approval.
14:36

anonymize text
```

### Approval required

```text
⚠️ Approval required

🔧 anonymize_text

{
  "text": "usuario@mattin.de, password 1234_mattin",
  "model_family": "spaCy",
  "model_name": "en_core_web_lg",
  "threshold": 0.4
}

✓ Approve
✗ Reject
```

### Response after approval

```text
Here is the anonymized text:

[EMAIL_ADDRESS], password [PASSWORD]

Detected:

EMAIL_ADDRESS: usuario@mattin.de
```

### Expected result

The HITL middleware pauses execution before calling `anonymize_text`.

After approval, the tool returns the anonymized text:

```text
[EMAIL_ADDRESS], password [PASSWORD]
```

### Validation

The **Human-in-the-Loop Middleware** works correctly because:

1. It detects a tool call.
2. It pauses execution.
3. It displays the exact arguments that will be sent.
4. It allows the user to approve or reject execution.
5. It continues correctly after approval.

---

## 5. PII Detection / Redaction Middleware

### Tested case

The user sends a message containing personal data:

```text
My email is pedro_perez@gmail.com and my IP address is 194.22.23.3. Repeat back to me the message you receive.
```

> Note: the "Repeat back to me the message you receive" instruction was added
> after the original prompt (without it) turned out not to give the model any
> reason to restate what it saw, making it impossible to confirm redaction
> from the visible response alone — the backend log below was the only
> evidence. Adding it lets the redaction be confirmed directly in the chat.

### Message received by the LLM

Before reaching the model, the middleware replaces sensitive data with placeholders.

```text
My email is [REDACTED_EMAIL] and my IP address is [REDACTED_IP]. Repeat back to me the message you receive.
```

### Generated log

```text
mattin-backend  | 2026-05-19 12:53:08,258 - tools.agentTools - INFO - [PII] Message after redaction: My email is [REDACTED_EMAIL] and my IP address is [REDACTED_IP]
```

### Expected result

| Original data | Redacted data |
|---|---|
| `pedro_perez@gmail.com` | `[REDACTED_EMAIL]` |
| `194.22.23.3` | `[REDACTED_IP]` |

### Validation

The **PII Detection Middleware** works correctly because it redacts sensitive information before the message reaches the LLM and before it is stored in the conversation.

### Additional case: LLM-based PII Detection

> _Placeholder — run this against a live agent with `llm_detector.enabled=true`
> and `extra_entities` set to `last name, ID number`, and replace the `_TODO_`
> markers with the actual conversation/log output before treating this case
> as verified._

Unlike the case above (email, IP — fixed regex patterns), this exercises the
LLM detector's ability to find entities regex can't: a person's last name,
and a free-form ID number format.

#### Configuration

```text
llm_detector.enabled = true
llm_detector.extra_entities = last name, ID number
```

#### Tested prompt

```text
My name is Pedro Perez and mi ID is 12345678A. Repeat back to me the message you receive.
```

#### Expected redaction

| Original data | Entity type | Redacted data |
|---|---|---|
| `Perez` | last name | `[REDACTED_LAST NAME]` |
| `12345678A` | ID number | `[REDACTED_ID NUMBER]` |
| `Pedro` | _(not in `extra_entities`)_ | left untouched |

The agent's reply should echo back the already-redacted values, e.g.:

```text
_TODO: paste the actual agent response — expected shape similar to:_
Got it — Pedro [REDACTED_LAST NAME], ID [REDACTED_ID NUMBER].
```

#### Validation

_TODO: fill in once run — confirm (1) the first name passes through untouched
since it isn't in `extra_entities`, (2) the last name and ID are both
redacted before the top-level model ever sees them, and (3) the LLM
detector's own raw structured-output JSON never leaks into the visible
response._

---

## 6. Model Call Limit Middleware

### Configuration

The middleware was configured with:

```text
Max LLM calls per run = 1
```

### Tested case

```text
Anonymize this: usuario@mattin.de, password 1234_mattin
15:26
Model call limits exceeded: run limit (1/1)
```

### Why this happens

When a tool is involved (for example `anonymize_text`), the run usually needs **2 model calls**:

| LLM call | Purpose |
|---|---|
| Call 1 | The model decides to invoke the tool and emits the tool call |
| Call 2 | After tool output is available, the model composes the final user-facing answer |

With `run_limit = 1`, the first call is allowed, but the second call is blocked.

### Expected result

The middleware stops the run and returns:

```text
Model call limits exceeded: run limit (1/1)
```

### Validation

The **Model Call Limit Middleware** works correctly because it enforces the per-run LLM cap and prevents the second model call required to finish a tool-based answer.

### Additional cases for Model Call Limit (pending manual run)

> _Placeholder — run these and replace with real output before treating them as verified._

| Case | Expected result | Evidence |
|---|---|---|
| `max_calls` high enough (e.g. `10`) for the same tool flow | Run completes normally, confirming the limit isn't blocking valid runs | _TODO: paste log/response_ |
| Pure Q&A prompt (no tool call) with `max_calls=1` | Succeeds, since only one LLM call is needed | _TODO: paste log/response_ |

---

## 7. Tool Call Limit Middleware

> _Placeholder — no prior evidence exists for this middleware. Run the cases
> below against a live agent and replace the `_TODO_` markers with the actual
> conversation/log output before treating this section as verified._

### Configuration

```text
Max tool calls per run = 1
```

### Tested case

A prompt that requires two sequential tool calls (e.g. the same tool called
twice, or two different tools).

```text
_TODO: paste the user prompt used_
```

### Recreated conversation

```text
_TODO: paste the recreated conversation, same style as the HITL sections above_
```

### Generated log / error

```text
_TODO: paste the actual log line or the error surfaced to the user, expected
shape: "Tool call limits exceeded: run limit (1/1)"_
```

### Expected result

The first tool call is allowed; the run stops before the second tool call
with a `Tool call limits exceeded: run limit (1/1)` error.

### Additional cases for Tool Call Limit (pending manual run)

| Case | Expected result | Evidence |
|---|---|---|
| `max_calls` high enough for the same two-tool-call flow | Completes normally | _TODO: paste log/response_ |
| Combined with `model_call_limit` on the same agent | Whichever limit is hit first produces its own distinct error message, no mixing | _TODO: paste log/response_ |

### Validation

_TODO: fill in once the cases above have real evidence — mirror the wording
style used for Model Call Limit §6._

---

## 8. Summarization Middleware

### Configuration

The middleware was configured with:

```text
trigger=('tokens', 500)
keep=('messages', 2)
trim_tokens_to_summarize=500
```

### What this middleware does

When the conversation history exceeds the trigger threshold, the middleware summarizes older messages and keeps only the most recent context (plus the generated summary), reducing memory size while preserving continuity.

### Activation evidence

```text
mattin-backend  | 2026-05-19 14:26:51,174 - tools.agentTools - INFO - [Summarization] abefore_model: agent=3, messages=5, approx_tokens=2396, trigger=('tokens', 500)
mattin-backend  | 2026-05-19 14:26:55 - INFO - [Summarization] TRIGGERED for agent 3: reduced to 4 messages (summary generated)
mattin-backend  | 2026-05-19 14:26:55,516 - tools.agentTools - INFO - [Summarization] TRIGGERED for agent 3: reduced to 4 messages (summary generated)
```

### Validation

The **Summarization Middleware** works correctly because:

1. It detects when the token threshold is exceeded (`approx_tokens=2396 > 500`).
2. It triggers summarization before the model call.
3. It rewrites conversation memory with a compact summary and reduced message window.

---

## 9. Results Summary

| Middleware | Tested case | Result |
|---|---|---|
| Monitoring | Logging tokens, model, and LLM calls | ✅ Correct |
| HITL | Call to `Greeting_Agent` | ✅ Correct |
| HITL | Edit `query` before approval (Greeting Agent, 5-language greeting) | ⏳ Pending manual run (see §3 additional case) |
| HITL | Call to `anonymize_text` | ✅ Correct |
| PII Detection | Email and IP redaction (regex) | ✅ Correct |
| PII Detection | Last name and ID redaction (LLM detector) | ⏳ Pending manual run (see §5 additional case) |
| Model Call Limit (`run_limit=1`) | Tool flow with `anonymize_text` | ✅ Correct (blocked at second LLM call) |
| Tool Call Limit (`run_limit=1`) | Two-sequential-tool-call flow | ⏳ Pending manual run (see §7) |
| Summarization (`trigger=('tokens', 500)`) | Long conversation memory compaction | ✅ Correct (triggered and summary generated) |

---

## 10. Conclusion

The tested middlewares work as expected:

- **Monitoring** logs execution metrics.
- **HITL** intercepts tool calls and requires human approval.
- **PII Detection** redacts sensitive data before it reaches the LLM and before it is persisted in the conversation.
- **Model Call Limit** enforces per-run limits and can intentionally block tool-based flows when the cap is too low (e.g., `1`).
- **Tool Call Limit** has no evidence yet — §7 is a placeholder pending a manual run.
- **Summarization** compacts long conversation history when token thresholds are exceeded, preserving recent context while reducing memory size.

The architecture provides stronger control over agent behaviour, especially for sensitive operations such as tool execution or handling personal data.
