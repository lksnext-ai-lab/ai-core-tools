# Feature Specification: System Embedding Services

## Summary

Add platform-level (system) embedding services that OMNIADMIN users can manage globally, mirroring the existing system AI services pattern. System embedding services have `app_id = NULL` and are available to all apps when selecting an embedding service for a silo. This eliminates the need for every app to independently configure the same embedding provider credentials, reduces duplication, and provides a centralized management point for platform administrators.

## Motivation

Currently, every app must create its own embedding services. In multi-tenant deployments (both self-managed and SaaS), the platform administrator often wants to provide a set of pre-configured embedding services (e.g., OpenAI `text-embedding-3-small`, Mistral embeddings) that all apps can use without requiring each app owner to supply their own API keys.

The exact same pattern was already implemented for AI services (`AIService.app_id` is nullable; `NULL` means system/platform service). This feature extends that pattern to `EmbeddingService`.

**Who benefits:**
- **OMNIADMIN** users: can manage shared embedding services from the admin panel.
- **App owners/editors**: can select system embedding services when configuring silos without needing to create and manage their own.

## Scope

### In scope

1. **Data model**: Make `EmbeddingService.app_id` nullable (currently `NOT NULL`).
2. **Backend admin CRUD**: New admin endpoints for system embedding service management (list, create, update, delete with impact check).
3. **Backend silo form data**: Include system embedding services alongside app-scoped ones when populating the silo form dropdown.
4. **Frontend admin page**: New `SystemEmbeddingServicesPage` in the admin section, reusing `EmbeddingServiceForm` / `BaseServiceForm`.
5. **Frontend silo form**: The embedding service selector in `SiloForm` must show both app-scoped and system embedding services, with a visual distinction (e.g., a "System" badge).
6. **Deletion impact warning**: Before deleting a system embedding service, provide an endpoint that returns the count and names of affected silos across all apps, and show a confirmation dialog in the UI.
7. **Navigation**: Add a link to the new admin page in the admin navigation section.
8. **Secondary: AI Services tier enforcement verification**: Confirm that the existing system AI services deletion flow also warns about impact (agents using the service). If not, note it as a follow-up but do not block this feature.

### Out of scope

- Restricting which system embedding services are available per tier (free/pro/enterprise). All system embedding services are available to all apps regardless of tier.
- Export/import of system embedding services (admin-only resources are not part of the app export/import flow).
- Public API exposure of system embedding services.
- Changing how embedding services are resolved at vector store query time (no functional changes to `SiloService.get_silo_retriever` etc. -- the FK still points to `embedding_service.service_id` regardless of whether the service is app-scoped or system-scoped).
- Per-silo restrictions on which embedding services can be used.

## Domain Model Changes

### Modified entity: `EmbeddingService`

**File**: `backend/models/embedding_service.py`

```python
# BEFORE
app_id = Column(Integer, ForeignKey('App.app_id'), nullable=False)

# AFTER
app_id = Column(Integer, ForeignKey('App.app_id'), nullable=True)  # NULL = system/platform service
```

This is identical to the pattern already used by `AIService`.

### Alembic migration

- **Migration name**: `make_embedding_service_app_id_nullable`
- **Upgrade**: `ALTER TABLE embedding_service ALTER COLUMN app_id DROP NOT NULL;`
- **Downgrade**: Before adding the constraint back, verify no rows have `app_id IS NULL`. If any exist, either delete them or raise an error. Then `ALTER TABLE embedding_service ALTER COLUMN app_id SET NOT NULL;`
- **Data migration**: None required. No existing rows need modification; all existing embedding services already have an `app_id`.

### No new entities

No new tables or models are needed. The system embedding service is simply an `EmbeddingService` row with `app_id = NULL`.

## API Design

All new endpoints are under `/internal/admin/` and require OMNIADMIN authentication (same `require_admin` dependency used by existing admin routes).

### 1. List system embedding services

```
GET /internal/admin/system-embedding-services
Auth: OMNIADMIN
Response: List[EmbeddingServiceListItemSchema] (with is_system=True added)
```

### 2. Create system embedding service

```
POST /internal/admin/system-embedding-services
Auth: OMNIADMIN
Request body: CreateUpdateEmbeddingServiceSchema
Response: EmbeddingServiceListItemSchema (201)
```

### 3. Update system embedding service

```
PUT /internal/admin/system-embedding-services/{service_id}
Auth: OMNIADMIN
Request body: CreateUpdateEmbeddingServiceSchema
Response: EmbeddingServiceListItemSchema
Validation: service must exist AND have app_id IS NULL
```

### 4. Get deletion impact (pre-delete check)

```
GET /internal/admin/system-embedding-services/{service_id}/impact
Auth: OMNIADMIN
Response:
{
  "service_id": int,
  "service_name": str,
  "affected_silos_count": int,
  "affected_apps_count": int,
  "affected_silos": [
    {"silo_id": int, "silo_name": str, "app_id": int, "app_name": str}
  ]
}
```

This endpoint queries all `Silo` rows where `embedding_service_id = service_id`, joins with `App` to get app names.

### 5. Delete system embedding service

```
DELETE /internal/admin/system-embedding-services/{service_id}
Auth: OMNIADMIN
Response: 204 No Content
Behavior: Sets embedding_service_id = NULL on all silos that reference this service, then deletes the service. This is a "safe detach" approach -- silos are not deleted, they just lose their embedding service reference.
Validation: service must exist AND have app_id IS NULL
```

### Modified endpoint: Silo form data

The existing silo detail endpoint (`GET /internal/apps/{app_id}/silos/{silo_id}`) already returns `embedding_services` for the dropdown. This must be modified to include system embedding services alongside app-scoped ones, with a flag to distinguish them.

The `embedding_services` field in `SiloDetailSchema` will change from:
```json
[{"service_id": 1, "name": "My OpenAI Embeddings"}]
```
to:
```json
[
  {"service_id": 1, "name": "My OpenAI Embeddings", "is_system": false},
  {"service_id": 5, "name": "Platform text-embedding-3-small", "is_system": true}
]
```

### Schema changes

**`EmbeddingServiceListItemSchema`** -- add `is_system: bool = False` field.

**`SiloDetailSchema`** -- the embedded embedding service items need `is_system` field. This may require a small helper schema:

```python
class EmbeddingServiceOptionSchema(BaseModel):
    service_id: int
    name: str
    provider: Optional[str] = None
    is_system: bool = False
```

## Service & Repository Layer

### Repository changes

**`EmbeddingServiceRepository`** -- add one new method:

```python
@staticmethod
def get_system_services(db: Session) -> List[EmbeddingService]:
    """Return all EmbeddingService records with app_id IS NULL."""
    return db.query(EmbeddingService).filter(EmbeddingService.app_id.is_(None)).all()
```

### Service changes

**`EmbeddingServiceService`** -- add a helper method (following `AIServiceService._to_list_item` pattern):

```python
@staticmethod
def _to_list_item(service: EmbeddingService, is_system: bool = False) -> EmbeddingServiceListItemSchema:
    ...
```

**`SiloRepository.get_form_data_for_silo`** -- modify to also fetch system embedding services:

```python
embedding_services = SiloRepository.get_embedding_services_by_app_id(app_id, db)
system_embedding_services = EmbeddingServiceRepository.get_system_services(db)
# Merge, marking system ones with is_system=True
```

**`SiloService.get_silo_detail`** -- update the embedding services list construction to include system services and the `is_system` flag.

### New service logic in admin routes

The admin route handlers will contain the CRUD logic directly (following the existing pattern in `admin.py` where system AI service endpoints are defined inline rather than delegating to a separate service class). This keeps the pattern consistent.

For the **impact check**:

```python
# Query silos referencing this embedding service, join with App
affected = db.query(Silo, App).join(App, Silo.app_id == App.app_id).filter(
    Silo.embedding_service_id == service_id
).all()
```

For the **delete with detach**:

```python
# Nullify references first
db.query(Silo).filter(Silo.embedding_service_id == service_id).update(
    {Silo.embedding_service_id: None}, synchronize_session='fetch'
)
# Then delete the service
db.delete(svc)
db.commit()
```

## Frontend Changes

### New page: `SystemEmbeddingServicesPage`

**File**: `frontend/src/pages/admin/SystemEmbeddingServicesPage.tsx`

Clone the structure of `SystemAIServicesPage.tsx`, but:
- Use `EmbeddingServiceForm` (or `BaseServiceForm` with embedding provider options) instead of `AIServiceForm`.
- On delete, first call the impact endpoint, then show a confirmation dialog with the impact details.

### New API methods in `api.ts`

```typescript
async getSystemEmbeddingServices(): Promise<EmbeddingServiceListItem[]>
async createSystemEmbeddingService(data: ServiceFormData): Promise<EmbeddingServiceListItem>
async updateSystemEmbeddingService(serviceId: number, data: ServiceFormData): Promise<EmbeddingServiceListItem>
async getSystemEmbeddingServiceImpact(serviceId: number): Promise<DeletionImpact>
async deleteSystemEmbeddingService(serviceId: number): Promise<void>
```

### Modified: `SiloForm.tsx`

The embedding service dropdown must:
1. Show both app-scoped and system services.
2. Visually distinguish system services (e.g., with a "(System)" suffix or a small badge).
3. Optionally group them: "App services" section and "System services" section in the dropdown.

### Modified: Navigation

**File**: `frontend/src/core/defaultNavigation.tsx`

Add entry under the admin section:
```typescript
{
  path: '/admin/system-embedding-services',
  label: 'System Embedding Services',
  icon: ...,
}
```

**File**: `frontend/src/core/ExtensibleBaseApp.tsx`

Add route:
```tsx
<Route path="/admin/system-embedding-services" element={
  <AdminRoute><SystemEmbeddingServicesPage /></AdminRoute>
} />
```

### Deletion confirmation dialog

When the admin clicks "Delete" on a system embedding service:
1. Call `GET /internal/admin/system-embedding-services/{id}/impact`.
2. If `affected_silos_count > 0`, show a warning dialog:
   > "This embedding service is used by **X silos** across **Y apps**. Deleting it will leave those silos without an embedding service. Are you sure?"
   >
   > [Show list of affected silos/apps if count is reasonable, e.g., < 20]
3. If `affected_silos_count == 0`, show a simpler confirmation: "Delete this system embedding service?"
4. On confirm, call `DELETE`.

### No client project changes

This feature is entirely within the base library. Client projects consuming `@lksnext/ai-core-tools-base` will get the new admin page and silo form changes automatically after rebuilding.

## Permissions & RBAC

| Action | Required Role |
|--------|--------------|
| List/create/update/delete system embedding services | OMNIADMIN (checked via `require_admin` dependency) |
| See system embedding services in silo form dropdown | VIEWER or above (existing silo detail endpoint) |
| Select a system embedding service for a silo | ADMINISTRATOR or above (existing silo create/update endpoint) |

No new RBAC rules are needed. The existing `require_admin` pattern (checking `is_omniadmin(email)`) handles admin access. The silo form already requires appropriate app-level roles.

## Edge Cases & Error Handling

| Edge case | Handling |
|-----------|---------|
| Attempt to update/delete an app-scoped service via admin endpoint | Return 404 (check `app_id IS NULL` in query) |
| Attempt to delete system embedding service used by silos | Impact endpoint returns counts; DELETE endpoint nullifies FK references before deletion |
| Silo with system embedding service after deletion | `embedding_service_id` becomes NULL; silo still exists but cannot perform embedding operations until a new service is assigned. This matches existing behavior when an app-scoped embedding service is deleted. |
| App export includes a silo referencing a system embedding service | The export should include the `embedding_service_id` reference. On import, if the target instance has a system embedding service with the same ID, it will work. If not, the silo will need manual reassignment. This is existing behavior for cross-instance portability and is not changed by this feature. |
| Downgrade migration with existing system embedding services | The Alembic downgrade must handle rows with `app_id IS NULL` -- either delete them or fail with a clear error message. Recommended: fail with an actionable error message. |
| System embedding service with same name as app-scoped service | Allowed -- they are in different scopes. The UI should visually distinguish them. |
| System embedding service with missing/placeholder API key | Existing `needs_api_key` flag already handles this in the list item schema. |

## Testing Plan

### Unit tests

- `tests/unit/test_embedding_service_repository.py`:
  - `test_get_system_services_returns_only_null_app_id`
  - `test_get_by_app_id_excludes_system_services`

### Integration tests

- `tests/integration/test_admin_system_embedding_services.py`:
  - `test_list_system_embedding_services_requires_admin`
  - `test_create_system_embedding_service`
  - `test_update_system_embedding_service`
  - `test_update_app_scoped_service_via_admin_returns_404`
  - `test_delete_system_embedding_service_no_silos`
  - `test_delete_system_embedding_service_with_silos_nullifies_references`
  - `test_impact_endpoint_returns_correct_counts`
  - `test_silo_form_includes_system_embedding_services`

### Test fixtures needed

- Factory/fixture for creating an `EmbeddingService` with `app_id=None` (system service).
- Fixture for creating silos that reference system embedding services.

## Open Questions / Deferred Decisions

1. **AI Services deletion impact parity**: The existing system AI services delete endpoint (`DELETE /internal/admin/system-ai-services/{id}`) does **not** have an impact check or detach logic. It will fail with an FK constraint error if any agent references it. A follow-up task should add the same impact check + detach pattern to system AI services for consistency. This is noted but not blocking for this feature.

2. **Export/import of system embedding services**: Not included in this feature. If needed later, a separate admin export/import flow could be added, but the use case is low-priority since system services are typically configured once per deployment.

3. **Cascading from app deletion**: When an app is deleted via `AppService.delete_app()`, it deletes all app-scoped embedding services. System embedding services (with `app_id IS NULL`) are naturally unaffected. No changes needed.
