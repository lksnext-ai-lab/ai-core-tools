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
