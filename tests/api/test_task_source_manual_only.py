"""API tests: ``POST /tasks`` accepts only ``source = manual``.

``TaskCreate`` shares the ``Source`` enum with ``CommitmentCreate``, so adding
``Source.ICS_IMPORT`` must not let clients create ``ics_import`` tasks. Before
the enum value existed, ``"source": "ics_import"`` was rejected with ``422``;
the ``_manual_only`` validator keeps it that way.

The app's ``get_db`` dependency is overridden to use an isolated in-memory
SQLite database (shared across connections via ``StaticPool``), so the real
``flowly.db`` file is never touched. The ``TestClient`` is not used as a context
manager, so the app's startup hook never runs.

Validates: Requirements 9.4, 16.1; Design §8
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data import models  # noqa: F401  (registers tables on Base.metadata)
from app.data.database import Base, get_db
from app.domain.enums import Source
from app.main import create_app
from app.schemas.task import TaskCreate, TaskUpdate


@pytest.fixture
def client():
    """Function-scoped client with an empty, isolated in-memory database."""
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
    yield TestClient(app)
    engine.dispose()


def _list_tasks(test_client: TestClient) -> list[dict]:
    response = test_client.get("/tasks")
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def test_create_with_explicit_manual_source_succeeds(client):
    response = client.post("/tasks", json={"title": "Essay", "source": "manual"})

    assert response.status_code == 201
    created = response.json()
    assert created["source"] == "manual"
    assert client.get(f"/tasks/{created['id']}").json()["source"] == "manual"


def test_create_without_source_defaults_to_manual(client):
    response = client.post("/tasks", json={"title": "Essay"})

    assert response.status_code == 201
    created = response.json()
    assert created["source"] == "manual"
    assert client.get(f"/tasks/{created['id']}").json()["source"] == "manual"


def test_create_with_ics_import_source_returns_422_and_stores_nothing(client):
    response = client.post("/tasks", json={"title": "Essay", "source": "ics_import"})

    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert error["type"] == "validation_error"
    assert error["message"] == "Request validation failed"
    assert len(error["details"]) == 1
    detail = error["details"][0]
    assert detail["field"] == "source"
    assert "source must be 'manual'" in detail["issue"]
    assert _list_tasks(client) == []


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["ics_import", Source.ICS_IMPORT])
def test_schema_rejects_ics_import_source(source):
    with pytest.raises(ValidationError) as exc_info:
        TaskCreate(title="Essay", source=source)

    errors = exc_info.value.errors()
    assert len(errors) == 1
    assert errors[0]["loc"] == ("source",)
    assert "source must be 'manual'" in errors[0]["msg"]


def test_update_has_no_source_field():
    assert "source" not in TaskUpdate.model_fields
