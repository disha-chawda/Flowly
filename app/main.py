"""FLOWLY application entry point.

Assembles the FastAPI application described in Design §3–§4: it creates the app
instance, wires the three feature routers (tasks, commitments, dashboard), and
registers the centralized error handlers (`app/api/errors.py`) so every failure
path shares the single error envelope. It also ensures the SQLite schema exists
before the app serves traffic, and serves the static ``frontend/`` folder at
``/app/`` (same origin as the API, so no CORS is needed).

This module is deliberately wiring-only — it contains no business logic. The
ORM models (`app/data/models.py`) are imported for their side effect of
registering the ``Task`` and ``Commitment`` tables on the declarative metadata,
so that the ``create_all`` helper (`app/data/database.py`) has every table to
create at startup.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

# Imported for the registration side effect: binding the ORM models to the
# declarative ``Base.metadata`` so ``create_all`` can create their tables.
from app.data import models  # noqa: F401
from app.data.database import create_all
from app.api.errors import register_error_handlers
from app.api.tasks import router as tasks_router
from app.api.commitments import router as commitments_router
from app.api.dashboard import router as dashboard_router

# The decoupled static frontend lives beside the ``app`` package. It is served
# from the same origin under ``FRONTEND_MOUNT`` so it can call the REST API
# without any CORS configuration.
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
FRONTEND_MOUNT = "/app"


@asynccontextmanager
async def lifespan(app):
    create_all()
    yield


def create_app() -> FastAPI:
    """Build and return the fully wired FLOWLY FastAPI application.

    Registers the feature routers and the centralized error handlers, and
    ensures the database tables exist on startup via the ``startup`` event so
    the schema is created once when the application boots.
    """
    app = FastAPI(title="FLOWLY", lifespan = lifespan)

    register_error_handlers(app)

    app.include_router(tasks_router)
    app.include_router(commitments_router)
    app.include_router(dashboard_router)

    # Serve the static frontend under its own prefix so it can never shadow the
    # API routes (/tasks, /commitments, /dashboard/*). Unknown paths outside
    # the prefix keep returning the API's JSON 404. The mount is skipped if the
    # frontend folder is absent, because the API does not depend on it.
    if FRONTEND_DIR.is_dir():
        app.mount(
            FRONTEND_MOUNT,
            StaticFiles(directory=FRONTEND_DIR, html=True),
            name="frontend",
        )

        @app.get("/", include_in_schema=False)
        def _root_redirect() -> RedirectResponse:
            """Send a browser that opens the server root to the frontend."""
            return RedirectResponse(url=f"{FRONTEND_MOUNT}/")

    return app


app = create_app()
