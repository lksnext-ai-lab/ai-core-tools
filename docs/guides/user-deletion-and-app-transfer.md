# User Deletion and App Ownership Transfer

> Part of [Mattin AI Documentation](../README.md)

## Overview

This guide covers the safe deletion of user accounts and the transfer of app ownership — two operations that are tightly coupled because apps are aggregate roots that own external resources (vector store collections in PGVector or Qdrant). Destroying a user without handling their apps would either leak those collections or leave orphaned apps in a broken state.

Before this feature, `DELETE /internal/admin/users/{user_id}` delegated straight to a single `db.delete(user)` call. That approach relied on SQLAlchemy to silently null out foreign keys before deleting the parent row, which fails with a `NotNullViolation` for any user who has credentials, sessions, a subscription, API keys, or collaboration memberships — effectively every real user.

The current implementation replaces that with an explicit, ordered orchestration (`UserService.delete_user`) that classifies every entity referencing `User.user_id` into one of four classes and handles each class by exactly one mechanism.

---

## Deletion Taxonomy

Every database table that holds a foreign key to `User.user_id` is assigned to exactly one class. The class determines how the data is handled when the user is deleted.

| Class | Description | Mechanism | Entities |
|-------|-------------|-----------|----------|
| **A — Owned internal data** | Data whose lifecycle is tied to the user; no external side effects | DB `ON DELETE CASCADE` + ORM `passive_deletes=True` | `user_credentials`, `refresh_tokens`, `subscriptions`, `usage_records`, `MarketplaceUsage`, `AgentMarketplaceRating` |
| **B — Aggregate roots with external side effects** | Apps that own agents, silos, and vector-store collections | Orchestrated via `AppService.delete_app()` (cascade) or ownership transfer; never a DB cascade | `App` (via `App.owner_id`) |
| **C — Access grants** | Collaboration memberships and API keys the user holds in apps they do not own | Explicit `db.delete()` in the orchestration, before `db.delete(user)` | `AppCollaborator` rows where `user_id == target`, `APIKey` rows owned by target in non-owned apps |
| **D — Audit/attribution** | Rows that record who performed an action; the row should survive with the actor anonymised | DB `ON DELETE SET NULL` (migration `userdel001`) | `AppCollaborator.invited_by`, `Conversation.user_id`, `crawl_job.triggered_by_user_id` |

Class A and D are handled at the database level — no application code touches those columns. Class C rows are removed explicitly in the service. Class B is never cascaded at the DB level; apps are always handled through the ordered `AppService.delete_app()` or an ownership transfer.

---

## Deleting a User

### Endpoint

```
DELETE /internal/admin/users/{user_id}
```

**Authorization**: omniadmin only (`require_admin` dependency).

**Parameters**: `mode` and `transfer_to_user_id` can be sent either as a JSON body or as query parameters. When both are present, the JSON body takes precedence.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | `"block" \| "cascade_apps" \| "transfer_apps"` | `"block"` | What to do with apps owned by the target user |
| `transfer_to_user_id` | integer | — | Required when `mode="transfer_apps"`; the user who will receive the apps |

#### Mode: `block` (default)

Rejects the request with HTTP **409** if the user owns one or more apps. No data is mutated.

```json
HTTP 409
{
  "detail": "User owns apps. Choose mode=cascade_apps or mode=transfer_apps.",
  "owned_apps": [
    {"app_id": 12, "name": "Billing Assistant"},
    {"app_id": 17, "name": "HR Portal"}
  ]
}
```

The `owned_apps` list is included in the 409 body so the frontend can render the transfer/cascade dialog without a separate preflight request.

#### Mode: `cascade_apps`

Deletes every app owned by the target user — including all agents, silos, API keys, and the corresponding vector-store collections — by calling `AppService.delete_app()` for each app. After all apps are removed, the user is deleted.

This is **destructive and irreversible**. Vector-store collections are dropped. Use this only when the apps themselves are no longer needed.

**Atomicity note**: each `AppService.delete_app()` call commits independently (it performs irreversible external operations). If a failure occurs mid-loop, the user row is still present and the remaining apps are intact; re-running the request with `mode=cascade_apps` will pick up where it left off.

#### Mode: `transfer_apps`

Reassigns every owned app to `transfer_to_user_id`, then deletes the (now app-less) user in a single transaction. The recipient must be an active user; the recipient cannot be the same user being deleted.

```http
DELETE /internal/admin/users/42
Content-Type: application/json

{
  "mode": "transfer_apps",
  "transfer_to_user_id": 7
}
```

On success: HTTP 200 with `{"message": "User 42 and all associated data have been deleted successfully"}`.

### Guardrails

| Condition | HTTP status | Detail |
|-----------|-------------|--------|
| Unknown `user_id` | 404 | User not found |
| Actor is deleting themselves | 400 | Self-deletion is not permitted |
| Target user is an omniadmin | 403 | Cannot delete an administrator account |
| User owns apps and `mode=block` | 409 | `{detail, owned_apps}` (see above) |
| `transfer_to_user_id` does not exist or is inactive | 400 | Invalid recipient message |
| Transfer would push recipient over their SaaS app limit | 409 | Tier limit message |

The actor identity is always resolved from the session cookie — never from the request body.

---

## App Ownership Transfer

Ownership is held solely by `App.owner_id`. There is no `AppCollaborator` row with `role=OWNER` for the current owner. Two transfer paths exist: administrative-direct and voluntary.

### Administrative-Direct Transfer (omniadmin)

Immediately reassigns `App.owner_id` with no recipient handshake. Used internally by `delete_user(mode=transfer_apps)` and also available as a standalone admin action.

```
POST /internal/admin/apps/{app_id}/transfer
```

**Authorization**: omniadmin only.

**Request body**:
```json
{"new_owner_id": 7}
```

**Response** (HTTP 200):
```json
{
  "app_id": 12,
  "name": "Billing Assistant",
  "previous_owner_id": 42,
  "new_owner_id": 7
}
```

**Validation**:
- App must exist (404 if not).
- Recipient must exist, be active, and not already be the owner (400 if invalid).
- In SaaS mode: recipient must not exceed their app limit (409 if exceeded).

**Side effects**:
- If the recipient had an existing `AppCollaborator` row on the app, it is removed (ownership supersedes collaboration).
- The previous owner is **not** automatically added as a collaborator when using this path. If they need continued access, an administrator must invite them after the transfer.
- Freeze/tier state is re-evaluated for the new owner.

### Voluntary Transfer (owner-initiated, recipient accepts)

The current app owner initiates an offer; the recipient must explicitly accept before ownership changes.

The offer is modelled as an `AppCollaborator` row with `role=OWNER, status=PENDING`. This reuses the existing collaboration status machine and surfaces the offer in the recipient's pending invitations. A pending offer grants nothing — role resolution derives OWNER solely from `App.owner_id`.

#### 1. Create an offer

```
POST /internal/apps/{app_id}/ownership/offer
```

**Authorization**: OWNER or omniadmin on the app.

**Request body**: `{"new_owner_id": 7}`

**Response** (HTTP 201): `OwnershipOfferResponse` with `collaboration_id` and offer details.

The operation is idempotent: a second offer to the same recipient refreshes the existing offer rather than creating a duplicate.

#### 2. Accept the offer (recipient only)

```
POST /internal/apps/{app_id}/ownership/accept/{collaboration_id}
```

**Authorization**: any authenticated user — the service validates that the actor is the named recipient.

On acceptance:
- `App.owner_id` is set to the recipient.
- The previous owner is demoted to an `ADMINISTRATOR` collaborator, retaining access to the app.
- The pending offer row is removed.
- SaaS tier limit is enforced on the recipient.

#### 3. Decline the offer (recipient only)

```
POST /internal/apps/{app_id}/ownership/decline/{collaboration_id}
```

Sets the offer status to `DECLINED`. No ownership change occurs.

#### 4. Cancel the offer (owner/omniadmin)

```
DELETE /internal/apps/{app_id}/ownership/offer
```

**Authorization**: OWNER or omniadmin on the app. Deletes the pending offer row. Returns 404 if no active offer exists.

---

## Migration: `userdel001`

**Revision**: `userdel001`  **Base revision**: `localauth001`

This migration converts three foreign keys from `NO ACTION` to `ON DELETE SET NULL` so that deleting a user anonymises attribution rows rather than blocking or cascading:

| Foreign key | Table | Column | Before | After |
|-------------|-------|--------|--------|-------|
| `fk_appcollaborator_invited_by_user` | `AppCollaborator` | `invited_by` | NO ACTION, NOT NULL | SET NULL, nullable |
| `fk_conversation_user_id_user` | `Conversation` | `user_id` | NO ACTION | SET NULL |
| `fk_crawl_job_triggered_by_user_id_user` | `crawl_job` | `triggered_by_user_id` | NO ACTION | SET NULL |

`AppCollaborator.invited_by` is also made nullable by the upgrade (required for `SET NULL` to work).

To apply:
```bash
alembic upgrade head
```

To verify (run against the test DB on port 5433):
```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

### Downgrade caveat

The downgrade restores `invited_by` to `NOT NULL`. This step **fails** if any `AppCollaborator` row has `invited_by = NULL`, which occurs once a user who had invited collaborators is deleted under the new system (the `SET NULL` rule nulled those rows).

**Before downgrading on a database that has had user deletions**, backfill the affected rows:

```sql
-- Replace 1 with the ID of any surviving active user to use as a placeholder.
UPDATE "AppCollaborator"
SET    invited_by = 1
WHERE  invited_by IS NULL;
```

Then run `alembic downgrade -1`.

---

## Operator Runbook

### How do I delete a user who owns apps?

**Option A — Transfer apps to another user, then delete**

Use this when the apps should continue to exist under a different owner.

Via the admin UI:
1. Go to Admin > Users and find the target user.
2. Click Delete.
3. The dialog detects owned apps and presents two options: "Transfer apps to" (user picker) or "Delete apps too".
4. Select "Transfer apps to", pick the recipient, and confirm.

Via curl:
```bash
curl -X DELETE "https://<host>/internal/admin/users/42" \
  -H "Content-Type: application/json" \
  -b "session=<cookie>" \
  -d '{"mode": "transfer_apps", "transfer_to_user_id": 7}'
```

The response is HTTP 200 on success. All apps are now owned by user 7 and the deleted user's data is gone.

**Option B — Delete the apps too (cascade), then delete the user**

Use this when the apps and all their data — agents, silos, vector-store collections — are no longer needed. This is **destructive and irreversible**.

Via the admin UI:
1. Go to Admin > Users and find the target user.
2. Click Delete.
3. In the dialog, select "Delete apps too", type the confirmation phrase, and confirm.

Via curl:
```bash
curl -X DELETE "https://<host>/internal/admin/users/42" \
  -H "Content-Type: application/json" \
  -b "session=<cookie>" \
  -d '{"mode": "cascade_apps"}'
```

**Option C — Handle apps separately before deleting**

Transfer each app individually using the admin transfer endpoint, then delete the (now app-less) user with the default `mode=block`:

```bash
# Transfer each app
curl -X POST "https://<host>/internal/admin/apps/12/transfer" \
  -H "Content-Type: application/json" \
  -b "session=<cookie>" \
  -d '{"new_owner_id": 7}'

# Delete the user (safe — no owned apps remain)
curl -X DELETE "https://<host>/internal/admin/users/42" \
  -b "session=<cookie>"
```

### How do I verify what apps a user owns before deleting?

```bash
curl "https://<host>/internal/admin/users/42" \
  -b "session=<cookie>"
```

The `owned_apps_count` field in the response shows the count. If you attempt to delete with `mode=block` (the default) and the user owns apps, the 409 response body includes the full `owned_apps` list with names.

---

## Known Limitations

- **In-flight requests**: deleting an app that is currently serving an active agent inference request is a hard delete — in-flight requests are not drained gracefully.
- **OIDC/JWT tokens**: a deleted user's access token remains valid until its natural expiry (typically 30 minutes). Refresh tokens are revoked immediately via the DB cascade on `refresh_tokens`. In LOCAL auth mode, `POST /internal/admin/users/{user_id}/revoke-sessions` can force session termination before deletion.
- **SaaS Stripe**: deleting a SaaS user removes the `subscriptions` row (class A cascade) but does not cancel a Stripe subscription. Handle Stripe cancellation manually before deleting the user.
- **Conversation checkpointer threads**: standalone `Conversation` rows are anonymised (user_id set to NULL). The LangGraph checkpointer threads associated with those conversations are cleaned only when the agent or app they belong to is deleted.
- **ActionDropdown accessibility**: the delete action dropdown in the admin users table has a pre-existing keyboard navigation limitation that is tracked separately.

---

## See Also

- [Authentication Guide](authentication.md) — Session auth, LOCAL mode, and omniadmin configuration
- [Role Authorization](../reference/role-authorization.md) — RBAC roles and the `require_min_role` decorator
- [Internal API](../api/internal-api.md) — Admin endpoint reference
- [Database Schema](../architecture/database.md) — ORM models and Alembic migrations
