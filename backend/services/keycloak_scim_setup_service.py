import asyncio
import ipaddress
import json
import time
from typing import Any
from urllib.parse import quote, urlsplit

import bcrypt
import httpx
from fastapi.concurrency import run_in_threadpool
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import AnyHttpUrl
from sqlalchemy.orm import Session

from models.provisioning_connection import ProvisioningConnection
from repositories.scim_connection_admin_repository import SCIMConnectionAdminRepository
from schemas.scim_connection_schemas import SCIMConnectionDetail, SCIMConnectionUpdate
from schemas.keycloak_scim_setup_schemas import (
    KeycloakReconciliationRequest,
    KeycloakReconciliationResponse,
    KeycloakReconciliationSummary,
    KeycloakTargetSetupRequest,
    KeycloakTargetSetupResponse,
)
from services.scim_connection_admin_service import (
    SCIMConnectionNotFoundError,
    scim_connection_admin_service,
)
from utils.secret_key import get_secret_key

_LOCAL_HOSTS = {"localhost", "host.docker.internal"}
_REQUEST_TIMEOUT_SECONDS = 10.0
_RECONCILIATION_PREVIEW_MAX_AGE_SECONDS = 300
_RECONCILIATION_PREVIEW_SALT = "scim-reconciliation-preview-v1"
_INVALID_TARGET_LIST_ERROR = "Keycloak returned an invalid target list."
_KEYCLOAK_ADMIN_URL_LABEL = "Keycloak Admin URL"
_LOCAL_KEYCLOAK_UNREACHABLE_ERROR = "Could not reach the local Keycloak server."


class KeycloakTargetSetupError(Exception):
    """Raised when Keycloak target setup cannot be completed safely."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class KeycloakSCIMSetupService:
    """Configure a local Keycloak outbound SCIM target without persisting secrets."""

    def __init__(
        self,
        repository: SCIMConnectionAdminRepository | None = None,
    ) -> None:
        self.repository = repository or SCIMConnectionAdminRepository()

    @staticmethod
    def _local_url(value: AnyHttpUrl, label: str) -> str:
        url = urlsplit(str(value))
        host = (url.hostname or "").lower()
        if (
            url.scheme not in {"http", "https"}
            or url.username
            or url.password
            or url.query
            or url.fragment
            or not host
        ):
            raise KeycloakTargetSetupError(f"{label} must be a local HTTP(S) URL.")

        is_loopback = False
        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            pass
        if host not in _LOCAL_HOSTS and not is_loopback:
            raise KeycloakTargetSetupError(
                f"{label} host must be localhost, host.docker.internal, or a loopback IP.",
                status_code=400,
            )
        return str(value).rstrip("/")

    @staticmethod
    def _preview_serializer() -> URLSafeTimedSerializer:
        return URLSafeTimedSerializer(
            get_secret_key(), salt=_RECONCILIATION_PREVIEW_SALT
        )

    @classmethod
    def _create_preview_token(
        cls,
        connection_id: int,
        target_id: str,
        keycloak_url: str,
        admin_realm: str,
        target_realm: str,
    ) -> str:
        return cls._preview_serializer().dumps(
            {
                "connection_id": connection_id,
                "target_id": target_id,
                "keycloak_url": keycloak_url,
                "admin_realm": admin_realm,
                "target_realm": target_realm,
                "dry_run": True,
                "blocked": False,
            }
        )

    @classmethod
    def _validate_preview_token(
        cls,
        preview_token: str | None,
        connection_id: int,
        target_id: str,
        keycloak_url: str,
        admin_realm: str,
        target_realm: str,
    ) -> None:
        if not preview_token:
            raise KeycloakTargetSetupError(
                "A successful, unblocked dry-run preview is required before real reconciliation.",
                status_code=400,
            )
        try:
            claims = cls._preview_serializer().loads(
                preview_token,
                max_age=_RECONCILIATION_PREVIEW_MAX_AGE_SECONDS,
            )
        except BadSignature as exc:
            raise KeycloakTargetSetupError(
                "The reconciliation preview is invalid or expired. Run a new dry-run.",
                status_code=400,
            ) from exc
        if not isinstance(claims, dict) or any(
            claims.get(key) != expected
            for key, expected in {
                "connection_id": connection_id,
                "target_id": target_id,
                "keycloak_url": keycloak_url,
                "admin_realm": admin_realm,
                "target_realm": target_realm,
                "dry_run": True,
                "blocked": False,
            }.items()
        ):
            raise KeycloakTargetSetupError(
                "The reconciliation preview does not match this target. Run a new dry-run.",
                status_code=400,
            )

    def _get_connection_key(
        self,
        db: Session,
        connection_id: int,
        bearer_token: str,
        keycloak_realm: str,
    ) -> str:
        connection = self.repository.get_by_id_for_update(db, connection_id)
        if (
            connection is None
            or not connection.is_active
            or connection.provider_type.lower() != "keycloak"
            or connection.auth_mode != "static_bearer"
        ):
            db.rollback()
            raise KeycloakTargetSetupError(
                "Active Keycloak SCIM connection not found.", status_code=404
            )
        if connection.external_directory_id != keycloak_realm:
            db.rollback()
            raise KeycloakTargetSetupError(
                "The Keycloak target realm must match the SCIM connection realm.",
                status_code=409,
            )
        try:
            token_matches = bcrypt.checkpw(
                bearer_token.encode("utf-8"),
                connection.credential_hash.encode("utf-8"),
            )
        except ValueError:
            token_matches = False
        if not token_matches:
            db.rollback()
            raise KeycloakTargetSetupError(
                "The SCIM bearer token does not match this connection.",
                status_code=400,
            )
        return connection.connection_key

    @staticmethod
    def _admin_headers(access_token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {access_token}"}

    @staticmethod
    async def _admin_access_token(
        client: httpx.AsyncClient,
        keycloak_url: str,
        admin_realm: str,
        username: str,
        password: str,
    ) -> str:
        token_response = await client.post(
            f"{keycloak_url}/realms/{admin_realm}/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": username,
                "password": password,
            },
        )
        if token_response.status_code != 200:
            if token_response.status_code in {400, 401}:
                raise KeycloakTargetSetupError(
                    "Keycloak rejected the admin credentials. Check the username, password, admin realm, and Direct Access Grants setting.",
                    status_code=401,
                )
            raise KeycloakTargetSetupError(
                f"Keycloak token endpoint returned HTTP {token_response.status_code}."
            )
        try:
            token_body = token_response.json()
        except ValueError as exc:
            raise KeycloakTargetSetupError(
                "Keycloak returned an invalid token response."
            ) from exc
        access_token = (
            token_body.get("access_token") if isinstance(token_body, dict) else None
        )
        if not isinstance(access_token, str) or not access_token:
            raise KeycloakTargetSetupError(
                "Keycloak did not return an admin access token."
            )
        return access_token

    def _get_connection_metadata(
        self, db: Session, connection_id: int
    ) -> tuple[str, str]:
        connection = self.repository.get_by_id(db, connection_id)
        if (
            connection is None
            or not connection.is_active
            or connection.provider_type.lower() != "keycloak"
            or connection.auth_mode != "static_bearer"
        ):
            raise KeycloakTargetSetupError(
                "Active Keycloak SCIM connection not found.", status_code=404
            )
        if not connection.external_directory_id:
            raise KeycloakTargetSetupError(
                "The SCIM connection has no Keycloak realm configured.",
                status_code=400,
            )
        return connection.connection_key, connection.external_directory_id

    @staticmethod
    def _target_list(document: Any) -> list[dict[str, Any]]:
        if isinstance(document, list):
            targets = document
        elif isinstance(document, dict):
            targets = next(
                (
                    document[key]
                    for key in ("targets", "items", "value")
                    if isinstance(document.get(key), list)
                ),
                None,
            )
        else:
            targets = None
        if targets is None or any(not isinstance(item, dict) for item in targets):
            raise KeycloakTargetSetupError(_INVALID_TARGET_LIST_ERROR)
        return targets

    async def _find_target_id(
        self,
        client: httpx.AsyncClient,
        target_path: str,
        headers: dict[str, str],
        connection_key: str,
    ) -> str:
        response = await client.get(target_path, headers=headers)
        if response.status_code != 200:
            raise KeycloakTargetSetupError(
                f"Could not list Keycloak SCIM targets (HTTP {response.status_code})."
            )
        try:
            targets = self._target_list(response.json())
        except ValueError as exc:
            raise KeycloakTargetSetupError(_INVALID_TARGET_LIST_ERROR) from exc
        matches = [
            item
            for item in targets
            if isinstance(item.get("baseUrl"), str)
            and urlsplit(item["baseUrl"]).path.rstrip("/").rsplit("/", 1)[-1]
            == connection_key
        ]
        if not matches:
            raise KeycloakTargetSetupError(
                "No Keycloak target points to this Mattin SCIM connection.",
                status_code=404,
            )
        if len(matches) > 1:
            raise KeycloakTargetSetupError(
                "More than one Keycloak target points to this Mattin SCIM connection; remove the duplicate target first.",
                status_code=409,
            )
        target = matches[0]
        if target.get("enabled") is not True:
            raise KeycloakTargetSetupError(
                "The Keycloak target for this connection is disabled.",
                status_code=409,
            )
        target_id = target.get("id")
        if not isinstance(target_id, str) or not target_id:
            raise KeycloakTargetSetupError(
                "Keycloak returned a target without an ID."
            )
        return target_id

    async def _realm_has_target(
        self,
        client: httpx.AsyncClient,
        keycloak_url: str,
        realm: str,
        headers: dict[str, str],
        connection_key: str,
    ) -> bool:
        targets_url = (
            f"{keycloak_url}/admin/realms/{quote(realm, safe='')}"
            "/scim-outbound/targets"
        )
        response = await client.get(targets_url, headers=headers)
        if response.status_code != 200:
            raise KeycloakTargetSetupError(
                f"Could not list Keycloak SCIM targets for realm '{realm}' "
                f"(HTTP {response.status_code})."
            )
        try:
            targets = self._target_list(response.json())
        except ValueError as exc:
            raise KeycloakTargetSetupError(_INVALID_TARGET_LIST_ERROR) from exc
        return any(
            isinstance(item.get("baseUrl"), str)
            and urlsplit(item["baseUrl"]).path.rstrip("/").rsplit("/", 1)[-1]
            == connection_key
            for item in targets
        )

    async def _verify_realm_change(
        self,
        connection: ProvisioningConnection,
        payload: SCIMConnectionUpdate,
    ) -> None:
        if (
            payload.keycloak_admin_base_url is None
            or payload.keycloak_admin_username is None
            or payload.keycloak_admin_password is None
        ):
            raise KeycloakTargetSetupError(
                "Keycloak admin URL and credentials are required to verify a realm change.",
                status_code=400,
            )
        keycloak_url = self._local_url(
            payload.keycloak_admin_base_url, _KEYCLOAK_ADMIN_URL_LABEL
        )
        admin_realm = quote(payload.keycloak_admin_realm, safe="")
        try:
            async with httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                access_token = await self._admin_access_token(
                    client,
                    keycloak_url,
                    admin_realm,
                    payload.keycloak_admin_username.get_secret_value(),
                    payload.keycloak_admin_password.get_secret_value(),
                )
                headers = self._admin_headers(access_token)
                realms = tuple(
                    dict.fromkeys(
                        realm
                        for realm in (
                            connection.external_directory_id,
                            payload.external_directory_id,
                        )
                        if realm
                    )
                )
                for realm in realms:
                    if await self._realm_has_target(
                        client,
                        keycloak_url,
                        realm,
                        headers,
                        connection.connection_key,
                    ):
                        raise KeycloakTargetSetupError(
                            "The realm cannot be changed while a Keycloak target for this connection exists. "
                            "Remove the target first, or edit only the connection name.",
                            status_code=409,
                        )
        except KeycloakTargetSetupError:
            raise
        except httpx.TimeoutException as exc:
            raise KeycloakTargetSetupError(
                "Timed out while checking the Keycloak realms."
            ) from exc
        except httpx.RequestError as exc:
            raise KeycloakTargetSetupError(
                _LOCAL_KEYCLOAK_UNREACHABLE_ERROR
            ) from exc

    async def update_connection(
        self,
        db: Session,
        connection_id: int,
        payload: SCIMConnectionUpdate,
    ) -> SCIMConnectionDetail:
        locked_connection = await run_in_threadpool(
            self.repository.get_by_id_for_update, db, connection_id
        )
        if locked_connection is None:
            db.rollback()
            raise SCIMConnectionNotFoundError
        try:
            if locked_connection.external_directory_id != payload.expected_external_directory_id:
                raise KeycloakTargetSetupError(
                    "The SCIM connection changed during this edit. Reload it and try again.",
                    status_code=409,
                )
            realm_changed = (
                locked_connection.external_directory_id
                != payload.external_directory_id
            )
            if realm_changed and locked_connection.provider_type.lower() == "keycloak":
                await self._verify_realm_change(locked_connection, payload)

            return await run_in_threadpool(
                scim_connection_admin_service.update_connection,
                db,
                connection_id,
                payload,
                True,
            )
        finally:
            await run_in_threadpool(db.rollback)

    @staticmethod
    def _summary_document(status_document: Any) -> dict[str, Any] | None:
        if not isinstance(status_document, dict):
            return None
        summary = status_document.get("lastReconcileSummary")
        if isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except json.JSONDecodeError:
                return None
        return summary if isinstance(summary, dict) else None

    async def _wait_for_reconciliation(
        self,
        client: httpx.AsyncClient,
        status_url: str,
        headers: dict[str, str],
        target_id: str,
        dry_run: bool,
        previous_reconcile_at: int,
    ) -> KeycloakReconciliationResponse:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)
            response = await client.get(status_url, headers=headers)
            if response.status_code != 200:
                raise KeycloakTargetSetupError(
                    f"Could not read Keycloak reconciliation status (HTTP {response.status_code})."
                )
            try:
                status_document = response.json()
            except ValueError:
                continue
            summary_document = self._summary_document(status_document)
            if not summary_document:
                continue
            started_at = summary_document.get("startedAt")
            finished_at = summary_document.get("finishedAt")
            blocked = summary_document.get("blocked")
            count_fields = (
                "localUsers",
                "remoteUsers",
                "userCreates",
                "userUpdates",
                "userRemovals",
                "unmanagedRemoteUsers",
                "groupUpserts",
                "groupRemovals",
            )
            if (
                summary_document.get("targetId") != target_id
                or summary_document.get("dryRun") is not dry_run
                or type(started_at) is not int
                or started_at <= previous_reconcile_at
                or type(finished_at) is not int
                or finished_at < started_at
                or type(blocked) is not bool
                or any(
                    type(summary_document.get(field)) is not int
                    or summary_document[field] < 0
                    for field in count_fields
                )
                or (
                    summary_document.get("message") is not None
                    and not isinstance(summary_document.get("message"), str)
                )
            ):
                continue
            summary = KeycloakReconciliationSummary(
                target_id=target_id,
                dry_run=dry_run,
                blocked=blocked,
                local_users=summary_document["localUsers"],
                remote_users=summary_document["remoteUsers"],
                user_creates=summary_document["userCreates"],
                user_updates=summary_document["userUpdates"],
                user_removals=summary_document["userRemovals"],
                unmanaged_remote_users=summary_document["unmanagedRemoteUsers"],
                group_upserts=summary_document["groupUpserts"],
                group_removals=summary_document["groupRemovals"],
                started_at=started_at,
                finished_at=finished_at,
                message=summary_document.get("message"),
            )
            outbox_document = status_document.get("outbox", {})
            outbox = (
                {
                    key: value
                    for key, value in outbox_document.items()
                    if isinstance(key, str) and isinstance(value, int)
                }
                if isinstance(outbox_document, dict)
                else {}
            )
            return KeycloakReconciliationResponse(
                target_id=target_id,
                dry_run=dry_run,
                summary=summary,
                outbox=outbox,
            )
        raise KeycloakTargetSetupError(
            "Keycloak accepted the reconciliation, but its report was not ready after 15 seconds. Check the target status and try again.",
            status_code=504,
        )

    @staticmethod
    async def _previous_reconciliation_timestamp(
        client: httpx.AsyncClient,
        status_url: str,
        headers: dict[str, str],
    ) -> int:
        previous_status = await client.get(status_url, headers=headers)
        if previous_status.status_code != 200:
            raise KeycloakTargetSetupError(
                f"Could not read Keycloak target status (HTTP {previous_status.status_code})."
            )
        try:
            previous_document = previous_status.json()
        except ValueError as exc:
            raise KeycloakTargetSetupError(
                "Keycloak returned an invalid target status."
            ) from exc
        previous_reconcile_at = (
            previous_document.get("lastReconcileAt", 0)
            if isinstance(previous_document, dict)
            else 0
        )
        return previous_reconcile_at if isinstance(previous_reconcile_at, int) else 0

    async def _submit_reconciliation(
        self,
        client: httpx.AsyncClient,
        targets_url: str,
        status_url: str,
        headers: dict[str, str],
        target_id: str,
        dry_run: bool,
        previous_reconcile_at: int,
    ) -> KeycloakReconciliationResponse:
        reconcile_response = await client.post(
            f"{targets_url}/{quote(target_id, safe='')}/reconcile"
            f"?dryRun={str(dry_run).lower()}",
            headers=headers,
        )
        if reconcile_response.status_code not in {200, 202}:
            raise KeycloakTargetSetupError(
                f"Keycloak rejected the reconciliation request (HTTP {reconcile_response.status_code}).",
                status_code=(
                    409 if reconcile_response.status_code == 409 else 502
                ),
            )
        return await self._wait_for_reconciliation(
            client,
            status_url,
            headers,
            target_id,
            dry_run,
            previous_reconcile_at,
        )

    async def reconcile(
        self,
        db: Session,
        connection_id: int,
        payload: KeycloakReconciliationRequest,
        dry_run: bool,
    ) -> KeycloakReconciliationResponse:
        if not dry_run and not payload.confirm_real_reconcile:
            raise KeycloakTargetSetupError(
                "Explicit confirmation is required for a real reconciliation.",
                status_code=400,
            )
        connection_key, target_realm = await run_in_threadpool(
            self._get_connection_metadata, db, connection_id
        )
        db.rollback()
        keycloak_url = self._local_url(
            payload.keycloak_admin_base_url, _KEYCLOAK_ADMIN_URL_LABEL
        )
        admin_realm = quote(payload.keycloak_admin_realm, safe="")
        target_realm_path = quote(target_realm, safe="")
        targets_url = (
            f"{keycloak_url}/admin/realms/{target_realm_path}/scim-outbound/targets"
        )
        try:
            async with httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                access_token = await self._admin_access_token(
                    client,
                    keycloak_url,
                    admin_realm,
                    payload.keycloak_admin_username.get_secret_value(),
                    payload.keycloak_admin_password.get_secret_value(),
                )
                headers = self._admin_headers(access_token)
                target_id = await self._find_target_id(
                    client, targets_url, headers, connection_key
                )
                if not dry_run:
                    self._validate_preview_token(
                        payload.preview_token,
                        connection_id,
                        target_id,
                        keycloak_url,
                        payload.keycloak_admin_realm,
                        target_realm,
                    )
                status_url = f"{targets_url}/{quote(target_id, safe='')}/status"
                previous_reconcile_at = await self._previous_reconciliation_timestamp(
                    client,
                    status_url,
                    headers,
                )
                response = await self._submit_reconciliation(
                    client,
                    targets_url,
                    status_url,
                    headers,
                    target_id,
                    dry_run,
                    previous_reconcile_at,
                )
                if dry_run and not response.summary.blocked:
                    response.preview_token = self._create_preview_token(
                        connection_id,
                        target_id,
                        keycloak_url,
                        payload.keycloak_admin_realm,
                        target_realm,
                    )
                return response
        except KeycloakTargetSetupError:
            raise
        except httpx.TimeoutException as exc:
            raise KeycloakTargetSetupError(
                "Timed out while contacting the local Keycloak server."
            ) from exc
        except httpx.RequestError as exc:
            raise KeycloakTargetSetupError(
                _LOCAL_KEYCLOAK_UNREACHABLE_ERROR
            ) from exc

    async def _create_target(
        self,
        client: httpx.AsyncClient,
        target_path: str,
        headers: dict[str, str],
        payload: KeycloakTargetSetupRequest,
        target_url: str,
    ) -> str:
        create_response = await client.post(
            target_path,
            headers=headers,
            json={
                "name": payload.target_name,
                "enabled": True,
                "baseUrl": target_url,
                "auth": {
                    "type": "BEARER",
                    "token": payload.bearer_token.get_secret_value(),
                },
                "syncGroups": payload.sync_groups,
            },
        )
        if create_response.status_code not in {200, 201}:
            message = (
                "Keycloak rejected the target configuration. For local testing, "
                "verify the outbound SCIM extension and its plaintext-secret setting."
                if create_response.status_code == 400
                else f"Keycloak target creation returned HTTP {create_response.status_code}."
            )
            raise KeycloakTargetSetupError(
                message,
                status_code=409 if create_response.status_code == 409 else 502,
            )
        try:
            target_body = create_response.json()
        except ValueError as exc:
            raise KeycloakTargetSetupError(
                "Keycloak created the target but returned an invalid response."
            ) from exc
        target_id = target_body.get("id") if isinstance(target_body, dict) else None
        if not isinstance(target_id, str) or not target_id:
            raise KeycloakTargetSetupError(
                "Keycloak created the target but returned no target ID."
            )
        return target_id

    @staticmethod
    async def _test_target(
        client: httpx.AsyncClient,
        target_path: str,
        headers: dict[str, str],
        target_id: str,
        target_name: str,
        target_url: str,
    ) -> KeycloakTargetSetupResponse:
        test_response = await client.post(
            f"{target_path}/{quote(target_id, safe='')}/test",
            headers=headers,
        )
        test_body: dict[str, Any] = {}
        if test_response.status_code == 200:
            try:
                body = test_response.json()
            except ValueError:
                body = None
            if isinstance(body, dict):
                test_body = body
        return KeycloakTargetSetupResponse(
            target_id=target_id,
            target_name=target_name,
            target_url=target_url,
            test_ok=(
                test_response.status_code == 200 and test_body.get("ok") is True
            ),
            test_status=(
                test_body.get("status")
                if isinstance(test_body.get("status"), int)
                else test_response.status_code
            ),
            patch_supported=test_body.get("patchSupported") is True,
            filter_supported=test_body.get("filterSupported") is True,
        )

    async def configure_target(
        self,
        db: Session,
        connection_id: int,
        payload: KeycloakTargetSetupRequest,
    ) -> KeycloakTargetSetupResponse:
        keycloak_url = self._local_url(
            payload.keycloak_admin_base_url, _KEYCLOAK_ADMIN_URL_LABEL
        )
        mattin_url = self._local_url(
            payload.mattin_scim_base_url, "Mattin SCIM URL"
        )
        admin_realm = quote(payload.keycloak_admin_realm, safe="")
        target_realm = quote(payload.keycloak_realm, safe="")
        connection_key = await run_in_threadpool(
            self._get_connection_key,
            db,
            connection_id,
            payload.bearer_token.get_secret_value(),
            payload.keycloak_realm,
        )
        target_url = f"{mattin_url}/{quote(connection_key, safe='')}"

        try:
            async with httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                access_token = await self._admin_access_token(
                    client,
                    keycloak_url,
                    admin_realm,
                    payload.keycloak_admin_username.get_secret_value(),
                    payload.keycloak_admin_password.get_secret_value(),
                )
                headers = self._admin_headers(access_token)
                target_path = (
                    f"{keycloak_url}/admin/realms/{target_realm}/scim-outbound/targets"
                )
                target_id = await self._create_target(
                    client, target_path, headers, payload, target_url
                )
                return await self._test_target(
                    client,
                    target_path,
                    headers,
                    target_id,
                    payload.target_name,
                    target_url,
                )
        except KeycloakTargetSetupError:
            raise
        except httpx.TimeoutException as exc:
            raise KeycloakTargetSetupError(
                "Timed out while contacting the local Keycloak server."
            ) from exc
        except httpx.RequestError as exc:
            raise KeycloakTargetSetupError(
                _LOCAL_KEYCLOAK_UNREACHABLE_ERROR
            ) from exc
        finally:
            await run_in_threadpool(db.rollback)


keycloak_scim_setup_service = KeycloakSCIMSetupService()
