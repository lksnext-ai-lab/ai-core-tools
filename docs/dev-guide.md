# Mattin AI - Development Guide

## Alembic migrations

### Install
```bash
pip install alembic
```


### Create a new migration from an existing model
```bash
alembic revision --autogenerate -m "Initial revision"
alembic upgrade head
```


docker-compose -f docker-compose.yaml --env-file .env up postgres

## Role Authorization

The application uses a unified role resolution system with a hierarchy:
`omniadmin > owner > administrator > editor > viewer > user > guest`

### Usage

Use the `require_min_role` or `require_any_role` dependencies in your FastAPI routers.

```python
from routers.controls.role_authorization import require_min_role, require_any_role, AppRole

@router.get("/")
async def get_items(
    app_id: int,
    role: AppRole = Depends(require_min_role("editor"))
):
    ...
```

### Error Semantics

- **404 Not Found**: If the app does not exist.
- **403 Forbidden**: If the user is authenticated but does not have the required role or affiliation with the app.
- **401 Unauthorized**: If the user is not authenticated (handled by `get_current_user_oauth`).

### Hierarchy Rationale

- **Omniadmin**: Superuser with access to everything.
- **Owner**: Creator of the app, full control.
- **Administrator**: Can manage app settings and users.
- **Editor**: Can edit content.
- **Viewer**: Can view content.
- **User**: Authenticated user with no specific role in the app.
- **Guest**: Unauthenticated user.

## Marketplace

The Agent Marketplace allows users to publish agents for public or private consumption. Marketplace consumers can browse, discover, and chat with published agents without needing access to the agent's app.

### Agent Publishing

Agent owners can set marketplace visibility via the agent management UI or API:

- **UNPUBLISHED**: Agent is not listed in marketplace (default)
- **PRIVATE**: Agent is listed but only accessible by direct link
- **PUBLIC**: Agent is publicly listed and discoverable in catalog

Set visibility using:

```python
PUT /internal/apps/{app_slug}/agents/{agent_id}/marketplace-visibility
{
  "visibility": "public"
}
```

### Marketplace Metadata

When publishing an agent, configure its marketplace profile:

- **Display Name**: Public-facing name (defaults to agent name)
- **Short Description**: 160-character summary for catalog cards
- **Long Description**: Full markdown description with usage instructions
- **Category**: One of 8 predefined categories (Customer Support, Education, Research & Analysis, Content Creation, Development Tools, Business & Finance, Health & Wellness, Other)
- **Tags**: Up to 5 tags for search and filtering
- **Icon**: Square image (recommended 256x256px)
- **Cover Image**: Wide banner (recommended 1200x400px)

Update profile using:

```python
PUT /internal/apps/{app_slug}/agents/{agent_id}/marketplace-profile
{
  "display_name": "Customer Support Assistant",
  "short_description": "24/7 AI support for common customer inquiries",
  "long_description": "# About\n\nThis agent helps...",
  "category": "customer_support",
  "tags": ["support", "customer-service", "FAQ"],
  "icon_url": "https://...",
  "cover_image_url": "https://..."
}
```

### USER Role

The marketplace introduces a new **USER** role below VIEWER in the hierarchy:

**Full hierarchy**: `omniadmin > owner > administrator > editor > viewer > user > guest`

**USER role characteristics**:
- Can browse the marketplace catalog
- Can chat with published agents
- Cannot access any app management features
- Cannot create or manage resources
- Authenticated but no app-specific permissions

This role enables public consumption of agents without granting app access.

### Marketplace Catalog

The marketplace provides a top-level navigation entry (🏪 "Marketplace") with:

- **Search**: Full-text search across agent names, descriptions, and tags
- **Category Filters**: Filter by the 8 predefined categories
- **Sorting**: Sort by newest, most popular, or A-Z
- **Pagination**: 12 agents per page

Access the catalog via:

```python
GET /internal/marketplace/agents
  ?search=customer%20support
  &category=customer_support
  &page=1
  &per_page=12
```

### Marketplace Chat

Consumers interact with marketplace agents through a simplified chat interface:

- **Conversation Privacy**: Each user's conversations are private
- **Source Tagging**: Conversations are tagged with `source=marketplace`
- **No App Context**: Users cannot access the agent's app or resources
- **Isolated Sessions**: Each conversation is independent

Start a new conversation:

```python
POST /internal/marketplace/agents/{agent_id}/conversations
{
  "title": "Help with product returns"  // optional
}
```

Send messages:

```python
POST /internal/marketplace/conversations/{conversation_id}/chat
{
  "message": "How do I return a product?"
}
```

### Resource Usage

**LLM Calls**: All marketplace agent executions use the agent's original App's AIService configuration. The agent owner's API keys and LLM credits are consumed.

**Rate Limits**: Rate limits apply at the App level (configured in `App.agent_rate_limit`).

**Usage Tracking**: Marketplace conversations are tracked separately from playground conversations via the `source` field in the Conversation model.
