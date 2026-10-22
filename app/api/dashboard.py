"""Dashboard API router.

Exposes the read-side dashboard endpoints from Design §6 — today, upcoming,
workload, and daily plan — wiring the dashboard service
(`app/services/dashboard_service.py`) to the dashboard response schemas
(`app/schemas/dashboard.py`). Each request builds a :class:`DashboardService`
backed by a :class:`TaskRepository` and a :class:`CommitmentRepository`, both
bound to the per-request session provided by the ``get_db`` dependency
(`app/data/database.py`).

Every endpoint accepts an optional ``date`` query parameter and defaults to the
current calendar date when it is absent (Design §6). All four endpoints return
``200``: they are pure reads with no not-found or validation failure paths of
their own. The service returns plain planning-core results and ORM entities,
which the declared ``response_model`` schemas serialize via ``from_attributes``.
"""

from __future__ import annotations

from datetime import date as date_type

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.data.commitment_repository import CommitmentRepository
from app.data.database import get_db
from app.data.task_repository import TaskRepository
from app.schemas.dashboard import (
    DailyPlan,
    TodayView,
    UpcomingView,
    WorkloadSummary,
)
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_dashboard_service(db: Session = Depends(get_db)) -> DashboardService:
    """Provide a :class:`DashboardService` bound to the request-scoped session."""
    return DashboardService(TaskRepository(db), CommitmentRepository(db))


def _resolve_date(date: date_type | None) -> date_type:
    """Return the requested date, defaulting to the current date when absent."""
    return date if date is not None else date_type.today()


@router.get("/today", response_model=TodayView)
def get_today(
    date: date_type | None = None,
    service: DashboardService = Depends(get_dashboard_service),
) -> TodayView:
    """Return the Today view for ``date`` (defaults to the current date)."""
    target = _resolve_date(date)
    tasks = service.today_view(target)
    return TodayView(date=target, tasks=tasks)


@router.get("/upcoming", response_model=UpcomingView)
def get_upcoming(
    date: date_type | None = None,
    service: DashboardService = Depends(get_dashboard_service),
) -> UpcomingView:
    """Return the Upcoming view relative to ``date`` (defaults to the current date)."""
    target = _resolve_date(date)
    tasks = service.upcoming_view(target)
    return UpcomingView(tasks=tasks)


@router.get("/workload", response_model=WorkloadSummary)
def get_workload(
    date: date_type | None = None,
    service: DashboardService = Depends(get_dashboard_service),
) -> WorkloadSummary:
    """Return the workload summary for ``date`` (defaults to the current date)."""
    target = _resolve_date(date)
    return service.workload(target)


@router.get("/daily-plan", response_model=DailyPlan)
def get_daily_plan(
    date: date_type | None = None,
    service: DashboardService = Depends(get_dashboard_service),
) -> DailyPlan:
    """Return the daily plan for ``date`` (defaults to the current date)."""
    target = _resolve_date(date)
    return service.daily_plan(target)
