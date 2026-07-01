# Authentication Guide

> Part of [Mattin AI Documentation](../README.md)

## Overview

Mattin AI supports two authentication modes, controlled by the `AICT_LOGIN` environment variable:

| Mode | Value | Use case |
|------|-------|----------|
| **OIDC** | `OIDC` | Enterprise identity provider (Azure Entra ID). Default. |
| **LOCAL** | `LOCAL` | Self-hosted deployments with admin-provisioned email + password accounts. |

> **FAKE mode is retired.** The `dev-login` endpoint no longer exists and returns 404 in OIDC and LOCAL modes. Setting `AICT_LOGIN=FAKE` raises a `RuntimeError` at startup. Existing deployments must migrate to LOCAL or OIDC.

Authentication is split into two independent surfaces:

- **Session auth** (`/internal`): Cookie-based for the frontend. Mechanism differs by mode (OIDC redirect flow vs LOCAL email+password).
- **API key auth** (`/public/v1`, `/mcp/v1`): `X-API-KEY` header. Completely unaffected by which session-auth mode is active.

---

## OIDC Mode

**OpenID Connect** authentication via enterprise identity providers.

**Supported provider**: Azure Entra ID (Microsoft Entra).

### Configuration

```bash
AICT_LOGIN=OIDC

ENTRA_TENANT_ID=your-tenant-id
ENTRA_CLIENT_ID=your-client-id
ENTRA_CLIENT_SECRET=your-client-secret
```

### Login flow

```
1. User clicks "Login" → frontend redirects to /internal/auth/login
2. Backend redirects to Azure Entra ID
3. User authenticates with Entra
4. Entra redirects to /internal/auth/callback with auth code
5. Backend exchanges code for tokens; user info is read from the id_token
6. User record created/updated in the database
7. Session cookie set → user redirected to frontend
```

**Libraries used**: `lks-idprovider-fastapi`, `lks-idprovider-entraid`.

### Azure setup

1. Register an app in the Azure Portal: Azure Active Directory → App registrations.
2. Add a redirect URI: `https://<your-host>/internal/auth/callback`.
3. Generate a client secret.
4. Copy the tenant ID, client ID, and client secret to `.env`.

### Frontend configuration

```bash
VITE_OIDC_ENABLED=true
VITE_OIDC_AUTHORITY=https://login.microsoftonline.com/{tenant-id}/v2.0
VITE_OIDC_CLIENT_ID=your-azure-client-id
VITE_OIDC_REDIRECT_URI=http://localhost:5173/auth/success
VITE_OIDC_SCOPE=openid profile email
```

---

## LOCAL Mode

**Admin-provisioned email + password** authentication for self-hosted deployments.

Self-registration is disabled. An administrator creates each user account, and the user receives a one-time set-password link to activate their account.

### How it works

Sessions are transported as **httpOnly cookies** — no token is ever stored in `localStorage` or returned in the response body. Three cookies are set at login:

| Cookie | httpOnly | Path | Purpose |
|--------|----------|------|---------|
| `access_token` | Yes | `/` | Signed JWT (HS256, 15-minute TTL by default) |
| `refresh_token` | Yes | `/internal/auth` | Opaque rotation token (14-day TTL by default) |
| `csrf_token` | No | `/` | CSRF double-submit value (JS-readable) |

Mutating requests to `/internal` must include the `X-CSRF-Token` header whose value is read from the `csrf_token` cookie. The paths `/auth/login` and `/auth/set-password` are exempt (called before a session cookie exists; protected by body credentials/token instead). Bearer and `X-API-KEY` requests are also a no-op for CSRF. The `Secure` flag is enabled by default; set `AUTH_COOKIE_SECURE=false` only for plain-HTTP local development.

Refresh tokens rotate on every use. Presenting an already-rotated token is treated as reuse and revokes the entire token family, forcing re-authentication.

### Required environment variable

```bash
AICT_LOGIN=LOCAL
SECRET_KEY=<random 64-char hex string>   # REQUIRED — no default
```

`SECRET_KEY` must be present, at least 32 characters, and not a known placeholder. The app fails fast at startup if the check fails. **Rotating `SECRET_KEY` invalidates all active sessions** because it is used to sign both JWT access tokens and set-password tokens.

Generate a safe key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Optional tuning variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_COOKIE_SECURE` | `true` | Set `false` for plain-HTTP local dev only — never in production |
| `LOCAL_ACCESS_TTL_MINUTES` | `15` | Access token lifetime in minutes |
| `LOCAL_REFRESH_TTL_DAYS` | `14` | Refresh token lifetime in days |
| `LOCAL_LOCKOUT_THRESHOLD` | `5` | Failed attempts before account lockout |
| `LOCAL_LOCKOUT_BASE_SECONDS` | `60` | Base lockout duration in seconds (exponential backoff) |
| `LOCAL_TOKEN_LEEWAY_SECONDS` | `30` | Clock-skew tolerance for JWT validation |
| `LOCAL_SET_PASSWORD_TOKEN_MAX_AGE_HOURS` | `48` | Set-password link validity window |

### Lockout behaviour

After `LOCAL_LOCKOUT_THRESHOLD` consecutive failed login attempts the account is locked with exponential backoff:

```
locked_until = now + base * 2^(failed_attempts - threshold)

Examples (threshold=5, base=60 s):
  5th failure:  60 s
  6th failure: 120 s
  7th failure: 240 s
 10th failure: 1920 s (~32 min)
```

Omniadmins (set via `AICT_OMNIADMINS`) are exempt from lockout to prevent self-lockout of a sole administrator.

### SMTP configuration (optional)

When both `SMTP_HOST` and `SMTP_FROM` are set, the app delivers set-password links by email. When either is absent the `NoopEmailSender` is used — it logs only the recipient address and subject (never the token or link value), and the token is returned only in the admin API response body.

| Variable | Default | Description |
|----------|---------|-------------|
| `SMTP_HOST` | — | SMTP relay hostname. Required to enable email delivery. |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | — | SMTP authentication username (optional) |
| `SMTP_PASSWORD` | — | SMTP authentication password. Never logged. |
| `SMTP_TLS` | `true` | Enable STARTTLS |
| `SMTP_FROM` | — | Sender address (e.g. `no-reply@example.com`). Required to enable email delivery. |
| `SMTP_TIMEOUT_SECONDS` | `10` | Per-connection timeout |

SMTP is entirely optional. Self-hosted deployments without an SMTP relay work normally — the administrator copies the token from the API response and forwards it to the user manually. If the token is lost, re-issue it via `POST /internal/admin/users/{id}/reset-link`.

### Admin provisioning workflow

Requires `OMNIADMIN` (set via `AICT_OMNIADMINS` env var) or the `admin` platform role. The app-scoped collaborator role (`ADMINISTRATOR`) does not grant access to these endpoints.

1. **Create user** — `POST /internal/admin/users/local`. The response body contains `user_id`, `email`, `name`, a one-time `set_password_token`, and its `expires_at`. The token is **not** logged or emailed at this step — the admin must forward it to the user manually (or build the set-password URL: `<frontend>/set-password?token=<token>`).
2. **User sets password** — the user POSTs to `/internal/auth/set-password` with the token and chosen password. The token is single-use and expires after `LOCAL_SET_PASSWORD_TOKEN_MAX_AGE_HOURS` (default 48 hours).
3. **User logs in** — `POST /internal/auth/login` with `{"email": "...", "password": "..."}`. Cookies are set on success.

**Re-issuing a token** (existing user only): `POST /internal/admin/users/{user_id}/reset-link`. If SMTP is configured the link is emailed; otherwise the token is returned in the response body for manual forwarding.

**Emergency password reset** (admin direct): `POST /internal/admin/users/{user_id}/set-password` with `{"new_password": "..."}`. Resets lockout state and revokes all active sessions.

### Omniadmin recovery

If the omniadmin account has no credential or needs a password reset, use the seed utility:

```bash
# Inside a running Docker deployment
docker compose exec -T backend \
  python -m utils.seed_dev_users --yes \
  --users "admin@acme.com:Admin:NewPass123!"
```

The utility refuses to run unless `AICT_LOGIN=LOCAL` (use `--force` to override). It is idempotent — existing users are updated in-place.

### Frontend configuration (LOCAL mode)

```bash
VITE_OIDC_ENABLED=false
```

No OIDC variables are needed. The login page collects email and password and POSTs to `/internal/auth/login`.

---

## API Key Auth

**Token-based authentication** for public API endpoints (`/public/v1`) and MCP endpoints (`/mcp/v1`). Completely independent of the session-auth mode — works identically regardless of whether `AICT_LOGIN` is `OIDC` or `LOCAL`.

### Generation

API keys are created by app owners via the internal API:

```http
POST /internal/api_keys?app_id=1
Cookie: ...
Content-Type: application/json

{
  "name": "Production API Key",
  "rate_limit": 100
}

Response:
{
  "key": "mattin_ABC123XYZ...",
  "key_id": 5,
  "name": "Production API Key",
  "rate_limit": 100,
  "create_date": "2024-01-15T10:30:00Z"
}
```

The raw key is **shown once at creation only**. Save it immediately.

### Usage

```http
GET /public/v1/agents?app_id=1
X-API-Key: mattin_ABC123XYZ...
```

### Revocation

```http
DELETE /internal/api_keys/5?app_id=1
Cookie: ...
```

---

## Frontend Auth

### AuthContext

```typescript
import { useAuth } from '@lksnext/ai-core-tools-base';

function MyComponent() {
  const { user, isAuthenticated, login, logout } = useAuth();

  if (!isAuthenticated) {
    return <button onClick={login}>Login</button>;
  }

  return (
    <div>
      <p>Welcome, {user.name}!</p>
      <button onClick={logout}>Logout</button>
    </div>
  );
}
```

### Protected Routes

```typescript
import { ProtectedRoute, AdminRoute } from '@lksnext/ai-core-tools-base';

<Routes>
  <Route path="/playground" element={
    <ProtectedRoute><Playground /></ProtectedRoute>
  } />
  <Route path="/admin/*" element={
    <AdminRoute><AdminDashboard /></AdminRoute>
  } />
</Routes>
```

---

## Omniadmins

Omniadmins are superusers with unrestricted access to all apps and operations.

### Configuration

```bash
AICT_OMNIADMINS=admin@example.com,superuser@example.com
```

Comma-separated list of email addresses. Checked at runtime on each request — no restart required to add or remove entries.

### Privileges

- Access all apps (bypasses ownership/collaboration checks)
- Perform admin operations (`/internal/admin/*` endpoints)
- View and modify all user accounts
- Exempt from the failed-login lockout (LOCAL mode)

### Role hierarchy

```
omniadmin > owner > administrator > editor > viewer
```

---

## Migrating from FAKE Mode

FAKE mode is retired. `AICT_LOGIN=FAKE` will not start the application. To migrate:

1. Set `AICT_LOGIN=LOCAL` and generate a strong `SECRET_KEY`.
2. Run migrations if needed: `alembic upgrade head`.
3. Seed or create user accounts:

   ```bash
   docker compose exec -T backend \
     python -m utils.seed_dev_users --yes \
     --users "admin@acme.com:Admin:TempPass123!"
   ```

4. Distribute set-password links to each user who needs one (or set passwords directly via the seed utility's `--users email:Name:password` format).

---

## Troubleshooting

### OIDC Mode

| Issue | Cause | Solution |
|-------|-------|----------|
| "Redirect URI mismatch" | Callback URL not registered in provider | Add the callback URL to the app registration's allowed redirect URIs |
| "Invalid client" | Wrong client ID or secret | Verify `ENTRA_CLIENT_ID` and `ENTRA_CLIENT_SECRET` |
| "Tenant not found" | Wrong tenant ID | Verify `ENTRA_TENANT_ID` |
| Login redirect loop | Session cookie not set | Check `SECRET_KEY` is set; verify cookies are enabled in the browser |

### LOCAL Mode

| Issue | Cause | Solution |
|-------|-------|----------|
| App fails to start | `SECRET_KEY` missing, too short, or placeholder | Generate a valid key: `python -c "import secrets; print(secrets.token_hex(32))"` |
| "Invalid email or password" | Wrong credentials or account not yet activated | Verify credentials; issue a new set-password link if the account has no password |
| "Account is temporarily locked" | Too many failed login attempts | Wait for lockout to expire; omniadmins are exempt |
| Set-password link expired | Link older than `LOCAL_SET_PASSWORD_TOKEN_MAX_AGE_HOURS` | Issue a new link via `POST /internal/admin/users/{id}/reset-link` |
| Cookies not sent | `Secure` flag set but site is HTTP | Set `AUTH_COOKIE_SECURE=false` for local HTTP dev |
| All sessions invalidated | `SECRET_KEY` was rotated | Expected — all users must log in again after a key rotation |

### API Key Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "Invalid API key" | Wrong key or typo | Verify the key; generate a new one if lost |
| "API key revoked" | Key was revoked | Generate a new key |
| 429 Too Many Requests | Rate limit exceeded | Wait for the window to reset or increase the rate limit on the key |

---

## Security Checklist

- Use OIDC or LOCAL in production — FAKE mode is gone.
- Always use HTTPS in production (`AUTH_COOKIE_SECURE=true`, which is the default).
- Keep `SECRET_KEY` strong and treat a rotation as a forced logout event for all users.
- Limit `AICT_OMNIADMINS` to trusted administrators.
- Revoke compromised API keys immediately.
- Store API keys in environment variables, never in source code.

---

## See Also

- [Environment Variables](../reference/environment-variables.md) — Complete variable reference including LOCAL mode tuning
- [Internal API](../api/internal-api.md) — Session-based authentication endpoints
- [Public API](../api/public-api.md) — API key authentication
- [Role Authorization](../reference/role-authorization.md) — RBAC system
- [Backend Architecture](../architecture/backend.md) — Auth router implementation
- [User Deletion and App Ownership Transfer](user-deletion-and-app-transfer.md) — Safe user deletion and app ownership handoff
