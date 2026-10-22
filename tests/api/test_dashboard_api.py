"""API tests for the dashboard endpoints (Task 13.3).

Exercises ``GET /dashboard/today``, ``/upcoming``, ``/workload``, and
``/daily-plan`` through FastAPI's ``TestClient``, asserting ``200`` responses and
the documented response shapes (Design §6), including overlapping commitments
and tasks with and without deadlines (Requirements §4–§8).

Isolation: every test gets a fresh app from ``create_app()`` whose ``get_db``
dependency is overridden to an in-memory SQLite database (``StaticPool`` so all
sessions share one connection). The ``TestClient`` is NOT used as a context
manager, so the app's startup hook (which would call ``create_all`` on the
configured engine) never runs and the real ``flowly.db`` is never touched. All
fixtures are self-contained in this module; no shared conftest is used. Data is
seeded via the public API (``POST /tasks``, ``POST /commitments``) and every
request passes an explicit ``date`` so results are deterministic.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data import models  # noqa: F401  (registers tables on Base.metadata)
from app.data.database import Base, get_db
from app.main import create_app

TARGET = "2025-03-10"

TASK_READ_KEYS = {
    "id",
    "title",
    "description",
    "deadline",
    "estimated_time",
    "priority",
    "category",
    "completion",
    "created_at",
    "source",
}
WORKLOAD_KEYS = {
    "date",
    "window_minutes",
    "committed_minutes",
    "available_minutes",
    "estimated_minutes",
    "difference_minutes",
    "overloaded",
}
DAILY_PLAN_KEYS = {"date", "available_minutes", "planned_tasks"}
PLANNED_TASK_KEYS = {"id", "title", "estimated_time", "priority", "deadline", "fits"}


# --------------------------------------------------------------------------- #
# Fixtures (self-contained; isolated in-memory SQLite database)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)

    def _override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    # Not used as a context manager: the startup hook (create_all on the real
    # engine) is intentionally skipped so the real database is never touched.
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _create_task(client: TestClient, **fields) -> dict:
    body = {"title": "Task", **fields}
    response = client.post("/tasks", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _complete(client: TestClient, task_id: int) -> dict:
    response = client.patch(f"/tasks/{task_id}/completion", json={"completion": "Complete"})
    assert response.status_code == 200, response.text
    return response.json()


def _create_commitment(client: TestClient, start: str, end: str, title: str = "Block") -> dict:
    response = client.post(
        "/commitments", json={"title": title, "start_time": start, "end_time": end}
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Empty state: all four endpoints return 200 with the documented shapes
# --------------------------------------------------------------------------- #


def test_all_dashboard_endpoints_return_200_and_shapes_on_empty_db(client):
    today = client.get("/dashboard/today", params={"date": TARGET})
    assert today.status_code == 200
    assert today.json() == {"date": TARGET, "tasks": []}

    upcoming = client.get("/dashboard/upcoming", params={"date": TARGET})
    assert upcoming.status_code == 200
    assert upcoming.json() == {"tasks": []}

    workload = client.get("/dashboard/workload", params={"date": TARGET})
    assert workload.status_code == 200
    assert workload.json() == {
        "date": TARGET,
        "window_minutes": 960,
        "committed_minutes": 0,
        "available_minutes": 960,
        "estimated_minutes": 0,
        "difference_minutes": 960,
        "overloaded": False,
    }

    plan = client.get("/dashboard/daily-plan", params={"date": TARGET})
    assert plan.status_code == 200
    assert plan.json() == {"date": TARGET, "available_minutes": 960, "planned_tasks": []}


# --------------------------------------------------------------------------- #
# Today view (Requirements §5)
# --------------------------------------------------------------------------- #


def test_today_returns_tasks_due_on_date_with_completed_distinguishable(client):
    due_incomplete = _create_task(client, title="Due today", deadline=f"{TARGET}T09:00:00")
    due_completed = _create_task(client, title="Done today", deadline=f"{TARGET}T18:00:00")
    _complete(client, due_completed["id"])
    _create_task(client, title="Tomorrow", deadline="2025-03-11T09:00:00")
    _create_task(client, title="Yesterday", deadline="2025-03-09T09:00:00")
    _create_task(client, title="No deadline")

    response = client.get("/dashboard/today", params={"date": TARGET})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"date", "tasks"}
    assert body["date"] == TARGET

    tasks = body["tasks"]
    for task in tasks:
        assert set(task) == TASK_READ_KEYS
    assert [t["id"] for t in tasks] == [due_incomplete["id"], due_completed["id"]]

    completion_by_id = {t["id"]: t["completion"] for t in tasks}
    assert completion_by_id[due_incomplete["id"]] == "Incomplete"
    assert completion_by_id[due_completed["id"]] == "Complete"


# --------------------------------------------------------------------------- #
# Upcoming view (Requirements §6)
# --------------------------------------------------------------------------- #


def test_upcoming_returns_incomplete_future_tasks_ordered_by_deadline(client):
    later = _create_task(client, title="Later", deadline="2025-03-20T09:00:00")
    sooner = _create_task(client, title="Sooner", deadline="2025-03-12T09:00:00")
    middle = _create_task(client, title="Middle", deadline="2025-03-15T09:00:00")
    done_future = _create_task(client, title="Done future", deadline="2025-03-13T09:00:00")
    _complete(client, done_future["id"])
    _create_task(client, title="Today", deadline=f"{TARGET}T23:00:00")
    _create_task(client, title="Past", deadline="2025-03-01T09:00:00")
    _create_task(client, title="No deadline")

    response = client.get("/dashboard/upcoming", params={"date": TARGET})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"tasks"}
    for task in body["tasks"]:
        assert set(task) == TASK_READ_KEYS
        assert task["completion"] == "Incomplete"
    assert [t["id"] for t in body["tasks"]] == [sooner["id"], middle["id"], later["id"]]


# --------------------------------------------------------------------------- #
# Workload summary (Requirements §7)
# --------------------------------------------------------------------------- #


def test_workload_counts_overlapping_commitments_once(client):
    # 09:00-11:00 and 10:00-12:00 overlap -> union 09:00-12:00 = 180 minutes.
    _create_commitment(client, f"{TARGET}T09:00:00", f"{TARGET}T11:00:00", "Class")
    _create_commitment(client, f"{TARGET}T10:00:00", f"{TARGET}T12:00:00", "Shift")
    # Nested inside the union: contributes nothing extra.
    _create_commitment(client, f"{TARGET}T10:15:00", f"{TARGET}T10:45:00", "Meeting")
    # Another day: excluded entirely.
    _create_commitment(client, "2025-03-11T09:00:00", "2025-03-11T15:00:00", "Other day")

    # Incomplete tasks due on the date: 60 + 30 + missing (0) = 90.
    _create_task(client, title="A", deadline=f"{TARGET}T13:00:00", estimated_time=60)
    _create_task(client, title="B", deadline=f"{TARGET}T14:00:00", estimated_time=30)
    _create_task(client, title="No estimate", deadline=f"{TARGET}T15:00:00")
    # Excluded from the estimate: completed, other-day, and no-deadline tasks.
    done = _create_task(client, title="Done", deadline=f"{TARGET}T08:00:00", estimated_time=500)
    _complete(client, done["id"])
    _create_task(client, title="Tomorrow", deadline="2025-03-11T08:00:00", estimated_time=400)
    _create_task(client, title="Someday", estimated_time=300)

    response = client.get("/dashboard/workload", params={"date": TARGET})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == WORKLOAD_KEYS
    assert body == {
        "date": TARGET,
        "window_minutes": 960,
        "committed_minutes": 180,
        "available_minutes": 780,
        "estimated_minutes": 90,
        "difference_minutes": 690,
        "overloaded": False,
    }


def test_workload_reports_overload_when_window_is_fully_committed(client):
    # Overlapping commitments covering beyond the 960-minute window.
    _create_commitment(client, f"{TARGET}T00:00:00", f"{TARGET}T10:00:00")
    _create_commitment(client, f"{TARGET}T08:00:00", f"{TARGET}T20:00:00")
    _create_task(client, title="Squeezed", deadline=f"{TARGET}T21:00:00", estimated_time=30)

    response = client.get("/dashboard/workload", params={"date": TARGET})
    assert response.status_code == 200
    body = response.json()
    assert body["committed_minutes"] == 960
    assert body["available_minutes"] == 0
    assert body["estimated_minutes"] == 30
    assert body["difference_minutes"] == -30
    assert body["overloaded"] is True


# --------------------------------------------------------------------------- #
# Daily plan (Requirements §8)
# --------------------------------------------------------------------------- #


def test_daily_plan_selects_orders_and_marks_fit(client):
    # 00:00-15:00 committed (900 min) -> 60 minutes available.
    _create_commitment(client, f"{TARGET}T00:00:00", f"{TARGET}T09:00:00")
    _create_commitment(client, f"{TARGET}T08:00:00", f"{TARGET}T15:00:00")

    overdue = _create_task(
        client, title="Overdue", deadline="2025-03-08T12:00:00", priority="Low", estimated_time=30
    )
    today_low = _create_task(client, title="Today low", deadline=f"{TARGET}T12:00:00", priority="Low")
    today_medium = _create_task(
        client, title="Today medium", deadline=f"{TARGET}T12:00:00", priority="Medium", estimated_time=40
    )
    today_high = _create_task(
        client, title="Today high", deadline=f"{TARGET}T18:00:00", priority="High", estimated_time=20
    )
    # Excluded: no deadline, future deadline, completed.
    _create_task(client, title="No deadline", priority="High", estimated_time=5)
    _create_task(client, title="Future", deadline="2025-03-11T09:00:00", priority="High")
    done = _create_task(client, title="Done", deadline=f"{TARGET}T09:00:00", priority="High")
    _complete(client, done["id"])

    response = client.get("/dashboard/daily-plan", params={"date": TARGET})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == DAILY_PLAN_KEYS
    assert body["date"] == TARGET
    assert body["available_minutes"] == 60

    planned = body["planned_tasks"]
    for item in planned:
        assert set(item) == PLANNED_TASK_KEYS

    # Deadline (by date) ascending, then High > Medium > Low.
    assert [p["id"] for p in planned] == [
        overdue["id"],
        today_high["id"],
        today_medium["id"],
        today_low["id"],
    ]
    # Cumulative: 30 (fits), 50 (fits), 90 (no), 90 (no; missing estimate = 0).
    assert [p["fits"] for p in planned] == [True, True, False, False]
    assert planned[3]["estimated_time"] is None


def test_daily_plan_is_deterministic_across_requests(client):
    _create_commitment(client, f"{TARGET}T09:00:00", f"{TARGET}T10:00:00")
    for i, priority in enumerate(["Low", "High", "Medium", "High"]):
        _create_task(
            client,
            title=f"T{i}",
            deadline=f"{TARGET}T1{i}:00:00",
            priority=priority,
            estimated_time=100,
        )

    first = client.get("/dashboard/daily-plan", params={"date": TARGET})
    second = client.get("/dashboard/daily-plan", params={"date": TARGET})
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
