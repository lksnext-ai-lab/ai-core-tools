import ipaddress
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from urllib.parse import urlsplit

from sqlalchemy.orm import Session
from models.sandbox_service import SandboxService, SandboxProviderEnum
from repositories.sandbox_service_repository import SandboxServiceRepository
from schemas.sandbox_service_schemas import (
    SandboxServiceListItemSchema,
    SandboxServiceDetailSchema,
    CreateUpdateSandboxServiceSchema,
)
from core.export_constants import PLACEHOLDER_API_KEY
from utils.secret_utils import mask_api_key, is_masked_key
from tools.sandbox_service_utils import build_extra_config, parse_extra_config
from datetime import datetime
from typing import List, Optional
from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# test_connection_with_config: SSRF guard + bounded-timeout probe settings
# ---------------------------------------------------------------------------

# When set to "true", disables the private/loopback/link-local endpoint check
# below. Off (strict) by default: a tenant app ADMINISTRATOR can reach this
# code path with an arbitrary endpoint, so — absent a reliable way to
# distinguish "the platform operator's own pre-configured default" from "a
# value a tenant just typed into this form" at this layer — the safe default
# blocks both. Self-hosted deployments whose OpenSandbox server genuinely
# lives on an internal/private address (e.g. the ``opensandbox:8080`` Docker
# service name from docker/.env.example) must opt in explicitly. This only
# gates the diagnostic "Test Connection" probe; actual sandbox usage via
# ``tools.sandbox.factory.resolve_provider`` is unaffected.
_ALLOW_PRIVATE_TEST_TARGETS_ENV = "SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE"

# Bounded timeout (seconds) for the create/run/destroy probe below, so a
# single bad/unreachable target can't stall the caller indefinitely.
_TEST_CONNECTION_TIMEOUT_ENV = "SANDBOX_TEST_CONNECTION_TIMEOUT_S"
_DEFAULT_TEST_CONNECTION_TIMEOUT_S = 20


def _allow_private_test_targets() -> bool:
    return os.getenv(_ALLOW_PRIVATE_TEST_TARGETS_ENV, "false").strip().lower() == "true"


def _test_connection_timeout_s() -> int:
    try:
        return int(os.getenv(_TEST_CONNECTION_TIMEOUT_ENV, str(_DEFAULT_TEST_CONNECTION_TIMEOUT_S)))
    except (TypeError, ValueError):
        return _DEFAULT_TEST_CONNECTION_TIMEOUT_S


# RFC 6598 shared/CGNAT address space (100.64.0.0/10) — used by some cloud
# providers' metadata services (e.g. Alibaba Cloud's 100.100.100.200) and by
# carrier-grade NAT. Not covered by ipaddress.is_private/is_reserved in
# Python's stdlib, so it must be checked explicitly.
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


def _is_blocked_ip(ip: "ipaddress.IPv4Address | ipaddress.IPv6Address") -> bool:
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or (ip.version == 4 and ip in _CGNAT_NETWORK)
    )


def _extract_hostname(endpoint: str) -> Optional[str]:
    """Best-effort hostname extraction from a ``host:port`` or full URL string."""
    endpoint = (endpoint or "").strip()
    if not endpoint:
        return None
    # urlsplit needs a "//" prefix to parse a bare "host:port" into netloc
    # instead of mistaking "host" for a URL scheme.
    candidate = endpoint if "//" in endpoint else f"//{endpoint}"
    try:
        return urlsplit(candidate).hostname
    except ValueError:
        return None


def _endpoint_is_disallowed(endpoint: Optional[str]) -> bool:
    """Return True if *endpoint* resolves to a loopback/link-local/private address.

    Uses ``ipaddress``'s own range checks (``is_loopback``/``is_link_local``/
    ``is_private``) rather than hand-rolled CIDR comparisons. Unresolvable
    hostnames are allowed through here — a DNS failure isn't itself an SSRF
    signal, and the provider call will fail naturally afterwards.
    """
    if not endpoint or _allow_private_test_targets():
        return False

    hostname = _extract_hostname(endpoint)
    if not hostname:
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        return _is_blocked_ip(ip)
    except ValueError:
        pass  # Not a literal IP — resolve it below.

    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, socket.timeout, UnicodeError):
        return False

    for info in infos:
        raw_ip = info[4][0]
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            return True
    return False


class SandboxServiceService:

    @staticmethod
    def _to_list_item(service: "SandboxService", is_system: bool = False) -> SandboxServiceListItemSchema:
        """Convert a SandboxService ORM instance to a list item schema."""
        needs_api_key = (
            not service.api_key
            or service.api_key == PLACEHOLDER_API_KEY
        )
        return SandboxServiceListItemSchema(
            service_id=service.service_id,
            name=service.name,
            provider=service.provider,
            created_at=service.create_date,
            needs_api_key=needs_api_key,
            is_system=is_system,
        )

    @staticmethod
    def _extra_config_fields(provider: str, extra_config_raw) -> dict:
        """Map the generic extra_config dict onto schema-specific field names."""
        extra_cfg = parse_extra_config(provider, extra_config_raw)
        return {
            "opensandbox_image": extra_cfg.get("image"),
            "daytona_target": extra_cfg.get("target"),
            "daytona_workspace": extra_cfg.get("workspace") if provider == SandboxProviderEnum.Daytona.value else None,
            "daytona_cpu": extra_cfg.get("cpu"),
            "daytona_memory_gb": extra_cfg.get("memory_gb"),
            "e2b_template": extra_cfg.get("template"),
            "e2b_workspace": extra_cfg.get("workspace") if provider == SandboxProviderEnum.E2B.value else None,
        }

    @staticmethod
    def get_sandbox_services_by_app_id(db: Session, app_id: int) -> List[SandboxServiceListItemSchema]:
        """Get all sandbox services for a specific app, including platform-level system services."""
        app_services = SandboxServiceRepository.get_by_app_id(db, app_id)
        system_services = SandboxServiceRepository.get_system_services(db)

        result = [SandboxServiceService._to_list_item(svc, is_system=False) for svc in app_services]
        result += [SandboxServiceService._to_list_item(svc, is_system=True) for svc in system_services]
        return result

    @staticmethod
    def get_sandbox_service_detail(db: Session, app_id: int, service_id: int) -> SandboxServiceDetailSchema:
        """Get detailed information about a specific sandbox service"""
        if service_id == 0:
            # New sandbox service
            providers = [{"value": p.value, "name": p.value} for p in SandboxProviderEnum]

            return SandboxServiceDetailSchema(
                service_id=0,
                name="",
                provider=None,
                api_key="",
                base_url="",
                created_at=None,
                available_providers=providers,
            )

        # Existing sandbox service
        service = SandboxServiceRepository.get_by_id_and_app_id(db, service_id, app_id)

        if not service:
            return None

        providers = [{"value": p.value, "name": p.value} for p in SandboxProviderEnum]

        needs_api_key = (
            not service.api_key
            or service.api_key == PLACEHOLDER_API_KEY
        )
        return SandboxServiceDetailSchema(
            service_id=service.service_id,
            name=service.name,
            provider=service.provider,
            api_key=mask_api_key(service.api_key),
            base_url=service.endpoint or "",
            created_at=service.create_date,
            available_providers=providers,
            needs_api_key=needs_api_key,
            **SandboxServiceService._extra_config_fields(service.provider, service.extra_config),
        )

    @staticmethod
    def _validate_provider_allowed(provider_name: str) -> None:
        """Raise if *provider_name* is registered but excluded by ``SANDBOX_ALLOWED_PROVIDERS``.

        Mirrors the allowlist ``tools.sandbox.factory`` enforces at
        resolution time, so a disallowed provider is rejected here at
        config-save time (immediate UI feedback) rather than only
        surfacing on first agent use. An empty/unset allowlist means "no
        restriction" — preserves existing behavior for deployments that
        have not configured it.

        Raises:
            SandboxProviderUnavailableError: If *provider_name* is not in a
                configured, non-empty allowlist.
        """
        import config as settings  # noqa: PLC0415
        from tools.sandbox.factory import SandboxProviderUnavailableError  # noqa: PLC0415

        allowed = getattr(settings, "SANDBOX_ALLOWED_PROVIDERS", None)
        if not allowed:
            return
        normalized = (provider_name or "").strip().lower()
        if normalized not in {p.strip().lower() for p in allowed}:
            raise SandboxProviderUnavailableError(
                f"Sandbox provider '{provider_name}' is not allowed in this deployment. "
                f"Allowed providers: {', '.join(sorted(allowed))}."
            )

    @staticmethod
    def create_or_update_sandbox_service(
        db: Session, app_id: int, service_id: int, service_data: CreateUpdateSandboxServiceSchema
    ) -> SandboxServiceDetailSchema:
        """Create a new sandbox service or update an existing one"""
        SandboxServiceService._validate_provider_allowed(service_data.provider)
        if _endpoint_is_disallowed(service_data.base_url):
            # Same SSRF guard as test_connection_with_config, applied at
            # save-time: an endpoint that's never tested (the "Test
            # Connection" button is optional) would otherwise reach real
            # sandbox creation with a loopback/link-local/private target on
            # every subsequent agent turn, not just a one-off diagnostic probe.
            logger.warning(
                "Rejected sandbox service save with a disallowed endpoint (provider=%s, app_id=%s)",
                service_data.provider,
                app_id,
            )
            raise ValueError("Invalid or disallowed endpoint")

        if service_id == 0:
            service = SandboxService()
            service.app_id = app_id
            service.create_date = datetime.now()
        else:
            service = SandboxServiceRepository.get_by_id_and_app_id(db, service_id, app_id)

            if not service:
                return None

        service.name = service_data.name
        service.provider = service_data.provider
        # Only update api_key if user provided a new (non-masked) value —
        # never clobber a real secret with an echoed masked placeholder.
        if not is_masked_key(service_data.api_key):
            service.api_key = service_data.api_key
        service.endpoint = service_data.base_url
        service.extra_config = build_extra_config(
            service_data.provider,
            image=service_data.opensandbox_image,
            target=service_data.daytona_target,
            workspace=service_data.daytona_workspace or service_data.e2b_workspace,
            cpu=service_data.daytona_cpu,
            memory_gb=service_data.daytona_memory_gb,
            template=service_data.e2b_template,
        )

        if service_id == 0:
            service = SandboxServiceRepository.create(db, service)
        else:
            service = SandboxServiceRepository.update(db, service)

        return SandboxServiceService.get_sandbox_service_detail(db, app_id, service.service_id)

    @staticmethod
    def copy_sandbox_service(db: Session, app_id: int, service_id: int) -> SandboxServiceDetailSchema:
        """Copy an existing sandbox service"""
        service = SandboxServiceRepository.get_by_id_and_app_id(db, service_id, app_id)

        if not service:
            return None

        existing = {s.name for s in SandboxServiceService.get_sandbox_services_by_app_id(db, app_id)}
        base_name = service.name.strip() if service.name else "Sandbox Service"
        new_name = f"{base_name} Copy"
        counter = 2
        while new_name in existing:
            new_name = f"{base_name} Copy {counter}"
            counter += 1

        new_service = SandboxService(
            app_id=app_id,
            name=new_name,
            provider=service.provider,
            api_key=service.api_key,
            endpoint=service.endpoint,
            extra_config=service.extra_config,
            create_date=datetime.now(),
        )

        new_service = SandboxServiceRepository.create(db, new_service)

        return SandboxServiceService.get_sandbox_service_detail(db, app_id, new_service.service_id)

    @staticmethod
    def delete_sandbox_service(db: Session, app_id: int, service_id: int) -> bool:
        """Delete a sandbox service"""
        service = SandboxServiceRepository.get_by_id_and_app_id(db, service_id, app_id)

        if not service:
            return False

        SandboxServiceRepository.delete(db, service)

        return True

    @staticmethod
    def delete_by_app_id(app_id: int):
        """Delete all sandbox services for a specific app"""
        from db.database import SessionLocal
        session = SessionLocal()
        try:
            SandboxServiceRepository.delete_by_app_id(session, app_id)
        finally:
            session.close()

    @staticmethod
    def test_connection_with_config(config: dict) -> dict:
        """Test connection to a sandbox provider using the provided configuration.

        Builds the same ``credentials`` dict shape ``resolve_provider`` derives
        from a ``SandboxService`` row and passes it into the provider
        constructor, so this exercises the actual submitted form values
        (``api_key``/``endpoint``/``extra_config``) rather than process env vars.
        """
        provider_name = (config.get("provider") or "").strip().lower()
        if not provider_name:
            return {"status": "error", "message": "Provider is required"}

        # OpenSandbox is self-hosted and commonly run with no auth configured
        # (OPENSANDBOX_INSECURE_SERVER) — mirrors the frontend wizard's
        # apiKey: 'optional' for this provider. Daytona/E2B are 'required'.
        api_key = config.get("api_key") or ""
        api_key_is_placeholder = (
            api_key == PLACEHOLDER_API_KEY or is_masked_key(api_key)
        )
        if api_key_is_placeholder:
            return {
                "status": "error",
                "message": (
                    "API key is required. Please configure "
                    "a valid API key before testing the "
                    "connection."
                ),
            }
        if not api_key and provider_name != "opensandbox":
            return {
                "status": "error",
                "message": (
                    "API key is required. Please configure "
                    "a valid API key before testing the "
                    "connection."
                ),
            }

        try:
            # _provider_class_for enforces SANDBOX_ALLOWED_PROVIDERS as well as
            # registry membership — use it here too (not a raw _PROVIDER_REGISTRY
            # lookup) so a deployment-restricted provider can't be probed via
            # this diagnostic endpoint even though it's rejected everywhere else.
            from tools.sandbox.factory import (  # noqa: PLC0415
                _provider_class_for,
                SandboxProviderUnavailableError,
            )

            provider_class = _provider_class_for(provider_name)
        except SandboxProviderUnavailableError as exc:
            return {"status": "error", "message": str(exc)}
        except Exception as exc:
            logger.error("Error importing sandbox provider factory: %s", exc)
            return {"status": "error", "message": "Sandbox provider factory unavailable"}

        endpoint = config.get("endpoint") or None
        if _endpoint_is_disallowed(endpoint):
            # Deliberately generic: don't tell the caller *why* it was
            # rejected (loopback vs RFC1918 vs unresolvable) — that
            # distinction is itself an oracle for network reconnaissance.
            logger.warning(
                "Rejected sandbox test-connection to a disallowed endpoint (provider=%s)",
                provider_name,
            )
            return {"status": "error", "message": "Invalid or disallowed endpoint"}

        provider = None
        handle = None
        try:
            import tempfile
            from tools.sandbox_service_utils import parse_extra_config  # noqa: PLC0415

            extra = parse_extra_config(provider_name, config.get("extra_config"))
            if provider_name == "opensandbox":
                credentials = {"domain": endpoint, "api_key": api_key, "image": extra.get("image")}
            elif provider_name == "daytona":
                credentials = {"api_key": api_key, "api_url": endpoint, "target": extra.get("target")}
            elif provider_name == "e2b":
                credentials = {"api_key": api_key, "template": extra.get("template")}
            else:
                credentials = {}

            provider = provider_class(credentials=credentials)

            def _probe():
                # Runs on a worker thread so a hung/unreachable target
                # can't block the caller's event loop; bounded below by
                # future.result(timeout=...).
                nonlocal handle
                with tempfile.TemporaryDirectory() as tmp_dir:
                    handle = provider.create_sandbox(tmp_dir)
                    return provider.run_code(handle, "1+1", language="python", timeout=10)

            timeout_s = _test_connection_timeout_s()
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sandbox_test_connection")
            try:
                future = executor.submit(_probe)
                try:
                    result = future.result(timeout=timeout_s)
                except FutureTimeoutError:
                    future.cancel()
                    logger.error(
                        "Sandbox test-connection timed out after %ss (provider=%s)",
                        timeout_s,
                        provider_name,
                    )
                    return {
                        "status": "error",
                        "message": f"Connection test timed out after {timeout_s}s.",
                    }
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

            return {
                "status": "success",
                "message": "Successfully connected to sandbox provider.",
                "response": str(result),
            }
        except Exception as e:
            # Deliberately generic, matching the endpoint-rejection message
            # above: connection-refused vs TLS-error vs HTTP-status text is
            # itself a network-reconnaissance oracle when this probe is
            # reachable by a tenant-level (non-platform-trusted) role.
            logger.error(f"Error testing sandbox service connection: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": "Could not connect to the sandbox provider. Check the endpoint and credentials.",
            }
        finally:
            if provider is not None and handle is not None:
                try:
                    provider.destroy_sandbox(handle)
                except Exception:
                    logger.warning(
                        "Failed to destroy test sandbox during connection test",
                        exc_info=True,
                    )

    @staticmethod
    def test_connection(db: Session, app_id: int, service_id: int) -> dict:
        """Test connection to sandbox service"""
        service = SandboxServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
        if not service:
            return {"status": "error", "message": "Sandbox service not found"}

        config = {
            "provider": service.provider,
            "api_key": service.api_key,
            "endpoint": service.endpoint,
            "extra_config": service.extra_config,
        }

        return SandboxServiceService.test_connection_with_config(config)
