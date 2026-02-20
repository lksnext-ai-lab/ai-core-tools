# Role Authorization

> Part of [Mattin AI Documentation](../README.md)

## Overview

Mattin AI uses **Role-Based Access Control (RBAC)** to manage permissions across apps and operations. Users are assigned roles within each app, and each role grants specific permissions.

**Key concepts**:
- **Global roles**: System-wide permissions (omniadmin)
- **App roles**: Per-app permissions (owner, administrator, editor, viewer)
- **Role hierarchy**: Higher roles inherit lower role permissions
- **Decorators**: Enforce minimum role requirements on endpoints

## Role Hierarchy

Roles are organized in a hierarchy where **higher roles inherit all permissions** from lower roles:

```
omniadmin  (system-wide superuser)
    ↓
  owner    (app creator, full app control)
    ↓
administrator (app management, user invites)
    ↓
  editor   (create/modify content)
    ↓
  viewer   (read-only access)
    ↓
   user    (authenticated, no app affiliation)
    ↓
  guest    (not authenticated)
```

**Hierarchy index** (defined in `role_authorization.py`):

```python
ROLE_HIERARCHY = [
    AppRole.GUEST,           # 0
    AppRole.USER,            # 1
    AppRole.VIEWER,          # 2
    AppRole.EDITOR,          # 3
    AppRole.ADMINISTRATOR,   # 4
    AppRole.OWNER,           # 5
    AppRole.OMNIADMIN        # 6
]
```

## Usage

### require_min_role Decorator

Endpoints use the `require_min_role` dependency to enforce minimum role requirements:

```python
from routers.controls.role_authorization import require_min_role, AppRole

@router.post("/agents")
async def create_agent(
    role: AppRole = Depends(require_min_role("editor")),
    db: Session = Depends(get_db)
):
    # Only users with 'editor' role or higher can access
    ...
```

**Usage patterns**:

```python
# Require viewer or higher
role = Depends(require_min_role("viewer"))

# Require editor or higher
role = Depends(require_min_role("editor"))

# Require administrator or higher
role = Depends(require_min_role("administrator"))

# Require owner
role = Depends(require_min_role("owner"))

# Require omniadmin (admin-only operations)
role = Depends(require_min_role("omniadmin"))
```

### require_any_role Decorator

Alternative decorator accepting multiple valid roles:

```python
from routers.controls.role_authorization import require_any_role

@router.get("/resource")
async def get_resource(
    role: AppRole = Depends(require_any_role(["editor", "viewer"])),
    db: Session = Depends(get_db)
):
    # Either editor or viewer can access
    ...
```

### FastAPI Depends Integration

Role checks integrate seamlessly with FastAPI's dependency injection:

```python
from fastapi import APIRouter, Depends
from routers.controls.role_authorization import require_min_role, AppRole
from sqlalchemy.orm import Session
from db.database import get_db

router = APIRouter()

@router.post("/")
async def create_resource(
    app_id: int,
    role: AppRole = Depends(require_min_role("editor")),
    db: Session = Depends(get_db)
):
    # role variable contains user's effective role
    # Only executed if user has editor role or higher
    return {"message": "Resource created"}
```

## Role Definitions

### Omniadmin

**System-wide superuser** with unrestricted access to all apps and operations.

**Privileges**:
- Access all apps (bypass ownership/collaboration checks)
- Perform admin operations (`/internal/admin/*` endpoints)
- View and modify all user accounts
- Override any role restrictions

**Configuration**:
```bash
AICT_OMNIADMINS=admin@example.com,superuser@company.com
```

### Owner

**App creator** with full control over the app.

**Privileges**:
- All administrator privileges
- Delete app
- Transfer ownership
- Generate API keys
- View app usage statistics

**Assignment**: Automatically assigned to user who creates the app

### Administrator

**App manager** who can manage users and app settings.

**Privileges**:
- All editor privileges
- Invite/remove collaborators
- Modify app settings
- Manage AI services and embedding services
- Configure MCP servers

**Assignment**: Granted by owner

### Editor

**Content creator** who can create and modify app resources.

**Privileges**:
- All viewer privileges
- Create/update/delete agents
- Create/update/delete silos
- Upload files to repositories
- Create/update/delete domains
- Configure agent settings

**Assignment**: Granted by owner or administrator

### Viewer

**Read-only access** to app resources.

**Privileges**:
- List and view agents
- List and view silos
- View repositories and files
- View domains
- Execute agents (chat)
- View conversation history

**Assignment**: Granted by owner or administrator

### User

**Authenticated user** with no app affiliation.

**Privileges**:
- Access user profile
- Create new apps (becomes owner)
- Accept collaboration invitations

**Assignment**: Automatically assigned after successful authentication

### Guest

**Unauthenticated** user (not logged in).

**Privileges**: None (no access to internal API)

**Assignment**: Default for non-authenticated requests

## Error Semantics

Role authorization returns specific HTTP status codes:

### 401 Unauthorized (Not Authenticated)

**When**: User is not authenticated (no valid session cookie or API key)

**Response**:
```json
{
  "detail": "Not authenticated"
}
```

**Solution**: Login via `/internal/auth/login` (OIDC) or provide valid API key

### 403 Forbidden (Insufficient Role)

**When**: User is authenticated but lacks required role

**Response**:
```json
{
  "detail": "Insufficient permissions. Required role: editor"
}
```

**Solution**: Request higher role from app owner/administrator

### 404 Not Found (App Not Found)

**When**: App doesn't exist OR user has no access to app

**Response**:
```json
{
  "detail": "App not found"
}
```

**Note**: Returns 404 instead of 403 to avoid information leakage (don't reveal app existence to unauthorized users)

**Causes**:
- Invalid `app_id`
- User not owner/collaborator of app
- App was deleted

## Frontend Integration

### useAppRole Hook

React hook to get user's role in current app:

```typescript
import { useAppRole } from '@lksnext/ai-core-tools-base';

function MyComponent() {
  const { role, isOwner, isAdmin, isEditor, isViewer } = useAppRole(appId);
  
  return (
    <div>
      {isEditor && <button>Create Agent</button>}
      {isAdmin && <button>Invite Users</button>}
      {isOwner && <button>Delete App</button>}
    </div>
  );
}
```

### ProtectedRoute

Require authentication to access route:

```typescript
import { ProtectedRoute } from '@lksnext/ai-core-tools-base';

<Route path="/playground" element={
  <ProtectedRoute>
    <Playground />
  </ProtectedRoute>
} />
```

**Behavior**: Redirects to login if not authenticated

### AdminRoute

Require admin/omniadmin role:

```typescript
import { AdminRoute } from '@lksnext/ai-core-tools-base';

<Route path="/admin/*" element={
  <AdminRoute>
    <AdminDashboard />
  </AdminRoute>
} />
```

**Behavior**: Shows "403 Forbidden" if not admin/omniadmin

### roleUtils

Utility functions for role checks:

```typescript
import { hasMinRole, getRoleLevel } from '@lksnext/ai-core-tools-base/roleUtils';

// Check if user has minimum role
if (hasMinRole(userRole, 'editor')) {
  // User can edit
}

// Compare role levels
if (getRoleLevel(userRole) >= getRoleLevel('administrator')) {
  // User is administrator or higher
}
```

## Code Examples

### Backend: Custom Authorization

```python
from routers.controls.role_authorization import resolve_user_app_role, AppRole

def can_modify_resource(db: Session, app_id: int, user_id: int, email: str) -> bool:
    """Check if user can modify resources in an app."""
    role = resolve_user_app_role(db, app_id, user_id, email)
    return role in [AppRole.OWNER, AppRole.ADMINISTRATOR, AppRole.EDITOR, AppRole.OMNIADMIN]
```

### Frontend: Conditional Rendering

```typescript
import { useAppRole } from '@lksnext/ai-core-tools-base';

function AgentList({ appId }) {
  const { role, isEditor } = useAppRole(appId);
  
  return (
    <div>
      <h1>Agents</h1>
      {/* Show list to all authenticated users */}
      <AgentListComponent />
      
      {/* Only editors can create */}
      {isEditor && (
        <button onClick={createAgent}>Create Agent</button>
      )}
    </div>
  );
}
```

### Permission Matrix

| Operation | Min Role | Endpoint |
|-----------|----------|----------|
| View agents | viewer | `GET /internal/agents` |
| Execute agent | viewer | `POST /internal/agents/{id}/chat` |
| Create agent | editor | `POST /internal/agents` |
| Update agent | editor | `PUT /internal/agents/{id}` |
| Delete agent | editor | `DELETE /internal/agents/{id}` |
| Invite collaborator | administrator | `POST /internal/collaboration/apps/{id}/invite` |
| Manage app settings | administrator | `PUT /internal/apps/{id}` |
| Generate API key | owner | `POST /internal/api_keys` |
| Delete app | owner | `DELETE /internal/apps/{id}` |
| Admin operations | omniadmin | `GET /internal/admin/users` |

## See Also

- [Authentication Guide](../guides/authentication.md) — User authentication
- [Internal API](../api/internal-api.md) — Role requirements per endpoint
- [Backend Architecture](../architecture/backend.md) — RBAC implementation
