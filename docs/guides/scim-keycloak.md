# Keycloak outbound SCIM provisioning

> Part of [Mattin AI Documentation](../README.md)

This guide explains how an administrator connects a Keycloak realm to Mattin AI
for outbound SCIM 2.0 provisioning. OIDC login and SCIM provisioning are
separate: OIDC authenticates users, while SCIM creates and updates users and
groups in Mattin.

## What is mandatory

The connection has two sides:

| Actor | Responsibility |
|---|---|
| Mattin administrator | Creates the SCIM connection and obtains its URL and bearer token. |
| Keycloak administrator | Configures the outbound SCIM target, selects the users/groups in scope, and starts reconciliation. |
| Keycloak SCIM client | Sends SCIM requests to Mattin. |
| Mattin SCIM API | Authenticates the connection and applies the provisioning changes. |

Creating the connection in Mattin is mandatory. The current backend generates
the opaque `connection_key` and the bearer token; they must not be invented in
Keycloak. The raw bearer token is returned only when the connection is created
or its token is rotated.

## Prerequisites

- Mattin is reachable from the Keycloak container or host.
- The URL is served over HTTPS outside local development.
- An administrator can call Mattin's internal API.
- The Keycloak outbound SCIM extension is installed and enabled.
- The Keycloak realm to provision is known.

When Keycloak runs in Docker and Mattin runs on the host, a local development
target commonly uses `host.docker.internal` instead of `localhost`. From
Keycloak's point of view, `localhost` means the Keycloak container itself.

## 1. Create the connection in Mattin

Use the authenticated internal API or the internal API documentation. The
endpoint is:

```text
POST /internal/admin/scim-connections
```

The authenticated actor must be a Mattin administrator. The request body for a
Keycloak connection is:

```json
{
  "provider_type": "keycloak",
  "external_directory_id": "my-realm",
  "display_name": "Keycloak my-realm",
  "auth_mode": "static_bearer"
}
```

The response contains the values needed by Keycloak:

```json
{
  "id": 12,
  "connection_key": "<opaque-connection-key>",
  "display_name": "Keycloak my-realm",
  "auth_mode": "static_bearer",
  "is_active": true,
  "bearer_token": "<token-shown-once>"
}
```

The SCIM base URL is:

```text
https://<mattin-host>/scim/v2/<opaque-connection-key>
```

Do not append `/Users` or `/Groups` to the base URL when configuring the
target. Store the bearer token in a secret manager or protected Keycloak
configuration. Do not commit it to source control or paste it into logs.

If the token is lost, rotate it from:

```text
POST /internal/admin/scim-connections/{connection_id}/rotate-token
```

After rotation, the old token stops working and the new token must be updated
in Keycloak.

## 2. Configure the Keycloak outbound target

The target can be configured from the Keycloak outbound SCIM extension UI. The
exact labels depend on the extension version, but the values are:

| Keycloak setting | Value |
|---|---|
| Realm | The realm represented by `external_directory_id`. |
| SCIM base URL | `https://<mattin-host>/scim/v2/<connection-key>` |
| Authentication | Bearer token / static bearer. |
| Bearer token | The token returned by Mattin. |
| Users | Select the users or groups that should be provisioned. |
| Groups | Enable group provisioning if group synchronization is required. |

The source scope matters: enabling SCIM does not automatically import every
realm user unless the extension is configured to include them.

After changing a user, group, or target setting in the Keycloak UI, click
**Save**. Changing the switch alone only changes the unsaved form state; it
does not generate a SCIM operation.

## 3. Configure the target through Keycloak Admin REST

The UI is preferred for normal operation. Admin REST is useful for automation,
repeatable local setup, or when the extension UI does not expose a setting.
The exact paths are supplied by the outbound SCIM extension, not by the
standard Keycloak Admin API.

The target lifecycle used by the extension is:

```text
GET  /admin/realms/{realm}/scim-outbound/targets
POST /admin/realms/{realm}/scim-outbound/targets
POST /admin/realms/{realm}/scim-outbound/targets/{targetId}/reconcile
POST /admin/realms/{realm}/scim-outbound/worker/run
```

Use a fresh Keycloak Admin REST access token in the `Authorization` header:

```powershell
$headers = @{
  Authorization = "Bearer $adminToken"
}
```

The target must point to the Mattin SCIM base URL, not to an individual
resource endpoint. A typical target configuration is conceptually:

```json
{
  "name": "mattin-local",
  "baseUrl": "http://host.docker.internal:8000/scim/v2/<connection-key>",
  "authentication": {
    "type": "bearer",
    "token": "<mattin-scim-token>"
  }
}
```

Use the extension's OpenAPI/Admin REST representation for the exact create or
update payload. The target's connectivity test should reach
`ServiceProviderConfig`, `ResourceTypes`, and `Schemas` successfully.

## 4. Validate the connection

The Mattin SCIM discovery endpoints require the connection bearer token:

```powershell
$scimHeaders = @{
  Authorization = "Bearer $mattinScimToken"
}

Invoke-RestMethod `
  -Method Get `
  -Uri "$scimBaseUrl/ServiceProviderConfig" `
  -Headers $scimHeaders

Invoke-RestMethod `
  -Method Get `
  -Uri "$scimBaseUrl/ResourceTypes" `
  -Headers $scimHeaders

Invoke-RestMethod `
  -Method Get `
  -Uri "$scimBaseUrl/Schemas" `
  -Headers $scimHeaders
```

Then run a target test or reconciliation from Keycloak. Expected results are:

- a new Keycloak user appears in `GET /Users`;
- an existing Mattin user with the same unique email is safely linked when it
  has no incompatible external identity;
- disabling the Keycloak user and saving it results in `active: false`;
- re-enabling the user and saving it results in `active: true`.

The resource URL for a provisioned user uses Mattin's generated SCIM id:

```text
GET /scim/v2/{connection-key}/Users/{scim-id}
```

## 5. Troubleshooting

| Symptom | Check |
|---|---|
| `401 Unauthorized` from Mattin | The bearer token may be expired, copied incorrectly, rotated, or sent to the wrong connection key. |
| Keycloak cannot connect from Docker | Use `host.docker.internal` for a host service in local Docker setups; verify the port is reachable from the container. |
| The user remains active | Confirm the Keycloak change was saved, then run reconciliation/worker and inspect the newest operation, not historical failures. |
| `Unsupported PATCH path: externalId` | Verify Mattin is running the current SCIM service and retry the operation. Keycloak may include an idempotent `externalId` operation with an `active` update. |
| Duplicate or email conflict | Check that the local Mattin user has no conflicting external identity and that the source `externalId` is stable. |
| Groups are missing | Enable group provisioning and select the groups in Keycloak's source scope. |

The outbox and failed-operation views are operational diagnostics. Historical
failed records can remain after a later successful retry, so compare operation
timestamps with the reconciliation time.

## See also

- [SCIM provisioning architecture](../architecture/rfc-scim-provisioning.md)
- [Authentication guide](authentication.md)
- [Internal API](../api/internal-api.md)
