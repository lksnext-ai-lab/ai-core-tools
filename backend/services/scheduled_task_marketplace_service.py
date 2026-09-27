"""Marketplace view of scheduled tasks: read-only results, visible like marketplace agents.

PUBLIC tasks are visible to every logged-in user, PRIVATE ones to members of the task's app,
UNPUBLISHED ones never.
"""

import math
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models.agent import MarketplaceVisibility
from models.app import App
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from schemas.scheduled_task_schemas import (
    MarketplaceScheduledTaskCardSchema, MarketplaceScheduledTaskCatalogSchema,
)
from services.marketplace_service import MarketplaceService


class ScheduledTaskMarketplaceService:
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self._app_ids: Optional[set] = None

    @property
    def app_ids(self) -> set:
        if self._app_ids is None:
            self._app_ids = MarketplaceService._get_user_app_ids(self.db, self.user_id)
        return self._app_ids

    def _visible(self, query, my_apps_only: bool = False):
        query = query.filter(ScheduledTask.marketplace_visibility != MarketplaceVisibility.UNPUBLISHED)
        if my_apps_only:
            return query.filter(ScheduledTask.app_id.in_(self.app_ids)) if self.app_ids else None
        if self.app_ids:
            return query.filter(or_(
                ScheduledTask.marketplace_visibility == MarketplaceVisibility.PUBLIC,
                ScheduledTask.app_id.in_(self.app_ids),
            ))
        return query.filter(ScheduledTask.marketplace_visibility == MarketplaceVisibility.PUBLIC)

    def catalog(self, *, search: Optional[str], my_apps_only: bool, page: int, page_size: int) -> MarketplaceScheduledTaskCatalogSchema:
        query = self._visible(self.db.query(ScheduledTask, App).join(App, ScheduledTask.app_id == App.app_id), my_apps_only)
        if query is None:
            return MarketplaceScheduledTaskCatalogSchema(tasks=[], total=0, page=page, page_size=page_size, total_pages=0)
        if search:
            pattern = f"%{search}%"
            query = query.filter(or_(ScheduledTask.name.ilike(pattern), ScheduledTask.description.ilike(pattern)))
        total = query.count()
        rows = query.order_by(ScheduledTask.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        stats = self._run_stats([task.id for task, _ in rows])
        return MarketplaceScheduledTaskCatalogSchema(
            tasks=[self._card(task, app, stats.get(task.id)) for task, app in rows],
            total=total, page=page, page_size=page_size, total_pages=math.ceil(total / page_size) if total else 0,
        )

    def get(self, task_id: int) -> Optional[ScheduledTask]:
        query = self._visible(self.db.query(ScheduledTask).filter(ScheduledTask.id == task_id))
        return query.one_or_none() if query is not None else None

    def card(self, task: ScheduledTask) -> MarketplaceScheduledTaskCardSchema:
        app = self.db.get(App, task.app_id)
        return self._card(task, app, self._run_stats([task.id]).get(task.id))

    def _run_stats(self, task_ids: list[int]) -> dict:
        if not task_ids:
            return {}
        rows = (
            self.db.query(
                ScheduledTaskRun.scheduled_task_id,
                func.count(ScheduledTaskRun.id),
                func.max(ScheduledTaskRun.scheduled_time),
            )
            .filter(ScheduledTaskRun.scheduled_task_id.in_(task_ids))
            .group_by(ScheduledTaskRun.scheduled_task_id)
            .all()
        )
        stats = {task_id: {"run_count": count, "last_run_at": last} for task_id, count, last in rows}
        for task_id, entry in stats.items():
            last = (
                self.db.query(ScheduledTaskRun.status)
                .filter(ScheduledTaskRun.scheduled_task_id == task_id)
                .order_by(ScheduledTaskRun.scheduled_time.desc(), ScheduledTaskRun.id.desc())
                .first()
            )
            entry["last_run_status"] = last[0] if last else None
        return stats

    @staticmethod
    def _card(task: ScheduledTask, app: Optional[App], stats: Optional[dict]) -> MarketplaceScheduledTaskCardSchema:
        stats = stats or {}
        return MarketplaceScheduledTaskCardSchema(
            id=task.id, name=task.name, description=task.description, app_id=task.app_id,
            app_name=app.name if app else None, cron_expression=task.cron_expression, timezone=task.timezone,
            conversation_mode=task.conversation_mode, status=task.status,
            marketplace_visibility=task.marketplace_visibility.value, next_run_at=task.next_run_at,
            last_run_at=stats.get("last_run_at"), last_run_status=stats.get("last_run_status"),
            run_count=stats.get("run_count", 0),
        )
