# A2A Agent Design

> Part of [Mattin AI Documentation](../README.md)

## Overview

This document describes the design for registering external A2A-compatible agents as first-class agents in MattinAI.

The goal is to make an imported A2A agent behave like any other agent in the platform from the end-user perspective. Once registered, it must appear in the agent catalog, be executable through the same chat and streaming APIs, participate in existing agent management flows, and be observable through LangSmith in the same way as local agents.

This design focuses on functional behavior and project integration. It does not define implementation code.

## Goal

Enable users to register an external A2A agent as a MattinAI agent by importing one specific skill from a public A2A agent card URL.

The resulting imported agent must:

- behave as a first-class MattinAI agent
- be created from the standard agent creation form
- expose the imported remote capability as the agent's primary execution backend
- preserve the existing MattinAI agent lifecycle and monitoring experience
- use the official A2A SDKs for protocol integration, with `@a2a-js/sdk` in the frontend for discovery and `a2a-python` in the backend for execution, refresh, and authoritative validation

## Confirmed Product Decisions

- Only public agent cards are supported. This follows the A2A standard assumptions for discovery.
- If an agent card exposes multiple skills, the user selects exactly one skill to import as one MattinAI agent.
- Metadata derived from the agent card, such as name, description, and icon, remains editable after import.
- If the upstream agent card changes or becomes unavailable, MattinAI keeps a cached local copy of imported metadata and exposes a visible health state.
- Imported A2A agents should ideally be allowed to use native MattinAI capabilities. This document includes an impact analysis and a recommended operating model.

## Non-Goals

- Implementing MattinAI as an A2A server in this feature
- Supporting private or authenticated agent cards
- Importing all remote skills as separate agents in one step
- Replacing the existing A2A client feature that consumes external A2A agents as tools inside another agent
- Defining wire-level protocol details already covered by the official SDK and the A2A specification

## User Experience

### Agent Registration Flow

Agent registration continues to start from the existing agent creation page.

The form introduces a source selection step:

- `Local`
- `External`

When `External` is selected, the first supported external source is `A2A Agent`.

The A2A registration flow is:

1. The user opens the standard Create Agent form.
2. The user selects `External`.
3. The user selects `A2A Agent`.
4. The user provides the public URL to the remote agent card.
5. The frontend loads the public agent card using `@a2a-js/sdk` and extracts its metadata and skills directly in the browser.
6. MattinAI presents the remote agent metadata and the list of importable skills.
7. The user selects one skill to import.
8. MattinAI pre-populates the agent form with data derived from the selected skill and the agent card.
9. The user can edit the visible MattinAI metadata before saving.
10. On save, the backend performs authoritative validation of the submitted A2A source configuration.
11. MattinAI saves the imported A2A agent as a regular platform agent with an external execution backend.

### User Expectations After Import

After creation, the imported A2A agent should look and feel like any other agent:

- it appears in the agents list
- it has a detail page and playground
- it is invoked through the same chat endpoints
- it can be monitored through LangSmith
- it can expose health and sync status in the UI

The user should not need to understand whether the execution is local or delegated to a remote A2A agent unless they explicitly inspect source details.

## Conceptual Model

### First-Class Agent Principle

An imported A2A agent is still a MattinAI `Agent` in the core domain.

The distinction is not whether it is an agent, but how its primary execution is fulfilled:

- `Local agent`: execution is driven by MattinAI's local LangGraph and configured LLM
- `A2A agent`: execution is fulfilled by a remote A2A-compatible agent selected from an imported skill

This preserves the current platform mental model. Users manage one unified concept of "agent" while the backend distinguishes between local and external execution strategies.

### Remote Skill as the Executable Unit

The imported entity is not the full remote card as a single opaque object. The executable unit is one selected remote skill.

This means:

- one remote card may produce multiple MattinAI agents over time
- each imported agent stores the source card identity plus the selected skill identity
- the imported agent name and description can start from remote metadata but become MattinAI-managed fields afterward

## Recommended Domain Design

### Agent Type Strategy

MattinAI should preserve the existing `Agent` table as the canonical first-class record and introduce an A2A-specific extension record linked one-to-one to `Agent`.

Recommended shape:

- `Agent` remains the platform-visible entity
- `A2AAgent` or equivalent extension table stores external-source details

This is preferable to storing all A2A fields directly in `Agent` because:

- it keeps the base model cleaner
- it avoids null-heavy generic columns
- it aligns with the existing pattern already used for `OCRAgent`
- it leaves room for future external source types beyond A2A

### A2A-Specific Data

The A2A extension record should capture at least:

- owning `agent_id`
- agent source type: `a2a`
- public agent card URL used at registration time
- normalized remote agent identifier if present in the card
- selected remote skill identifier
- selected remote skill name
- cached remote agent metadata snapshot
- cached selected skill metadata snapshot
- synchronization state
- health state
- last successful refresh timestamp
- last refresh attempt timestamp
- last refresh error summary
- optional remote documentation URL
- optional remote icon URL

### Health Model

Health should be visible and operationally meaningful.

Suggested states:

- `healthy`: last refresh and execution checks succeeded
- `degraded`: execution can continue from cached registration data, but refresh or validation recently failed
- `unreachable`: the remote card or remote execution endpoint is currently unavailable
- `invalid`: the imported skill is no longer compatible or no longer present in the card

Health is not the same as publication or enablement. An agent may remain enabled while degraded if cached execution metadata is still considered usable.

## Backend Integration

### Agent Creation and Update

The existing internal agent creation flow already centralizes agent persistence in:

- [backend/routers/internal/agents.py](/home/jjrodrig/projects/ai-core-tools/backend/routers/internal/agents.py)
- [backend/services/agent_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/agent_service.py)
- [backend/schemas/agent_schemas.py](/home/jjrodrig/projects/ai-core-tools/backend/schemas/agent_schemas.py)

The design should extend this flow rather than create a separate parallel registration path.

Required functional additions:

- extend the create/update schema with agent source information
- allow the form to submit `Local` or `External`
- when source is `External/A2A`, require a card URL, selected skill, and submitted discovery snapshot from the frontend
- persist the base `Agent` first, then persist the A2A extension record
- allow later edits to MattinAI-managed metadata without losing the remote source linkage
- re-validate the A2A source configuration in the backend before final persistence

### Agent Retrieval

The existing detail response returned by `get_agent_detail()` should be expanded so the UI can render external agent state.

The detail payload should include:

- agent source type
- external subtype `a2a`
- imported card URL
- imported skill identity and display name
- cached remote metadata
- sync and health status
- refresh capability flags

The list response may also include a compact source badge and health indicator so imported A2A agents are distinguishable in administration screens without appearing second-class.

### Registration Validation Model

The create form needs a preview step before final save, but that preview does not need to come from the backend.

Recommended interaction model:

- the frontend uses `@a2a-js/sdk` to resolve the public agent card and extract available skills
- the frontend renders the discovery result immediately without a MattinAI backend round-trip for card inspection
- the backend receives the selected skill plus the discovery snapshot when the user saves
- the backend performs authoritative validation before persistence so the browser is not the trust boundary

Recommended backend validation on save:

- verify the submitted card URL is still reachable
- verify the selected skill still exists in the card
- normalize and persist the canonical source metadata used by MattinAI
- reject mismatches between submitted discovery data and authoritative validation when they affect correctness

### Refresh Endpoint

Imported A2A agents need a manual and optionally automatic refresh path.

Recommended capability:

- refresh remote card metadata on demand
- reconcile the currently selected skill
- update the cached snapshot
- update health and sync status
- preserve local editable fields unless the user explicitly chooses to reapply remote values

This supports the product decision that imported metadata is editable while still allowing re-synchronization with upstream changes.

## Execution Design

### Execution Principle

An imported A2A agent must execute through the same MattinAI chat and streaming entry points already used for local agents:

- [backend/services/agent_execution_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/agent_execution_service.py)
- [backend/services/agent_streaming_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/agent_streaming_service.py)

The key design decision is to keep the existing platform envelope and swap the execution strategy underneath it.

Recommended execution model:

1. MattinAI resolves the requested `Agent`.
2. If the agent source is local, the current LangGraph-based execution path runs unchanged.
3. If the agent source is A2A, MattinAI routes execution through an A2A executor that uses the official SDK to call the imported remote skill.
4. MattinAI still owns conversation persistence, file references, API-level auth, auditability, and response normalization.

### A2A Executor Responsibility

The A2A executor should be a focused component responsible for:

- creating the SDK client
- calling the imported remote skill
- mapping MattinAI requests into the A2A request model
- collecting the remote response
- normalizing the result into MattinAI chat and streaming payloads
- surfacing remote failures as platform-standard errors

This keeps A2A-specific behavior out of the generic agent service and lets the rest of the system continue to treat the result as a normal agent turn.

### Streaming

If the SDK supports streamed task or message updates for the selected interaction mode, MattinAI should relay them through the existing SSE model.

If streamed remote updates are not available for a specific remote agent or interaction mode, MattinAI should still support the standard non-streaming execution path and may degrade streaming to buffered delivery while preserving the same frontend contract.

### Conversation Memory

MattinAI should continue to own conversation persistence for imported A2A agents at the platform level.

Recommended behavior:

- MattinAI stores conversation history exactly as it does for local agents
- remote A2A agents receive the turn context that MattinAI chooses to send
- MattinAI memory settings remain available as a platform concern unless explicitly restricted later

This preserves consistent user expectations and avoids treating remote agents as stateless exceptions in the product.

## LangSmith Observability

The existing codebase already attaches LangSmith tracing around local agent execution in:

- [backend/tools/agentTools.py](/home/jjrodrig/projects/ai-core-tools/backend/tools/agentTools.py)
- [backend/services/agent_execution_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/agent_execution_service.py)
- [backend/services/agent_streaming_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/agent_streaming_service.py)

Imported A2A agents should preserve the same observability promise.

Recommended tracing model:

- create a MattinAI trace for every imported A2A invocation
- record the A2A executor call as the main execution step
- attach remote card URL, selected skill identifier, source type, and health state as trace metadata
- record request/response lifecycle, latency, and failures

From the user perspective, the imported A2A agent remains visible in LangSmith like any other agent. The trace internals differ, but the monitoring surface stays unified.

If the remote A2A provider emits its own traces, those remain external to MattinAI unless explicit cross-linking is added later.

## Frontend Integration

The existing agent form in [frontend/src/pages/AgentFormPage.tsx](/home/jjrodrig/projects/ai-core-tools/frontend/src/pages/AgentFormPage.tsx) is the natural integration point.

The frontend should use `@a2a-js/sdk` as the discovery layer for public A2A agent cards. This moves the initial card inspection and skill extraction to the browser and avoids using the MattinAI backend only to obtain preview information.

### Form Changes

The form should add:

- source selector: `Local` or `External`
- external subtype selector when `External` is chosen, initially `A2A Agent`
- input for public agent card URL
- action to load the card in-browser through `@a2a-js/sdk`
- skill picker populated from the discovered card response
- preview area showing remote metadata and health
- fields showing which values were imported versus locally edited

### Frontend Discovery Behavior

The frontend discovery step should:

- resolve the public agent card URL directly from the browser
- extract normalized agent metadata and the list of remote skills
- derive a local preview model that can populate the form
- submit the chosen skill and discovery snapshot as part of agent creation

This avoids using the backend as a discovery proxy while still allowing the backend to remain authoritative for persistence and operational checks.

### Browser Constraints

Moving discovery to the frontend introduces browser-level constraints that should be explicit in the design:

- the remote card endpoint must be reachable from the user's browser
- the remote endpoint must allow cross-origin access for browser fetches
- failures caused by CORS, TLS, or browser networking should be surfaced as discovery errors in the UI

Because of this, backend validation remains necessary on save and refresh even if the browser already loaded the card successfully.

### Editing Behavior

Because imported metadata is editable, the form should separate:

- local editable fields managed by MattinAI
- source linkage fields managed by the A2A integration

Recommended UX:

- name, description, and icon-related display fields are editable
- card URL and selected skill are treated as source configuration
- a refresh action lets the user re-read the remote card
- the UI clearly shows whether displayed values come from local edits or the latest remote snapshot

### List and Detail Screens

Imported A2A agents should expose lightweight administrative signals:

- source badge such as `External / A2A`
- health badge
- last sync timestamp
- optional warning when the selected remote skill is no longer present upstream

These signals are for transparency, not for creating a different user workflow.

## Interaction with Existing A2A Client Feature

The existing A2A client feature and this new first-class agent feature should coexist but remain conceptually separate.

Current A2A client behavior:

- MattinAI local agents can consume external A2A agents as tools inside a broader workflow

New A2A agent behavior:

- one external A2A skill is imported and registered as an agent in its own right

They may reuse shared infrastructure:

- official A2A SDK client setup
- agent card fetching and normalization
- request and response mapping
- error handling
- health checking

But they should remain different product concepts because one is a tool-consumption pattern and the other is a platform registration pattern.

## Impact of Allowing Native MattinAI Capabilities

The user preference is to ideally allow imported A2A agents to use native MattinAI capabilities as well. This is feasible, but it changes the semantics of what an imported agent means.

### Capability Categories

Native capabilities fall into two different groups.

Group 1: platform envelope capabilities

- conversation memory
- LangSmith tracing
- agent listing and permissions
- marketplace visibility
- rate limits and quotas

These should be allowed by default because they belong to MattinAI as the hosting platform, not to the remote skill implementation.

Group 2: execution-shaping capabilities

- silos
- output parsers
- local tool agents
- MCP configs
- skills
- code interpreter and server-side tools

These can materially alter how the imported agent behaves.

### Main Architectural Risk

If all execution-shaping capabilities are enabled directly on an imported A2A agent, the imported agent stops being a clean representation of a remote capability and becomes a hybrid orchestration wrapper.

That hybrid model has trade-offs:

- clearer power for advanced users
- harder reasoning about responsibility boundaries
- more difficult debugging when failures come from the remote agent versus local augmentations
- more ambiguous observability because one "agent" may partly execute remotely and partly locally
- more complicated user expectations around portability and reproducibility

### Recommended Policy

Allow native MattinAI capabilities in phases instead of opening all of them immediately.

Recommended default policy:

- allow platform envelope capabilities by default
- allow non-invasive administrative capabilities by default
- defer or explicitly constrain execution-shaping capabilities

Recommended first release behavior:

- allowed: memory, LangSmith, marketplace metadata, quotas, visibility, health, refresh, conversations
- disallowed initially: local tool agents, MCP configs, skills, silo retrieval, output parser enforcement, code interpreter, provider-native server tools

This keeps the imported A2A agent faithful to the remote skill while preserving the first-class platform experience.

### Future Hybrid Mode

If product requirements later demand richer augmentation, a second operating mode can be introduced:

- `Pure external agent`: remote skill is the sole execution backend
- `Hybrid wrapped agent`: MattinAI surrounds the remote skill with local capabilities

That distinction should be explicit in configuration and traces. It should not be silently implied by attaching local resources to an imported agent.

## Data Synchronization Strategy

Imported A2A agents need two different kinds of data:

- stable registration data used to keep the local agent working
- refreshable remote metadata used to show health and detect drift

Recommended synchronization rules:

- store a full local snapshot of the card and selected skill at registration time
- use the snapshot for display fallback and compatibility checks
- on refresh, compare upstream card identity and skill availability with the stored snapshot
- if upstream metadata changes, update cached remote fields and mark drift status
- do not overwrite user-edited MattinAI display metadata automatically

The registration snapshot may originate in frontend discovery, but the persisted canonical snapshot should be the one accepted by backend validation.

This approach supports resilience when the remote card is unavailable and supports transparent change detection.

## Export and Import Considerations

MattinAI already supports agent export and import through:

- [backend/services/agent_export_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/agent_export_service.py)
- [backend/services/agent_import_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/agent_import_service.py)

Imported A2A agents should integrate with these flows.

Recommended behavior:

- export the base agent plus A2A source metadata
- export the cached snapshot used for resilience
- never assume the target environment can dereference the remote card immediately
- on import, preserve the agent as an imported A2A agent
- mark health as unknown or pending until the new environment refreshes the card

This keeps exports deterministic and avoids making import success depend on immediate remote availability.

## Error Handling

The design should distinguish between:

- registration-time validation failures
- refresh-time failures
- execution-time failures

Recommended principles:

- registration fails if the card cannot be fetched or the selected skill cannot be validated
- refresh failure does not necessarily disable the agent if the last known configuration is still usable
- execution failure should surface as a standard MattinAI agent error with A2A-specific diagnostics in logs and traces

## Security and Trust Boundaries

Because only public agent cards are supported, this feature avoids the complexity of storing remote credentials in the initial scope.

Even so, the remote service remains outside MattinAI's trust boundary.

Operationally this means:

- the remote card content should be validated and normalized before persistence
- only the selected skill should be bound to the imported agent
- remote metadata should be treated as untrusted display content
- health checks and execution should use timeouts and controlled error handling

## Recommended Delivery Scope

### Phase 1

- register external A2A agents from the existing Create Agent form
- fetch public card URL through the official SDK
- allow one-skill import as one agent
- persist A2A source metadata and cached snapshot
- execute imported A2A agents through the existing chat and streaming APIs
- preserve LangSmith observability
- expose visible health and last sync status
- allow editing local display metadata

### Phase 2

- manual refresh and drift inspection UX
- richer health diagnostics
- export/import support for imported A2A agents
- optional background refresh jobs

### Phase 3

- explicit hybrid mode for safe local augmentation
- policy-driven support for selected native capabilities on top of imported A2A agents

## Recommended Project Integration Summary

The most natural integration path in the current codebase is:

- extend the agent domain rather than introducing a parallel external-agent domain
- add an A2A-specific one-to-one extension model similar in spirit to the OCR specialization
- add registration preview and refresh endpoints
- route execution through a dedicated A2A executor while preserving current chat and streaming APIs
- keep LangSmith tracing at the MattinAI platform layer
- treat imported A2A agents as first-class agents everywhere in the UI and API

This design gives MattinAI a clean first release that is consistent with the current architecture and leaves room for a future hybrid execution model without overloading the initial feature.
