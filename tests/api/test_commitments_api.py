"""API / integration tests for the commitment endpoints (FastAPI TestClient).

Exercises the real ``/commitments`` router, schemas, service, repository, and
centralized error handlers end to end against an isolated in-memory SQLite
database. The production ``get_db`` session dependency is overridden per test
app, so the real ``flowly.db`` file is never touched. ``TestClient`` is used
without its context manager so the app's startup hook (which would call
``create_all`` on the production engine) does not run.

Covers:
  Feature: flowly-mvp, Property 7: Commitment creation round-trip with end-after-start validation

Validates: Requirements 3.1, 3.4, 10
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data import models  # noqa: F401  (registers tables on Base.metadata)
from app.data.database import Base, get_db
from app.main import create_app


# --------------------------------------------------------------------------- #
# Self-contained test plumbing: a fresh app bound to a fresh in-memory DB.
# --------------------------------------------------------------------------- #
@contextmanager
def _make_client() -> Iterator[TestClient]:
    """Yield a TestClient for a new app wired to a private in-memory database."""
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
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with _make_client() as c:
        yield c


def _payload(title="Lecture", start="2025-03-10T09:00:00", end="2025-03-10T10:30:00"):
    return {"title": title, "start_time": start, "end_time": end}


def _assert_error_envelope(body: dict, expected_type: str) -> None:
    """Assert ``body`` matches the single error envelope from Design Error Handling."""
    assert set(body.keys()) == {"error"}
    error = body["error"]
    assert error["type"] == expected_type
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["details"], list)
    for detail in error["details"]:
        assert set(detail.keys()) == {"field", "issue"}
        assert isinstance(detail["field"], str)
        assert isinstance(detail["issue"], str)


# --------------------------------------------------------------------------- #
# Happy paths
# --------------------------------------------------------------------------- #
def test_create_returns_201_with_defaults(client):
    resp = client.post("/commitments", json=_payload(title="  Lecture  "))
    assert resp.status_code == 201
    body = resp.json()
    assert isinstance(body["id"], int)
    assert body["title"] == "Lecture"
    assert datetime.fromisoformat(body["start_time"]) == datetime(2025, 3, 10, 9, 0)
    assert datetime.fromisoformat(body["end_time"]) == datetime(2025, 3, 10, 10, 30)
    assert body["source"] == "manual"
    assert body["created_at"]


def test_list_and_get_return_200(client):
    first = client.post("/commitments", json=_payload(title="A")).json()
    second = client.post(
        "/commitments",
        json=_payload(title="B", start="2025-03-11T13:00:00", end="2025-03-11T14:00:00"),
    ).json()

    resp = client.get("/commitments")
    assert resp.status_code == 200
    assert {c["id"] for c in resp.json()} == {first["id"], second["id"]}

    resp = client.get(f"/commitments/{first['id']}")
    assert resp.status_code == 200
    assert resp.json() == first


def test_list_empty_returns_200(client):
    resp = client.get("/commitments")
    assert resp.status_code == 200
    assert resp.json() == []


def test_update_returns_200_and_persists(client):
    created = client.post("/commitments", json=_payload()).json()
    resp = client.put(
        f"/commitments/{created['id']}",
        json={"title": "Seminar", "end_time": "2025-03-10T11:00:00"},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["title"] == "Seminar"
    assert datetime.fromisoformat(updated["start_time"]) == datetime(2025, 3, 10, 9, 0)
    assert datetime.fromisoformat(updated["end_time"]) == datetime(2025, 3, 10, 11, 0)

    assert client.get(f"/commitments/{created['id']}").json() == updated


def test_delete_returns_204_and_removes(client):
    created = client.post("/commitments", json=_payload()).json()
    resp = client.delete(f"/commitments/{created['id']}")
    assert resp.status_code == 204
    assert resp.content == b""

    assert client.get(f"/commitments/{created['id']}").status_code == 404
    assert client.get("/commitments").json() == []


# --------------------------------------------------------------------------- #
# 404 on missing id
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "method, kwargs",
    [
        ("get", {}),
        ("put", {"json": {"title": "x"}}),
        ("delete", {}),
    ],
)
def test_missing_id_returns_404_envelope(client, method, kwargs):
    resp = getattr(client, method)("/commitments/9999", **kwargs)
    assert resp.status_code == 404
    _assert_error_envelope(resp.json(), "not_found")


# --------------------------------------------------------------------------- #
# 422 validation failures
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "start, end",
    [
        ("2025-03-10T10:00:00", "2025-03-10T10:00:00"),  # equal
        ("2025-03-10T10:00:00", "2025-03-10T09:00:00"),  # before
    ],
)
def test_create_end_not_after_start_returns_422(client, start, end):
    resp = client.post("/commitments", json=_payload(start=start, end=end))
    assert resp.status_code == 422
    _assert_error_envelope(resp.json(), "validation_error")
    assert resp.json()["error"]["details"]
    assert client.get("/commitments").json() == []


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_create_invalid_title_returns_422(client, title):
    resp = client.post("/commitments", json=_payload(title=title))
    assert resp.status_code == 422
    body = resp.json()
    _assert_error_envelope(body, "validation_error")
    assert any(d["field"] == "title" for d in body["error"]["details"])
    assert client.get("/commitments").json() == []


def test_create_missing_fields_returns_422(client):
    resp = client.post("/commitments", json={"title": "Lecture"})
    assert resp.status_code == 422
    body = resp.json()
    _assert_error_envelope(body, "validation_error")
    fields = {d["field"] for d in body["error"]["details"]}
    assert {"start_time", "end_time"} <= fields


def test_update_inverting_interval_returns_422_and_keeps_stored(client):
    created = client.post("/commitments", json=_payload()).json()

    # Partial update that moves start past the stored end (service-level check).
    resp = client.put(
        f"/commitments/{created['id']}", json={"start_time": "2025-03-10T12:00:00"}
    )
    assert resp.status_code == 422
    body = resp.json()
    _assert_error_envelope(body, "validation_error")
    assert any(d["field"] == "end_time" for d in body["error"]["details"])

    # Both times supplied but inverted (schema-level check).
    resp = client.put(
        f"/commitments/{created['id']}",
        json={"start_time": "2025-03-10T12:00:00", "end_time": "2025-03-10T11:00:00"},
    )
    assert resp.status_code == 422
    _assert_error_envelope(resp.json(), "validation_error")

    assert client.get(f"/commitments/{created['id']}").json() == created


# --------------------------------------------------------------------------- #
# Property 7
# --------------------------------------------------------------------------- #
_titles = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc")),
    min_size=1,
    max_size=200,
).filter(lambda s: s.strip() != "")

_starts = st.datetimes(
    min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1)
).map(lambda d: d.replace(microsecond=0))

# Positive durations produce valid commitments; zero/negative must be rejected.
_durations = st.integers(min_value=-24 * 60 * 60, max_value=7 * 24 * 60 * 60)


# Feature: flowly-mvp, Property 7: Commitment creation round-trip with end-after-start validation
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(title=_titles, start=_starts, duration_seconds=_durations)
def test_property_7_commitment_creation_round_trip(title, start, duration_seconds):
    """**Validates: Requirements 3.1, 3.4, 10**

    For any valid title and start time: if end_time is strictly after
    start_time the API creates the commitment (201) and it round-trips with
    source=manual; otherwise the API returns a 422 error envelope and nothing
    is persisted.
    """
    end = start + timedelta(seconds=duration_seconds)
    payload = {
        "title": title,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    }

    with _make_client() as client:
        resp = client.post("/commitments", json=payload)

        if end > start:
            assert resp.status_code == 201
            created = resp.json()
            assert created["title"] == title.strip()
            assert datetime.fromisoformat(created["start_time"]) == start
            assert datetime.fromisoformat(created["end_time"]) == end
            assert created["source"] == "manual"

            fetched = client.get(f"/commitments/{created['id']}")
            assert fetched.status_code == 200
            assert fetched.json() == created
        else:
            assert resp.status_code == 422
            _assert_error_envelope(resp.json(), "validation_error")
            assert client.get("/commitments").json() == []
