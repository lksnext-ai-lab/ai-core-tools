# A2A TCK Remediation Design

> Part of [Mattin AI Documentation](../README.md)
>
> Related: [A2A Integration](a2a-integration.md)

## Overview

This document describes the high-level design changes required to close the **real** A2A compatibility gaps found when running `a2a-tck` against the Mattin AI implementation.

The goal is not to redesign the whole A2A stack. The goal is to keep the current SDK-based adapter approach and make targeted changes so that:

- Mattin AI behaves like a compliant A2A task-based server
- multi-turn task continuation works reliably
- cancellation and resubscription behave as A2A clients expect
- streaming responses use standards-compatible SSE semantics
- discovery works without a custom compatibility shim

## Scope

This remediation covers the failures that remained after correcting the test harness setup so the TCK was exercising the real Mattin AI endpoint rather than a shim artifact.

### Real mandatory failures

- `test_core_method_mapping_compliance`
- `test_message_send_continue_task`
- `test_task_history_length`
- `test_tasks_cancel_valid`

### Real capability failures

- `test_message_send_continue_with_contextid`
- `test_tasks_resubscribe`
- `test_sse_header_compliance`

### Out of scope for remediation

- `test_invalid_authentication` from the TCK capability suite

That test fails before reaching Mattin AI because the TCK constructs an invalid HTTP header value with leading whitespace. No Mattin AI change should be driven by that result.

## Additional Interoperability Gap

The corrected TCK run focused on task and streaming semantics, but one additional compatibility gap was also observed:

- Mattin AI exposes agent cards only at agent-specific paths such as `/.well-known/a2a/apps/{app_slug}/agents/{agent_id}/agent-card.json`
- many generic A2A tools and TCK flows expect root discovery at `/.well-known/agent-card.json`

This is not one of the corrected test failures listed above, but it is still a real interoperability issue and should be fixed in the same workstream.

## Root Cause Summary

The failures cluster into three design problems:

1. **Task identity is modeled as a single execution run instead of a durable conversation thread.**
2. **`message/send` completes too eagerly, which makes continuation and cancellation race-prone or impossible.**
3. **Streaming state is not replayable, so `tasks/resubscribe` and SSE compliance are incomplete.**

The current implementation stores a single mutable `A2ATask` snapshot and derives continuation from the latest task metadata. That works for one-shot execution, but it does not provide enough structure for:

- reusing the same `taskId` across multiple user turns
- keeping a bounded history for `historyLength`
- canceling an in-flight turn before it becomes terminal
- resubscribing to a live or recently completed stream

## Design Goals

- Keep the official Python A2A SDK as the protocol shell.
- Preserve Mattin AI conversations as the memory source of truth.
- Treat A2A `taskId` as a stable external thread identifier.
- Support follow-up `message/send` calls against an existing `taskId`.
- Make `tasks/cancel` reliable for active work.
- Make `tasks/resubscribe` always return SSE when streaming is declared.
- Add root Agent Card discovery without removing the current agent-specific routes.

## Proposed Design

### 1. Discovery Compatibility

#### Problem

Mattin AI currently requires clients to know the app slug and agent ID before they can fetch an Agent Card.

#### Required change

Add root discovery endpoints:

- `GET /.well-known/agent-card.json`
- `GET /.well-known/agent.json` as a backward-compatible alias

#### Resolution policy

Because Mattin AI can expose more than one A2A agent, root discovery must resolve a single default card in a deterministic way. The design should introduce one of:

- a deployment-level default A2A agent
- an app-level default A2A agent
- a strict single-agent-only root discovery policy that returns `404` or `409` when ambiguous

#### Impacted backend areas

- [backend/routers/a2a.py](/home/jjrodrig/projects/ai-core-tools/backend/routers/a2a.py)
- [backend/services/a2a_agent_card_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/a2a_agent_card_service.py)

### 2. Task Model Refactor

#### Problem

The current [A2ATask](/home/jjrodrig/projects/ai-core-tools/backend/models/a2a_task.py) row stores only one mutable task payload. That is not sufficient for multi-turn continuation, history reconstruction, or replayable streaming.

#### Required change

Split protocol persistence into:

- a **stable task thread record**
- an **execution turn record**
- a **stream event buffer**

#### Recommended data model

#### `A2ATask`

Represents the stable external A2A task thread:

- `task_id`
- `context_id`
- `app_id`
- `agent_id`
- `conversation_id`
- `current_state`
- `active_turn_id`
- `cancel_requested_at`
- `terminal_at`

#### `A2ATaskTurn`

Represents one user turn executed under the same `task_id`:

- `turn_id`
- `task_id`
- `request_message_id`
- `submitted_at`
- `started_at`
- `completed_at`
- `state`
- `request_payload`
- `response_payload`

#### `A2ATaskEvent`

Represents ordered task or artifact updates for replay and resubscription:

- `task_id`
- `turn_id`
- `sequence_no`
- `event_kind`
- `event_payload`
- `is_terminal`
- `created_at`

#### Why this change is needed

This lets Mattin AI treat:

- **conversation** as memory state
- **task** as external protocol thread identity
- **turn** as one execution attempt inside that thread
- **event buffer** as the replay source for SSE and history projection

### 3. `message/send` Must Become Task-First

#### Problem

`message/send` currently waits for the agent to finish and often returns a task that is already `completed`. That causes:

- cancellation to fail because the task is already terminal
- continuation by `taskId` to fail because the SDK sees a terminal task
- history-building tests to fail because follow-up messages are rejected

#### Required change

Adopt **task-first, asynchronously advancing** semantics for `message/send`:

1. validate the request
2. resolve or create the stable `A2ATask`
3. create a new `A2ATaskTurn`
4. persist initial task state as `submitted` or `working`
5. return the task promptly
6. continue execution asynchronously and update the task as results arrive

#### Continuation rule

If a new message contains an existing `taskId`:

- reuse the same stable A2A task thread
- reuse the same Mattin AI `conversation_id`
- create a **new turn** under that task
- do **not** reject the message just because the previous turn completed

#### `contextId` rule

If a request includes both `taskId` and `contextId`, the server should:

- verify they belong to the same task thread
- reject mismatches with a protocol validation error
- otherwise continue the same task thread

#### Impacted backend areas

- [backend/services/a2a_agent_executor.py](/home/jjrodrig/projects/ai-core-tools/backend/services/a2a_agent_executor.py)
- [backend/services/a2a_task_store.py](/home/jjrodrig/projects/ai-core-tools/backend/services/a2a_task_store.py)
- [backend/repositories/a2a_task_repository.py](/home/jjrodrig/projects/ai-core-tools/backend/repositories/a2a_task_repository.py)

### 4. `tasks/get` and `historyLength` Must Be Built From Turns

#### Problem

`historyLength` cannot work correctly while Mattin AI only keeps a single mutable task snapshot.

#### Required change

Make `tasks/get` reconstruct the task view from:

- the stable `A2ATask`
- ordered `A2ATaskTurn` records
- ordered `A2ATaskEvent` records

#### History projection rules

- `history` should represent the bounded message/task history of the task thread
- `historyLength` should apply after ordering the history from newest to oldest or oldest to newest, whichever the SDK contract requires consistently
- the response should still surface the latest task state as the current task snapshot

This keeps `tasks/get` aligned with a durable conversation thread rather than a one-off run.

### 5. Cancellation Must Target the Active Turn

#### Problem

`tasks/cancel` currently fails in the TCK because the task has already reached `completed` before cancellation is attempted.

#### Required change

Cancellation should operate on the **active turn** of a task thread.

#### Proposed behavior

- if the task has an active non-terminal turn, mark cancellation requested
- stop emitting further non-terminal events
- if underlying runtime interruption is available, stop execution
- if interruption is not available, finalize the turn as canceled on a best-effort basis once the platform can safely stop delivery

#### Important design constraint

The fix is not only in `cancel()`. The deeper fix is that `message/send` must stop returning already-completed tasks so often. Without that change, cancellation will always race against near-instant completion.

### 6. `tasks/resubscribe` Must Always Return SSE

#### Problem

Mattin AI declares streaming support, but `tasks/resubscribe` currently returns plain JSON in the failing scenario instead of an SSE stream.

#### Required change

`tasks/resubscribe` should always negotiate an SSE response when the task supports streaming.

#### Proposed behavior

#### If the task is still active

- attach the client to the live event queue
- continue streaming subsequent events

#### If the task has already completed recently

- replay buffered events from `A2ATaskEvent`
- at minimum replay the terminal event
- close the SSE stream after replay finishes

#### If the task does not exist

- return the proper task-not-found protocol error

#### Why replay is needed

The TCK and real clients both assume that resubscription is meaningful even if the original stream was interrupted late in the task lifecycle.

### 7. SSE Header Compliance

#### Problem

The stream currently returns `Cache-Control: no-store`, but the TCK expects `no-cache` to be present for SSE behavior.

#### Required change

For `message/stream` and `tasks/resubscribe`, ensure the response headers include:

- `Content-Type: text/event-stream`
- `Cache-Control: no-cache`
- `X-Accel-Buffering: no`

Optional additions:

- `Cache-Control: no-cache, no-store`
- `Connection: keep-alive` when compatible with the serving stack

The important point is that `no-cache` must be present whenever `Cache-Control` is emitted for SSE.

### 8. Executor and Store Responsibilities After Refactor

#### Executor

The executor should become responsible for:

- resolving task thread versus new task creation
- creating new turn records
- appending task events
- emitting status transitions without assuming that task terminality ends the whole thread

#### Task store

The task store should become responsible for:

- reconstructing the current task snapshot
- returning bounded history
- surfacing active-turn metadata for cancellation and resubscription
- loading replayable event sequences

### 9. Rollout Plan

#### Phase 1: Discovery and protocol headers

- add root Agent Card discovery
- align SSE headers

#### Phase 2: Persistence refactor

- add task-turn and task-event persistence
- migrate current `A2ATask` usage to thread-level state

#### Phase 3: Task-first execution

- make `message/send` create non-terminal tasks first
- move execution progression to asynchronous updates

#### Phase 4: Cancellation and resubscription

- cancel active turns
- replay buffered events over SSE for `tasks/resubscribe`

#### Phase 5: Validation

- add Mattin AI integration tests for continuation, cancel, resubscribe, and root discovery
- rerun `a2a-tck` mandatory and capabilities categories

## Acceptance Criteria

The remediation is complete when:

- root Agent Card discovery works without a compatibility shim
- `message/send` supports follow-up messages against the same `taskId`
- `tasks/get` supports `historyLength` over multi-turn task history
- `tasks/cancel` succeeds for newly created active tasks
- `tasks/resubscribe` returns SSE and can replay the terminal event
- streaming responses include `Cache-Control: no-cache`

Target TCK outcome:

- all real mandatory failures resolved
- all real capability failures resolved
- the only remaining known issue is the external TCK header-construction bug in `test_invalid_authentication`
