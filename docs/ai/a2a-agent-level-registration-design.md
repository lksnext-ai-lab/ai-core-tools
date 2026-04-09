# A2A Agent-Level Registration Design

> Review of the current MattinAI A2A import implementation and a proposed shift from skill-level import semantics to agent-level registration.

## Summary

The current implementation already persists the remote A2A agent identity and its full card snapshot, but the product contract still treats the imported unit as "one selected remote skill".

That mismatch shows up in the create/update schema, refresh behavior, UI copy, tests, tracing metadata, and the existing design document in [docs/ai/a2a-agent-design.md](/home/jjrodrig/projects/ai-core-tools/docs/ai/a2a-agent-design.md).

The A2A protocol shape is closer to:

- one remote agent card
- one primary interaction URL
- one set of agent-level capabilities and security requirements
- many advertised skills describing capabilities exposed by that same agent

MattinAI should therefore register an imported A2A integration at the remote agent level and treat skills as cached capability metadata, not as the imported identity.

## Review of the Current Implementation

### What Already Aligns Well

The current backend is not fully modeled as an `agent-skill` pair in storage.

- [backend/models/a2a_agent.py](/home/jjrodrig/projects/ai-core-tools/backend/models/a2a_agent.py) already stores `card_url`, `remote_agent_id`, and a full `remote_agent_metadata` snapshot.
- [backend/services/a2a_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/a2a_service.py) resolves and persists the whole agent card, including the full `skills` array inside `remote_agent_metadata`.
- [backend/services/a2a_executor_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/a2a_executor_service.py) connects to the remote agent through the card URL and transport negotiation. It does not derive a different endpoint per skill.

This means the implementation is already structurally close to agent-level registration.

### Where the Implementation Is Still Skill-Centric

Several important parts of the system still assume that the imported entity is one selected skill:

- [backend/schemas/agent_schemas.py](/home/jjrodrig/projects/ai-core-tools/backend/schemas/agent_schemas.py) requires `selected_skill_id` in `A2AAgentSourceConfigSchema`.
- [backend/services/a2a_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/a2a_service.py) validates persistence against one selected skill and stores `remote_skill_id`, `remote_skill_name`, and `remote_skill_metadata`.
- [backend/services/a2a_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/a2a_service.py) marks the imported record `invalid` if that selected skill disappears during refresh.
- [frontend/src/pages/AgentFormPage.tsx](/home/jjrodrig/projects/ai-core-tools/frontend/src/pages/AgentFormPage.tsx) tells the user to choose exactly one remote skill before saving.
- [backend/services/a2a_executor_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/a2a_executor_service.py) sends `imported_skill_id` and `imported_skill_name` as request metadata even though they are MattinAI-specific hints, not A2A routing primitives.
- [docs/ai/a2a-agent-design.md](/home/jjrodrig/projects/ai-core-tools/docs/ai/a2a-agent-design.md) explicitly states that one selected remote skill is the imported executable unit.

### Protocol Observation

The bundled A2A SDK models an `AgentCard` as a single agent manifest with:

- one `url`
- one preferred transport
- one set of card-level metadata
- many `skills`

In the local dependency, `AgentCard.skills` is described as "the set of skills, or distinct capabilities, that the agent can perform", while `AgentCard.url` is the preferred endpoint URL for interacting with the agent.

That strongly suggests skills are descriptive capabilities of one agent, not independent remote registrations.

## Main Findings

### Finding 1

The persistence model is already agent-first, but the API contract is skill-first.

Impact:
MattinAI stores the remote agent identity, yet still forces callers to bind the record to one selected skill. That creates unnecessary coupling and makes the public contract misleading.

### Finding 2

Execution does not actually use skill-level routing.

Impact:
The executor connects to one remote card URL and transport. The selected skill is only carried as MattinAI request metadata, so the current model implies stronger protocol meaning than the code actually uses.

### Finding 3

Refresh health is tied to skill drift instead of agent viability.

Impact:
If the remote agent remains healthy but one advertised skill changes or disappears, MattinAI marks the imported agent `invalid`. That is too strict for an agent-level integration.

### Finding 4

The current UX encourages users to think they are importing a remote skill endpoint.

Impact:
This does not match the actual runtime behavior and makes future multi-skill or capability-aware UX harder to design cleanly.

## Proposed Target Model

### Core Principle

An imported A2A record in MattinAI should represent one remote A2A agent, discovered from one agent card URL.

The imported record should keep:

- the remote agent identity
- the canonical card snapshot
- the advertised skill catalog as metadata
- the auth configuration used to call the remote agent
- sync and health information

The imported record should not require a single selected skill to remain valid.

### Role of Skills

Skills should be treated as capability metadata used for:

- discovery and user understanding
- display in detail and admin views
- optional prompting or filtering hints in the future
- drift detection when the remote capability catalog changes

Skills should not define the identity of the imported MattinAI agent.

### Product Semantics

After this change:

- one remote A2A card maps to one imported MattinAI A2A agent
- the imported MattinAI agent represents the remote agent as a whole
- the skill list is visible metadata, not the import key

This is the cleanest match to the A2A card model and the current executor behavior.

## Required Changes

### 1. Domain and Persistence

Recommended direction:

- keep [backend/models/a2a_agent.py](/home/jjrodrig/projects/ai-core-tools/backend/models/a2a_agent.py) as the A2A extension table
- keep `card_url`, `remote_agent_id`, `auth_config`, `remote_agent_metadata`, `sync_status`, `health_status`, and refresh timestamps
- remove `remote_skill_id`, `remote_skill_name`, and `remote_skill_metadata`

Recommended schema change:

- delete the `remote_skill_*` columns from the database model and migrations
- treat `remote_agent_metadata["skills"]` as the authoritative skill catalog

Because this functionality has not been released yet, there is no need to preserve backward compatibility for the skill-specific persistence model.

### 2. Create and Update API

Update [backend/schemas/agent_schemas.py](/home/jjrodrig/projects/ai-core-tools/backend/schemas/agent_schemas.py):

- remove the requirement for `selected_skill_id`
- rename the A2A source payload so it is clearly agent-level
- accept the submitted card snapshot and auth config without requiring a chosen skill

Recommended source payload shape:

```json
{
  "card_url": "https://example.com/.well-known/agent-card.json",
  "card_snapshot": { "...": "..." },
  "auth_config": { "...": "..." }
}
```

If MattinAI still wants a local UX hint such as "primary displayed capability", it should be optional and explicitly non-authoritative.

### 3. Validation and Refresh Logic

Update [backend/services/a2a_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/a2a_service.py):

- `validate_source_config()` should validate card-level reachability, transport compatibility, and auth compatibility
- validation should no longer fail because no skill was selected
- refresh should update the cached skill catalog as part of `remote_agent_metadata`
- refresh should not mark the record `invalid` solely because a previously stored skill disappeared

Recommended health interpretation:

- `healthy`: agent card reachable and execution checks succeed
- `degraded`: card reachable but skill catalog drifted or non-critical metadata changed unexpectedly
- `unreachable`: card or endpoint cannot currently be reached
- `invalid`: the remote card is structurally incompatible with MattinAI's A2A integration

Skill drift should become metadata drift, not identity loss.

### 4. Execution Semantics

Update [backend/services/a2a_executor_service.py](/home/jjrodrig/projects/ai-core-tools/backend/services/a2a_executor_service.py):

- stop presenting the selected skill as the primary execution identity
- remove `imported_skill_id` and `imported_skill_name` request metadata unless there is a proven downstream consumer for them
- keep agent-level trace metadata such as `card_url`, `remote_agent_id`, `health_status`, and `sync_status`

If a future remote provider needs capability hints, those should be modeled as optional MattinAI extensions, not as the core import identity.

### 5. Frontend UX

Update [frontend/src/pages/AgentFormPage.tsx](/home/jjrodrig/projects/ai-core-tools/frontend/src/pages/AgentFormPage.tsx):

- change the form from "select one remote skill to import" to "review the remote agent and its advertised skills"
- keep the discovered skill list visible as informational metadata
- prefill name and description from agent-level metadata first
- remove save-time validation that blocks persistence when no skill is selected
- replace detail copy such as "Imported skill" and "selected remote skill" with agent-level wording

Recommended create flow:

1. Enter card URL.
2. Load remote card.
3. Review remote agent metadata.
4. Review advertised skills.
5. Save the imported remote agent.

### 6. Response Schemas and Detail Views

Update the agent detail response so the frontend can render the capability catalog directly from the persisted card snapshot.

Recommended detail behavior:

- keep `a2a_config.remote_agent_metadata`
- expose a normalized `skills` or `advertised_skills` view derived from the card snapshot
- remove `remote_skill_name` and `remote_skill_metadata` from the required response contract

### 7. Tests

Update unit and integration tests that currently assert skill-bound semantics, especially in:

- [tests/unit/services/test_a2a_service.py](/home/jjrodrig/projects/ai-core-tools/tests/unit/services/test_a2a_service.py)
- [tests/unit/services/test_a2a_executor_service.py](/home/jjrodrig/projects/ai-core-tools/tests/unit/services/test_a2a_executor_service.py)
- [tests/unit/services/test_agent_service.py](/home/jjrodrig/projects/ai-core-tools/tests/unit/services/test_agent_service.py)
- [tests/integration/routers/internal/test_agents.py](/home/jjrodrig/projects/ai-core-tools/tests/integration/routers/internal/test_agents.py)

The new assertions should verify:

- agent-level creation without a selected skill
- refresh updates the skill catalog without invalidating the import when skills change
- trace metadata is agent-level
- detail responses expose the advertised skills from the card snapshot

### 8. Documentation

Update or supersede [docs/ai/a2a-agent-design.md](/home/jjrodrig/projects/ai-core-tools/docs/ai/a2a-agent-design.md), which currently encodes the "one selected skill equals one imported agent" assumption.

That document also says discovery should happen in-browser through `@a2a-js/sdk`, while the current implementation uses a backend discovery proxy in [backend/routers/internal/agents.py](/home/jjrodrig/projects/ai-core-tools/backend/routers/internal/agents.py). That divergence should be clarified as part of the rewrite.

## Migration Strategy

### Phase 1

- remove `remote_skill_*` fields from the database model, schemas, and service logic
- stop requiring `selected_skill_id` on create and update
- update UI copy to agent-level language

### Phase 2

- update refresh logic to use skill drift as metadata drift
- remove skill-centric trace metadata
- move detail views and exports to card-level capability metadata

### Phase 3

- remove remaining code paths that depend on one selected skill

## Risks and Tradeoffs

### Reduced Ability to Create Multiple MattinAI Agents from One Remote Card

The old design allowed one remote card to produce many MattinAI agents by importing different skills separately.

The proposed design removes that as a primary concept.

Recommendation:
Treat "multiple local wrappers around one remote agent" as a separate future feature if it is still needed. It should be a MattinAI composition feature, not the base A2A import model.

### Slightly Less Specific Naming at Import Time

If the user no longer selects one skill, the default imported name may be broader.

Recommendation:
Use the remote agent name as the initial default and let the user rename it locally.

## Recommendation

Adopt the agent-level registration model and treat skills as cached remote capability metadata.

This is the cleanest fit with:

- the A2A card structure
- the current executor behavior
- the current storage model
- a simpler long-term MattinAI mental model

Because the feature is still unreleased, the cleanest implementation path is to remove the selected-skill fields directly and shift validation, refresh, execution, and UI behavior to the remote agent as the imported unit.
