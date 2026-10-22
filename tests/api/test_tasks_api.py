"""API tests for the task endpoints (Design §6, Requirements §1, §2, §10, §11).

Exercises the ``/tasks`` router end to end through FastAPI's ``TestClient``:
CRUD + completion-toggle happy paths, ``404`` on missing ids, and ``422`` with
the centralized error envelope for invalid bodies. Properties 5 and 6 are
checked with ``hypothesis``.

All fixtures are self-contained. The app's ``get_db`` dependency is overridden
to use an isolated in-memory SQLite database (shared across connections via
``StaticPool``), so the real ``flowly.db`` file is never touched. The
``TestClient`` is deliberately *not* used as a context manager, so the app's
startup hook (which calls ``create_all`` on the configured engine) never runs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data import models  # noqa: F401  (registers tables on Base.metadata)
from app.data.database import Base, get_db
from app.main import create_app

MISSING_ID = 999_999


# ---------------------------------------------------------------------------
# Fixtures (self-contained; no shared conftest)
# ---------------------------------------------------------------------------


def _build_client() -> tuple[TestClient, object]:
    """Build a TestClient wired to a fresh, isolated in-memory database."""
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
    return TestClient(app), engine


@pytest.fixture
def client():
    """Function-scoped client with an empty database per test."""
    test_client, engine = _build_client()
    yield test_client
    engine.dispose()


@pytest.fixture(scope="module")
def module_client():
    """Module-scoped client for hypothesis tests (avoids per-example fixtures)."""
    test_client, engine = _build_client()
    yield test_client
    engine.dispose()


def _assert_error_envelope(body: dict, expected_type: str) -> None:
    """Assert ``body`` matches the centralized error envelope shape."""
    assert set(body) == {"error"}
    error = body["error"]
    assert error["type"] == expected_type
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["details"], list)
    for detail in error["details"]:
        assert set(detail) == {"field", "issue"}


def _task_count(test_client: TestClient) -> int:
    response = test_client.get("/tasks")
    assert response.status_code == 200
    return len(response.json())


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_create_task_applies_defaults(client):
    response = client.post("/tasks", json={"title": "  Write essay  "})

    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], int)
    assert body["title"] == "Write essay"
    assert body["description"] == ""
    assert body["deadline"] is None
    assert body["estimated_time"] is None
    assert body["priority"] == "Medium"
    assert body["category"] == "Personal"
    assert body["completion"] == "Incomplete"
    assert body["source"] == "manual"
    assert body["created_at"]


def test_create_task_with_all_fields(client):
    payload = {
        "title": "Lab report",
        "description": "Chem 101",
        "deadline": "2025-03-01T17:00:00",
        "estimated_time": 90,
        "priority": "High",
        "category": "Academic",
    }
    response = client.post("/tasks", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["description"] == "Chem 101"
    assert body["deadline"].startswith("2025-03-01T17:00:00")
    assert body["estimated_time"] == 90
    assert body["priority"] == "High"
    assert body["category"] == "Academic"


def test_list_and_get_tasks(client):
    first = client.post("/tasks", json={"title": "A"}).json()
    second = client.post("/tasks", json={"title": "B"}).json()

    listed = client.get("/tasks")
    assert listed.status_code == 200
    assert {t["id"] for t in listed.json()} == {first["id"], second["id"]}

    fetched = client.get(f"/tasks/{first['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == first


def test_update_task(client):
    created = client.post("/tasks", json={"title": "Old", "estimated_time": 30}).json()

    response = client.put(
        f"/tasks/{created['id']}",
        json={"title": "New", "priority": "Low", "category": "Work"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New"
    assert body["priority"] == "Low"
    assert body["category"] == "Work"
    # Omitted fields stay untouched.
    assert body["estimated_time"] == 30
    assert client.get(f"/tasks/{created['id']}").json() == body


def test_delete_task(client):
    created = client.post("/tasks", json={"title": "Temp"}).json()

    response = client.delete(f"/tasks/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/tasks/{created['id']}").status_code == 404
    assert _task_count(client) == 0


def test_completion_toggle_round_trip(client):
    created = client.post("/tasks", json={"title": "Toggle me"}).json()
    url = f"/tasks/{created['id']}/completion"

    done = client.patch(url, json={"completion": "Complete"})
    assert done.status_code == 200
    assert done.json()["completion"] == "Complete"
    assert client.get(f"/tasks/{created['id']}").json()["completion"] == "Complete"

    undone = client.patch(url, json={"completion": "Incomplete"})
    assert undone.status_code == 200
    assert undone.json()["completion"] == "Incomplete"


# ---------------------------------------------------------------------------
# 404 on missing ids
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method, url, body",
    [
        ("GET", f"/tasks/{MISSING_ID}", None),
        ("PUT", f"/tasks/{MISSING_ID}", {"title": "x"}),
        ("DELETE", f"/tasks/{MISSING_ID}", None),
        ("PATCH", f"/tasks/{MISSING_ID}/completion", {"completion": "Complete"}),
    ],
)
def test_missing_task_returns_404_envelope(client, method, url, body):
    response = client.request(method, url, json=body)

    assert response.status_code == 404
    _assert_error_envelope(response.json(), "not_found")


# ---------------------------------------------------------------------------
# 422 validation failures with the error envelope
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload, field",
    [
        ({}, "title"),
        ({"title": ""}, "title"),
        ({"title": "   "}, "title"),
        ({"title": "x" * 201}, "title"),
        ({"title": "ok", "estimated_time": 0}, "estimated_time"),
        ({"title": "ok", "estimated_time": -5}, "estimated_time"),
        ({"title": "ok", "priority": "Urgent"}, "priority"),
        ({"title": "ok", "category": "Hobby"}, "category"),
    ],
)
def test_create_invalid_body_returns_422_envelope(client, payload, field):
    response = client.post("/tasks", json=payload)

    assert response.status_code == 422
    body = response.json()
    _assert_error_envelope(body, "validation_error")
    assert field in {d["field"] for d in body["error"]["details"]}
    assert _task_count(client) == 0


def test_update_invalid_body_returns_422_and_leaves_task_unchanged(client):
    created = client.post("/tasks", json={"title": "Keep"}).json()

    response = client.put(f"/tasks/{created['id']}", json={"title": "   "})

    assert response.status_code == 422
    _assert_error_envelope(response.json(), "validation_error")
    assert client.get(f"/tasks/{created['id']}").json() == created


def test_completion_invalid_value_returns_422_envelope(client):
    created = client.post("/tasks", json={"title": "Task"}).json()

    response = client.patch(
        f"/tasks/{created['id']}/completion", json={"completion": "Done"}
    )

    assert response.status_code == 422
    body = response.json()
    _assert_error_envelope(body, "validation_error")
    assert "completion" in {d["field"] for d in body["error"]["details"]}


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

_whitespace = st.text(alphabet=" \t\n\r", max_size=20)
_over_length = st.text(min_size=201, max_size=400).filter(
    lambda s: len(s.strip()) > 200
)
_invalid_titles = st.one_of(st.just(""), _whitespace, _over_length)


# Feature: flowly-mvp, Property 5: Title validation rejects empty/whitespace/over-length, with no persistence
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(title=_invalid_titles)
def test_property_5_invalid_title_rejected_without_persistence(module_client, title):
    """**Validates: Requirements §2.1, §10**"""
    before = _task_count(module_client)

    response = module_client.post("/tasks", json={"title": title})

    assert response.status_code == 422
    body = response.json()
    _assert_error_envelope(body, "validation_error")
    assert "title" in {d["field"] for d in body["error"]["details"]}
    assert _task_count(module_client) == before


_non_positive_ints = st.integers(max_value=0)
_fractional_floats = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
).filter(lambda f: not f.is_integer())
_non_numeric_text = st.text(min_size=1, max_size=20).filter(
    lambda s: not s.strip().lstrip("+-").replace(".", "", 1).isdigit()
)
_invalid_estimates = st.one_of(_non_positive_ints, _fractional_floats, _non_numeric_text)


# Feature: flowly-mvp, Property 6: Estimated-time validation
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(estimated_time=_invalid_estimates)
def test_property_6_invalid_estimated_time_rejected(module_client, estimated_time):
    """**Validates: Requirements §2.4**"""
    before = _task_count(module_client)

    response = module_client.post(
        "/tasks", json={"title": "Task", "estimated_time": estimated_time}
    )

    assert response.status_code == 422
    body = response.json()
    _assert_error_envelope(body, "validation_error")
    assert "estimated_time" in {d["field"] for d in body["error"]["details"]}
    assert _task_count(module_client) == before


# Feature: flowly-mvp, Property 6: Estimated-time validation
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(estimated_time=st.one_of(st.none(), st.integers(min_value=1, max_value=10_000)))
def test_property_6_omitted_or_positive_estimated_time_accepted(
    module_client, estimated_time
):
    """**Validates: Requirements §2.4**"""
    payload = {"title": "Task"}
    if estimated_time is not None:
        payload["estimated_time"] = estimated_time

    response = module_client.post("/tasks", json=payload)

    assert response.status_code == 201
    assert response.json()["estimated_time"] == estimated_time
