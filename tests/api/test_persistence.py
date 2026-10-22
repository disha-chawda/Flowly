"""Persistence integration tests (Requirements §9; Design Testing Strategy).

These tests write tasks and commitments through the HTTP API, then read them
back through a *fresh* SQLAlchemy engine and session bound to the same
file-backed SQLite database. Because the second engine shares no connection,
identity map, or cache with the one that served the requests, a successful
read-back proves the data was actually committed to durable storage.

Everything is self-contained in this module: each test gets its own SQLite
file under pytest's ``tmp_path`` (never the real ``flowly.db``), and the
``get_db`` dependency is overridden so the app uses that file. ``TestClient``
is deliberately not used as a context manager, so the app's startup hook
(which targets the configured production engine) never runs. No network
access is required.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.data import models  # noqa: F401  (registers tables on Base.metadata)
from app.data.database import Base, get_db
from app.data.models import Commitment, Task
from app.domain.enums import Category, Completion, Priority, Source
from app.main import create_app


def _make_engine(db_path: Path) -> Engine:
    """Build an engine on the given SQLite file, usable across test threads."""
    return create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )


def _make_client(db_path: Path) -> tuple[TestClient, Engine]:
    """Create a fresh app whose ``get_db`` is bound to ``db_path``."""
    engine = _make_engine(db_path)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    def _override_get_db() -> Iterator[Session]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app), engine


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "persistence_test.db"


@pytest.fixture
def api(db_path: Path) -> Iterator[TestClient]:
    client, engine = _make_client(db_path)
    try:
        yield client
    finally:
        client.close()
        engine.dispose()


@pytest.fixture
def fresh_session(db_path: Path, api: TestClient) -> Iterator[Session]:
    """A session on a brand-new engine, independent of the one serving the API.

    Depends on ``api`` so the schema exists before the session is opened. The
    session is created lazily on first use, i.e. after the test has made its
    API writes.
    """
    engine = _make_engine(db_path)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_tasks_created_via_api_survive_in_fresh_session(
    api: TestClient, fresh_session: Session
) -> None:
    payloads = [
        {
            "title": "Write lab report",
            "description": "Chem 101",
            "deadline": "2030-05-01T17:00:00",
            "estimated_time": 90,
            "priority": "High",
            "category": "Academic",
        },
        # Minimal body: defaults must be persisted too.
        {"title": "Buy groceries"},
    ]
    created = []
    for body in payloads:
        resp = api.post("/tasks", json=body)
        assert resp.status_code == 201, resp.text
        created.append(resp.json())

    rows = {t.id: t for t in fresh_session.scalars(select(Task)).all()}
    assert set(rows) == {c["id"] for c in created}

    full = rows[created[0]["id"]]
    assert full.title == "Write lab report"
    assert full.description == "Chem 101"
    assert full.deadline == datetime(2030, 5, 1, 17, 0, 0)
    assert full.estimated_time == 90
    assert full.priority == Priority.HIGH
    assert full.category == Category.ACADEMIC
    assert full.completion == Completion.INCOMPLETE
    assert full.source == Source.MANUAL
    assert full.created_at is not None

    minimal = rows[created[1]["id"]]
    assert minimal.title == "Buy groceries"
    assert minimal.description == ""
    assert minimal.deadline is None
    assert minimal.estimated_time is None
    assert minimal.priority == Priority.MEDIUM
    assert minimal.category == Category.PERSONAL
    assert minimal.completion == Completion.INCOMPLETE
    assert minimal.source == Source.MANUAL


def test_commitments_created_via_api_survive_in_fresh_session(
    api: TestClient, fresh_session: Session
) -> None:
    resp = api.post(
        "/commitments",
        json={
            "title": "Shift at cafe",
            "start_time": "2030-05-01T09:00:00",
            "end_time": "2030-05-01T13:30:00",
        },
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()

    rows = fresh_session.scalars(select(Commitment)).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.id == created["id"]
    assert row.title == "Shift at cafe"
    assert row.start_time == datetime(2030, 5, 1, 9, 0, 0)
    assert row.end_time == datetime(2030, 5, 1, 13, 30, 0)
    assert row.source == Source.MANUAL
    assert row.created_at is not None


def test_updates_completion_and_deletes_are_persisted(
    api: TestClient, fresh_session: Session
) -> None:
    keep = api.post("/tasks", json={"title": "Draft essay"}).json()
    drop = api.post("/tasks", json={"title": "Old reminder"}).json()
    commitment = api.post(
        "/commitments",
        json={
            "title": "Lecture",
            "start_time": "2030-05-02T10:00:00",
            "end_time": "2030-05-02T11:00:00",
        },
    ).json()

    assert api.put(
        f"/tasks/{keep['id']}", json={"title": "Final essay", "estimated_time": 45}
    ).status_code == 200
    assert api.patch(
        f"/tasks/{keep['id']}/completion", json={"completion": "Complete"}
    ).status_code == 200
    assert api.delete(f"/tasks/{drop['id']}").status_code == 204
    assert api.put(
        f"/commitments/{commitment['id']}", json={"title": "Lecture (moved)"}
    ).status_code == 200

    tasks = fresh_session.scalars(select(Task)).all()
    assert [t.id for t in tasks] == [keep["id"]]
    assert tasks[0].title == "Final essay"
    assert tasks[0].estimated_time == 45
    assert tasks[0].completion == Completion.COMPLETE

    stored_commitment = fresh_session.get(Commitment, commitment["id"])
    assert stored_commitment is not None
    assert stored_commitment.title == "Lecture (moved)"
    assert stored_commitment.start_time == datetime(2030, 5, 2, 10, 0, 0)
    assert stored_commitment.end_time == datetime(2030, 5, 2, 11, 0, 0)


def test_data_survives_app_restart(db_path: Path) -> None:
    """Data written by one app instance is served by a brand-new instance."""
    first, first_engine = _make_client(db_path)
    try:
        task = first.post(
            "/tasks", json={"title": "Persisted task", "priority": "Low"}
        ).json()
        commitment = first.post(
            "/commitments",
            json={
                "title": "Persisted commitment",
                "start_time": "2030-06-01T08:00:00",
                "end_time": "2030-06-01T09:00:00",
            },
        ).json()
    finally:
        first.close()
        first_engine.dispose()

    second, second_engine = _make_client(db_path)
    try:
        task_resp = second.get(f"/tasks/{task['id']}")
        assert task_resp.status_code == 200
        assert task_resp.json() == task

        commitment_resp = second.get(f"/commitments/{commitment['id']}")
        assert commitment_resp.status_code == 200
        assert commitment_resp.json() == commitment
    finally:
        second.close()
        second_engine.dispose()
