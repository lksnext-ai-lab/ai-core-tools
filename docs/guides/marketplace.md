# Agent Marketplace

> Part of [Mattin AI Documentation](../README.md)

## Overview

The **Agent Marketplace** is a platform-wide catalog that lets teams publish agents so other users — inside or outside the owning workspace — can discover and chat with them directly, without needing to create their own app or AI service configuration.

Agents can be in one of three visibility states:

| Visibility | Who can see it |
|------------|----------------|
| `UNPUBLISHED` | Owner/editor only (default) |
| `PRIVATE` | Owner app members + accepted collaborators |
| `PUBLIC` | All authenticated platform users |

---

## Publishing an Agent

### 1. Set visibility

An agent with `editor` or higher role on the app can update the agent's marketplace visibility:

```http
PATCH /internal/apps/{app_id}/agents/{agent_id}/marketplace-visibility
Content-Type: application/json

{
  "marketplace_visibility": "public"
}
```

Valid values: `"unpublished"`, `"private"`, `"public"`.

### 2. Create or update the marketplace profile

The marketplace profile stores the presentation metadata shown in the catalog (display name, descriptions, category, tags, and cover images). A profile is separate from the underlying agent configuration.

```http
POST /internal/apps/{app_id}/agents/{agent_id}/marketplace-profile
Content-Type: application/json

{
  "display_name": "Research Assistant",
  "short_description": "Answers questions from your knowledge base",
  "long_description": "Full **Markdown** description of what this agent does.",
  "category": "Research",
  "tags": ["rag", "search", "knowledge"],
  "icon_url": "https://example.com/icon.png",
  "cover_image_url": "https://example.com/cover.png"
}
```

**Profile fields**:

| Field | Type | Limit | Purpose |
|-------|------|-------|---------|
| `display_name` | string | 255 chars | Name shown in catalog (falls back to agent name) |
| `short_description` | string | 200 chars | One-line summary shown on catalog cards |
| `long_description` | string (Markdown) | none | Full description on the detail page |
| `category` | string | see below | Main category for filtering |
| `tags` | string[] | max 5 | Free-form tags for search |
| `icon_url` | string | 500 chars | URL to agent icon |
| `cover_image_url` | string | 500 chars | URL to cover image |

**Available categories**: `Productivity`, `Research`, `Writing`, `Code`, `Data Analysis`, `Customer Support`, `Education`, `Other`

### Read an existing profile

```http
GET /internal/apps/{app_id}/agents/{agent_id}/marketplace-profile
```

---

## Browsing the Catalog

### List agents

```http
GET /internal/marketplace/agents
```

**Query parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `search` | — | Full-text search on display name, description, agent name, tags |
| `category` | — | Filter by category |
| `my_apps_only` | `false` | Show only agents from the user's own apps |
| `page` | `1` | Page number (1-based) |
| `page_size` | `20` | Items per page (max 100) |
| `sort_by` | `relevance` | Sort order: `relevance`, `alphabetical`, `newest` |

**Response** (`MarketplaceCatalogResponseSchema`):

```json
{
  "agents": [
    {
      "agent_id": 42,
      "display_name": "Research Assistant",
      "short_description": "Answers questions from your knowledge base",
      "category": "Research",
      "tags": ["rag", "search"],
      "icon_url": "https://...",
      "app_name": "My Workspace",
      "app_id": 7,
      "has_knowledge_base": true,
      "marketplace_visibility": "public",
      "rating_avg": 4.3,
      "rating_count": 12,
      "conversation_count": 87,
      "published_at": "2026-02-20T10:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

**Sort by `relevance`**: ranked by average rating (highest first), then by number of ratings, then alphabetically.

### Agent detail

```http
GET /internal/marketplace/agents/{agent_id}
```

Returns the full `MarketplaceAgentDetailSchema` including the long description and all profile metadata. Only available for `PRIVATE` or `PUBLIC` agents the requesting user can see.

### Available categories

```http
GET /internal/marketplace/categories
```

Returns the static list of predefined category strings.

---

## Chatting with a Marketplace Agent

Marketplace conversations are scoped separately from regular app playground conversations. They use `ConversationSource.MARKETPLACE`.

### Start a conversation

```http
POST /internal/marketplace/agents/{agent_id}/conversations
```

```json
{
  "title": "My research session"  // optional
}
```

Returns a `ConversationResponse` with the new `conversation_id`.

### Send a message

```http
POST /internal/marketplace/conversations/{conversation_id}/chat
Content-Type: multipart/form-data

message=<text>
files=<optional file>
file_references=<optional JSON array of file_ids>
```

Responses are synchronous (`ChatResponseSchema`). Streaming is not currently supported in the marketplace endpoint.

### List conversations

```http
GET /internal/marketplace/conversations?limit=50&offset=0
```

Returns `MarketplaceConversationListSchema` — the authenticated user's marketplace conversations across all agents.

### Get conversation with history

```http
GET /internal/marketplace/conversations/{conversation_id}
```

Returns `ConversationWithHistoryResponse` — full message history for the conversation.

---

## File Attachments in Conversations

Marketplace conversations support file attachments. Files are stored under the owning agent's app workspace and are accessible only to the uploading user.

### Upload a file

```http
POST /internal/marketplace/conversations/{conversation_id}/upload-file
Content-Type: multipart/form-data

file=<file>
```

Response includes `file_id`, `filename`, `file_type`, `file_size_bytes`, `processing_status`, `content_preview`, and `has_extractable_content`. Pass one or more `file_id` values as `file_references` in a subsequent `/chat` request to make the agent aware of the uploaded content.

### List attached files

```http
GET /internal/marketplace/conversations/{conversation_id}/files
```

Returns a list of file objects plus `total_size_bytes` and `total_size_display`.

### Remove a file

```http
DELETE /internal/marketplace/conversations/{conversation_id}/files/{file_id}
```

Returns `{"success": true}` on successful removal.

### Download a file

```http
GET /internal/marketplace/conversations/{conversation_id}/files/{file_id}/download
```

Returns a cryptographically signed `download_url` valid for the requesting user. The URL is constructed using `AICT_BASE_URL` and includes a per-user HMAC signature (`?user=&sig=`).

---

## Rating Agents

Users who have had at least one conversation with a marketplace agent can submit a star rating (1–5).

### Submit / update a rating

```http
POST /internal/marketplace/agents/{agent_id}/rate
Content-Type: application/json

{
  "rating": 5
}
```

Submitting again with a different value **updates** the existing rating. The profile's `rating_avg` and `rating_count` are updated atomically.

### Get your own rating

```http
GET /internal/marketplace/agents/{agent_id}/my-rating
```

Returns `{"rating": 4}` or `{"rating": null}` if not yet rated.

---

## Usage Quotas

Platform administrators can configure a **monthly call quota** per user for marketplace agents via the system setting `marketplace_call_quota`. Users in the `AICT_OMNIADMINS` list are always exempt.

### Check your quota usage

```http
GET /internal/marketplace/quota-usage
```

```json
{
  "call_count": 14,
  "quota": 100,
  "is_exempt": false
}
```

When `quota > 0` and a user exceeds the limit, `/chat` requests return **HTTP 429** with a message indicating the current usage and when the quota resets (first day of the next UTC month).

---

## Agent Configuration Fields

The following `Agent` model fields are relevant to marketplace behaviour:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `marketplace_visibility` | enum | `UNPUBLISHED` | Controls marketplace visibility |
| `enable_code_interpreter` | bool | `false` | Enable the code interpreter tool for this agent |
| `server_tools` | JSON (list) | `[]` | Server-side built-in tool configurations |

### `marketplace_visibility` enum

```python
class MarketplaceVisibility(enum.Enum):
    UNPUBLISHED = "unpublished"   # Not in catalog; access restricted to app members
    PRIVATE     = "private"       # Visible to app members and collaborators only
    PUBLIC      = "public"        # Visible to all platform users
```

---

## Data Model

```
Agent (1:1)─────────► AgentMarketplaceProfile
                          display_name, short_description, long_description
                          category, tags, icon_url, cover_image_url
                          rating_avg, rating_count, conversation_count
                          published_at, updated_at

                       AgentMarketplaceRating (M:1 → Profile)
                          user_id, rating (1-5), created_at, updated_at

                       MarketplaceUsage (per user per month)
                          user_id, year, month, call_count
```

The `AgentMarketplaceProfile` is auto-created when an agent is first published and is cascade-deleted when the agent is deleted.

---

## Access Control Summary

| Action | Required role |
|--------|--------------|
| View catalog (public agents) | authenticated user |
| View catalog (private agents) | app member / collaborator |
| Start / chat in conversation | authenticated user (quota applies) |
| Rate an agent | must have a conversation with agent |
| Update visibility | editor on owning app |
| Create / update profile | editor on owning app |
| Read own profile | viewer on owning app |
