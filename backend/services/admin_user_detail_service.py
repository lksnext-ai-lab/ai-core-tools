"""Business logic for retrieving the internal admin user detail view."""

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from models.user import User
from repositories.admin_user_detail_repository import (
    AdminUserDetailRepository,
    APIKeyDetailRecord,
    CollaborationDetailRecord,
    OwnedAppDetailRecord,
)
from repositories.usage_record_repository import UsageRecordRepository
from utils.config import is_omniadmin


@dataclass
class AdminUserDetailData:
    """Selected ORM data used to construct the admin detail response."""

    user: User
    owned_apps: List[OwnedAppDetailRecord]
    collaborations: List[CollaborationDetailRecord]
    api_keys: List[APIKeyDetailRecord]
    call_count: int
    billing_period_start: date
    is_omniadmin: bool


class AdminUserDetailService:
    """Orchestrate the targeted data reads for an admin user detail request."""

    @staticmethod
    def get_user_detail(db: Session, user_id: int) -> Optional[AdminUserDetailData]:
        """Return details for one user, or ``None`` if that user does not exist.

        Usage represents system LLM calls recorded for the user in the current
        calendar billing period; it does not include app-wide or execution metrics.
        """
        repository = AdminUserDetailRepository(db)
        user = repository.get_user(user_id)
        if user is None:
            return None

        current_period_start = date.today().replace(day=1)
        usage = UsageRecordRepository(db).get_current(user_id)

        return AdminUserDetailData(
            user=user,
            owned_apps=repository.get_owned_apps(user_id),
            collaborations=repository.get_collaborations(user_id),
            api_keys=repository.get_api_keys(user_id),
            call_count=usage.call_count if usage is not None else 0,
            billing_period_start=(
                usage.billing_period_start if usage is not None else current_period_start
            ),
            is_omniadmin=is_omniadmin(user.email),
        )
