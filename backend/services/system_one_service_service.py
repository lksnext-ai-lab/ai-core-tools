"""Business logic of System One services (per-app connections to a System One server)."""
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.export_constants import PLACEHOLDER_API_KEY
from models.system_one_service import SystemOneService
from repositories.system_one_service_repository import SystemOneServiceRepository
from schemas.system_one_service_schemas import (
    CreateUpdateSystemOneServiceSchema,
    SystemOneServiceDetailSchema,
    SystemOneServiceListItemSchema,
)
from tools import system_one_client
from utils.logger import get_logger
from utils.secret_utils import is_masked_key, mask_api_key

logger = get_logger(__name__)


def _workers() -> int:
    # 2 = the Docker image's default when UVICORN_WORKERS is unset (it is not exported to the process).
    try:
        return max(1, int(os.getenv("UVICORN_WORKERS", "2")))
    except ValueError:
        return 1


def _same_endpoint(a: Optional[str], b: Optional[str]) -> bool:
    """Whether two base URLs name the same server (case and a trailing slash do not matter)."""
    return (a or "").strip().rstrip("/").casefold() == (b or "").strip().rstrip("/").casefold()


def _read_extra(raw: Optional[str]) -> Dict[str, Any]:
    try:
        data = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def max_concurrency_of(service: SystemOneService) -> int:
    """Per-process cap stored in ``extra_config`` (1 when missing or broken)."""
    value = _read_extra(service.extra_config).get("max_concurrency")
    return value if isinstance(value, int) and value >= 1 else 1


class SystemOneServiceService:

    @staticmethod
    def _to_list_item(service: SystemOneService, agent_count: int = 0) -> SystemOneServiceListItemSchema:
        return SystemOneServiceListItemSchema(
            agent_count=agent_count,
            service_id=service.service_id,
            name=service.name,
            endpoint=service.endpoint or "",
            model=service.description or "",
            max_concurrency=max_concurrency_of(service),
            created_at=service.create_date,
        )

    @staticmethod
    def _to_detail(service: SystemOneService) -> SystemOneServiceDetailSchema:
        return SystemOneServiceDetailSchema(
            service_id=service.service_id,
            name=service.name,
            endpoint=service.endpoint or "",
            api_key=mask_api_key(service.api_key),
            model=service.description or "",
            max_concurrency=max_concurrency_of(service),
            created_at=service.create_date,
        )

    @staticmethod
    def get_system_one_services_by_app_id(db: Session, app_id: int) -> List[SystemOneServiceListItemSchema]:
        return [
            SystemOneServiceService._to_list_item(s, len(SystemOneServiceRepository.get_agents_using(db, s.service_id)))
            for s in SystemOneServiceRepository.get_by_app_id(db, app_id)
        ]

    @staticmethod
    def get_system_one_service_detail(db: Session, app_id: int, service_id: int) -> Optional[SystemOneServiceDetailSchema]:
        if service_id == 0:
            return SystemOneServiceDetailSchema(service_id=0, name="", endpoint="", api_key="", model="",
                                                max_concurrency=1)
        service = SystemOneServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
        return SystemOneServiceService._to_detail(service) if service else None

    @staticmethod
    def create_or_update_system_one_service(
        db: Session, app_id: int, service_id: int, data: CreateUpdateSystemOneServiceSchema
    ) -> Optional[SystemOneServiceDetailSchema]:
        # No private-address blocking on purpose: a self-hosted server normally sits on a private network.
        # Only the scheme/host are checked; only administrators can reach this code.
        endpoint = system_one_client.check_base_url(data.endpoint)

        if service_id == 0:
            service = SystemOneService()
            service.app_id = app_id
            service.create_date = datetime.now()
        else:
            service = SystemOneServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
            if not service:
                return None

        previous_endpoint = service.endpoint
        service.name = data.name
        service.endpoint = endpoint
        service.description = data.model
        # "****abcd" is the masked echo of the stored token: never overwrite a real secret with it.
        token = data.api_key or ""
        if is_masked_key(token) and service.api_key and not _same_endpoint(previous_endpoint, endpoint):
            # The stored secret belongs to the server it was typed for: it must not follow the URL elsewhere.
            raise ValueError("The URL changed: type the token again (or clear it) so it is not sent to a new server")
        if not is_masked_key(token):
            service.api_key = token or None
        concurrency = data.max_concurrency or system_one_client.default_max_concurrency(None, _workers())
        service.extra_config = json.dumps({"max_concurrency": concurrency})

        if service_id == 0:
            service = SystemOneServiceRepository.create(db, service)
        else:
            service = SystemOneServiceRepository.update(db, service)
        return SystemOneServiceService._to_detail(service)

    @staticmethod
    def copy_system_one_service(db: Session, app_id: int, service_id: int) -> Optional[SystemOneServiceDetailSchema]:
        service = SystemOneServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
        if not service:
            return None
        existing = {s.name for s in SystemOneServiceRepository.get_by_app_id(db, app_id)}
        base_name = (service.name or "").strip() or "System One Service"
        new_name, counter = f"{base_name} Copy", 2
        while new_name in existing:
            new_name = f"{base_name} Copy {counter}"
            counter += 1
        copy = SystemOneService(
            app_id=app_id,
            name=new_name,
            endpoint=service.endpoint,
            api_key=service.api_key,           # same convention as AI/Sandbox services: the copy keeps the token
            description=service.description,
            extra_config=service.extra_config,
            create_date=datetime.now(),
        )
        return SystemOneServiceService._to_detail(SystemOneServiceRepository.create(db, copy))

    @staticmethod
    def _agents_using(db: Session, service_id: int) -> List[Dict[str, Any]]:
        return [{"agent_id": a.agent_id, "name": a.name} for a in SystemOneServiceRepository.get_agents_using(db, service_id)]

    @staticmethod
    def delete_system_one_service(db: Session, app_id: int, service_id: int) -> Optional[List[Dict[str, Any]]]:
        """Delete the service; returns the agents it leaves without one (they stay, inoperative), None if not found."""
        service = SystemOneServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
        if not service:
            return None
        detached = SystemOneServiceService._agents_using(db, service_id)
        SystemOneServiceRepository.delete(db, service)   # the FK is ON DELETE SET NULL
        return detached

    # ------------------------------------------------------------ connection tests

    @staticmethod
    def _probe_result(result: Dict[str, Any]) -> Dict[str, Any]:
        limits = result["limits"]
        server_limit = limits.get("max_concurrent_requests") if isinstance(limits, dict) else None
        return {
            "status": "success" if result["ok"] else "error",
            "message": result["message"],
            "models": result["models"],
            "limits": limits,
            # The cap is per backend process and every process shares the server's limit (NFR-2).
            "suggested_max_concurrency": (
                system_one_client.default_max_concurrency(server_limit, _workers())
                if result["ok"] and isinstance(server_limit, int) else None
            ),
        }

    @staticmethod
    async def test_connection_with_config(
        db: Session, app_id: int, config: Dict[str, Any], service_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Probe the server with the form's values (nothing is saved).

        With ``service_id`` and no retyped token (empty or masked) the stored token is used, so editing
        a service never forces re-typing the secret just to test it.
        """
        endpoint = (config.get("endpoint") or "").strip()
        api_key = config.get("api_key") or ""
        if service_id is not None and (not api_key or is_masked_key(api_key) or api_key == PLACEHOLDER_API_KEY):
            stored = SystemOneServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
            # Only for the server the token was stored for: a changed URL gets no secret.
            same = stored is not None and _same_endpoint(stored.endpoint, endpoint)
            api_key = (stored.api_key if same else None) or ""
        try:
            result = await system_one_client.probe(endpoint, api_key or None)
        except ValueError as exc:
            return {"status": "error", "message": str(exc), "models": [], "limits": None, "suggested_max_concurrency": None}
        return SystemOneServiceService._probe_result(result)

    @staticmethod
    async def test_connection(db: Session, app_id: int, service_id: int) -> Optional[Dict[str, Any]]:
        service = SystemOneServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
        if not service:
            return None
        try:
            result = await system_one_client.probe(service.endpoint or "", service.api_key)
        except ValueError as exc:
            return {"status": "error", "message": str(exc), "models": [], "limits": None, "suggested_max_concurrency": None}
        return SystemOneServiceService._probe_result(result)
