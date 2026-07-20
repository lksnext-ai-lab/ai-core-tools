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
from typing import List
from utils.logger import get_logger

logger = get_logger(__name__)


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
    def create_or_update_sandbox_service(
        db: Session, app_id: int, service_id: int, service_data: CreateUpdateSandboxServiceSchema
    ) -> SandboxServiceDetailSchema:
        """Create a new sandbox service or update an existing one"""
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
            from tools.sandbox.factory import _PROVIDER_REGISTRY  # noqa: PLC0415
        except Exception as exc:
            logger.error("Error importing sandbox provider factory: %s", exc)
            return {"status": "error", "message": "Sandbox provider factory unavailable"}

        provider_class = _PROVIDER_REGISTRY.get(provider_name)
        if provider_class is None:
            available = ", ".join(sorted(_PROVIDER_REGISTRY.keys())) or "<none registered>"
            return {
                "status": "error",
                "message": f"Sandbox provider '{provider_name}' is not available. Registered: {available}.",
            }

        provider = None
        handle = None
        try:
            import tempfile
            from tools.sandbox_service_utils import parse_extra_config  # noqa: PLC0415

            extra = parse_extra_config(provider_name, config.get("extra_config"))
            endpoint = config.get("endpoint") or None
            if provider_name == "opensandbox":
                credentials = {"domain": endpoint, "api_key": api_key, "image": extra.get("image")}
            elif provider_name == "daytona":
                credentials = {"api_key": api_key, "api_url": endpoint, "target": extra.get("target")}
            elif provider_name == "e2b":
                credentials = {"api_key": api_key, "template": extra.get("template")}
            else:
                credentials = {}

            provider = provider_class(credentials=credentials)
            with tempfile.TemporaryDirectory() as tmp_dir:
                handle = provider.create_sandbox(tmp_dir)
                result = provider.run_code(handle, "1+1", language="python", timeout=10)
            return {
                "status": "success",
                "message": "Successfully connected to sandbox provider.",
                "response": str(result),
            }
        except Exception as e:
            logger.error(f"Error testing sandbox service connection: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
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
