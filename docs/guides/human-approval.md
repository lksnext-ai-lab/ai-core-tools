# Human approval in the public API

> Part of [Mattin AI Documentation](../README.md)

## Overview

An agent with a **Human approval** middleware stops before running the tools you choose and waits
for a person (or your application) to approve, edit or reject each call. In the public API the
paused turn is a normal result with `status: "requires_approval"`; your application shows the
request to its user (or applies its own rules) and answers it by id.

The design follows the pattern shared by LangGraph Agent Server interrupts, AG-UI interrupts and
OpenAI's `mcp_approval_request`: the run ends in a pending state with a stable id, actions are
addressed by id, answers are accepted once, and requests expire.

```
POST /chat/{agent}/call ──► 200 {status: "requires_approval", pending_approval: {approval_id, expires_at, actions}}
                                   │
         your app asks its user / applies its rules
                                   │
POST /approvals/{approval_id}/decisions ──► 200 {status: "completed", response}   (or requires_approval again)
```

## Endpoints

All under `/public/v1/app/{app_id}`, authenticated with `X-API-KEY`, rate-limited like the chat endpoints.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/chat/{agent_id}/call` | Returns `status: "completed"` or `"requires_approval"` with `pending_approval` |
| `POST` | `/chat/{agent_id}/call/stream` | SSE; a pause emits `hitl_interrupt` then `done{status: "requires_approval", approval_id}` |
| `GET` | `/approvals/{approval_id}` | Status, actions, expiry, decisions and outcome |
| `POST` | `/approvals/{approval_id}/decisions` | Answer and run the rest of the turn (same response as `/call`) |
| `POST` | `/approvals/{approval_id}/decisions/stream` | Same, streamed with the `/call/stream` SSE contract |

## Payloads

`pending_approval` (also the `hitl_interrupt` SSE event):

```json
{
  "approval_id": "3e2bce8d-e3df-4a67-83bd-6815e784d602",
  "status": "pending",
  "expires_at": "2026-10-08T14:07:54Z",
  "actions": [
    {
      "action_id": "call_Qy3k...",
      "name": "send_invoice",
      "args": {"customer_id": 42, "amount": 120.5},
      "description": "Tool execution requires approval\n\nTool: send_invoice",
      "allowed_decisions": ["approve", "edit", "reject"]
    }
  ]
}
```

Decisions — exactly one per action:

```json
{
  "decisions": [
    {"action_id": "call_Qy3k...", "type": "approve"},
    {"action_id": "call_Zx81...", "type": "edit", "args": {"customer_id": 42, "amount": 100}},
    {"action_id": "call_Pp02...", "type": "reject", "message": "Amount not authorised"}
  ]
}
```

- `edit` replaces the tool arguments (`args`, at most 64 KB, validated against the tool schema when
  available); it cannot change which tool runs.
- `reject` may carry a `message`; the agent reads it and answers without running the tool.
- The answer may be `requires_approval` again if the agent then asks for another approved tool.

## Expiry

Each human-approval middleware sets `approval_timeout_seconds` (default 1 hour, maximum
`HITL_MAX_APPROVAL_TTL_SECONDS`, default 7 days). When it passes:

- `GET /approvals/{id}` reports `status: "expired"` and decisions get `409 approval_expired`.
- The server **rejects** the pending calls (an approval is never granted automatically), the agent
  writes its final answer into the conversation (within about a minute) and the conversation
  accepts new messages again.

## Errors

Errors use `{"detail": {"code": "...", "message": "..."}}`.

| HTTP | `code` | Meaning |
|---|---|---|
| 404 | `approval_not_found` | Unknown id, or created with another API key |
| 409 | `approval_pending` | New message on a conversation that is waiting for an answer |
| 409 | `approval_already_decided` | Answered before (double submit, retry); `status` holds the outcome |
| 409 | `approval_expired` | The deadline passed; the tool was not executed |
| 409 | `approval_stale` | The conversation no longer waits for this approval |
| 409 | `approval_not_supported_in_channel` | MCP / OpenAI-compatible API / scheduled tasks cannot ask a person; the call was rejected |
| 422 | `invalid_decision` | Missing, duplicated or unknown `action_id`, decision type not allowed, invalid `args` |

## Example (Python)

```python
import httpx

BASE = "https://mattin.example.com/public/v1/app/1"
HEADERS = {"X-API-KEY": API_KEY}

result = httpx.post(f"{BASE}/chat/7/call", headers=HEADERS,
                    data={"message": "Send the invoice to ACME"}, timeout=120).json()

while result["status"] == "requires_approval":
    pending = result["pending_approval"]
    decisions = [
        {"action_id": a["action_id"], "type": "approve" if ask_user(a) else "reject"}
        for a in pending["actions"]
    ]
    result = httpx.post(f"{BASE}/approvals/{pending['approval_id']}/decisions",
                        headers=HEADERS, json={"decisions": decisions}, timeout=120).json()

print(result["response"])
```

## Security notes

- Only the API key that started the conversation can read or answer its approvals.
- Each approval is answered once: concurrent or repeated answers get `409`, never a second execution.
- Arguments shown to the reviewer are the exact ones that will run (or the edited ones); tool
  arguments are not written to logs.
- Changing an agent's approval rules cancels its pending approvals.

## See also

- [Middleware behaviour and test checklist](../testing/middleware.md)
- [Public API](../api/public-api.md)
