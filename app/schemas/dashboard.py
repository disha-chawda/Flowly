from datetime import date as date_type, datetime

from pydantic import BaseModel

from app.domain.enums import Priority
from app.schemas.task import TaskRead


class WorkloadSummary(BaseModel):
    date: date_type
    window_minutes: int
    committed_minutes: int
    available_minutes: int
    estimated_minutes: int
    difference_minutes: int
    overloaded: bool


class PlannedTask(BaseModel):
    id: int
    title: str
    estimated_time: int | None
    priority: Priority
    deadline: datetime | None
    fits: bool


class DailyPlan(BaseModel):
    date: date_type
    available_minutes: int
    planned_tasks: list[PlannedTask]


class TodayView(BaseModel):
    date: date_type
    tasks: list[TaskRead]


class UpcomingView(BaseModel):
    tasks: list[TaskRead]
