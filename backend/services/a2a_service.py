from __future__ import annotations

import base64
import json
import os
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.orm import Session

from models.a2a_agent import A2AAgent
from utils.secret_utils import is_masked_secret, mask_secret
from utils.logger import get_logger

logger = get_logger(__name__)


class A2AService:
    """Shared A2A helpers for validation, persistence, and health updates."""

    SECRET_AUTH_FIELDS = {
        "api_key",
        "bearer_token",
        "password",
        "client_certificate",
        "client_key",
        "ca_certificate",
    }
    SECURITY_SCHEME_WRAPPERS = {
        "apiKeySecurityScheme": "apiKey",
        "httpAuthSecurityScheme": "http",
        "oauth2SecurityScheme": "oauth2",
        "openIdConnectSecurityScheme": "openIdConnect",
        "mutualTlsSecurityScheme": "mtls",
        "mutualTLSSecurityScheme": "mtls",
        "mtlsSecurityScheme": "mtls",
    }

    HEALTHY = "healthy"
    PENDING = "pending"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"
    INVALID = "invalid"

    SYNCED = "synced"
    ERROR = "error"

    @staticmethod
    def is_a2a_agent(agent: Any) -> bool:
        return bool(getattr(agent, "a2a_config", None))

    @staticmethod
    def split_card_url(card_url: str) -> tuple[str, str]:
        parsed = urlsplit(card_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("A2A card URL must be an absolute http(s) URL")
        if parsed.fragment:
            raise ValueError("A2A card URL must not include a fragment")

        base_url = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        path = parsed.path or "/.well-known/agent-card.json"
        if path == "/":
            path = "/.well-known/agent-card.json"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        return base_url, path

    @staticmethod
    def _normalize_security_scheme(
        scheme_name: str,
        raw_scheme: Any,
    ) -> Optional[dict[str, Any]]:
        if not isinstance(raw_scheme, dict):
            return None

        for wrapper_name, scheme_type in A2AService.SECURITY_SCHEME_WRAPPERS.items():
            nested = raw_scheme.get(wrapper_name)
            if isinstance(nested, dict):
                normalized_config = dict(nested)
                if raw_scheme.get("description") and "description" not in normalized_config:
                    normalized_config["description"] = raw_scheme["description"]
                return {
                    "name": scheme_name,
                    "type": scheme_type,
                    "config": normalized_config,
                    "raw": raw_scheme,
                }

        scheme_type = raw_scheme.get("type")
        if scheme_type == "mutualTLS":
            scheme_type = "mtls"

        if scheme_type in {"apiKey", "http", "oauth2", "openIdConnect", "mtls"}:
            return {
                "name": scheme_name,
                "type": scheme_type,
                "config": dict(raw_scheme),
                "raw": raw_scheme,
            }

        return None

    @staticmethod
    def extract_security_schemes(card_snapshot: Optional[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if not isinstance(card_snapshot, dict):
            return {}

        raw_schemes = card_snapshot.get("securitySchemes") or {}
        if not isinstance(raw_schemes, dict):
            return {}

        normalized: dict[str, dict[str, Any]] = {}
        for scheme_name, raw_scheme in raw_schemes.items():
            scheme = A2AService._normalize_security_scheme(scheme_name, raw_scheme)
            if scheme:
                normalized[scheme_name] = scheme
        return normalized

    @staticmethod
    def _merge_secret_value(submitted_value: Optional[str], existing_value: Optional[str]) -> Optional[str]:
        if is_masked_secret(submitted_value):
            return existing_value or None
        if submitted_value is None:
            return existing_value or None
        value = submitted_value.strip()
        return value or None

    @staticmethod
    def _canonicalize_auth_config(
        submitted_auth_config: Optional[dict[str, Any]],
        *,
        advertised_schemes: dict[str, dict[str, Any]],
        existing_auth_config: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        if not submitted_auth_config:
            return None

        scheme_name = (submitted_auth_config.get("scheme_name") or "").strip() or None
        if not scheme_name:
            return None

        scheme = advertised_schemes.get(scheme_name)
        if not scheme:
            raise ValueError(f"Selected A2A auth scheme '{scheme_name}' is no longer advertised by the agent card")

        existing_auth_config = existing_auth_config or {}
        scheme_type = scheme["type"]
        config = scheme.get("config") or {}
        canonical_auth_config: dict[str, Any] = {
            "scheme_name": scheme_name,
            "scheme_type": scheme_type,
        }

        if scheme_type == "apiKey":
            api_key = A2AService._merge_secret_value(
                submitted_auth_config.get("api_key"),
                existing_auth_config.get("api_key"),
            )
            if not api_key:
                raise ValueError("The selected A2A API key scheme requires an API key value")
            canonical_auth_config["api_key"] = api_key
            return canonical_auth_config

        if scheme_type == "http":
            http_scheme = str(config.get("scheme") or submitted_auth_config.get("http_scheme") or "Bearer").strip()
            canonical_auth_config["http_scheme"] = http_scheme
            if http_scheme.lower() == "basic":
                username = (submitted_auth_config.get("username") or existing_auth_config.get("username") or "").strip() or None
                password = A2AService._merge_secret_value(
                    submitted_auth_config.get("password"),
                    existing_auth_config.get("password"),
                )
                if not username or not password:
                    raise ValueError("HTTP Basic authentication requires both username and password")
                canonical_auth_config["username"] = username
                canonical_auth_config["password"] = password
                return canonical_auth_config

            bearer_token = A2AService._merge_secret_value(
                submitted_auth_config.get("bearer_token"),
                existing_auth_config.get("bearer_token"),
            )
            if not bearer_token:
                raise ValueError(f"HTTP {http_scheme} authentication requires a token value")
            canonical_auth_config["bearer_token"] = bearer_token
            return canonical_auth_config

        if scheme_type in {"oauth2", "openIdConnect"}:
            bearer_token = A2AService._merge_secret_value(
                submitted_auth_config.get("bearer_token"),
                existing_auth_config.get("bearer_token"),
            )
            if not bearer_token:
                raise ValueError(f"{scheme_type} authentication currently requires a configured access token")
            canonical_auth_config["bearer_token"] = bearer_token
            return canonical_auth_config

        if scheme_type == "mtls":
            client_certificate = A2AService._merge_secret_value(
                submitted_auth_config.get("client_certificate"),
                existing_auth_config.get("client_certificate"),
            )
            client_key = A2AService._merge_secret_value(
                submitted_auth_config.get("client_key"),
                existing_auth_config.get("client_key"),
            )
            ca_certificate = A2AService._merge_secret_value(
                submitted_auth_config.get("ca_certificate"),
                existing_auth_config.get("ca_certificate"),
            )
            if not client_certificate or not client_key:
                raise ValueError("mTLS authentication requires both a client certificate and client key")
            canonical_auth_config["client_certificate"] = client_certificate
            canonical_auth_config["client_key"] = client_key
            if ca_certificate:
                canonical_auth_config["ca_certificate"] = ca_certificate
            return canonical_auth_config

        raise ValueError(f"Unsupported A2A auth scheme type '{scheme_type}'")

    @staticmethod
    def mask_auth_config(auth_config: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not auth_config:
            return None

        masked = dict(auth_config)
        for field_name in A2AService.SECRET_AUTH_FIELDS:
            if field_name in masked:
                masked[field_name] = mask_secret(masked.get(field_name))
        return masked

    @staticmethod
    def sanitize_export_auth_config(auth_config: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not auth_config:
            return None

        sanitized = dict(auth_config)
        for field_name in A2AService.SECRET_AUTH_FIELDS:
            if field_name in sanitized:
                sanitized[field_name] = None
        return sanitized

    @staticmethod
    @asynccontextmanager
    async def create_authenticated_httpx_client(
        *,
        card_snapshot: Optional[dict[str, Any]] = None,
        auth_config: Optional[dict[str, Any]] = None,
        timeout: Any,
        follow_redirects: bool = True,
    ):
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "A2A support requires the 'httpx' dependency to be installed."
            ) from exc

        client_kwargs: dict[str, Any] = {
            "timeout": timeout,
            "follow_redirects": follow_redirects,
        }
        cleanup_paths: list[str] = []

        if auth_config:
            selected_scheme_name = auth_config.get("scheme_name")
            advertised_scheme = None
            if selected_scheme_name:
                advertised_scheme = A2AService.extract_security_schemes(card_snapshot).get(selected_scheme_name)

            headers: dict[str, str] = {}
            params: dict[str, str] = {}
            cookies: dict[str, str] = {}

            scheme_type = auth_config.get("scheme_type")
            if scheme_type == "apiKey":
                api_key = auth_config.get("api_key")
                location = (advertised_scheme or {}).get("config", {}).get("in", "header")
                parameter_name = (advertised_scheme or {}).get("config", {}).get("name") or "X-API-Key"
                if api_key:
                    if location == "query":
                        params[parameter_name] = api_key
                    elif location == "cookie":
                        cookies[parameter_name] = api_key
                    else:
                        headers[parameter_name] = api_key
            elif scheme_type == "http":
                http_scheme = auth_config.get("http_scheme") or (advertised_scheme or {}).get("config", {}).get("scheme") or "Bearer"
                if str(http_scheme).lower() == "basic":
                    username = auth_config.get("username") or ""
                    password = auth_config.get("password") or ""
                    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
                    headers["Authorization"] = f"Basic {token}"
                elif auth_config.get("bearer_token"):
                    headers["Authorization"] = f"{http_scheme} {auth_config['bearer_token']}"
            elif scheme_type in {"oauth2", "openIdConnect"} and auth_config.get("bearer_token"):
                headers["Authorization"] = f"Bearer {auth_config['bearer_token']}"

            if headers:
                client_kwargs["headers"] = headers
            if params:
                client_kwargs["params"] = params
            if cookies:
                client_kwargs["cookies"] = cookies

            if scheme_type == "mtls":
                client_certificate = auth_config.get("client_certificate")
                client_key = auth_config.get("client_key")
                ca_certificate = auth_config.get("ca_certificate")
                if client_certificate and client_key:
                    cert_file = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
                    cert_file.write(client_certificate)
                    cert_file.flush()
                    cert_file.close()
                    cleanup_paths.append(cert_file.name)

                    key_file = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
                    key_file.write(client_key)
                    key_file.flush()
                    key_file.close()
                    cleanup_paths.append(key_file.name)
                    client_kwargs["cert"] = (cert_file.name, key_file.name)

                if ca_certificate:
                    ca_file = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
                    ca_file.write(ca_certificate)
                    ca_file.flush()
                    ca_file.close()
                    cleanup_paths.append(ca_file.name)
                    client_kwargs["verify"] = ca_file.name

        try:
            async with httpx.AsyncClient(**client_kwargs) as httpx_client:
                yield httpx_client
        finally:
            for path in cleanup_paths:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass

    @staticmethod
    async def _resolve_agent_card(card_url: str):
        try:
            import httpx
            from a2a.client import A2ACardResolver
        except ImportError as exc:
            raise RuntimeError(
                "A2A support requires the optional 'a2a-sdk' dependency to be installed."
            ) from exc

        if not card_url:
            raise ValueError("A2A card URL is required")

        base_url, relative_path = A2AService.split_card_url(card_url)
        timeout = httpx.Timeout(15.0, read=20.0)
        logger.info(
            "Resolving A2A card from %s (base_url=%s, path=%s)",
            card_url,
            base_url,
            relative_path,
        )

        async with A2AService.create_authenticated_httpx_client(
            timeout=timeout,
            follow_redirects=True,
        ) as httpx_client:
            resolver = A2ACardResolver(httpx_client, base_url)
            agent_card = await resolver.get_agent_card(
                relative_card_path=relative_path
            )

        logger.info(
            "Resolved A2A card from %s with %s skill(s)",
            card_url,
            len(getattr(agent_card, "skills", []) or []),
        )
        return agent_card

    @staticmethod
    async def _fetch_raw_card_snapshot(card_url: str) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "A2A support requires the 'httpx' dependency to be installed."
            ) from exc

        base_url, relative_path = A2AService.split_card_url(card_url)
        timeout = httpx.Timeout(15.0, read=20.0)
        raw_url = f"{base_url}{relative_path}"

        async with A2AService.create_authenticated_httpx_client(
            timeout=timeout,
            follow_redirects=True,
        ) as httpx_client:
            response = await httpx_client.get(raw_url)
            response.raise_for_status()

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ValueError("A2A agent card did not return valid JSON") from exc

        if not isinstance(payload, dict):
            raise ValueError("A2A agent card JSON must be an object")

        return payload

    @staticmethod
    def _merge_card_snapshot(
        agent_card: Any,
        raw_snapshot: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        parsed_snapshot = agent_card.model_dump(mode="json", exclude_none=True)
        if not isinstance(raw_snapshot, dict):
            return parsed_snapshot

        merged_snapshot = dict(raw_snapshot)
        merged_snapshot.update(parsed_snapshot)
        return merged_snapshot

    @staticmethod
    async def _resolve_agent_card_with_snapshot(
        card_url: str,
    ) -> tuple[Any, dict[str, Any]]:
        agent_card = await A2AService._resolve_agent_card(card_url)
        raw_snapshot = await A2AService._fetch_raw_card_snapshot(card_url)
        return agent_card, A2AService._merge_card_snapshot(
            agent_card,
            raw_snapshot,
        )

    @staticmethod
    async def discover_card(card_url: str) -> dict[str, Any]:
        agent_card, card_snapshot = await A2AService._resolve_agent_card_with_snapshot(card_url)

        return {
            "card_url": card_url,
            "remote_agent_id": agent_card.url,
            "card": card_snapshot,
            "skills": card_snapshot.get("skills", []),
            "documentation_url": getattr(agent_card, "documentation_url", None),
            "icon_url": getattr(agent_card, "icon_url", None),
        }

    @staticmethod
    async def validate_source_config(
        source_config: dict[str, Any],
        existing_auth_config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        card_url = source_config.get("card_url")
        selected_skill_id = source_config.get("selected_skill_id")
        if not selected_skill_id:
            raise ValueError("An A2A skill must be selected")

        agent_card, card_snapshot = await A2AService._resolve_agent_card_with_snapshot(card_url)
        selected_skill = next(
            (skill for skill in agent_card.skills if skill.id == selected_skill_id),
            None,
        )
        if selected_skill is None:
            raise ValueError(
                f"Selected A2A skill '{selected_skill_id}' is no longer present in the agent card"
            )

        submitted_skill_snapshot = source_config.get("skill_snapshot") or {}
        snapshot_skill_id = submitted_skill_snapshot.get("id")
        if snapshot_skill_id and snapshot_skill_id != selected_skill_id:
            raise ValueError("Submitted A2A skill snapshot does not match the selected skill")

        now = datetime.utcnow()
        skill_snapshot = selected_skill.model_dump(mode="json", exclude_none=True)
        advertised_schemes = A2AService.extract_security_schemes(card_snapshot)
        canonical_auth_config = A2AService._canonicalize_auth_config(
            source_config.get("auth_config"),
            advertised_schemes=advertised_schemes,
            existing_auth_config=existing_auth_config,
        )

        return {
            "card_url": card_url,
            "remote_agent_id": agent_card.url,
            "remote_skill_id": selected_skill.id,
            "remote_skill_name": selected_skill.name,
            "auth_config": canonical_auth_config,
            "remote_agent_metadata": card_snapshot,
            "remote_skill_metadata": skill_snapshot,
            "sync_status": A2AService.SYNCED,
            "health_status": A2AService.HEALTHY,
            "last_successful_refresh_at": now,
            "last_refresh_attempt_at": now,
            "last_refresh_error": None,
            "documentation_url": getattr(agent_card, "documentation_url", None),
            "icon_url": getattr(agent_card, "icon_url", None),
        }

    @staticmethod
    async def refresh_card(record: A2AAgent, db: Session) -> A2AAgent:
        """Refresh cached remote metadata for an imported A2A agent."""
        if not record:
            raise ValueError("A2A agent configuration is required")

        refresh_attempt_at = datetime.utcnow()
        record.last_refresh_attempt_at = refresh_attempt_at

        try:
            agent_card, card_snapshot = await A2AService._resolve_agent_card_with_snapshot(record.card_url)
        except RuntimeError:
            raise
        except Exception as exc:
            record.sync_status = A2AService.ERROR
            record.health_status = A2AService.UNREACHABLE
            record.last_refresh_error = str(exc)[:1000] or "Failed to refresh the remote A2A agent card"
            db.add(record)
            db.commit()
            logger.warning(
                "Failed to refresh A2A card for agent %s from %s: %s",
                record.agent_id,
                record.card_url,
                exc,
            )
            return record

        record.remote_agent_id = agent_card.url
        record.remote_agent_metadata = card_snapshot
        record.documentation_url = getattr(agent_card, "documentation_url", None)
        record.icon_url = getattr(agent_card, "icon_url", None)

        selected_skill = next(
            (skill for skill in agent_card.skills if skill.id == record.remote_skill_id),
            None,
        )
        if selected_skill is None:
            record.sync_status = A2AService.ERROR
            record.health_status = A2AService.INVALID
            record.last_refresh_error = (
                f"Selected A2A skill '{record.remote_skill_id}' is no longer present in the agent card"
            )[:1000]
            db.add(record)
            db.commit()
            logger.warning(
                "Refreshed A2A card for agent %s but skill %s is no longer present",
                record.agent_id,
                record.remote_skill_id,
            )
            return record

        record.remote_skill_name = selected_skill.name
        record.remote_skill_metadata = selected_skill.model_dump(mode="json", exclude_none=True)
        record.sync_status = A2AService.SYNCED
        record.health_status = A2AService.HEALTHY
        record.last_successful_refresh_at = refresh_attempt_at
        record.last_refresh_error = None
        db.add(record)
        db.commit()

        logger.info(
            "Refreshed A2A card for agent %s from %s (skill=%s)",
            record.agent_id,
            record.card_url,
            record.remote_skill_id,
        )
        return record

    @staticmethod
    def apply_source_config(record: A2AAgent, canonical_config: dict[str, Any]) -> A2AAgent:
        record.card_url = canonical_config["card_url"]
        record.remote_agent_id = canonical_config.get("remote_agent_id")
        record.remote_skill_id = canonical_config["remote_skill_id"]
        record.remote_skill_name = canonical_config["remote_skill_name"]
        record.auth_config = canonical_config.get("auth_config")
        record.remote_agent_metadata = canonical_config["remote_agent_metadata"]
        record.remote_skill_metadata = canonical_config["remote_skill_metadata"]
        record.sync_status = canonical_config.get("sync_status", A2AService.SYNCED)
        record.health_status = canonical_config.get("health_status", A2AService.HEALTHY)
        record.last_successful_refresh_at = canonical_config.get("last_successful_refresh_at")
        record.last_refresh_attempt_at = canonical_config.get("last_refresh_attempt_at")
        record.last_refresh_error = canonical_config.get("last_refresh_error")
        record.documentation_url = canonical_config.get("documentation_url")
        record.icon_url = canonical_config.get("icon_url")
        return record

    @staticmethod
    def serialize_record(record: Optional[A2AAgent]) -> Optional[dict[str, Any]]:
        if not record:
            return None

        return {
            "card_url": record.card_url,
            "remote_agent_id": record.remote_agent_id,
            "remote_skill_id": record.remote_skill_id,
            "remote_skill_name": record.remote_skill_name,
            "auth_config": A2AService.mask_auth_config(record.auth_config),
            "remote_agent_metadata": record.remote_agent_metadata or {},
            "remote_skill_metadata": record.remote_skill_metadata or {},
            "sync_status": record.sync_status,
            "health_status": record.health_status,
            "last_successful_refresh_at": record.last_successful_refresh_at,
            "last_refresh_attempt_at": record.last_refresh_attempt_at,
            "last_refresh_error": record.last_refresh_error,
            "documentation_url": record.documentation_url,
            "icon_url": record.icon_url,
        }

    @staticmethod
    def serialize_export_record(record: Optional[A2AAgent]) -> Optional[dict[str, Any]]:
        if not record:
            return None

        return {
            "card_url": record.card_url,
            "remote_agent_id": record.remote_agent_id,
            "remote_skill_id": record.remote_skill_id,
            "remote_skill_name": record.remote_skill_name,
            "auth_config": A2AService.sanitize_export_auth_config(record.auth_config),
            "remote_agent_metadata": record.remote_agent_metadata or {},
            "remote_skill_metadata": record.remote_skill_metadata or {},
            "sync_status": record.sync_status,
            "health_status": record.health_status,
            "last_successful_refresh_at": record.last_successful_refresh_at,
            "last_refresh_attempt_at": record.last_refresh_attempt_at,
            "last_refresh_error": record.last_refresh_error,
            "documentation_url": record.documentation_url,
            "icon_url": record.icon_url,
        }

    @staticmethod
    def prepare_imported_config(exported_config: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not exported_config:
            return None

        imported = dict(exported_config)
        imported["auth_config"] = A2AService.sanitize_export_auth_config(
            exported_config.get("auth_config")
        )
        imported["health_status"] = A2AService.PENDING
        imported["last_successful_refresh_at"] = None
        imported["last_refresh_attempt_at"] = None
        imported["last_refresh_error"] = (
            "Imported from export. Refresh the remote A2A agent card before first execution."
        )
        return imported

    @staticmethod
    def update_health(
        db: Session,
        record: Optional[A2AAgent],
        *,
        healthy: bool,
        error_summary: Optional[str] = None,
    ) -> None:
        if not record:
            return

        record.last_refresh_attempt_at = datetime.utcnow()
        if healthy:
            record.health_status = A2AService.HEALTHY
            record.sync_status = A2AService.SYNCED
            record.last_successful_refresh_at = record.last_refresh_attempt_at
            record.last_refresh_error = None
        else:
            record.health_status = A2AService.UNREACHABLE
            record.sync_status = A2AService.ERROR
            record.last_refresh_error = (error_summary or "Unknown A2A error")[:1000]

        logger.info(
            "Updated A2A health for agent %s: healthy=%s sync_status=%s health_status=%s error=%s",
            record.agent_id,
            healthy,
            record.sync_status,
            record.health_status,
            record.last_refresh_error,
        )
        db.add(record)
        db.commit()
