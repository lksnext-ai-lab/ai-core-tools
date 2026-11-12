# Connectors: Adding an Output Provider

Output Channels deliver scheduled-task results to external systems (today: Teams Workflow webhooks and generic HTTPS webhooks with HMAC / bearer / no authentication). Providers live in `backend/connectors/`; orchestration lives in `backend/services/output_channels/`. This guide explains the layering, the provider contract, and the exact steps to add a provider.

Original design: [Output Providers RFC](rfc-scheduled-task-output-providers.md) and [Webhooks RFC](rfc-scheduled-task-webhooks.md).

## Layers

```
connectors.core  <-  connectors.providers.*  <-  connectors.registry  <-  services.output_channels  <-  routers / scheduling
```

| Layer | Path | Role |
|-------|------|------|
| Core | `backend/connectors/core/` | Contracts (`contracts.py`), `registry.py` (`ProviderRegistry` mechanism), `errors.py`, `http.py` (SSRF/pinned-client helpers), `messages.py`, `inbound.py`, `settings.py` |
| Providers | `backend/connectors/providers/{teams_workflow,webhook}/` | One folder per provider (`provider.py`, `config.py`, ...) |
| Registry | `backend/connectors/registry.py` | The single explicit map `_REGISTRY` and the `DestinationSettings` union |
| Orchestration | `backend/services/output_channels/` | `destinations.py`, `delivery_factory.py`, `delivery_processor.py`, `delivery_policy.py`, `destination_test.py`, `spool.py`, `bindings.py`, `attachments.py`, `dto.py`, `deliveries.py`, `messages.py` |
| Persistence | `backend/repositories/output_*_repository.py`, `scheduled_task_output_binding_repository.py` | Data access |
| Workers | `backend/scheduling/output_delivery.py` | DBOS queue `output-deliveries`, `process_output_delivery_step`, `output_delivery_workflow`, `output_delivery_reconciler`; workflow id `output-delivery-{id}-g{gen}`. Names are stable: do not rename them |

The old `backend/output/` package no longer exists.

### Enforced rules

`tests/unit/connectors/test_architecture_guard.py` (AST based) enforces:

| Rule | Meaning |
|------|---------|
| R1 | No `str` constant equal to a registered provider key, except in `connectors/registry.py` and inside the provider's own folder. The core never names providers |
| R2 | Files outside `connectors/` never import `connectors.providers` |
| R3 | `connectors/core/**` imports only `connectors.core.*`, `utils.logger`, `utils.ssrf_guard` (also as dynamic-import strings) |
| R7 | `connectors/**` (except `registry.py`) may import only `connectors.core.*`, its own provider package, `utils.logger`, `utils.ssrf_guard`. No sibling providers |
| R4 / R5 | Outside `connectors/`, `OutputDestination.credentials` is read only through `read_credentials(...)` and never used in SQL predicates (the column is JSON; `{}` and `None` must not be distinguished) |
| R6 | `VerifiedRequest` is never forged (no `_VERIFY_TOKEN`, `__new__` tricks) in `backend/` or `tests/` |
| R8 | Only `backend/connectors/**` and `backend/services/*_channels/**` may import `connectors` |
| Size | No file under `connectors/**` or `services/output_channels/**` may exceed 400 lines (`test_output_channel_and_connector_modules_stay_under_400_lines`) |

R1, R4 and R5 run on a watched set (fixed floor of files + globs + every backend file importing `connectors.*`, `services.*_channels*` or `models.output_delivery`), not on all of `backend/`. The schema Literal and the model default are intentionally outside it.

`tests/unit/connectors/test_import_isolation.py` checks that connectors only load an allowlist of first-party modules (`utils`, `utils.logger`, `utils.ssrf_guard`) that importing `connectors.core` loads neither `connectors.providers.*` nor `connectors.registry`, and that every `connectors.*` and `services.output_channels.*` module, plus `services.scheduled_task_service`, `scheduling.output_delivery` and `routers.internal.output_providers`, imports cleanly in a fresh interpreter (no load-time cycles).

## The `OutboundProvider` contract

From `backend/connectors/core/contracts.py`:

```python
@runtime_checkable
class OutboundProvider(Protocol):
    descriptor: ProviderDescriptor

    def validate_destination(
        self, url: str, public_config: Mapping[str, JsonValue] | None, credentials: Mapping[str, str] | None,
    ) -> ValidatedDestination: ...
    def parse_settings(
        self, public_config: Mapping[str, JsonValue] | None, credentials: Mapping[str, str] | None,
    ) -> DestinationSettingsBase: ...
    def ensure_same_endpoint(self, current_url: str, new_url: str) -> None: ...
    def includes_attachments(self, public_config: Mapping[str, JsonValue] | None) -> bool: ...
    def receiver_deduplicates(self, public_config: Mapping[str, JsonValue] | None) -> bool: ...
    def build_snapshot(self, destination: DestinationView) -> JsonDict: ...
    def snapshot_public_config(self, snapshot: Mapping[str, JsonValue]) -> JsonDict: ...
    def build_run_delivery(self, context: RunDeliveryContext) -> PreparedDelivery: ...
    def build_test_delivery(self, context: TestDeliveryContext, stager: AttachmentStager) -> PreparedDelivery: ...
    async def send(self, request: OutboundRequest) -> SendReceipt: ...
    def example_destination(self) -> DestinationExample: ...
```

Validation methods raise `ValueError` (the router turns them into 400). `send` raises `DeliveryError(kind=...)` with `kind` in `permanent | retryable | unknown`.

### Descriptor and capabilities

```python
@dataclass(frozen=True)
class OutboundCapabilities:
    receiver_deduplication: bool = False
    spooled_attachments: bool = False
    attachment_lease_seconds: int | None = None
    update_policy: UpdatePolicy = UpdatePolicy.ROTATE_URL_ONLY
    url_allows_fragment: bool = False

@dataclass(frozen=True)
class ProviderDescriptor:
    key: str
    name: str
    supports_links: bool = True
    supports_native_attachments: bool = False
    supports_binary_attachments: bool = False
    content_modes: tuple[str, ...] = ("result", "excerpt", "link_only")
    directions: frozenset[Direction] = frozenset({Direction.OUTBOUND})
    outbound: OutboundCapabilities | None = OutboundCapabilities()
```

Each capability drives one generic branch in the orchestration layer (no provider names in the core):

| Capability | Branch it controls |
|------------|--------------------|
| `receiver_deduplication` | `delivery_policy.receiver_can_deduplicate` (also requires `provider.receiver_deduplicates(config)` to be true for the destination). It feeds the single stale-"sending" rule (`classify_stale_sending`) and the `TimeoutError` classification in `delivery_processor.process_delivery`: deduplicating receivers are `retryable`, others `unknown` |
| `spooled_attachments` | Registry helper `spool_attachment_provider_keys()`: destinations of these providers admit spooled/multipart attachments |
| `attachment_lease_seconds` | `delivery_policy.lease_seconds_for`: when `includes_attachments(...)` is true, the attempt lease is this value instead of `LEASE_SECONDS` (120) |
| `update_policy` | PATCH semantics in `destinations._validate_endpoint_changes` (below) |
| `url_allows_fragment` | Whether the conformance suite expects URLs with fragments to be accepted |

`content_modes` must be a subset of the schema Literal `["result", "excerpt", "link_only"]`; a new mode is a schema + golden + frontend change.

`update_policy`:

- `REVALIDATE_ALL` (webhook): every PATCH revalidates URL + config + credentials; credentials are rewritten only if the PATCH touches them.
- `ROTATE_URL_ONLY` (Teams): only a new `webhook_url` is validated and persisted. **Invariant:** such a provider takes no settings. `parse_settings` accepts only empty `public_config`/`credentials` and rejects any key, and URL rotation calls `validate_destination(url, None, None)`.

`includes_attachments` and `receiver_deduplicates` read the raw `public_config` dict on purpose: they run against delivery snapshots and legacy rows, which may not satisfy the typed model.

Descriptors currently registered: `teams_workflow` (`ROTATE_URL_ONLY`, `url_allows_fragment=True`) and `webhook` (`receiver_deduplication=True`, `spooled_attachments=True`, `attachment_lease_seconds=180`, `REVALIDATE_ALL`).

## Inbound contract (defined, not implemented)

```python
@runtime_checkable
class InboundProvider(Protocol):
    descriptor: ProviderDescriptor
    def verify(self, raw: RawInboundRequest) -> VerifiedRequest: ...
    def parse(self, verified: VerifiedRequest) -> InboundMessage: ...
```

No inbound provider is registered in this phase; only the contract and its conformance checks exist. `VerifiedRequest` (`connectors/core/inbound.py`) is a `@final`, immutable, non-copyable, non-picklable proof of verification. It can be built only with a module-private sentinel passed by `BaseInboundProvider.verify`, so `parse` knows authentication ran. `verify` is fail-closed (raises `PermissionError`); `BaseInboundProvider` makes `verify`/`parse` final and providers implement `_authenticate`/`_parse_verified`. The sentinel guards against accidental construction, not deliberate in-process forgery (R6 plus `test_inbound_contract.py` cover this).

## Typed settings

Each provider owns Pydantic models for its public config and credentials (see `providers/webhook/config.py`):

- `ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)`; secrets are `SecretStr`.
- A settings class derived from `DestinationSettingsBase` with `provider_key: Literal["<key>"] = "<key>"`, `public_config_json()` and `credentials_json()` (values exactly as stored).
- `DestinationSettings` in `connectors/registry.py` is a discriminated union (`Field(discriminator="provider_key")`). It mirrors the registry by hand; the conformance suite checks they agree. Parse untrusted dicts through `DESTINATION_SETTINGS_ADAPTER`, because `hide_input_in_errors` only works on the root validator.

User-facing error messages do **not** come from Pydantic. `parse_<key>_settings` runs hand-written checks first, in the historical order and with the historical texts (e.g. `"Unsupported webhook authentication mode"`), and builds the models only after every check passed. Pydantic therefore never produces a message that could echo an input value, and the API texts stay stable.

## Adding a provider

1. Create `backend/connectors/providers/<key>/` with `__init__.py` (exporting the provider class), `provider.py` (class implementing `OutboundProvider`, `descriptor` with a unique `key`) and `config.py` (typed settings + `parse_<key>_settings`). Import only `connectors.core.*`, your own package, `utils.logger`, `utils.ssrf_guard`. Use `connectors.core.http` for DNS checks and the pinned client; never follow redirects.
   - `build_snapshot` must apply `provider_key`, `name` and `content_mode` **after** merging `public_config` (see `build_snapshot` in `providers/webhook/provider.py`: `{**reserved, **public_config, **reserved}`). Policy and dispatch read `provider_key` from the snapshot, so letting `public_config` override it would route the delivery to another provider.
   - Keep every file under 400 lines (size rule above); split `provider.py`, `config.py` and payload builders (`card.py`, `events.py`) as the existing providers do.
2. Register it in `backend/connectors/registry.py`: import the provider and its settings class, and add one line to `_REGISTRY`:
   ```python
   _REGISTRY = ProviderRegistry({
       "teams_workflow": TeamsWorkflowProvider(),
       "webhook": WebhookProvider(),
       "slack": SlackProvider(),   # new
   })
   ```
3. Add the settings model to the `DestinationSettings` union in the same file.
4. Add the key to the `provider_key` Literal of `OutputDestinationCreateSchema` in `backend/schemas/output_provider_schemas.py` (currently `Literal["teams_workflow", "webhook"]`). Responses/patch schemas use plain `str`.
5. Update the OpenAPI golden. Adding the Literal value changes the `provider_key` enum pinned in `tests/unit/connectors/golden/fixtures/openapi_output_routes.json`, so `test_openapi_output_routes.py` fails until it is regenerated. This is a deliberate API contract change: regenerate only that fixture and check the diff is just the new enum value.
   ```bash
   GOLDEN_UPDATE=1 pytest tests/unit/connectors/golden/test_openapi_output_routes.py
   ```
   The wire-format fixtures `G01`-`G15` must stay unchanged (optionally add golden fixtures for the new provider itself).
6. Verify (conformance, architecture guard, import isolation and golden tests are all under this directory):
   ```bash
   pytest tests/unit/connectors -v
   ```
7. Frontend (not covered by backend tests). The UI falls back to Teams for any unknown `provider_key`, so a new provider shows up mislabelled and editing its destination builds a Teams-shaped PATCH until these are updated:
   - `frontend/src/components/output/OutputChannelWizard.tsx` (provider choice, per-provider form and summary);
   - `frontend/src/components/output/outputChannelForm.ts` (`ProviderKey` type; the form initializer maps anything other than `'webhook'` to `'teams_workflow'`);
   - `frontend/src/pages/settings/OutputDestinationsPage.tsx` (provider, authentication, attachments and content-mode columns);
   - `frontend/src/pages/ScheduledTaskFormPage.tsx` (provider badge: Webhook or Teams);
   - `frontend/src/services/api.ts` (`provider_key` literal unions in the destination types and `createOutputDestination`).

   A future improvement would be to drive the UI from the `GET` providers response (descriptors) instead of hard-coded keys.

Touch-points: the new folder; `connectors/registry.py` (the `_REGISTRY` line, the settings import, the union); the create-schema Literal; the OpenAPI golden fixture; the frontend files above. The core, orchestration, repositories and workers need no change (R1 forbids provider keys there). `models/output_delivery.py` only carries the legacy default `"teams_workflow"` for old rows.

### What the conformance suite checks

`tests/unit/connectors/conformance/` runs every check in `checks.py` against every provider registered for each direction it declares (`test_provider_conformance.py`):

| Check | Verifies |
|-------|----------|
| `check_protocol_and_signatures` | `isinstance(provider, OutboundProvider)`; every Protocol method has identical parameter names, kinds and types; return type equal or a **covariant subclass** (TypedDicts and generics match by equality only); `send` is a coroutine |
| `check_descriptor` | key/name, OUTBOUND in directions, `outbound` capabilities and `UpdatePolicy`, content modes, key registered |
| `check_unique_registration` | The registry returns this same instance, once |
| `check_settings_roundtrip_and_strictness` | `example_destination()` parses and round-trips; extra keys rejected without echoing values or secrets |
| `check_update_policy_invariants` | `ROTATE_URL_ONLY` providers have empty example config/credentials, reject any key, validate with `(None, None)` |
| `check_destination_validation` | Rejects http/ftp/file, userinfo, ports 80/8443, fragments (unless `url_allows_fragment`), private/loopback/link-local/CGNAT/IPv6 resolutions, mixed public/private DNS, unresolvable hosts |
| `check_send_classification` | 202 accepted, 400 permanent, 429 retryable with `Retry-After`, 5xx and read timeout `unknown` (`retryable` when deduplicating; needs `deduplicating_public_config` in the example), connect errors retryable, redirects not followed (302 permanent), no secrets in errors or logs |
| `check_secrets_not_in_repr` | No URL/path/query/credential in `repr`/`str` of provider, request, settings, validated destination, example, snapshot |
| `check_snapshot` | Snapshot is JSON, carries `provider_key`/`name`/`content_mode`, and `snapshot_public_config` round-trips |
| `check_snapshot_provider_key_not_overridable` | Hostile `public_config` cannot override reserved snapshot keys |
| `check_send_is_ssrf_guarded` | DNS is re-resolved at send time through the pinned transport; hostile answers give `permanent` |

Inbound providers (none registered yet) are checked by `check_inbound_protocol`, `check_parse_rejects_unverified`, `check_parse_rejects_foreign_verified` and `check_verify_fails_closed`; `check_unconfigured_secret_fails_closed` is a factory-level check applied to a provider built with an empty secret.

Supporting tests:

- `test_settings_union_conformance.py`: the `DestinationSettings` union members equal the settings types the providers return, each member's `provider_key` Literal matches its descriptor, and the create-schema Literal equals the registered output provider keys.
- `test_negative_controls.py`: one deliberately broken `DummyEchoProvider` per assertion branch must fail with its own message, so a check that asserts nothing is caught (and `test_every_check_has_a_negative_control` forces new checks to come with a control).
- `test_dummy_provider_conformance.py` + `dummy_provider.py`: a provider built only on `connectors.core` (plus `utils.ssrf_guard`) is picked up and passes everything, in both directions.

## Example (hypothetical): Slack

Illustrative only; there is no Slack provider in the codebase. An incoming-webhook provider would:

- Use `descriptor = ProviderDescriptor(key="slack", name="Slack", outbound=OutboundCapabilities(update_policy=UpdatePolicy.ROTATE_URL_ONLY))`: no settings, the secret lives in the URL, like Teams.
- Implement `validate_destination` with `connectors.core.http` (HTTPS only, host `hooks.slack.com`, public-IP check) and `ensure_same_endpoint` to stop rotation to another host.
- Build a Slack JSON body in `build_run_delivery` / `build_test_delivery`, and POST it in `send` with the pinned client, mapping statuses to `DeliveryError` kinds as the conformance suite expects (no deduplication, so 5xx and timeouts are `unknown`).
- Return `DestinationExample(url="https://hooks.slack.com/services/T000/B000/XXXX", public_config={}, credentials={}, deduplicating_public_config=None)` from `example_destination()`, add `SlackSettings` to the union, and add `"slack"` to the schema Literal.

## Testing invariants

- **Patch where used.** Patch module attributes at the place they are read, not copies imported by name: `services.output_channels.spool.spool_root`, `connectors.registry.get_output_provider` (modules call `connector_registry.get_output_provider(...)`), the `delivery_policy` constants (`MAX_ATTEMPTS`, `LEASE_SECONDS`, ...), and `db.database.SessionLocal` (resolved lazily in `process_delivery`; `scheduling.output_delivery` has its own `SessionLocal`).
- **Golden fixtures** in `tests/unit/connectors/golden/fixtures/` pin the wire output (payloads, multipart, signatures, persistence, OpenAPI of the output routes). Do not regenerate them casually; `GOLDEN_UPDATE=1` is only for a deliberate, reviewed contract change. Adding a provider legitimately changes only the OpenAPI fixture (step 5 above); the wire-format fixtures `G01`-`G15` must not change.

## Behavior changes in this refactor

| ID | Before | After |
|----|--------|-------|
| CB-1 | A Teams destination PATCH carrying `public_config` or `credentials` was accepted and those fields were silently ignored (create already rejected them); name/enabled/content mode were assigned before the URL was validated, so a rejected PATCH could leave a half-mutated object in the session | A non-empty `public_config` or `credentials` on a Teams (`ROTATE_URL_ONLY`) PATCH returns 400. Empty `{}` and `clear_credentials` remain accepted no-ops. Updates are atomic: all validation runs before any mutation (`update_destination`), so a rejected PATCH changes nothing |
| CB-2 | Create stored empty credentials as given (`{}` or `None`), while every webhook PATCH rewrote credentials as `new_credentials or None`, even when the request did not touch them (turning a stored `{}` into `None`) | Empty credentials are persisted as `None` (JSON null in the JSON column) via `normalize_credentials`; `{}` and `None` are equivalent on read (`read_credentials`); a webhook PATCH that does not touch credentials leaves them untouched |
| CB-3 | `process_delivery` and the reconciler classified an abandoned `sending` delivery with separate rules. The old reconciler retried with no expiry check, a hard-coded `attempt_count < 5` and `provider_key == "webhook"`, while `process_delivery` used `MAX_ATTEMPTS` and checked expiry; so an expired deduplicating webhook at any attempt below the limit diverged | One rule, `classify_stale_sending` in `delivery_policy.py`, used by both (`apply_stale_sending`) and capability-driven (no provider key). Retry only if the receiver deduplicates, attempts remain (`< MAX_ATTEMPTS`) and the delivery is not expired; otherwise `unknown`. The previously divergent case is now `unknown` in both paths |
