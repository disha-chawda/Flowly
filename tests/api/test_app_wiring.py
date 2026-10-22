"""End-to-end wiring smoke checks for ``app/main.py`` (task 16.1).

Confirms the same FastAPI app serves both the REST API and the static
frontend, and that the frontend mount does not shadow any API route. The API
uses a temporary SQLite file (never the real ``flowly.db``) via a ``get_db``
override; no network access is required.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.data import models  # noqa: F401  (registers tables on Base.metadata)
from app.data.database import Base, get_db
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'wiring.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
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
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        engine.dispose()


def test_frontend_index_is_served(client: TestClient):
    response = client.get("/app/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "FLOWLY" in response.text


@pytest.mark.parametrize("asset", ["app.js", "styles.css"])
def test_frontend_assets_are_served(client: TestClient, asset: str):
    assert client.get(f"/app/{asset}").status_code == 200


def test_root_redirects_to_frontend(client: TestClient):
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/app/"


@pytest.mark.parametrize(
    "path",
    [
        "/tasks",
        "/commitments",
        "/dashboard/today",
        "/dashboard/upcoming",
        "/dashboard/workload",
        "/dashboard/daily-plan",
    ],
)
def test_api_routes_still_respond_alongside_frontend(client: TestClient, path: str):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


def test_unknown_api_id_still_returns_json_404(client: TestClient):
    response = client.get("/tasks/999999")
    assert response.status_code == 404
    assert "error" in response.json()
