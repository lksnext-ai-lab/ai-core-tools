# RFC: Provider-Neutral SCIM Provisioning

> Part of [Mattin AI Documentation](../README.md)

## Overview

This document describes the provider-neutral SCIM 2.0 service for provisioning users and groups into Mattin AI, while keeping interactive login through OIDC separate. Microsoft Entra and Keycloak outbound SCIM clients use the same connection-scoped API. For the concrete Keycloak setup, see the [Keycloak outbound SCIM guide](../guides/scim-keycloak.md).

## Status and scope

The provider-neutral SCIM user and group API, static bearer connections, OIDC
identity links, and Keycloak outbound interoperability profile are implemented.
The operational setup and validation procedure is maintained in the
[Keycloak outbound SCIM guide](../guides/scim-keycloak.md).

### Initial scope

- One Mattin AI deployment can connect to multiple external directories through SCIM 2.0, including directories hosted by different providers.
- Each source directory has an isolated `ProvisioningConnection`, credentials, external identities, groups, and memberships.
- SCIM handles provisioning; OIDC remains a separate interactive-login flow. The first login integration profile remains Entra OIDC, but the SCIM API does not depend on Entra.
- Provider-neutral SCIM support does not automatically make interactive login provider-neutral; adding another OIDC identity provider is a separate integration.
- OIDC-first account creation remains allowed (just-in-time provisioning, or JIT) only where a trusted, configured OIDC-to-SCIM identity mapping exists.
- A compatible SCIM client can create accounts before their first login and enrich accounts created by OIDC.
- SCIM synchronizes users, account status, selected profile attributes, groups, and group membership.
- Mattin administrators explicitly map synchronized groups to apps and app roles.
- Direct-manager access is optional and applies only when a source sends a reliable manager attribute; a manager receives `VIEWER` on apps owned by direct reports in the same connection.
- SCIM deprovisioning retains the local `User`, business data, apps, and ownership, while removing the user's SCIM/OIDC identity mappings, group memberships, and manager references. Ownership transfer or deletion is a separate administrative action.
- Entra is the first client profile to validate. Keycloak outbound SCIM is a second interoperability target, not a requirement for Entra-specific behavior in the SCIM core.

### Out of scope for the first release

- General directory synchronization through provider-specific APIs such as Microsoft Graph.
- Adding OIDC login integrations beyond the existing Entra profile.
- Linking one local Mattin account to identities from multiple provisioning connections. A person represented in two connections receives separate Mattin user records in release one.
- Transitive manager-chain access.
- Sharing an individual AI service, agent, silo, or repository without granting app-level access.
- Assigning `OWNER`, `ADMINISTRATOR`, platform roles, or `OMNIADMIN` through SCIM groups.
- Hard deletion of Mattin users and their data on a SCIM deprovisioning event.

## Decisions

1. **The connected SCIM source is authoritative for the attributes and memberships it provisions.** Mattin retains local app ownership and manually granted collaborations.
2. **OIDC and SCIM are separate flows.** OIDC authenticates a person; SCIM provisions and updates directory data. Neither protocol substitutes for the other.
3. **Every independently provisioned external directory has a `ProvisioningConnection`.** The connection is the isolation boundary for external users, groups, credentials, and policies. One connection may serve several Mattin apps; each app is associated with at most one connection in release one.
4. **Identity matching uses the connection and the stable external identifier supplied by that source.** Email, username, and provider-specific aliases remain profile/login attributes, not identity keys.
5. **JIT is permitted.** An OIDC login can create a basic Mattin account before SCIM runs. The account receives no group- or manager-derived app permissions until the corresponding SCIM data and policies exist.
6. **Connection and externalId remain canonical.** SCIM may use an email as a one-time bootstrap reconciliation hint when exactly one unlinked local `User` has that email. It must not link a user that already has an external identity from another connection (or a conflicting identity in the same connection); ambiguous and conflicting mappings remain `409` responses. No accounts are merged, and groups and authorization are unaffected.
7. **Only users and groups in the source system's configured SCIM scope are synchronized.** The source administrator selects the users/groups to provision; enabling SCIM does not import the whole directory by itself.
8. **Group permissions are explicit and managed by an authorized user.** The app owner (or an accepted app administrator) can map groups from their connected source to apps they manage. A manager may manage access only if Mattin explicitly grants that capability; manager-derived `VIEWER` access alone does not grant policy-management rights.
9. **Manager permissions are direct-report only, connection-scoped, and read-only.** The policy grants `VIEWER` on apps owned by direct reports in the same connection.
10. **Derived access is computed, not copied into manual collaborations.** Removing a group membership removes only access derived from that group; it must not delete an independently accepted `AppCollaborator` record.
11. **Deprovisioning disables the local user and removes provisioning links.** It sets `User.is_active=false`, removes the user's `UserExternalIdentity`, `OIDCIdentityLink` mappings, SCIM group memberships, and manager references, but retains the `User`, business data, apps, group rows, group-to-app policies, and app ownership.
12. **Group and manager data are not platform roles.** No group mapping or manager relationship can grant a cross-app administrator role.

## Actors and runtime flows

### SCIM-first: user is provisioned before login

1. **The source-directory administrator** selects users or groups for provisioning to Mattin and enables SCIM synchronization.
2. **The source SCIM client** calls the SCIM base URL and authenticates with credentials belonging to its `ProvisioningConnection`.
3. **Mattin's SCIM router and service** verify that the authenticated connection matches the URL, then upsert only that connection's user, group, and membership records.
4. **Mattin's access policy service** computes app permissions from the explicit app policy and synchronized memberships; it does not require the app itself to store an external directory identifier.
5. **The end user** later signs in through OIDC.
6. **Mattin's OIDC authentication dependency** resolves the identity only when the configured OIDC-to-SCIM mapping supplies a verified stable identifier for that connection.

### OIDC-first: user logs in before SCIM

1. **The end user** signs in through OIDC.
2. **The configured OIDC identity provider** authenticates the user and returns validated issuer and subject claims.
3. **Mattin's OIDC authentication dependency** validates the issuer, resolves its configured provisioning connection and identity mapping, then creates the local `User` and external identity when the mapping is unambiguous.
4. **Mattin** grants no group- or manager-derived access yet; existing ownership or manually accepted collaboration rules continue to apply.
5. **The source SCIM client** later sends the resource with the identifier mapped to the same external identity.
6. **Mattin's SCIM service** finds the existing identity under the same connection and updates its linked `User`, memberships, and optional manager reference without creating a duplicate account.

If OIDC and SCIM use different identifiers, issuers, or source systems, SCIM may bootstrap-link only an otherwise unlinked local user when the email matches exactly one account. Existing external identities still require the stable connection-scoped mapping; explicit OIDC identity links remain available for reviewed overrides.

### Group permission change

1. **The source-directory administrator** changes a user's group membership in the source directory.
2. **The source SCIM client** sends a SCIM group-membership patch using its connection credentials.
3. **Mattin** updates `ExternalGroupMembership` for that connection only.
4. **Mattin's access policy service** sees the new effective membership on the next authorization and app-list request. A removed membership no longer contributes a role.

### Deprovisioning

1. **The source-directory administrator** removes or disables a user in the source directory or removes the user from its provisioning scope.
2. **The source SCIM client** sends `active=false` or the supported deprovision operation.
3. **Mattin** sets the local `User.is_active=false` and removes that user's `UserExternalIdentity`, `OIDCIdentityLink` mappings, SCIM group memberships, and manager references.
4. **Mattin** retains the local `User`, business data, apps, and ownership. Group rows and group-to-app policies also remain; an administrator separately transfers ownership or deletes apps if required.

## Data model

The models below are proposed. `User`, `App`, and `AppCollaborator` remain the existing local-domain models.

### Existing `User` model changes

Do not add provider-specific profile columns such as `department`, `job_title`, `office_location`, or `user_type` to `User`. Keep externally provisioned attributes on `UserExternalIdentity`, which represents the identity and profile synchronized from a particular source connection.

Keep the current global uniqueness constraint on `User.email`, reflecting the expectation that work email addresses are unique. Connection plus stable external identifier is the canonical SCIM identity. During SCIM provisioning only, an email may bootstrap-link exactly one local user that has no external identity; an ambiguous email or an email belonging to a user already linked to another identity remains an actionable conflict. Do not merge accounts.

Each external identity maps to one local `User`; identities from different
provisioning connections are never automatically linked to a user that already
has an external identity. A unique email match may bootstrap-link an otherwise
unlinked local user, while an ambiguous or already-linked match is rejected.

### New `ProvisioningConnection` model

One row represents one customer/company external directory (tenant, organization, or realm) connected to this Mattin deployment.

| Attribute | Constraints and purpose |
|---|---|
| `id` | Internal primary key. |
| `provider_type` | Provider label for operations and interoperability profiles, e.g. `entra`, `keycloak`, or `generic_scim`; it does not select or alter SCIM semantics. |
| `external_directory_id` | Optional external tenant, organization, or realm identifier; unique with `provider_type` when supplied. |
| `connection_key` | Random opaque identifier included in this source's SCIM base URL; not a credential. |
| `display_name` | Admin-facing name for the connected organization. |
| `auth_mode` | Per-connection authentication strategy supported by the configured client profile, initially static bearer or OAuth 2.0 client credentials. |
| `client_id` | OAuth client identifier; required only for OAuth mode. |
| `credential_hash` | Non-recoverable verifier for the per-connection shared secret or bearer token; never store its raw value in the database. |
| `is_active` | Disables SCIM provisioning for this connection and any OIDC login mapping explicitly attached to it when false. |
| `created_at`, `updated_at` | Audit timestamps. |

Required uniqueness: `(provider_type, external_directory_id)` when the external identifier is supplied, and `connection_key`. `client_id` is unique when OAuth mode is selected.

The connection owns synchronized identities, groups, memberships, and provisioning credentials; it does not own Mattin apps. Apps remain associated with their owner through the existing `App.owner_id`. Mattin authorizes a user to manage an app through ownership or an accepted app-administrator collaboration. For group policies, the managing user's linked external identity determines which connection's groups they may select. The app does not need an external-directory column or FK. Manager relationships remain scoped to one connection; a manager's inherited read access does not by itself grant permission to manage app policies.

### New `UserExternalIdentity` model

One row links a local user to one external identity and its SCIM resource.

| Attribute | Constraints and purpose |
|---|---|
| `id` | Internal primary key. |
| `user_id` | Required FK to `User`; unique in release one because each external identity has its own local user record. |
| `connection_id` | Required FK to `ProvisioningConnection`; all external IDs and manager references are scoped through it. |
| `external_id` | Stable source identifier received through SCIM `externalId`; it may be matched to a verified OIDC identifier only through an explicit trusted mapping. |
| `scim_id` | Mattin-generated stable SCIM resource identifier exposed as SCIM `id` and used in resource URLs. |
| `user_name` | Current SCIM `userName`; mutable and not an identity key. |
| `is_active` | State of a currently provisioned identity. On deprovisioning, the identity row is removed and the linked local `User.is_active` is set to false. |
| `manager_external_id` | Optional external identifier of the manager, retained while that identity is not yet resolved. |
| `manager_identity_id` | Nullable self-FK to the manager's `UserExternalIdentity` once resolved. |
| `department` | Optional informational department synchronized from the source; not an authorization rule. |
| `last_synced_at` | Timestamp of the latest successful SCIM update. |
| `created_at`, `updated_at` | Audit timestamps. |

Required uniqueness: `(connection_id, external_id)`, `(connection_id, scim_id)`, and one linked external identity per `User` in release one. Manager resolution must verify that both identities belong to the same connection.

### New `ExternalGroup` model

| Attribute | Purpose |
|---|---|
| `id` | Internal primary key. |
| `connection_id` | FK to the owning `ProvisioningConnection`. |
| `external_id` | Stable external group identifier, scoped to the connection and unchanged by group renames. |
| `scim_id` | Mattin-generated stable SCIM resource identifier exposed as SCIM `id`. |
| `display_name` | Current group name shown to Mattin administrators. |
| `is_active` | Whether the group is currently provisioned and eligible for policy selection. |
| `last_synced_at` | Timestamp of the latest successful update. |
| `created_at`, `updated_at` | Audit timestamps. |

Required uniqueness: `(connection_id, external_id)` and `(connection_id, scim_id)`. Each supported client profile's matching attributes and group-name behavior must be verified during interoperability testing.

### New `ExternalGroupMembership` model

Join table representing current, directly synchronized membership:

| Attribute | Purpose |
|---|---|
| `group_id` | FK to `ExternalGroup`. |
| `user_external_identity_id` | FK to `UserExternalIdentity`. |
| `created_at`, `updated_at` | Membership lifecycle timestamps. |

Required uniqueness: `(group_id, user_external_identity_id)`. Add and remove operations are idempotent.

### New `GroupAppAccessRule` model

Mattin-owned policy mapping a synchronized group to one app:

| Attribute | Purpose |
|---|---|
| `id` | Internal primary key. |
| `group_id` | FK to `ExternalGroup`. |
| `app_id` | FK to `App`. |
| `role` | In release one, `VIEWER` or `EDITOR` only. |
| `created_by_user_id` | User who created the policy. |
| `is_active` | Allows disabling the rule without losing audit history. |
| `created_at`, `updated_at` | Audit timestamps. |

Required uniqueness: `(group_id, app_id)`. The app owner or an accepted app `ADMINISTRATOR` can manage rules for that app; platform administrators retain their existing separate controls. No rule may assign `OWNER`, `ADMINISTRATOR`, or a platform role in the first release.

### Models deliberately not added in release one

- **No materialized `AppAccessGrant` table:** effective roles are computed from source records. This prevents synchronization from overwriting manual permissions and avoids stale grants.
- **No `ManagerAccessPolicy` table:** the initial manager rule is fixed (direct reports, `VIEWER`). Add a policy table only if administrators need to configure variants.
- **No separate `AppCollaborator` source field:** `AppCollaborator` continues to mean a manually invited/accepted collaboration.

Store only a non-recoverable verifier for inbound per-connection credentials in the database; never persist the raw bearer token or client secret. Keep token-signing keys in the deployment's secret manager. The implementation must validate token issuer, audience, expiry, scope, connection identity, and the match between the authenticated connection and the connection in the request URL.

## SCIM API

Expose a connection-scoped SCIM base URL under `/scim/v2/{connection_key}`. Every endpoint is service-to-service, protected by the configured provisioning authentication mechanism, served only over HTTPS, and emits SCIM-compliant response media types and error bodies. The authenticated connection must match the `connection_key` in the URL. The path and SCIM resource model are provider-neutral.

### Provisioning authentication

SCIM 2.0 does not prescribe a client-authentication mechanism. Authentication is configured independently for each connection and must be confirmed against that client's provisioning product; do not assume every client supports the same credentials or token flow.

Two alternatives are under consideration:

1. **OAuth 2.0 client credentials, when supported by the client.** Mattin exposes `POST /scim/oauth/token`, accepts `grant_type=client_credentials` for one `ProvisioningConnection`, and returns a short-lived access token scoped to that connection. The SCIM client uses that token for resource calls. The client secret is verified against the stored non-recoverable verifier; signing keys remain in the deployment secret manager.
2. **Static per-connection bearer token, when supported by the client.** Mattin generates a high-entropy token for the connection; an authorized administrator configures it in the source provisioning product, which sends it as a bearer token on SCIM requests. This mode does not use `/scim/oauth/token`. Mattin verifies it against the stored non-recoverable verifier and supports rotation without logging the token.

Additional authentication strategies can be added when a supported client requires them, without changing SCIM resource handling. In every mode, credentials are connection-specific, HTTPS is required, and the authenticated connection must match the `{connection_key}` in the request URL. Implement only modes tested with supported client profiles; do not expose an unused token endpoint as if every client requires it.

### Required endpoints

| Method and path | Behavior |
|---|---|
| `GET /scim/v2/{connection_key}/ServiceProviderConfig` | Advertise supported SCIM capabilities for the authenticated connection. |
| `GET /scim/v2/{connection_key}/ResourceTypes` | Describe `User` and `Group` resources. |
| `GET /scim/v2/{connection_key}/Schemas` | Advertise supported core and enterprise attributes. |
| `POST /scim/v2/{connection_key}/Users` | Create or safely reconcile a user within this connection; return its stable Mattin resource identifier as SCIM `id`. |
| `GET /scim/v2/{connection_key}/Users` | List/search only this connection's users with pagination and supported filters, at minimum the matching attributes configured for each supported client profile (`externalId`, `userName`). |
| `GET /scim/v2/{connection_key}/Users/{scim_id}` | Retrieve a currently provisioned user resource from this connection. |
| `PATCH /scim/v2/{connection_key}/Users/{scim_id}` | Apply partial updates to supported attributes, including `active` and same-connection manager reference. |
| `DELETE /scim/v2/{connection_key}/Users/{scim_id}` | Deprovision the user as described below, while retaining the local user, business data, apps, and ownership. |
| `POST /scim/v2/{connection_key}/Groups` | Create a synchronized group in this connection. |
| `GET /scim/v2/{connection_key}/Groups` | List/search only this connection's groups; support exclusion of `members` where requested. |
| `GET /scim/v2/{connection_key}/Groups/{scim_id}` | Retrieve a group from this connection. |
| `PATCH /scim/v2/{connection_key}/Groups/{scim_id}` | Rename a group and add/remove same-connection membership entries; `remove` with `path=members` and no `value` clears all memberships. |
| `DELETE /scim/v2/{connection_key}/Groups/{scim_id}` | Mark the group inactive, remove its memberships, and ensure its rules no longer grant access. |

`/Bulk` is not required for the initial release. `ServiceProviderConfig` must advertise only capabilities actually implemented by Mattin. Implement and test the filter operators, casing behavior, pagination, status codes, and response schemas used by each supported client profile; do not claim general SCIM compatibility beyond what is tested.

All resource reads and writes must be constrained by the authenticated connection in both the route and repository query. A valid token for one connection must not read or mutate resources belonging to another connection, even if the caller changes an ID in the path.

### Attribute mapping

The SCIM schema is provider-neutral; each source product maps its own directory attributes to SCIM attributes. Mattin stores only the supported profile attributes and treats unmapped or omitted attributes as absent. Example mapping:

| Source value | SCIM attribute | Mattin destination |
|---|---|---|
| Stable user identifier | `externalId` | `UserExternalIdentity.external_id` |
| Tenant, organization, or realm identifier | Connection context/configuration | `ProvisioningConnection.external_directory_id` |
| Login name or username | `userName` | `UserExternalIdentity.user_name` |
| Work email | `emails[type eq "work"].value` | `User.email` |
| Display/given/family name | `displayName`, `name.givenName`, `name.familyName` | `User.name` |
| Provisioning/account state | `active` | `User.is_active`; deactivation also removes the user's provisioning identity links |
| Department, when supported | Enterprise User `department` | `UserExternalIdentity.department` |
| Stable group identifier | Group `externalId` | `ExternalGroup.external_id`, scoped by `connection_id` |
| Group name | Group `displayName` | `ExternalGroup.display_name` |
| Group membership | Group `members` references | `ExternalGroupMembership` |
| Manager relationship, when supported | Enterprise User `manager` reference | `manager_external_id`, then `manager_identity_id` |

For Entra, the source values may be the Entra user/group object IDs and tenant ID; for Keycloak they may be user/group IDs and realm context. These are client-profile mappings, not assumptions in the SCIM service. The SCIM `id` and `meta` values are generated and maintained by Mattin.

## OIDC identity linking and user lifecycle

The current OIDC configuration is Entra-specific: it has one `ENTRA_TENANT_ID` setting, and the OIDC dependency resolves or creates a `User` by email in [`auth_utils.py`](../../backend/routers/internal/auth_utils.py). The first login profile therefore remains Entra OIDC, independently of the provider-neutral SCIM API. Supporting another OIDC provider requires its own issuer/claim validation and an explicit mapping to a SCIM connection.

### Required resolution order

1. **Mattin OIDC authentication dependency** validates the token signature, issuer, audience, and lifetime and checks that the issuer is explicitly allowed for login.
2. **Mattin** extracts verified OIDC claims. For the initial Entra profile, confirm that `lks-idprovider-entraid` can validate multiple allowed tenants and exposes tenant ID and stable object ID; extend the provider adapter if it cannot.
3. **Mattin** resolves the associated provisioning connection using its configured OIDC-to-SCIM identity mapping and looks up `UserExternalIdentity` by `(connection_id, external_id)`.
4. If found, **Mattin** uses its linked local `User` and checks active status.
5. If not found and JIT is enabled, **Mattin** creates a separate local `User` and its `UserExternalIdentity` in one transaction using the verified claims.
6. If another connection has a user with the same email, SCIM may reuse that
local user only when it has no external identity. A user already linked to
another connection or external ID is a mapping conflict; Mattin does not merge
accounts.

SCIM matches by `(connection_id, externalId)`. OIDC may resolve that same identity only when the configured mapping proves that the verified issuer/subject corresponds to the SCIM external identifier. A SCIM create/update first searches by `externalId`; on a match it updates the linked user, including an email change if the new email is not already in use. It must not create another local user merely because the username or email changed.

### Existing-account migration

Before enabling SCIM, developers and deployment administrators inventory existing
OIDC-created `User` records and determine which connection owns each account. An
exact email match can bootstrap-link only an unlinked local user; existing
identities still require a verified stable identifier or an explicit reviewed
reconciliation. No identities are merged.

### Deactivation behavior

On SCIM user deactivation (`PATCH` with `active=false` or `DELETE /Users/{scim_id}`), Mattin:

- Sets `User.is_active=false`, blocking authenticated requests for that user.
- Removes the user's `UserExternalIdentity`, `OIDCIdentityLink` mappings, SCIM group memberships, and manager references.
- Retains the local `User`, its business data, apps, and ownership. Group rows and group-to-app policies also remain.
- Does not transfer `App.owner_id`; app transfer/deletion remains a separate explicit workflow.

## Permission resolution

The existing access resolver in [`role_authorization.py`](../../backend/routers/controls/role_authorization.py) currently evaluates app ownership and accepted `AppCollaborator` rows. The new implementation adds derived sources without replacing those sources.

### Effective app role

For a user and app, resolve the highest applicable role from:

1. **App ownership:** owner remains `OWNER`.
2. **Manual collaboration:** accepted `AppCollaborator` role.
3. **Group policy:** highest active `GroupAppAccessRule.role` among the user's active synchronized group memberships. A rule can be created or changed only by an authorized app manager whose linked identity belongs to the same connection as the group.
4. **Manager policy:** `VIEWER` when the user is the direct manager of the app owner and both identities belong to the same connection.
5. **No affiliation:** existing authenticated `USER` behavior.

`GUEST` remains unauthenticated. Group and manager-derived permissions can never produce `OWNER`, `ADMINISTRATOR`, or a platform role in release one. If multiple non-owner sources grant roles, the effective app role is the highest role in the existing app role hierarchy; removing one source removes only that source's contribution.

### App listing and enforcement

The same permission service must be used for both:

- Endpoint authorization through `resolve_user_app_role` / `RoleChecker`.
- The user's accessible-app query currently routed through `AppCollaborationRepository.get_user_accessible_apps` and `AppCollaborationService`.

Updating authorization without updating app discovery would make a permitted app invisible; updating app listing without authorization would expose an insecure path. Tests must cover both.

### Management endpoints for group rules

These are Mattin internal APIs, not SCIM endpoints. Proposed routes:

| Method and path | Behavior |
|---|---|
| `GET /internal/external-groups` | List active synchronized groups from the authenticated caller's connection; this is not scoped to a particular app and does not grant access. |
| `GET /internal/apps/{app_id}/group-access` | List active and disabled group access assignments. |
| `POST /internal/apps/{app_id}/group-access` | Create a rule with `{ "group_id": ..., "role": "viewer" }`. |
| `PATCH /internal/apps/{app_id}/group-access/{group_access_id}` | Change the role or enable/disable the group-app access assignment. |
| `DELETE /internal/apps/{app_id}/group-access/{group_access_id}` | Remove the group-app access assignment; it does not delete the external group. |

Listing external groups requires an authenticated caller with a linked external identity and returns only groups from that identity's connection. Creating, changing, or deleting a group-access assignment remains app-scoped: only the app owner or an accepted app administrator may manage these assignments in the first release. The backend verifies the caller's app-management rights, and that the selected group is active and belongs to the caller's connection. A later manager-access feature may grant policy-management rights explicitly; ordinary manager-derived `VIEWER` access is insufficient.

The first release grants app-level access. It does not share only an AI service or hide particular app data from a `VIEWER`; all routes and data currently covered by app-level roles remain in scope. Service-level sharing requires a separate authorization design.

## Backend implementation responsibilities

Keep the existing layered architecture:

- **SCIM router**: parse/validate SCIM requests, authenticate service calls, resolve and enforce the connection scope, convert service errors to SCIM responses.
- **SCIM schemas**: typed request/response models for users, groups, PATCH operations, and list responses.
- **SCIM provisioning service**: idempotent user/group upserts, external identity resolution, manager resolution, membership diffs, and deprovisioning.
- **Repositories**: persistence and filtered/paginated SCIM queries.
- **OIDC auth dependency/provider**: accept only configured issuers, validate provider-specific claims, resolve through an explicit OIDC-to-SCIM identity mapping before falling back to JIT creation, and preserve claims required for identity linking.
- **App access policy service**: compute effective role and accessible apps from ownership, manual collaborations, group rules, and the manager rule.
- **Internal app router/service**: authorize and persist group-to-app policy management.
- **Alembic migrations**: add/alter models with a tested downgrade; register every model through the normal model import registry.

Do not put provisioning business logic directly in FastAPI route handlers. Do not log bearer tokens, client secrets, or full SCIM payloads containing personal data.

### Backend request lifecycle

#### SCIM authentication and request processing

1. **The source SCIM client** authenticates using the mode configured for its connection: it either requests a short-lived token from `POST /scim/oauth/token` or sends its configured static bearer token.
2. **Mattin's SCIM authentication dependency** validates the bearer credential and resolves the active connection. For each SCIM request, it verifies that the authenticated connection matches the `{connection_key}` in the URL.
3. **The SCIM router** validates the request shape with the SCIM schemas and passes the connection context and validated data to the provisioning service.
4. **The provisioning service** applies the operation in a database transaction. Repositories scope all reads and writes by `connection_id`; a resource ID supplied by the caller is never sufficient to cross that boundary.
5. **The router** returns the resulting SCIM resource or a SCIM-compliant error response. Authentication failures, invalid resources, and conflicting email updates must not be reported as successful operations.

The authentication endpoint, when OAuth mode is selected, and the SCIM resource endpoints are service-to-service APIs. Internal app-management APIs instead use Mattin's existing authenticated-user dependencies.

#### User create, update, and login

- For SCIM user creation or lookup, **Mattin** matches by `(connection_id, external_id)`. On first creation, the service creates the local `User` and its `UserExternalIdentity` together; on subsequent updates, it updates those linked records rather than creating another account.
- The service checks the global uniqueness of `User.email`. When no SCIM identity exists yet, an exact email match may bootstrap-link one otherwise unlinked local `User`; an ambiguous match or a user already linked to an external identity remains an actionable conflict. If the email changes and is unused, the service updates it on the already matched user.
- For OIDC login, **the identity provider** validates the sign-in token and **Mattin** resolves a provisioning connection only through its configured issuer/claim mapping. If there is no SCIM-created identity and JIT is enabled, Mattin creates the local user and external identity in one transaction. Login must not fall back to email-only identity linking.
- The current `get_current_user_oidc` flow enriches the authentication context by looking up or creating a local user by email. The initial Entra OIDC profile must replace that lookup with the configured tenant/object-ID resolution above, while still enriching the authenticated context with Mattin's local `User.user_id` for existing authorization dependencies.

#### Group membership and manager synchronization

- For SCIM group requests, **Mattin** matches each `ExternalGroup` by `(connection_id, external_id)`. Group member references are resolved only to user identities in that same connection.
- A SCIM membership add creates a missing `ExternalGroupMembership`; adding an existing membership is a no-op. A removal deletes the matching membership if present; removing an absent membership is a no-op. These operations are idempotent so clients can safely retry requests.
- For a SCIM user update carrying a manager reference, **Mattin** stores `manager_external_id` and resolves it to `manager_identity_id` only within the same connection. If the manager has not arrived yet, the external ID is retained and resolution can be retried when identities are synchronized.
- Group PATCH `remove` with `path=members` and no `value` clears all memberships from that group.
- Deactivation sets `User.is_active=false` and removes the user's `UserExternalIdentity`, `OIDCIdentityLink` mappings, SCIM group memberships, and manager references. It preserves the local user, business data, apps, ownership, group rows, and group-to-app policies.

#### App access evaluation

- **An app owner or authorized app administrator** creates or updates the group-to-app role assignment through the internal `group-access` API. Mattin verifies app-management permission and that the selected active group belongs to the caller's connection.
- **The app access policy service** resolves a user's effective role from app ownership, accepted `AppCollaborator` records, active group memberships and group-to-app assignments, and the direct-manager policy. It returns the highest applicable role; it does not create per-user `AppCollaborator` rows for group or manager access.
- **RoleChecker and app listing** must use the same policy service. Therefore, a newly saved group assignment applies to already-synchronized group members on their next authorization or app-list request; an incoming SCIM membership change affects the next evaluation without a separate permission-grant job.

The existing implementation places OIDC account enrichment in `routers/internal/auth_utils.py`, app-role resolution in `routers/controls/role_authorization.py`, and accessible-app queries in `AppCollaborationRepository`/`AppCollaborationService`. The implementation must update these paths coherently rather than adding an independent permission check used by only some endpoints.

## Implementation sequence and gates

### Phase 0 — SCIM contract and interoperability verification

**Developers** define the provider-neutral SCIM profile and test its discovery, authentication, user/group operations, PATCH behavior, and error responses with at least Microsoft Entra and Keycloak outbound SCIM. They document unsupported optional capabilities and provider-specific mappings instead of adding provider conditionals to the SCIM core. They separately verify that the initial Entra OIDC profile supports an allowlist of tenants and exposes tenant ID and object ID claims. **Each source-directory administrator** confirms that the intended users/groups can be assigned to the SCIM target.

**Exit gate:** connection and app-access scope, identity matching key, email uniqueness assumption and exceptional conflict handling, supported SCIM capabilities, provider-specific mappings, role policy, deactivation behavior, and per-connection authentication are documented and testable.

### Phase 1 — Database and identity lifecycle

**Developers** add `ProvisioningConnection`, `UserExternalIdentity` (including `department`), `ExternalGroup`, `ExternalGroupMembership`, and `GroupAppAccessRule`; replace global OIDC email resolution with configured issuer/claim mapping and external-ID resolution while retaining the global email uniqueness constraint; implement safe collision handling and OIDC/SCIM linking; and add Alembic upgrade/downgrade for the new tables. No provider or connection FK is added to `App`.

**Exit gate:** OIDC-first and SCIM-first tests converge on exactly one local user
when the stable mapping exists or when a unique email safely bootstraps an
unlinked account; ambiguous and already-linked email collisions are rejected;
one connection cannot see or affect another connection's identity, group, app
policy, or credential.

### Phase 2 — SCIM user endpoints

**Developers** implement and test the user resource endpoints, filters, pagination, PATCH behavior, active-state changes, SCIM errors, and production authentication.

**Exit gate:** interoperability tests for each supported client profile pass for create, find, update, disable, duplicate/retry, and reactivation.

### Phase 3 — SCIM groups and group-app access

**Developers** implement group endpoints and membership PATCH operations, then implement the internal group-access management endpoints and effective role resolution. **App owners/admins** can create explicit rules in Mattin.

**Exit gate:** a group member gets only the configured app role; removing membership removes that derived access but preserves manual collaboration; group deletion cannot leave an effective grant.

### Phase 4 — Manager-derived read access

**Developers** implement optional manager-attribute mapping and resolution. **Each source-directory administrator** verifies that its SCIM client sends manager references for users in scope before enabling manager-derived access. Mattin grants `VIEWER` only on apps owned by direct reports in the same connection.

**Exit gate:** manager changes and unresolved manager references update access safely; no transitive access is granted.

### Phase 5 — Provider pilots and rollout

1. **Mattin operators** create an active `ProvisioningConnection`, choose an authentication mode supported by that client's profile, generate per-connection credentials, and provide the SCIM URL, authentication setup, attribute mapping guide, and test procedure to the source-directory administrator.
2. **The source-directory administrator** configures its provisioning client with Mattin's URL and credentials, assigns a pilot group, maps user/group attributes, and runs that product's connection test or on-demand provisioning.
3. **The source SCIM client** sends the initial synchronization and subsequent changes using its connection-specific credentials and URL.
4. **Mattin operators, app owners/administrators, and the source-directory administrator** review provisioning logs and Mattin audit events, configure app access policies, resolve errors, and only then expand the source's assigned scope.

Validate Entra and Keycloak as separate client profiles before describing both as supported. Do not claim compatibility with every SCIM product based only on protocol conformance; add each product after its profile passes the interoperability suite.

## Test plan and acceptance criteria

- SCIM `POST` retries do not create duplicate users, groups, or memberships.
- User queries find resources by the configured matching attributes and return SCIM `ListResponse` with correct pagination.
- OIDC-first and SCIM-first ordering links the same external identity through an explicit mapping or, for SCIM provisioning only, a unique email bootstrap match to an otherwise unlinked local user.
- Email or username changes do not create a new account or detach the external identity.
- A different external ID using an existing email may be linked only during SCIM provisioning when the email identifies exactly one local user with no external identity; OIDC login never uses email-only linking.
- The same email in two provisioning connections reuses an unlinked local user
  only for the first safe bootstrap match; a user already linked to an external
  identity produces a safe, actionable conflict.
- A credential for one connection cannot read, change, or delete users/groups belonging to another connection.
- A user cannot create or change a group access rule using a group from a connection different from their own linked identity.
- Apps have no provider or connection FK; group-policy management is authorized through the app owner/administrator and that user's linked identity.
- Manager lookup and inherited access cannot cross provisioning connections.
- OIDC rejects unconfigured issuers and never links identities through email alone.
- SCIM email bootstrap never links an OIDC identity during login, never crosses an existing external identity, and rejects ambiguous matches.
- `active=false` and `DELETE /Users` set `User.is_active=false` and remove provisioning links, memberships, and manager references while retaining the local user and business data/apps.
- Group add/remove and group deprovision update effective access correctly and idempotently.
- A group rule grants only the configured role on the configured app.
- A user with several roles receives the highest applicable app role; removing one source preserves other sources.
- Manager policy grants `VIEWER` only for direct reports' owned apps.
- App listing and every protected API endpoint agree on effective access.
- SCIM cannot modify app ownership, manual collaborations, platform roles, or `OMNIADMIN`.
- Secret rotation, invalid credentials, wrong issuer/audience/connection mapping, malformed PATCH, and missing mappings fail safely with actionable logs and SCIM-compliant errors.
- Migration upgrade and downgrade both pass.

## Operations and responsibilities

| Actor | Responsibility |
|---|---|
| Mattin developers | Implement schema, API, identity linking, authorization, tests, and technical setup instructions. |
| Mattin operators | Deploy HTTPS endpoints, protect/rotate provisioning credentials, monitor errors, and coordinate rollout. |
| Source-directory administrator | Configure the provisioning client, assign users/groups, set attribute mappings, start provisioning, and review its provisioning logs. |
| Source SCIM client | Periodically send SCIM changes only for the users/groups in that connection's configured scope. |
| End user | Sign in interactively through OIDC; does not call SCIM. |
| Mattin backend | Persist provisioning state, resolve effective app roles, and enforce access on each request. |

## References

- [SCIM Core Schema, RFC 7643](https://www.rfc-editor.org/rfc/rfc7643)
- [SCIM Protocol, RFC 7644](https://www.rfc-editor.org/rfc/rfc7644)
- [Microsoft Entra: Develop a SCIM endpoint and provision users and groups](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/use-scim-to-provision-users-and-groups)
- [Microsoft Entra: Customize attribute mappings](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/customize-application-attributes)
- [Keycloak SCIM Outbound extension](https://github.com/shebang-labs/scim-outbound-for-keycloak) (community project; validate its supported Keycloak version before use)
- [Mattin authentication guide](../guides/authentication.md)
- [Mattin role authorization reference](../reference/role-authorization.md)
